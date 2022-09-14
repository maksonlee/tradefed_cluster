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
import copy
import datetime
import logging
import uuid

from protorpc import messages
from protorpc import remote

from tradefed_cluster.util import ndb_shim as ndb

from tradefed_cluster import affinity_manager
from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import command_manager
from tradefed_cluster import command_task_matcher
from tradefed_cluster import command_task_store
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import device_manager
from tradefed_cluster import env_config
from tradefed_cluster import metric
from tradefed_cluster import request_manager

_HOSTNAME_KEY = "hostname"
_HOST_GROUP_KEY = "host_group"
_LAB_NAME_KEY = "lab_name"
_TFC_COMMAND_ATTEMPT_QUEUE_START_TIMESTAMP_KEY = (
    "tfc_command_attempt_queue_start_timestamp")
_TFC_COMMAND_ATTEMPT_QUEUE_END_TIMESTAMP_KEY = (
    "tfc_command_attempt_queue_end_timestamp")
_AFFINITY_TAG = "affinity_tag"


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
  run_index = messages.IntegerField(12)
  attempt_index = messages.IntegerField(13)


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


def _CreateAttemptId():
  """Create an attempt ID."""
  return str(uuid.uuid4())


@api_common.tradefed_cluster_api.api_class(
    resource_name="tasks", path="tasks")
class CommandTaskApi(remote.Service):
  """A class for task API service."""

  @api_common.method(
      LeaseHostTasksRequest,
      CommandTaskList,
      path="leasehosttasks",
      http_method="POST",
      name="leasehosttasks")
  def LeaseHostTasks(self, request):
    """Lease available command tasks for a given host.

    Args:
      request: a HostInfo
    Returns:
      a TaskList object.
    """
    logging.debug("leasehosttasks: request=%s", request)
    host = device_manager.GetHost(request.hostname)
    if not host:
      host = datastore_entities.HostInfo(
          hostname=request.hostname,
          host_group=request.cluster)
    matcher = command_task_matcher.CommandTaskMatcher(request)
    self._ApplyDeviceAffinityInfos(matcher)
    run_targets = matcher.GetRunTargets()
    if not run_targets:
      return CommandTaskList(tasks=[])
    clusters = [request.cluster]
    clusters.extend(request.next_cluster_ids)
    leased_tasks = []
    num_tasks = request.num_tasks
    for cluster in clusters:
      try:
        cluster_leased_tasks = self._LeaseHostTasksForCluster(
            matcher, cluster, host, num_tasks)
        leased_tasks.extend(cluster_leased_tasks)
        if num_tasks is not None:
          num_tasks -= len(cluster_leased_tasks)
          if num_tasks <= 0:
            break
        if matcher.IsEmpty():
          break
            except:
        logging.exception(
            'Failed to lease tasks for "%s" cluster. Skipping...',
            cluster)

    env_config.CONFIG.plugin.OnCommandTasksLease(leased_tasks)
    self._CreateCommandAttempt(leased_tasks)
    return CommandTaskList(tasks=leased_tasks)

  def _ApplyDeviceAffinityInfos(self, matcher):
    """Apply device affinity infos to a matcher.

    This adds a "affinity_tag" attribute to devices with affinity infos.

    Args:
      matcher: a CommandTaskMatcher object.
    """
    serials = matcher.GetDeviceSerials()
    infos = affinity_manager.GetDeviceAffinityInfos(serials)
    for serial, info in zip(serials, infos):
      affinity_tag = info.affinity_tag if info else None
      # Try reset device affinity if we have more than enough devices for its
      # affinity tag.
      if affinity_tag and affinity_manager.ResetDeviceAffinity(
          serial, only_if_excess=True):
        affinity_tag = None
      logging.info("Device %s: affinity_tag=%s", serial, affinity_tag)
      # Check affinity status and reset if we don't need this device.
      matcher.AddDeviceAttributes(serial, **{_AFFINITY_TAG: affinity_tag})

  def _GetTargetAffinityTags(self, task_id):
    """Return target affinity tags for a task.

    Args:
      task_id: a task ID.
    Returns:
      (an affinity tag, a list of target affinity tags)
    """
    info = affinity_manager.GetTaskAffinityInfo(task_id)
    affinity_tag = info.affinity_tag if info else None
    target_affinity_tags = [affinity_tag]
    if affinity_tag:
      status = affinity_manager.GetAffinityStatus(affinity_tag)
      if status and status.device_count < status.needed_device_count:
        # Need more devices. Also target no affinity devices.
        target_affinity_tags.append(None)
    return affinity_tag, target_affinity_tags

  @ndb.transactional()
  def _CreateCommandAttempt(self, leased_tasks):
    for task in leased_tasks:
      attempt_id = _CreateAttemptId()
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
          run_index=task.run_index,
          attempt_index=task.attempt_index,
          hostname=plugin_data_.get(_HOSTNAME_KEY),
          device_serial=task.device_serials[0],
          device_serials=task.device_serials,
          plugin_data=plugin_data_)
      command_manager.AddToSyncCommandAttemptQueue(attempt_entity)
      attempt_entity.put()

      stored_task = command_task_store.GetTask(task.task_id)
      if stored_task:
        stored_task.attempt_id = attempt_id
        stored_task.put()
      else:
        logging.warning("No task found with id %s", task.task_id)

  def _LeaseHostTasksForCluster(
      self, matcher, cluster, host, num_tasks=None):
    leased_tasks = []
    leasable_tasks = command_task_store.GetLeasableTasks(
        cluster, matcher.GetRunTargets())

    # Deadline to return a response. Tradefed may timeout requests after 90s, so
    # if we haven't been able to lease enough tasks, just terminate and return
    # what we have, instead of risking allocating tasks only for Tradefed not to
    # receive it.
    # TODO: Consider removing if we've fully mitigated the issue.
    deadline = Now() + datetime.timedelta(seconds=45)
    for task in leasable_tasks:
      if Now() > deadline:
        break
      affinity_tag, target_affinity_tags = self._GetTargetAffinityTags(
          task.task_id)
      logging.debug(
          "Task %s: affinity_tag=%s, target_affinity_tags=%s",
          task.task_id, affinity_tag, target_affinity_tags)
      for tag in target_affinity_tags:
        matched_devices = matcher.Match(task, [
            datastore_entities.Attribute(name=_AFFINITY_TAG, value=tag)
        ])
        if matched_devices:
          break
      if not matched_devices:
        continue
      try:
        # b/27136167: Touch command to prevent coordinator from cancelling
        # during task lease.
        command = command_manager.Touch(task.request_id, task.command_id)
        # task comes from GetLeasableTasks is eventual consistent.
        # LeaseTask return the strong consistent task, so the data is more
        # accurate.
        leased_task = command_task_store.LeaseTask(task.task_id)
        if not leased_task:
          continue
        data_consistent = self._EnsureCommandConsistency(
            task.request_id, task.command_id, task.task_id)

        # Update matched devices' affinity.
        if affinity_tag:
          for device in matched_devices:
            affinity_manager.SetDeviceAffinity(
                device.device_serial, affinity_tag)
      except Exception as e:          # Datastore entities can only be written to once per second.  If we fail
        # to update the command or task, log the error, and try leasing other
        # tasks.
        logging.warning("Error leasing task %s: %s", task.task_id, e)
        continue
      if not data_consistent:
        continue

      matcher.RemoveDeviceGroups(matched_devices)

      logging.debug("lease task %s to run on %s %s",
                    str(leased_task.task_id),
                    host.hostname,
                    tuple(m.device_serial for m in matched_devices))
      plugin_data_dict = copy.copy(leased_task.plugin_data)
      plugin_data_dict[_HOSTNAME_KEY] = host.hostname
      plugin_data_dict[_LAB_NAME_KEY] = host.lab_name or common.UNKNOWN_LAB_NAME
      plugin_data_dict[_HOST_GROUP_KEY] = host.host_group
      if leased_task.schedule_timestamp:
        plugin_data_dict[_TFC_COMMAND_ATTEMPT_QUEUE_START_TIMESTAMP_KEY] = (
            common.DatetimeToAntsTimestampProperty(
                leased_task.schedule_timestamp))
      plugin_data_dict[_TFC_COMMAND_ATTEMPT_QUEUE_END_TIMESTAMP_KEY] = (
          common.DatetimeToAntsTimestampProperty(leased_task.lease_timestamp or
                                                 common.Now()))

      plugin_data_ = api_messages.MapToKeyValuePairMessages(plugin_data_dict)
      leased_tasks.append(
          CommandTask(
              request_id=leased_task.request_id,
              command_id=leased_task.command_id,
              task_id=leased_task.task_id,
              command_line=leased_task.command_line,
              request_type=leased_task.request_type,
              device_serials=[match.device_serial for match in matched_devices],
              shard_count=leased_task.shard_count,
              shard_index=leased_task.shard_index,
              run_index=leased_task.run_index,
              attempt_index=leased_task.attempt_index,
              plugin_data=plugin_data_))
      for run_target in leased_task.run_targets:
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
      logging.warning("Command with id [%s %s] does not exist. Deleting leased "
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
      logging.warning(
          "Request [%s] and command [%s] are inconsistent with tasks.",
          request_id, command_id)
      if not common.IsFinalRequestState(request.state):
        logging.warning(
            "Ensure request consistency, cancelling request [%s].",
            request_id)
        request_manager.CancelRequest(
            request_id,
            # TODO: rename cancel_reason to be more accurate
            cancel_reason=common.CancelReason.COMMAND_ALREADY_CANCELED)
      if not common.IsFinalCommandState(command.state):
        logging.warning(
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
