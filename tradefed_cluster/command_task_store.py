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

import collections
import datetime
import json
import logging

from tradefed_cluster.util import ndb_shim as ndb

from tradefed_cluster import common
from tradefed_cluster import datastore_entities

DEFAULT_COMMAND_ATTEMPT_HEARTBEAT = datetime.timedelta(hours=24)


CommandTaskArgs = collections.namedtuple(
    'CommandTaskArgs',
    ['request_id',
     'command_id',
     'task_id',
     'plugin_data',
     'command_line',
     'run_count',
     'run_index',
     'attempt_index',
     'shard_count',
     'shard_index',
     'cluster',
     'run_target',
     'priority',
     'request_type'])


def _Now():
  """Returns UTC now."""
  return datetime.datetime.utcnow()


def _GetTestBench(cluster, run_target):
  """Parse the run target, and create a test bench.

  Test bench info is encoded in run_target. Run target will have json format.
  The structure is the same as datastore_entities.TestBench:
  {
    "host": {
      "groups": [{
        "run_targets": [{
          "name": "run_target6",
            "device_attributes": [
              {"name": "sim_state", "value": "READY"}
            ]
          }]
        }]
    }
  }

  Args:
    cluster: cluster name
    run_target: encoded run_target
  Returns:
    a TestBench entity.
  """
  # TODO: move this logic to common util if other parts need this.
  run_target = run_target.strip()
  if not run_target.startswith('{'):
    return _GetLegacyTestBench(cluster, run_target)

  test_bench_json = json.loads(run_target)
  host_json = test_bench_json.get(common.TestBenchKey.HOST, {})
  groups = []
  for group_json in host_json.get(common.TestBenchKey.GROUPS, []):
    run_targets = []
    for run_target_json in group_json.get(common.TestBenchKey.RUN_TARGETS, []):
      run_target_name = run_target_json.get(
          common.TestBenchKey.RUN_TARGET_NAME)
      attributes = []
      for attribute_json in run_target_json.get(
          common.TestBenchKey.DEVICE_ATTRIBUTES, []):
        attributes.append(
            datastore_entities.Attribute(
                name=attribute_json[common.TestBenchKey.ATTRIBUTE_NAME],
                value=attribute_json[common.TestBenchKey.ATTRIBUTE_VALUE],
                operator=attribute_json.get(
                    common.TestBenchKey.ATTRIBUTE_OPERATOR)
            ))
      run_targets.append(
          datastore_entities.RunTarget(
              name=run_target_name,
              device_attributes=attributes))
    groups.append(datastore_entities.Group(run_targets=run_targets))
  host = datastore_entities.Host(groups=groups)
  test_bench = datastore_entities.TestBench(
      cluster=cluster,
      host=host)
  return test_bench


def _GetLegacyTestBench(cluster, run_target):
  """Parse the run target, and create a test bench.

  Test bench info is encoded in run_target. Run target will have format:
  run_target1,run_target2;run_target3,run_target4
  There are two groups.
  Run_target1 and run_target2 are in the same group.
  Run_target3 and run_target4 are in the same group.

  Args:
    cluster: cluster name
    run_target: encoded run_target
  Returns:
    a TestBench entity.
  """
  test_bench = datastore_entities.TestBench(
      cluster=cluster,
      host=datastore_entities.Host(
          groups=[]))
  group_strs = run_target.split(';')
  for group_str in group_strs:
    group = datastore_entities.Group(
        run_targets=[])
    run_target_strs = group_str.split(',')
    for run_target_str in run_target_strs:
      run_target = datastore_entities.RunTarget(
          name=run_target_str)
      group.run_targets.append(run_target)
    test_bench.host.groups.append(group)
  return test_bench


def CreateTask(command_task_args):
  """Save the command task in datastore.

  Args:
    command_task_args: a CommandTaskArgs object
  Returns:
    true if created a new task, false if the task already exists.
  """
  test_bench = _GetTestBench(
      command_task_args.cluster, command_task_args.run_target)

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
      schedule_timestamp=common.Now())
  return _DoCreateTask(task)


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
    task.leasable = True
    task.schedule_timestamp = common.Now()
    task.run_index = run_index
    task.attempt_index = attempt_index
    task.put()
  else:
    logging.warning(
        '%s doesn\'t exist in task store, don\'t reschedule', str(task_id))


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
          datastore_entities.CommandTask.leasable == True,            namespace=common.NAMESPACE)
      .order(-datastore_entities.CommandTask.priority,
             datastore_entities.CommandTask.key))

  run_target_set = set(run_targets)
  for task in tasks:
    if not set(task.run_targets).issubset(run_target_set):
      continue
    yield task


@ndb.transactional()
def LeaseTask(task_id):
  """Lease a task.

  Args:
    task_id: the task id
  Returns:
    None if the task is not leasable, otherwise the task.
  """
  task = _Key(task_id).get()
  if not task or not task.leasable:
    return None
  task.leasable = False
  task.lease_timestamp = common.Now()
  task.lease_count += 1
  task.put()
  return task


def DeleteTask(task_id):
  """Delete a task.

  Args:
    task_id: the task id
  """
  DeleteTasks([task_id])


def DeleteTasks(task_ids):
  """Delete tasks.

  This is processing multiple entities, so it should not be
  transactional.

  Args:
    task_ids: a list of task ids
  """
  keys = [_Key(task_id) for task_id in task_ids]
  ndb.delete_multi(keys)


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
