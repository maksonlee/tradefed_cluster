# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""TaskStore to store tasks, get tasks and lease tasks."""

import dataclasses
import datetime
import logging
import random

from typing import Dict, Optional, Any

from tradefed_cluster.util import ndb_shim as ndb


from tradefed_cluster import affinity_manager
from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities

DEFAULT_COMMAND_ATTEMPT_HEARTBEAT = datetime.timedelta(hours=24)


@dataclasses.dataclass
class CommandTaskArgs(object):
  """CommandTask arguments."""
  request_id: str
  command_id: str
  task_id: str
  command_line: str
  cluster: str
  run_target: str
  plugin_data: Optional[Dict[str, Any]] = None
  run_count: int = 1
  run_index: int = 0
  attempt_index: int = 0
  shard_count: Optional[int] = None
  shard_index: Optional[int] = None
  priority: Optional[int] = None
  request_type: Optional[api_messages.RequestType] = None
  allow_partial_device_match: bool = False
  test_bench: Optional[datastore_entities.TestBench] = None
  affinity_tag: Optional[str] = None


def _Now():
  """Returns UTC now."""
  return datetime.datetime.utcnow()


def CreateTask(command_task_args):
  """Save the command task in datastore.

  Args:
    command_task_args: a CommandTaskArgs object
  Returns:
    true if created a new task, false if the task already exists.
  """
  test_bench = datastore_entities.BuildTestBench(
      cluster=command_task_args.cluster,
      run_target=command_task_args.run_target,
      test_bench=command_task_args.test_bench)

  task = datastore_entities.CommandTask(
      request_id=str(command_task_args.request_id),
      command_id=str(command_task_args.command_id),
      task_id=command_task_args.task_id,
      plugin_data=command_task_args.plugin_data,
      lease_count=0,
      command_line=command_task_args.command_line,
      run_count=command_task_args.run_count,
      run_index=command_task_args.run_index,
      attempt_index=command_task_args.attempt_index,
      shard_count=command_task_args.shard_count,
      shard_index=command_task_args.shard_index,
      test_bench=test_bench,
      priority=command_task_args.priority or 0,
      leasable=True,
      request_type=command_task_args.request_type,
      schedule_timestamp=common.Now(),
      allow_partial_device_match=command_task_args.allow_partial_device_match)
  created_new = _DoCreateTask(task)
  if command_task_args.affinity_tag:
    affinity_manager.SetTaskAffinity(
        task.task_id, command_task_args.affinity_tag, len(task.run_targets))
  return created_new


def _DoCreateTask(command_task):
  """Create the task to the datastore.

  This method is used to limit the scope of transaction.

  Args:
    command_task: a CommandTask datastore object
  Returns:
    true if created a new task, false if the task already exists.
  """
  key = _Key(command_task.task_id)
  if key.get():
    return False
  command_task.key = key
  command_task.put()
  return True


@ndb.transactional()
def RescheduleTask(task_id, run_index, attempt_index):
  """Reschedule the command task.

  Args:
    task_id: the task's id
    run_index: the new run_index
    attempt_index: the new attempt index
  """
  task = _Key(task_id).get()

  if task:
    if task.leasable:
      # Ignore leasable tasks
      logging.info('%s is leasable, don\'t reschedule', str(task_id))
      return

    logging.debug('Making task %s leasable', task_id)
    task.leasable = True
    task.schedule_timestamp = common.Now()
    task.run_index = run_index
    task.attempt_index = attempt_index
    task.put()
  else:
    logging.warning(
        '%s doesn\'t exist in task store, don\'t reschedule', str(task_id))


def Random():
  return random.random()


def GetLeasableTasks(cluster, run_targets):
  """Get leasable tasks from datastore.

  Args:
    cluster: cluster id
    run_targets: a list of run targets
  Yields:
    task entities
  """
  tasks = (
      datastore_entities.CommandTask.query(
          datastore_entities.CommandTask.cluster == cluster,
          datastore_entities.CommandTask.leasable == True,  
          namespace=common.NAMESPACE)
      .order(-datastore_entities.CommandTask.priority))

  # Because Datastore will always return the tasks from the above query in the
  # same order, this means that multiple hosts trying to lease tasks for the
  # same cluster will also iterate over the tasks in the exact same order, which
  # will result in contention since a task can only be leased by a single host.
  #   [A, B, C, D, E, F, G, ...]
  #
  # There isn't a good solution to modifying the query for this, due to
  # Datastore constraints, but we can instead return a random list, where the
  # probability of a task appearing is weighed by its index in the sequence.
  #   [A(100%), B(50%), C(50%), D(25%), E(25%), F(25%), G(25%), ...]
  #
  # This is nearly equivalent to choosing a random element from
  # exponentially-increasing groups:
  #   [{A(100%)}, {B(50%), C(50%)}, {D(25%), E(25%), F(25%), G(25%)}, ...]
  #
  # But the former is easier to test, and we can tune the weights to allow for
  # heavier weighing towards elements at the beginning of the list, at the cost
  # of increased lease contention.
  #
  # This method is similar to how randomized exponential backoff is used for
  # collision avoidance.
  # https://en.wikipedia.org/wiki/Exponential_backoff#Collision_avoidance
  i, bucket = 0, 2
  p = 1

  run_target_set = set(run_targets)
  for task in tasks:
    if not task or not set(task.run_targets).issubset(run_target_set):
      continue

    if Random() < p:
      yield task
    else:
      logging.info('Skipping leasable task %s', task.key.id())
    i += 1
    if i == bucket:
      p = 1 / bucket
      bucket = bucket * 2


@ndb.transactional()
def LeaseTask(task_id):
  """Lease a task.

  Args:
    task_id: the task id
  Returns:
    None if the task is not leasable, otherwise the task.
  """
  task = _Key(task_id).get()
  logging.debug('Attempting to lease task: %s', task)
  if not task or not task.leasable:
    return None
  task.leasable = False
  task.lease_timestamp = common.Now()
  task.lease_count += 1
  task.put()
  return task


@ndb.transactional(xg=True)
def DeleteTask(task_id):
  """Delete a task.

  Args:
    task_id: the task id
  """
  affinity_manager.ResetTaskAffinity(task_id)
  _Key(task_id).delete()


def DeleteTasks(task_ids):
  """Delete tasks.

  This is processing multiple entities, so it should not be
  transactional.

  Args:
    task_ids: a list of task ids
  """
  for task_id in task_ids:
    DeleteTask(task_id)


def GetActiveTaskCount(task_ids):
  """Get number of tasks still exist in task store.

  Args:
    task_ids: a list of task ids.
  Returns:
    the number of existing tasks.
  """
  tasks = GetTasks(task_ids)
  active_tasks = [t.task_id for t in tasks if t]
  logging.info('%r are active in command store', active_tasks)
  return len(active_tasks)


def GetTask(task_id):
  """Get task by task id.

  Args:
    task_id: task id
  Returns:
    task entity
  """
  return _Key(task_id).get()


def GetTasks(task_ids):
  """Get tasks in task store.

  Args:
    task_ids: a list of task ids.
  Returns:
    a list of task entities.
  """
  keys = [_Key(task_id) for task_id in task_ids]
  return ndb.get_multi(keys)


def _Key(task_id):
  """Get the task's key in datastore.

  Args:
    task_id: task id
  Returns:
    task's datastore key.
  """
  return ndb.Key(datastore_entities.CommandTask, task_id,
                 namespace=common.NAMESPACE)
