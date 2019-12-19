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

"""A module for managing test events."""

import datetime
import logging
import re

from tradefed_cluster import command_error_type_config
from tradefed_cluster import common
from tradefed_cluster import datastore_entities

# Default length for truncating strings.
# The number was chosen arbitrarily (2^12 - 1) but should be enough to hold our
# current summaries and errors. The only requirement is that it needs to be less
# than the task size limit (102400): b/38498960
MAX_STRING_LENGTH = 4095

TF_SHUTDOWN_ERROR_REGEX = re.compile(
    r"(?:.*DeviceNotAvailableException: aborted test session.*|"
    r".*TF is shutting down.*)"
)


class CommandEvent(object):
  """A immutable class representing a single command event."""

  def __init__(self, **kwargs):
    self.task_id = kwargs.get("command_task_id", kwargs.get("task_id"))
    self.request_id, self.command_id = _ParseTaskId(self.task_id)
    self.attempt_id = kwargs.get("attempt_id")
    self.type = kwargs.get("type")
    self.time = kwargs.get("time")
    if not isinstance(self.time, datetime.datetime):
      self.time = datetime.datetime.utcfromtimestamp(self.time)
    self.hostname = kwargs.get("hostname")
    # TODO Deprecated.
    self.device_serial = kwargs.get("device_serial")
    self.device_serials = (
        kwargs.get("device_serials") or
        [self.device_serial] if self.device_serial else None)
    self.data = kwargs.get("data", {})

    self.status = _GetEventData(self.data, CommandEventDataKey.STATUS)
    self.error = _GetEventData(self.data, CommandEventDataKey.ERROR)
    self.summary = _GetEventData(self.data, CommandEventDataKey.SUMMARY)
    self.summary = Truncate(self.summary)
    self.total_test_count = _GetEventData(
        self.data, CommandEventDataKey.TOTAL_TEST_COUNT, int)
    self.failed_test_count = _GetEventData(
        self.data, CommandEventDataKey.FAILED_TEST_COUNT, int)
    self.failed_test_run_count = _GetEventData(
        self.data, CommandEventDataKey.FAILED_TEST_RUN_COUNT, int)
    self.invocation_status = _ParseInvocationStatus(
        kwargs.get("invocation_status"))

    # The field 'attempt_state' is the potential new attempt state.
    # But based on the state of the command and command attempt, the
    # corresponding command attempt may or may not update to this state.
    # The attempt_state is calculated by the event's data.
    self.attempt_state = common.CommandState.UNKNOWN
    self.attempt_start_time = None
    self.attempt_end_time = None
    self._CalculateAttemptPropertyChanges()
    if self.error:
      self.error_reason, self.error_type = (
          command_error_type_config.GetConfig(self.error))
    else:
      self.error_reason, self.error_type = None, None
    self.error = Truncate(self.error)

  def _CalculateAttemptPropertyChanges(self):
    """Set up command event next attempt state."""
    if self.type == common.InvocationEventType.ALLOCATION_FAILED:
      # TF wasn't able to allocate a device for this leased task, due to a
      # device not meeting the command requirement. The command may be
      # misconfigured, so we should surface the allocation failure for
      # transparency.
      self.attempt_state = common.CommandState.CANCELED
      self.error = "Device allocation failed: %s" % (
          self.error or "Device did not meet command requirements")
      return
    if self.type == common.InvocationEventType.CONFIGURATION_ERROR:
      self.attempt_state = common.CommandState.FATAL
      return
    if self.type in (common.InvocationEventType.FETCH_FAILED,
                     common.InvocationEventType.EXECUTE_FAILED):
      self.attempt_state = common.CommandState.ERROR
      return
    if self.type in (common.InvocationEventType.INVOCATION_INITIATED,
                     common.InvocationEventType.INVOCATION_STARTED,
                     common.InvocationEventType.TEST_RUN_IN_PROGRESS,
                     common.InvocationEventType.INVOCATION_ENDED):
      self.attempt_state = common.CommandState.RUNNING
      self.attempt_start_time = self.time
      return
    if self.type == common.InvocationEventType.INVOCATION_COMPLETED:
      logging.debug("summary: %s", self.summary)
      self.attempt_end_time = self.time
      if self.error:
        # TODO: Remove this handling once InvocationCancelled events
        # are implemented.
        if TF_SHUTDOWN_ERROR_REGEX.match(self.error):
          self.attempt_state = common.CommandState.CANCELED
          return
        else:
          self.attempt_state = common.CommandState.ERROR
          return
      else:
        self.attempt_state = common.CommandState.COMPLETED
        return
    logging.warning("Unknown event type %s; ignored", self.type)

  def __str__(self):
    return ("<CommandEvent task_id:%s attempt_id:%s type:%s "
            "time:%s hostname:%s device_serial:%s "
            "attempt_state:%s data:%s>" %
            (self.task_id, self.attempt_id, self.type, self.time,
             self.hostname, self.device_serial, self.attempt_state,
             self.data))


def _GetEventData(data, key, value_type=None):
  """Get value for key from data.

  Args:
    data: a dict contains data.
    key: the key to get value.
    value_type: value's type.
  Returns:
    value
  """
  value = data.get(key)
  if value and value_type:
    value = value_type(value)
  return value


def Truncate(value, length=MAX_STRING_LENGTH):
  """Truncates a string.

  Args:
    value: value to truncate
    length: max length to truncate the value
  Returns:
    Truncated string
  """
  if not value:
    return value
  return value[:length]


def _ParseInvocationStatus(data):
  """Parses invocation progress data.

  Args:
    data: an invocation status object sent from TF.
  Returns:
    a datastore_entities.InvocationStatus object.
  """
  logging.info("invocation progress data: %s", data)
  if data is None:
    return None
  obj = datastore_entities.InvocationStatus()
  for t in data.get("test_group_statuses", []):
    obj.test_group_statuses.append(datastore_entities.TestGroupStatus(**t))
  return obj


def _ParseTaskId(task_id):
  """Parses a command ID from a task ID.

  Args:
    task_id: a task ID.
  Returns:
    (request_id, command_id)
  """
  ids = task_id.split("-", 2)
  if len(ids) == 3:
    return ids[0], ids[1]
  return None, ids[0]


class CommandEventBundle(object):
  """A class repesenting a command event bundle.

  Command events are uploaded as bundles by TF to avoid high traffic.
  """

  def __init__(self, task_id, task_data):
    """A constructor.

    Args:
      task_id: task ID.
      task_data: task data.
    """

    self._task_id = task_id
    self._events = []
    for item in task_data:
      try:
        self._events.append(CommandEvent(**item))
      except (KeyError, TypeError) as e:
        logging.warn("Failed to parse a command event %s: %s", item, e)

  @property
  def task_id(self):
    return self._task_id

  @property
  def events(self):
    return self._events


class CommandEventDataKey(object):
  """Command event data keys."""
  STATUS = "status"
  ERROR = "error"
  SUMMARY = "summary"
  TOTAL_TEST_COUNT = "total_test_count"
  FAILED_TEST_COUNT = "failed_test_count"
  TOTAL_TEST_RUN_COUNT = "total_test_run_count"
  FAILED_TEST_RUN_COUNT = "failed_test_run_count"


