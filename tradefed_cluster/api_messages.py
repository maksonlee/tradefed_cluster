# Lint as: python2, python3
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

# Messages may be used in api config,
# and we want to set the api parameter camel case.
"""Common config and classes for api."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from protorpc import message_types
from protorpc import messages

import six
from tradefed_cluster import common


# Expose those enum messages so library (in atp switcher) use api_message
# doesn't need to import a sparate common.
CommandErrorType = common.CommandErrorType
CommandState = common.CommandState
CancelReason = common.CancelReason
PredefinedMessageType = common.PredefinedMessageType
RequestState = common.RequestState


class KeyValuePair(messages.Message):
  """A message class for a key-value pair."""
  key = messages.StringField(1, required=True)
  value = messages.StringField(2)


class KeyMultiValuePair(messages.Message):
  """A message class for a key-multi value pair."""
  key = messages.StringField(1, required=True)
  values = messages.StringField(2, repeated=True)


def KeyValuePairMessagesToMap(key_value_pair_messages):
  """Transform a list of KeyValuePair message to a map.

  Args:
    key_value_pair_messages: a list of KeyValuePair message.
  Returns:
    a map with a string as key and a string as value
  """
  return {msg.key: msg.value for msg in key_value_pair_messages}


def MapToKeyValuePairMessages(key_value_map):
  """Transform a key value map to a list of KeyValuePair message.

  Args:
    key_value_map: a map with a string as key and a string as value, or None.
  Returns:
    a list of KeyValuePair message.
  """
  key_value_pair_messages = []
  if not key_value_map:
    return key_value_pair_messages
  for k, v in six.iteritems(key_value_map):
    if v is not None:
      v = _ValueToText(v)
    key_value_pair_messages.append(KeyValuePair(key=k, value=v))
  key_value_pair_messages.sort(key=lambda p: p.key)
  return key_value_pair_messages


def KeyMultiValuePairMessagesToMap(pairs):
  """Transform a list of KeyMultiValuePair message to a dict."""
  return {pair.key: pair.values for pair in pairs}


def MapToKeyMultiValuePairMessages(key_values_map):
  """Transform a key-values dict to a list of KeyMultiValuePairs."""
  pairs = []
  for key, values in six.iteritems((key_values_map or {})):
    str_values = [_ValueToText(v) if v is not None else v
                  for v in values]
    pairs.append(KeyMultiValuePair(key=key, values=str_values))
  pairs.sort(key=lambda p: p.key)
  return pairs


def _ValueToText(value):
  """Convert a value to text."""
  if isinstance(value, six.string_types):
    return six.ensure_text(value)
  return six.ensure_text(repr(value))


class TradefedConfigObjectType(messages.Enum):
  """TF config object types."""
  UNKNOWN = 0
  TARGET_PREPARER = 1
  RESULT_REPORTER = 2


class TradefedConfigObject(messages.Message):
  """A message class for a Tradefed config object."""
  type = messages.EnumField(TradefedConfigObjectType, 1, required=True)
  class_name = messages.StringField(2, required=True)
  option_values = messages.MessageField(KeyMultiValuePair, 3, repeated=True)


class TestEnvironment(messages.Message):
  """A message class to house environment settings for a test request.

  Attributes:
    env_vars: a dict of environment variables to be set before running a test.
    setup_scripts: a list of Linux shell scripts to run before running a test.
        (e.g. "sleep 5", "adb reboot")
    output_file_patterns: a list of regexes for output file patterns. TFC will
        collect these files from test working directoty after a test is
        completed.
    output_file_upload_url: an URL to which output files will be uploaded. This
        can be either a GCS or a HTTP url.
    use_subprocess_reporting: a flag on whether to use TF subprocess reporting.
    output_idle_timeout_millis: millis to wait for an idle subprocess
    jvm_options: a list of JVM options to be passed to TF.
    java_properties: a dict of Java properties to be passed to TF.
    context_file_pattern: a regex pattern for a test context file which needs to
        be passed across attempts (e.g. test_result.xml for xTS).
    retry_command_line: a command line to use in retry attempts (optional).
    log_level: a log level for a test launcher invocation.
    tradefed_config_objects:
        a list of TradefedConfigObject to add to a launcher config.
  """
  env_vars = messages.MessageField(KeyValuePair, 1, repeated=True)
  setup_scripts = messages.StringField(2, repeated=True)
  output_file_patterns = messages.StringField(3, repeated=True)
  output_file_upload_url = messages.StringField(4)
  use_subprocess_reporting = messages.BooleanField(5)
  output_idle_timeout_millis = messages.IntegerField(6)
  jvm_options = messages.StringField(7, repeated=True)
  java_properties = messages.MessageField(KeyValuePair, 8, repeated=True)
  context_file_pattern = messages.StringField(9)
  extra_context_files = messages.StringField(10, repeated=True)
  retry_command_line = messages.StringField(11)
  log_level = messages.EnumField(common.LogLevel, 12)
  tradefed_config_objects = messages.MessageField(
      TradefedConfigObject, 13, repeated=True)


class TestResource(messages.Message):
  """A message class for a test resource.

  Attributes:
    url: a url to download a test resource from.
    name: a filename with which a test resource to be stored in the test working
        directory.
    path: an option relative path to where a test resource should be downloaded
        to.
  """
  url = messages.StringField(1, required=True)
  name = messages.StringField(2)
  path = messages.StringField(3)


class TestResourceCollection(messages.Message):
  """A message class for a test resource collection."""
  test_resources = messages.MessageField(TestResource, 1, repeated=True)


class TestContext(messages.Message):
  """A message class for a text context.

  A text context is a data object which gets passed across attempts of a same
  command to allow a test invocation to pass information to the next
  invocations.

  Attributes:
    command_line: a command line to run in the next invocation.
    env_vars: addtional env. variables.
    test_resources: additional test resources.
  """
  command_line = messages.StringField(1)
  env_vars = messages.MessageField(KeyValuePair, 2, repeated=True)
  test_resources = messages.MessageField(TestResource, 3, repeated=True)


class CommandAttemptMessage(messages.Message):
  """Information for a command attempt.

  Attributes:
    request_id: Request ID for the command this attempt belongs to.
    command_id: Command ID this attempt belongs to.
    attempt_id: ID of this attempt.
    task_id: Task ID for this attempt.
    state: State of the attempt. See common.CommandState.
    hostname: Host for the device that ran this attempt.
    device_serial: Serial for the device that ran this attempt.
    start_time: Time when the invocation started.
    end_time: Time when the invocation completed.
    status: Status from command event for attempt. Used to log exceptions.
    error: Error from command event for attempt. User friendly error message.
    subprocess_command_error: Error from a subprocess command if exists.
    summary: Summary from command event for attempt. Usually a sponge link.
    total_test_count: Number of total test case.
    failed_test_count: Number of failed test case.
    passed_test_count: Number of passed test case.
    create_time: Time of the first command event processed for this attempt.
    update_time: Time of the last command event processed for this attempt.
    error_reason: Error reason get from error. Informative message.
    error_type: Error type get from error. See common.CommandErrorType.
    failed_test_run_count: Number of failed test run.
    device_serials: a list of device serials that the command attempt uses.
    device_lost_detected: Number of devices lost.
    run_index: run index from [0, run_count). The (run_index, attempt_index)
      tuple should be unique for a given command.
    attempt_index: attempt index. The (run_index, attempt_index) tuple should be
      unique for a given command.
  """
  request_id = messages.StringField(1, required=True)
  command_id = messages.StringField(2, required=True)
  attempt_id = messages.StringField(3, required=True)
  task_id = messages.StringField(4, required=True)
  state = messages.EnumField(common.CommandState, 5)
  hostname = messages.StringField(6)
  # TODO Deprecated.
  device_serial = messages.StringField(7)
  start_time = message_types.DateTimeField(8)
  end_time = message_types.DateTimeField(9)
  status = messages.StringField(10)
  error = messages.StringField(11)
  subprocess_command_error = messages.StringField(12)
  summary = messages.StringField(13)
  total_test_count = messages.IntegerField(14)
  failed_test_count = messages.IntegerField(15)
  passed_test_count = messages.IntegerField(16)
  create_time = message_types.DateTimeField(17)
  update_time = message_types.DateTimeField(18)
  error_reason = messages.StringField(19)
  error_type = messages.EnumField(common.CommandErrorType, 20)
  failed_test_run_count = messages.IntegerField(21)
  device_serials = messages.StringField(22, repeated=True)
  device_lost_detected = messages.IntegerField(23)
  run_index = messages.IntegerField(24)
  attempt_index = messages.IntegerField(25)


class CommandAttemptMessageCollection(messages.Message):
  """A class representing a collection of command attempts."""
  command_attempts = messages.MessageField(CommandAttemptMessage, 1,
                                           repeated=True)


class CommandAttemptEventMessage(messages.Message):
  """A class representing a command attempt event.

  This is used in notifier when publishing command attempt events.

  Attributes:
    type: an attempt event type string
    attempt: a command attempt message
    old_state: an enum type command state
    new_state: an enum type command state
    event_time: a datetime when the event occurred
  """
  type = messages.StringField(1)
  attempt = messages.MessageField(CommandAttemptMessage, 2)
  old_state = messages.EnumField(common.CommandState, 3)
  new_state = messages.EnumField(common.CommandState, 4)
  event_time = message_types.DateTimeField(5)


class CommandMessage(messages.Message):
  """Information for a Command."""
  id = messages.StringField(1, required=True)
  request_id = messages.StringField(2, required=True)
  command_line = messages.StringField(3, required=True)
  cluster = messages.StringField(4)
  run_target = messages.StringField(5)
  run_count = messages.IntegerField(6)
  shard_count = messages.IntegerField(7)
  shard_index = messages.IntegerField(8)
  state = messages.EnumField(common.CommandState, 9)
  start_time = message_types.DateTimeField(10)
  end_time = message_types.DateTimeField(11)
  create_time = message_types.DateTimeField(12)
  update_time = message_types.DateTimeField(13)
  cancel_reason = messages.EnumField(common.CancelReason, 14)
  error_reason = messages.EnumField(common.ErrorReason, 15)


class RequestType(messages.Enum):
  """Request types."""
  UNMANAGED = 0   # An unmanaged request
  MANAGED = 1     # A request for which TFC/TF handles setup/teardown process.


class RequestMessage(messages.Message):
  """A class representing a test request.

  TODO: add attributes the frontend needed to this class

  Attributes:
    id: a request ID.
    user: email of an user who made the request.
    command_line: a command line.
    priority: a priority value. Should be in range [0-1000]. Higher number means
        higher priority.
    queue_timeout_seconds: a queue timeout in seconds. A request will time out
        if it stays in QUEUED state longer than a given timeout.
    cancel_reason: a enum cancel reason.
    cluster: a target cluster name.
    run_target: a run target.
    run_count: a run count.
    shard_count: a shard count.
    max_retry_on_test_failures: the max number of retries on test failure per
        each command.
    prev_test_context: a previous test context.

    state: a state of the request.
    start_time: test execution start time.
    end_time: test execution stop time.
    create_time: time when the request was created.
    update_time: time when the request was last updated.
    command_attempts: a list of CommandAttemptMessages.
    cancel_message: a cancel message.
    api_module_version: API module version.
    commands: a list of commands of the request.
    command_attempts: a list of command attempts of the request.
  """
  id = messages.StringField(1)
  type = messages.EnumField(RequestType, 2)
  user = messages.StringField(3)
  command_line = messages.StringField(4)
  priority = messages.IntegerField(5)
  queue_timeout_seconds = messages.IntegerField(6)
  cancel_reason = messages.EnumField(common.CancelReason, 7)
  cluster = messages.StringField(8)
  run_target = messages.StringField(9)
  run_count = messages.IntegerField(10)
  shard_count = messages.IntegerField(11)
  max_retry_on_test_failures = messages.IntegerField(12)
  prev_test_context = messages.MessageField(TestContext, 13)

  state = messages.EnumField(common.RequestState, 15)
  start_time = message_types.DateTimeField(16)
  end_time = message_types.DateTimeField(17)
  create_time = message_types.DateTimeField(18)
  update_time = message_types.DateTimeField(19)
  # TODO: Deprecate cancel_message after remove the usage in ATP.
  cancel_message = messages.StringField(20)
  api_module_version = messages.StringField(21)
  commands = messages.MessageField(
      CommandMessage, 22, repeated=True)
  command_attempts = messages.MessageField(
      CommandAttemptMessage, 23, repeated=True)


class RequestMessageCollection(messages.Message):
  """A class representing a collection of test requests."""
  requests = messages.MessageField(RequestMessage, 1, repeated=True)


class RequestEventMessage(messages.Message):
  """A class representing a test request event.

  Attributes:
    type: a request event type string.
    request_id: a request ID.
    new_state: a enum type new state.
    request: a request obejct.
    summary: concatention of summaries in all attempts.
    total_test_count: total test count.
    failed_test_count: failed test count.
    passed_test_count: passed test count.
    result_links: result links for all attempts.
    total_run_time_sec: total run time seconds
    error_reason: first error reason string in all attempts.
    error_type: first error type enum in all attempts.
    failed_test_run_count: failed test run count.
    device_lost_detected: Number of devices lost.

  This is used in notifier when publishing request events.
  """
  type = messages.StringField(1)
  request_id = messages.StringField(2)
  new_state = messages.EnumField(common.RequestState, 3)
  request = messages.MessageField(RequestMessage, 4)
  summary = messages.StringField(5)
  total_test_count = messages.IntegerField(6)
  failed_test_count = messages.IntegerField(7)
  passed_test_count = messages.IntegerField(8)
  result_links = messages.StringField(9, repeated=True)
  total_run_time_sec = messages.IntegerField(10)
  error_reason = messages.StringField(11)
  error_type = messages.EnumField(common.CommandErrorType, 12)
  event_time = message_types.DateTimeField(13)
  failed_test_run_count = messages.IntegerField(14)
  device_lost_detected = messages.IntegerField(15)


class Note(messages.Message):
  """Note for a cluster, host, or device."""
  id = messages.StringField(1)
  user = messages.StringField(2)
  timestamp = message_types.DateTimeField(3)
  message = messages.StringField(4)
  offline_reason = messages.StringField(5)
  recovery_action = messages.StringField(6)
  type = messages.EnumField(common.NoteType, 7)
  cluster_id = messages.StringField(8)
  hostname = messages.StringField(9)
  device_serial = messages.StringField(10)
  event_time = message_types.DateTimeField(11)


class NoteCollection(messages.Message):
  """A class representing a collection of notes."""
  notes = messages.MessageField(Note, 1, repeated=True)
  more = messages.BooleanField(2)
  next_cursor = messages.StringField(3)
  prev_cursor = messages.StringField(4)


class NoteEvent(messages.Message):
  """Note event with part of the cluster/host/device info message."""
  note = messages.MessageField(Note, 1, required=True)
  cluster_id = messages.StringField(2)
  hostname = messages.StringField(3)
  lab_name = messages.StringField(4)
  run_target = messages.StringField(5)
  publish_timestamp = message_types.DateTimeField(6, required=True)


class BatchUpdateNotesWithPredefinedMessageRequest(messages.Message):
  """An object that contains the request body of batch update notes endpoint."""
  notes = messages.MessageField(Note, 1, repeated=True)
  message = messages.StringField(2)
  offline_reason = messages.StringField(3)
  recovery_action = messages.StringField(4)
  offline_reason_id = messages.IntegerField(5)
  recovery_action_id = messages.IntegerField(6)
  lab_name = messages.StringField(7)
  user = messages.StringField(8)
  event_time = message_types.DateTimeField(9)


class DeviceStateHistory(messages.Message):
  """Device state history record."""
  timestamp = message_types.DateTimeField(1, required=True)
  state = messages.StringField(2, required=True)


class DeviceTypeMessage(messages.Enum):
  """Device types."""
  EMULATOR = 0
  TCP = 1
  NULL = 2
  PHYSICAL = 3
  GCE = 4
  REMOTE = 5
  LOCAL_VIRTUAL = 6


class DeviceInfo(messages.Message):
  """Information for a given test device.

  TODO: Create an extra_info field for data not intended to be queried
  individually (eg. SIM information).

  Attributes:
    device_serial: Serial identifying the device. It should be unique.
      According to @bgay, it is a rare occurrence and non-unique device serials
      are usually rejected.
    lab_name: the name of the lab this device belong to.
    hostname: The name of the host this device is connected to.
    run_target: Run target for the device.
    build_id: Current build ID in the device.
    product: Device product (Eg.: flounder).
    product_variant: Device product variant (Eg.: flounder_lte)
    sdk_version: SDK version of the device's build.
    state: Reported state of the device.
    battery_level: Reported battery level of the device.
    hidden: Is the device hidden.
    notes: Notes entered by a user.
    history: State history.
    utilization: Rate of allocated over total time of the device.
    cluster: Cluster ID for this device's host.
    host_group: a group of host using the same host config.
    pools: pools of devices to manage device resources.
    mac_address: MAC address of the device.
    group_name: Device group name.
    sim_state: State of the SIM.
    sim_operator: Operator of the SIM.
    extra_info: a key value list for device's extra info.
    flated_extra_info: a list representation of extra_info,
        each element is "key=value".
    test_harness: test harness the device is running under.
    recovery_state: recovery state for the host, e.g. assigned, fixed, verified.
    last_recovery_time: the last time the device gets recovered.
  """
  device_serial = messages.StringField(1)
  lab_name = messages.StringField(2)
  hostname = messages.StringField(3)
  run_target = messages.StringField(4)
  build_id = messages.StringField(5)
  product = messages.StringField(6)
  product_variant = messages.StringField(7)
  sdk_version = messages.StringField(8)
  state = messages.StringField(9)
  timestamp = message_types.DateTimeField(10)
  battery_level = messages.StringField(11)
  hidden = messages.BooleanField(12)
  notes = messages.MessageField(Note, 13, repeated=True)
  history = messages.MessageField(DeviceStateHistory, 14, repeated=True)
  utilization = messages.FloatField(15)
  # TODO: deprecate physical_cluster, use host_group.
  cluster = messages.StringField(16)
  host_group = messages.StringField(17)
  pools = messages.StringField(18, repeated=True)
  device_type = messages.EnumField(DeviceTypeMessage, 19)
  mac_address = messages.StringField(20)
  group_name = messages.StringField(21)
  sim_state = messages.StringField(22)
  sim_operator = messages.StringField(23)
  extra_info = messages.MessageField(KeyValuePair, 24, repeated=True)
  # TODO: Change to flattened_extra_info.
  flated_extra_info = messages.StringField(25, repeated=True)
  test_harness = messages.StringField(26)
  recovery_state = messages.StringField(27)
  last_recovery_time = message_types.DateTimeField(28)


class DeviceInfoCollection(messages.Message):
  """A class representing a collection of host infos."""
  device_infos = messages.MessageField(DeviceInfo, 1, repeated=True)
  # The cursor after the last device entity.
  # This is the start cursor for the next batch query.
  next_cursor = messages.StringField(2)
  prev_cursor = messages.StringField(3)
  # There are more entities after or not.
  # TODO: remove more, use next_cursor should be enough.
  more = messages.BooleanField(4)


class DeviceInfoHistoryCollection(messages.Message):
  """A class representing a collection of device histories."""
  histories = messages.MessageField(DeviceInfo, 1, repeated=True)
  next_cursor = messages.StringField(2)
  prev_cursor = messages.StringField(3)


class HostState(messages.Enum):
  """Enum for host states."""
  UNKNOWN = 0
  GONE = 1
  RUNNING = 2
  QUITTING = 3
  KILLING = 4


class HostStateHistory(messages.Message):
  """Host state history."""
  hostname = messages.StringField(1, required=True)
  timestamp = message_types.DateTimeField(2, required=True)
  state = messages.StringField(3, required=True)


class HostUpdateState(messages.Enum):
  """Enum for host update states."""
  # An unknown state.
  UNKNOWN = 0
  # The update task is scheduled, but not started.
  PENDING = 1
  # The step "syncing image" during an update.
  SYNCING = 2
  # The step "shutting down container" during an update.
  SHUTTING_DOWN = 3
  # The step "starting a new container" during an update.
  RESTARTING = 4
  # The update task is considered timeout because not receiving state report
  # after the timeout.
  FAILED_TIMED_OUT = 5
  # The update failed because of error state reported.
  FAILED_ERRORED = 6
  # The update succeeded.
  SUCCEEDED = 7


class HostConfig(messages.Message):
  """Information for a given host config."""
  hostname = messages.StringField(1)
  tf_global_config_path = messages.StringField(2)
  host_login_name = messages.StringField(3)


class DeviceCountSummary(messages.Message):
  """Information of device count for a host."""
  run_target = messages.StringField(1)
  total = messages.IntegerField(2)
  offline = messages.IntegerField(3)
  available = messages.IntegerField(4)
  allocated = messages.IntegerField(5)
  timestamp = message_types.DateTimeField(6)


class HostInfo(messages.Message):
  """Information for a given test host."""
  hostname = messages.StringField(1)
  lab_name = messages.StringField(2)
  # TODO: deprecate physical_cluster, use host_group.
  cluster = messages.StringField(3)
  host_group = messages.StringField(4)
  # TODO: deprecated test runner and test runner version.
  test_runner = messages.StringField(5)
  test_runner_version = messages.StringField(6)
  device_infos = messages.MessageField(DeviceInfo, 7, repeated=True)
  timestamp = message_types.DateTimeField(8)
  total_devices = messages.IntegerField(9)
  offline_devices = messages.IntegerField(10)
  available_devices = messages.IntegerField(11)
  allocated_devices = messages.IntegerField(12)
  device_count_timestamp = message_types.DateTimeField(13)
  hidden = messages.BooleanField(14)
  notes = messages.MessageField(Note, 15, repeated=True)
  extra_info = messages.MessageField(KeyValuePair, 16, repeated=True)
  # TODO: deprecate clusters, use pools.
  next_cluster_ids = messages.StringField(17, repeated=True)
  pools = messages.StringField(18, repeated=True)
  host_state = messages.StringField(19)
  tf_start_time = message_types.DateTimeField(20)
  state_history = messages.MessageField(HostStateHistory, 21, repeated=True)
  assignee = messages.StringField(22)
  device_count_summaries = messages.MessageField(
      DeviceCountSummary, 23, repeated=True)
  # Bad host is defined in datastore_entities._IsBadHost.
  is_bad = messages.BooleanField(24)
  test_harness = messages.StringField(25)
  test_harness_version = messages.StringField(26)
  flated_extra_info = messages.StringField(27, repeated=True)
  last_recovery_time = message_types.DateTimeField(28)
  recovery_state = messages.StringField(29)
  update_state = messages.StringField(30)


class HostInfoCollection(messages.Message):
  """A class representing a collection of host infos."""
  host_infos = messages.MessageField(HostInfo, 1, repeated=True)
  next_cursor = messages.StringField(2)
  prev_cursor = messages.StringField(3)
  # TODO: remove more, use next_cursor should be enough
  more = messages.BooleanField(4)


class HostInfoHistoryCollection(messages.Message):
  """A class representing a collection of host histories."""
  histories = messages.MessageField(HostInfo, 1, repeated=True)
  next_cursor = messages.StringField(2)
  prev_cursor = messages.StringField(3)


class RunTarget(messages.Message):
  """Run target message class."""
  name = messages.StringField(1, required=True)


class ClusterInfo(messages.Message):
  """Information for a given Cluster."""
  cluster_id = messages.StringField(1)
  total_devices = messages.IntegerField(2)
  offline_devices = messages.IntegerField(3)
  available_devices = messages.IntegerField(4)
  allocated_devices = messages.IntegerField(5)
  device_count_timestamp = message_types.DateTimeField(6)
  host_infos = messages.MessageField(HostInfo, 7, repeated=True)
  notes = messages.MessageField(Note, 8, repeated=True)
  run_targets = messages.MessageField(RunTarget, 9, repeated=True)


class LabInfo(messages.Message):
  """Information for a given Lab."""
  lab_name = messages.StringField(1)
  update_timestamp = message_types.DateTimeField(2)
  owners = messages.StringField(3, repeated=True)


class LabInfoCollection(messages.Message):
  """A class representing a collection of lab infos."""
  lab_infos = messages.MessageField(LabInfo, 1, repeated=True)
  next_cursor = messages.StringField(2)
  prev_cursor = messages.StringField(3)
  # TODO: remove more, use next_cursor should be enough
  more = messages.BooleanField(4)


class CheckAdminMessage(messages.Message):
  """A message class for admin check."""
  isAdmin = messages.BooleanField(1, default=False)


class NonEmptyStringField(messages.StringField):
  """A StringField can not be empty or all whitespace."""

  def validate_element(self, value):
    """Validate the value is not empty or all whitespace.

    Args:
      value: the value of the field
    Raises:
      ValidationError: value is empty or all whitespace
    """
    if isinstance(value, str) or isinstance(value, six.text_type):
      if not value.strip():
        name = getattr(self, "name")
        if not name:
          validation_error = messages.ValidationError(
              "Field encountered empty string %s" % value)
        else:
          validation_error = messages.ValidationError(
              "Field %s encountered empty string %s" % (name, value))
          validation_error.field_name = name
        raise validation_error
    messages.StringField.validate_element(self, value)


class NewRequestMessage(messages.Message):
  """A message class for parameters to create new request."""
  type = messages.EnumField(RequestType, 1)
  user = messages.StringField(2)
  command_line = messages.StringField(3)
  priority = messages.IntegerField(4)
  queue_timeout_seconds = messages.IntegerField(5)
  cluster = NonEmptyStringField(6)
  run_target = NonEmptyStringField(7)
  run_count = messages.IntegerField(8, default=1)
  shard_count = messages.IntegerField(9, default=1)
  max_retry_on_test_failures = messages.IntegerField(10)
  prev_test_context = messages.MessageField(TestContext, 11)

  test_environment = messages.MessageField(TestEnvironment, 12)
  test_resources = messages.MessageField(TestResource, 13, repeated=True)
  plugin_data = messages.MessageField(KeyValuePair, 14, repeated=True)
  test_bench_attributes = messages.StringField(15, repeated=True)


class CommandEventType(messages.Enum):
  """The different types of command events."""
  FETCH_FAILED = 1
  EXECUTE_FAILED = 2
  INVOCATION_STARTED = 3
  INVOCATION_FAILED = 4
  INVOCATION_ENDED = 5
  INVOCATION_COMPLETED = 6
  TEST_RUN_STARTED = 7
  TEST_RUN_ENDED = 8
  TEST_ENDED = 9


class CommandEventData(messages.Message):
  """Extra data included in a command event."""
  total_test_count = messages.IntegerField(1)
  exec_test_count = messages.IntegerField(2)


class DeviceNote(messages.Message):
  """Device note message."""
  id = messages.StringField(1, required=True)
  device_serial = messages.StringField(2, required=True)
  user = messages.StringField(3)
  update_timestamp = message_types.DateTimeField(4)
  offline_reason = messages.StringField(5)
  recovery_action = messages.StringField(6)
  message = messages.StringField(7)


class DeviceNoteEvent(messages.Message):
  """Device note event with part of the device info message."""
  device_note = messages.MessageField(DeviceNote, 1, required=True)
  hostname = messages.StringField(2, required=True)
  lab_name = messages.StringField(3)
  run_target = messages.StringField(4)
  publish_timestamp = message_types.DateTimeField(5, required=True)


class DeviceNoteCollection(messages.Message):
  """A class representing a collection of device notes."""
  device_notes = messages.MessageField(DeviceNote, 1, repeated=True)
  # TODO: remove more, use next_cursor should be enough
  more = messages.BooleanField(2)
  next_cursor = messages.StringField(3)
  prev_cursor = messages.StringField(4)


class HostNote(messages.Message):
  """Host note message."""
  id = messages.StringField(1, required=True)
  hostname = messages.StringField(2, required=True)
  user = messages.StringField(3)
  update_timestamp = message_types.DateTimeField(4)
  offline_reason = messages.StringField(5)
  recovery_action = messages.StringField(6)
  message = messages.StringField(7)


class HostNoteEvent(messages.Message):
  """Host note event message."""
  host_note = messages.MessageField(HostNote, 1, required=True)
  lab_name = messages.StringField(2)
  publish_timestamp = message_types.DateTimeField(3, required=True)


class HostNoteCollection(messages.Message):
  """A class representing a collection of host notes."""
  host_notes = messages.MessageField(HostNote, 1, repeated=True)
  # TODO: remove more, use next_cursor should be enough
  more = messages.BooleanField(2)
  next_cursor = messages.StringField(3)
  prev_cursor = messages.StringField(4)


class PredefinedMessage(messages.Message):
  """Predefined messages that describe incidents.

  Attributes:
    id: int, the id of a PredefinedMessage.
    lab_name: lab_name, the lab that the predefined_message belongs to.
    type: the type of the message.
    content: a unique text content of the message.
    create_timestamp: the datetime that the message is first created.
    used_count: the count the message has been used.
  """
  id = messages.IntegerField(1, required=True)
  lab_name = messages.StringField(2, required=True)
  type = messages.EnumField(PredefinedMessageType, 3, required=True)
  content = messages.StringField(4, required=True)
  create_timestamp = message_types.DateTimeField(5)
  used_count = messages.IntegerField(6, default=0)


class PredefinedMessageCollection(messages.Message):
  """A class representing a collection of predefined messages."""
  predefined_messages = messages.MessageField(
      PredefinedMessage, 1, repeated=True)
  next_cursor = messages.StringField(2)
  prev_cursor = messages.StringField(3)


class TestGroupStatus(messages.Message):
  """A message class to store test group status.

  Attributes:
    name: a test group name.
    total_test_count: total number of tests.
    completed_test_count: number of completed tests.
    failed_test_count: number of failed tests.
    passed_test_count: number of passed tests.
    is_complete: a flag indicating completion of a test module.
    elapsed_time: elapsed time in millis
    failure_message: a failure message.
  """
  name = messages.StringField(1)
  total_test_count = messages.IntegerField(2)
  completed_test_count = messages.IntegerField(3)
  failed_test_count = messages.IntegerField(4)
  passed_test_count = messages.IntegerField(5)
  is_complete = messages.BooleanField(6)
  elapsed_time = messages.IntegerField(7)
  failure_message = messages.StringField(8)


class InvocationStatus(messages.Message):
  test_group_statuses = messages.MessageField(TestGroupStatus, 1, repeated=True)


class CommandEvent(messages.Message):
  """A message class representing a cluster command event.

  TODO: 'event_type' field is not being used. Coordinator uses the
  'type' field for command event types.
  """
  event_type = messages.EnumField(CommandEventType, 1)
  time = messages.IntegerField(2)
  task_id = messages.StringField(3)
  attempt_id = messages.StringField(4)
  hostname = messages.StringField(5)
  # TODO Deprecated.
  device_serial = messages.StringField(6)
  data = messages.MessageField(CommandEventData, 7)
  type = messages.StringField(8)
  invocation_status = messages.MessageField(InvocationStatus, 9)
  device_serials = messages.StringField(10, repeated=True)


class CommandEventList(messages.Message):
  """A message class representing a list of cluster command events."""
  command_events = messages.MessageField(CommandEvent, 1, repeated=True)


class FilterHintMessage(messages.Message):
  """A message class representing filter hint."""
  value = messages.StringField(1)


class FilterHintCollection(messages.Message):
  """A class representing a collection of filter hint."""
  filter_hints = messages.MessageField(FilterHintMessage, 1, repeated=True)


class DeviceBlocklistMessage(messages.Message):
  """Device blocklist message."""
  key_id = messages.IntegerField(1)
  lab_name = messages.StringField(2)
  # TODO: Add other fields, e.g. cluster, hostname, etc.
  create_timestamp = message_types.DateTimeField(3)
  note = messages.StringField(4)
  user = messages.StringField(5)


class DeviceBlocklistCollection(messages.Message):
  """A list of device block lists."""
  device_blocklists = messages.MessageField(
      DeviceBlocklistMessage, 1, repeated=True)
  next_cursor = messages.StringField(2)
  prev_cursor = messages.StringField(3)


class DeviceBlocklistArchiveMessage(messages.Message):
  """Device blocklist archive message."""
  device_blocklist = messages.MessageField(DeviceBlocklistMessage, 1)
  start_timestamp = message_types.DateTimeField(2)
  end_timestamp = message_types.DateTimeField(3)
  archived_by = messages.StringField(4)


class HostRecoveryStateRequest(messages.Message):
  """Host recovery state request."""
  hostname = messages.StringField(1, required=True)
  recovery_state = messages.StringField(2, required=True)
  assignee = messages.StringField(3)


class HostRecoveryStateRequests(messages.Message):
  """A list of host recovery state request."""
  host_recovery_state_requests = messages.MessageField(
      HostRecoveryStateRequest, 1, repeated=True)


class DeviceRecoveryStateRequest(messages.Message):
  """Device recovery state request."""
  hostname = messages.StringField(1)
  device_serial = messages.StringField(2, required=True)
  recovery_state = messages.StringField(3, required=True)
  assignee = messages.StringField(4)


class DeviceRecoveryStateRequests(messages.Message):
  """A list of device recovery state request."""
  device_recovery_state_requests = messages.MessageField(
      DeviceRecoveryStateRequest, 1, repeated=True)


class TestHarnessImageMetadataMessage(messages.Message):
  """Test harness image metadata message."""
  repo_name = messages.StringField(1)
  digest = messages.StringField(2)
  test_harness = messages.StringField(3)
  test_harness_version = messages.StringField(4)
  create_time = message_types.DateTimeField(5)
  tags = messages.StringField(9, repeated=True)


class TestHarnessImageMetadataCollection(messages.Message):
  """A collection of test harness image metadata."""
  images = messages.MessageField(
      TestHarnessImageMetadataMessage, 1, repeated=True)
  next_cursor = messages.StringField(2)
