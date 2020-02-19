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

"""API module to serve command task service calls."""

import datetime
import logging
import uuid

from protorpc import messages
from protorpc import remote

from google.appengine.ext import ndb
from google3.third_party.apphosting.python.endpoints.v1_1 import endpoints

from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import command_manager
from tradefed_cluster import command_task_matcher
from tradefed_cluster import command_task_store
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config
from tradefed_cluster import metric
from tradefed_cluster import request_manager


class CommandTask(messages.Message):
  """A message class representing a single command task."""
  request_id = messages.StringField(1)
  command_id = messages.StringField(2)
  task_id = messages.StringField(3)
  command_line = messages.StringField(4)
  request_type = messages.EnumField(api_messages.RequestType, 5)
  device_serials = messages.StringField(6, repeated=True)
  shard_count = messages.IntegerField(7)
  shard_index = messages.IntegerField(8)
  plugin_data = messages.MessageField(
      api_messages.KeyValuePair, 9, repeated=True)
  extra_options = messages.MessageField(
      api_messages.KeyMultiValuePair, 10, repeated=True)
  attempt_id = messages.StringField(11)


class CommandTaskList(messages.Message):
  """A message class representing a list of command tasks."""
  tasks = messages.MessageField(CommandTask, 1, repeated=True)


class LeaseHostTasksRequest(messages.Message):
  """Request message for leasing host tasks."""
  hostname = messages.StringField(1)
  cluster = messages.StringField(2)
  device_infos = messages.MessageField(
      api_messages.DeviceInfo, 3, repeated=True)
  next_cluster_ids = messages.StringField(4, repeated=True)
  num_tasks = messages.IntegerField(5)


def Now():
  """Get current datetime in UTC."""
  return datetime.datetime.utcnow()


@api_common.tradefed_cluster_api.api_class(
    resource_name="tasks", path="tasks")
class CommandTaskApi(remote.Service):
  """A class for task API service."""

  @endpoints.method(
      LeaseHostTasksRequest,
      CommandTaskList,
      path="leasehosttasks",
      http_method="POST",
      name="leasehosttasks"
      )
  def LeaseHostTasks(self, request):
    """Lease available command tasks for a given host.

    Args:
      request: a HostInfo
    Returns:
      a TaskList object.
    """
    logging.debug("Get request:\n%s", request)
    matcher = command_task_matcher.CommandTaskMatcher(request)
    run_targets = matcher.GetRunTargets()
    if not run_targets:
      return CommandTaskList(tasks=[])
    clusters = [request.cluster]
    clusters.extend(request.next_cluster_ids)
    leased_tasks = []
    num_tasks = request.num_tasks
    for cluster in clusters:
      cluster_leased_tasks = self._LeaseHostTasksForCluster(
          matcher, cluster, num_tasks)
      leased_tasks.extend(cluster_leased_tasks)
      if num_tasks is not None:
        num_tasks -= len(cluster_leased_tasks)
        if num_tasks <= 0:
          break
      if matcher.IsEmpty():
        break

    env_config.CONFIG.plugin.OnCommandTasksLease(leased_tasks)
    self._CreateCommandAttempt(leased_tasks)
    return CommandTaskList(tasks=leased_tasks)

  def _CreateCommandAttempt(self, leased_tasks):
    # TODO: treat test run and attempt differently.
    for task in leased_tasks:
      attempt_id = str(uuid.uuid4())
      task.attempt_id = attempt_id

      plugin_data_ = api_messages.KeyValuePairMessagesToMap(task.plugin_data)
      attempt_key = ndb.Key(
          datastore_entities.Request, task.request_id,
          datastore_entities.Command, task.command_id,
          datastore_entities.CommandAttempt, attempt_id,
          namespace=common.NAMESPACE)
      attempt_entity = datastore_entities.CommandAttempt(
          key=attempt_key,
          attempt_id=attempt_id,
          state=common.CommandState.UNKNOWN,
          command_id=task.command_id,
          last_event_time=Now(),
          task_id=task.task_id,
          plugin_data=plugin_data_)
      command_manager.AddToSyncCommandAttemptQueue(attempt_entity)
      attempt_entity.put()

  def _LeaseHostTasksForCluster(self, matcher, cluster, num_tasks=None):
    leased_tasks = []
    leasable_tasks = command_task_store.GetLeasableTasks(
        cluster, matcher.GetRunTargets())
    for task in leasable_tasks:
      matched_devices = matcher.Match(task)
      if not matched_devices:
        continue
      if not command_task_store.LeaseTask(task.task_id):
        continue
      data_consistent = self._EnsureCommandConsistency(
          task.request_id, task.command_id, task.task_id)
      if not data_consistent:
        continue

      matcher.RemoveDeviceGroups(matched_devices)

      logging.debug("lease task %s to run on %s",
                    str(task.task_id),
                    tuple(m.device_serial for m in matched_devices))
      plugin_data_ = api_messages.MapToKeyValuePairMessages(task.plugin_data)
      leased_tasks.append(
          CommandTask(
              request_id=task.request_id,
              command_id=task.command_id,
              task_id=task.task_id,
              command_line=task.command_line,
              request_type=task.request_type,
              device_serials=[match.device_serial for match in matched_devices],
              shard_count=task.shard_count,
              shard_index=task.shard_index,
              plugin_data=plugin_data_))
      # b/27136167: Touch command to prevent coordinator from cancelling
      # during task lease.
      command = command_manager.Touch(task.request_id, task.command_id)
      for run_target in task.run_targets:
        metric.RecordCommandTimingMetric(
            cluster_id=cluster,
            run_target=run_target,
            create_timestamp=command.create_time,
            command_action=metric.CommandAction.LEASE,
            count=True)
      if matcher.IsEmpty():
        break
      if num_tasks is not None and len(leased_tasks) >= num_tasks:
        break
    return leased_tasks

  def _EnsureCommandConsistency(self, request_id, command_id, task_id):
    """Ensures consistency between the command in DB and the task store.

    Args:
      request_id: request id, str
      command_id: command id, str
      task_id: leased task's id for this command.
    Returns:
      True if data is consistent and it should proceed. False otherwise.
    """
    command = command_manager.GetCommand(request_id, command_id)
    if command:
      return (self._EnsureRequestConsistency(command) and
              self._EnsureCommandBeingActive(command))
    else:
      # Command has been deleted.
      logging.warn("Command with id [%s %s] does not exist. Deleting leased "
                   "task [%s].", request_id, command_id, task_id)
      command_manager.DeleteTask(task_id)
    return False

  def _EnsureCommandBeingActive(self, command):
    """Ensures consistency between the command in its tasks.

    Args:
      command: a command entity, read only

    Returns:
      True if data is consistent and it should proceed. False otherwise.
    """
    if common.IsFinalCommandState(command.state):
      logging.warning(
          "command [%s] is in final state and its tasks should not "
          "be leaseable.", command.key)
      command_manager.DeleteTasks(command)
      return False

    return True

  def _EnsureRequestConsistency(self, command):
    """Ensures consistency between the request and command in the DB.

    Args:
      command: a command entity, read only
    Returns:
      True if data is consistent and it should proceed. False otherwise.
    """
    _, request_id, _, command_id = command.key.flat()
    request = request_manager.GetRequest(request_id)
    if (request.state == common.RequestState.CANCELED
        or command.state == common.CommandState.CANCELED):
      # There should not be any tasks in the queue.
      logging.warn("Request [%s] and command [%s] are inconsistent with tasks.",
                   request_id, command_id)
      if not common.IsFinalRequestState(request.state):
        logging.warn(
            "Ensure request consistency, cancelling request [%s].",
            request_id)
        request_manager.CancelRequest(
            request_id,
            # TODO: rename cancel_reason to be more accurate
            cancel_reason=common.CancelReason.COMMAND_ALREADY_CANCELED)
      if not common.IsFinalCommandState(command.state):
        logging.warn(
            "Ensure request consistency, cancelling command [%s %s].",
            request_id, command_id)
        command_manager.Cancel(
            request_id, command_id,
            cancel_reason=common.CancelReason.REQUEST_ALREADY_CANCELED)
      else:
        # Clear all dangling tasks (tasks for finalized commands).
        command_manager.DeleteTasks(command)
      return False
    return True
