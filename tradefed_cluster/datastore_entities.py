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

"""Datastore entity classes."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import datetime
import six


from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster.util import ndb_shim as ndb

# Constant to hold a time of 0 (0 hours, 0 minutes, 0 seconds)
ZERO_TIME = datetime.time()

# A dispatch dictionary mapping entity classes to message converter functions.
_CONVERTER_DISPATCH_DICT = {}


def MessageConverter(entity_cls):
  """A decorator for labelling converter functions of entity classes.

  A utility decorator for mapping a message converter to an entity class.  We
  use a utility decorator as opposed to manually defining the dispatch
  dictionary so that it's more apparent if we forget a converter.

  Args:
    entity_cls: The entity class to convert a message from.
  Returns:
    A function decorator for registering the converter function.
  """
  def ConverterWrapper(converter_fn):
    _CONVERTER_DISPATCH_DICT[entity_cls] = converter_fn
    return converter_fn
  return ConverterWrapper


def ToMessage(entity, *args, **kwargs):
  """A utility method to convert a datastore entity into an API message."""
  if entity is None:
    return None
    assert type(entity) in _CONVERTER_DISPATCH_DICT, (
      'Converter for "%s" not defined.' % type(entity).__name__)
    return _CONVERTER_DISPATCH_DICT[type(entity)](entity, *args, **kwargs)


class TestResource(ndb.Model):
  """A test resource entity.

  Attributes:
    url: a test resource download url.
    name: an expected filename in a test working directory.
    path: an expected path in a test working directory.
  """
  url = ndb.StringProperty()
  name = ndb.StringProperty()
  path = ndb.StringProperty()

  @classmethod
  def FromMessage(cls, msg):
    return cls(url=msg.url, name=msg.name, path=msg.path)


class TestContext(ndb.Model):
  """A text context entity.

  Attributes:
    command_line: a command line to run in the next invocation.
    env_vars: addtional env. variables.
    test_resources: additional test resources.
  """
  command_line = ndb.StringProperty()
  env_vars = ndb.JsonProperty()
  test_resources = ndb.StructuredProperty(TestResource, repeated=True)

  @classmethod
  def FromMessage(cls, msg):
    return cls(
        command_line=msg.command_line,
        env_vars={p.key: p.value for p in msg.env_vars},
        test_resources=[
            TestResource.FromMessage(r) for r in msg.test_resources
        ])


@MessageConverter(TestContext)
def TestContextToMessage(entity):
  """Converts a TextContext entity to a message.

  Args:
    entity: a TestContext object.
  Returns:
    a api_messages.TestContext object.
  """
  env_vars = []
  if entity.env_vars:
    env_vars = [
        api_messages.KeyValuePair(key=key, value=value)
        for key, value in six.iteritems(entity.env_vars)
    ]
  test_resources = []
  if entity.test_resources:
    test_resources = [
        api_messages.TestResource(name=r.name, url=r.url, path=r.path)
        for r in entity.test_resources
    ]
  return api_messages.TestContext(
      command_line=entity.command_line,
      env_vars=env_vars,
      test_resources=test_resources)


class Request(ndb.Model):
  """A test request entity.

  Attributes:
    type: a request type.
    user: email of an user who made the request.
    command_line: a command line.
    priority: a priority value. Should be in range [0-1000].
    queue_timeout_seconds: a queue timeout in seconds. A request will time out
        if it stays in QUEUED state longer than a given timeout.
    cancel_reason: a machine readable enum cancel reason.
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
    cancel_message: a human readable cancel message.
    dirty: whether or not the state of this request needs to be updated.
    notify_state_change: whether or not the state of this request needs to be
        notified.
    plugin_data: the plugin data.
  """
  type = ndb.EnumProperty(api_messages.RequestType)
  user = ndb.StringProperty()
  command_line = ndb.TextProperty()
  # priority should be an integer. The larger, the higher priority.
  # The lowest priority is 0, it's the default priority.
  priority = ndb.IntegerProperty()
  queue_timeout_seconds = ndb.IntegerProperty()
  cancel_reason = ndb.EnumProperty(common.CancelReason)
  cluster = ndb.StringProperty()
  run_target = ndb.StringProperty()
  run_count = ndb.IntegerProperty()
  shard_count = ndb.IntegerProperty()
  max_retry_on_test_failures = ndb.IntegerProperty()
  prev_test_context = ndb.LocalStructuredProperty(TestContext)

  state = ndb.EnumProperty(common.RequestState,
                           default=common.RequestState.UNKNOWN)
  start_time = ndb.DateTimeProperty()
  end_time = ndb.DateTimeProperty()
  create_time = ndb.DateTimeProperty(auto_now_add=True)
  update_time = ndb.DateTimeProperty(auto_now=True)
  cancel_message = ndb.TextProperty()
  # Whether a given Request data is stale and needs to be re-evaluated
  dirty = ndb.BooleanProperty(default=False)
  # Whether we need to notify that the state has changed.
  notify_state_change = ndb.BooleanProperty(default=False)
  plugin_data = ndb.JsonProperty()


@MessageConverter(Request)
def RequestToMessage(request, command_attempts=None, commands=None):
  """Convert a request entity to a RequestMessage.

  Args:
    request: A request entity.
    command_attempts: A list of CommandAttempt entities.
    commands: A list of Command entities.
  Returns:
    a RequestMessage.
  """
  command_attempts = command_attempts or []
  commands = commands or []
  request_id = request.key.id()
  return api_messages.RequestMessage(
      id=request_id,
      type=request.type,
      user=request.user,
      command_line=request.command_line,
      state=request.state,
      start_time=request.start_time,
      end_time=request.end_time,
      create_time=request.create_time,
      update_time=request.update_time,
      command_attempts=[ToMessage(ca) for ca in command_attempts],
      commands=[ToMessage(command) for command in commands],
      cancel_message=request.cancel_message,
      cancel_reason=request.cancel_reason,
      cluster=request.cluster,
      run_target=request.run_target,
      run_count=request.run_count,
      shard_count=request.shard_count,
      max_retry_on_test_failures=request.max_retry_on_test_failures,
      prev_test_context=ToMessage(request.prev_test_context))


class TradefedConfigObject(ndb.Model):
  """A Tradefed config object entity."""
  type = ndb.EnumProperty(api_messages.TradefedConfigObjectType)
  class_name = ndb.StringProperty()
  option_values = ndb.JsonProperty()

  @classmethod
  def FromMessage(cls, msg):
    return cls(
        type=msg.type,
        class_name=msg.class_name,
        option_values={p.key: p.values for p in msg.option_values})


@MessageConverter(TradefedConfigObject)
def TradefedConfigObjectToMessage(entity):
  """Converts a TradefedConfigObject object to an API message."""
  option_values = []
  if entity.option_values:
    option_values = [
        api_messages.KeyMultiValuePair(key=k, values=v)
        for k, v in six.iteritems(entity.option_values)
    ]
  return api_messages.TradefedConfigObject(
      type=entity.type,
      class_name=entity.class_name,
      option_values=option_values)


class TestEnvironment(ndb.Model):
  """A test environment entity."""
  env_vars = ndb.JsonProperty()
  setup_scripts = ndb.StringProperty(repeated=True)
  output_file_upload_url = ndb.StringProperty()
  output_file_patterns = ndb.StringProperty(repeated=True)
  use_subprocess_reporting = ndb.BooleanProperty()
  output_idle_timeout_millis = ndb.IntegerProperty()
  jvm_options = ndb.StringProperty(repeated=True)
  java_properties = ndb.JsonProperty()
  context_file_pattern = ndb.StringProperty()
  extra_context_files = ndb.StringProperty(repeated=True)
  retry_command_line = ndb.StringProperty()
  log_level = ndb.EnumProperty(common.LogLevel)
  tradefed_config_objects = ndb.LocalStructuredProperty(
      TradefedConfigObject, repeated=True)

  @classmethod
  def FromMessage(cls, msg):
    return cls(
        env_vars={p.key: p.value for p in msg.env_vars},
        setup_scripts=msg.setup_scripts,
        output_file_upload_url=msg.output_file_upload_url,
        output_file_patterns=msg.output_file_patterns,
        use_subprocess_reporting=msg.use_subprocess_reporting,
        output_idle_timeout_millis=msg.output_idle_timeout_millis,
        jvm_options=msg.jvm_options,
        java_properties={p.key: p.value for p in msg.java_properties},
        context_file_pattern=msg.context_file_pattern,
        extra_context_files=msg.extra_context_files,
        retry_command_line=msg.retry_command_line,
        log_level=msg.log_level,
        tradefed_config_objects=[
            TradefedConfigObject.FromMessage(o)
            for o in msg.tradefed_config_objects
        ])


@MessageConverter(TestEnvironment)
def TestEnvironmentToMessage(entity):
  """Converts a TestEnvironment entity to a message.

  Args:
    entity: a TestEnvironment object.
  Returns:
    a api_messages.TestEnvironment object.
  """
  env_vars = api_messages.MapToKeyValuePairMessages(entity.env_vars)
  java_properties = api_messages.MapToKeyValuePairMessages(
      entity.java_properties)
  return api_messages.TestEnvironment(
      env_vars=env_vars,
      setup_scripts=entity.setup_scripts,
      output_file_upload_url=entity.output_file_upload_url,
      output_file_patterns=entity.output_file_patterns,
      use_subprocess_reporting=entity.use_subprocess_reporting,
      output_idle_timeout_millis=entity.output_idle_timeout_millis,
      jvm_options=entity.jvm_options,
      java_properties=java_properties,
      context_file_pattern=entity.context_file_pattern,
      extra_context_files=entity.extra_context_files,
      retry_command_line=entity.retry_command_line,
      log_level=entity.log_level,
      tradefed_config_objects=[
          ToMessage(t) for t in entity.tradefed_config_objects
      ])


class Command(ndb.Model):
  """A test command entity.

  Attributes:
    request_id: a request ID.
    command_hash: a hash of the command line.
    command_line: a command line.
    cluster: a target cluster ID.
    run_target: a target run target.
    run_count: a target run count.
    state: a state of the command.
    start_time: command execution start time.
    end_time: command execution stop time.
    create_time: time when the command was created.
    update_time: time when the command was last updated.
    dirty: whether or not the state of this command needs to be updated.
    priority: a priority value. Should be in range [0-1000].
    queue_timeout_seconds: a queue timeout in seconds. A command will time out
        if it stays in QUEUED state longer than a given timeout.
    request_type: a request type.
    cancel_reason: a cancel reason
    shard_count: a shard count.
    shard_index: a shard index.
    plugin_data: the plugin data.
  """
  request_id = ndb.StringProperty()
  command_hash = ndb.StringProperty()
  command_line = ndb.TextProperty()
  cluster = ndb.StringProperty()
  run_target = ndb.StringProperty()
  run_count = ndb.IntegerProperty()
  state = ndb.EnumProperty(common.CommandState,
                           default=common.CommandState.UNKNOWN)
  start_time = ndb.DateTimeProperty()
  end_time = ndb.DateTimeProperty()
  create_time = ndb.DateTimeProperty(auto_now_add=True)
  update_time = ndb.DateTimeProperty(auto_now=True)
  dirty = ndb.BooleanProperty(default=False)
  priority = ndb.IntegerProperty()
  queue_timeout_seconds = ndb.IntegerProperty()
  request_type = ndb.EnumProperty(api_messages.RequestType)
  cancel_reason = ndb.EnumProperty(common.CancelReason)
  shard_count = ndb.IntegerProperty()
  shard_index = ndb.IntegerProperty()
  plugin_data = ndb.JsonProperty()


@MessageConverter(Command)
def CommandToMessage(command):
  _, request_id, _, command_id = command.key.flat()
  return api_messages.CommandMessage(
      id=command_id,
      request_id=request_id,
      command_line=command.command_line,
      cluster=command.cluster,
      run_target=command.run_target,
      run_count=command.run_count,
      state=common.CommandState(command.state or common.CommandState.UNKNOWN),
      start_time=command.start_time,
      end_time=command.end_time,
      create_time=command.create_time,
      update_time=command.update_time,
      cancel_reason=command.cancel_reason,
      shard_count=command.shard_count,
      shard_index=command.shard_index)


class TestGroupStatus(ndb.Model):
  """A class to store progress of a test group."""
  name = ndb.StringProperty(required=True)
  total_test_count = ndb.IntegerProperty(default=0)
  completed_test_count = ndb.IntegerProperty(default=0)
  failed_test_count = ndb.IntegerProperty(default=0)
  passed_test_count = ndb.IntegerProperty(default=0)
  is_complete = ndb.BooleanProperty(default=False)
  elapsed_time = ndb.IntegerProperty(default=0)
  failure_message = ndb.TextProperty()

  def Merge(self, other):
    assert self.name == other.name
    self.total_test_count += other.total_test_count
    self.completed_test_count += other.completed_test_count
    self.failed_test_count += other.failed_test_count
    self.passed_test_count += other.passed_test_count
    self.is_complete &= other.is_complete
    self.elapsed_time += other.elapsed_time
    self.failure_message = ('\n'.join(
        [fm for fm in [self.failure_message, other.failure_message] if fm]) or
                            None)


@MessageConverter(TestGroupStatus)
def TestGroupStatusToMessage(entity):
  return api_messages.TestGroupStatus(
      name=entity.name,
      total_test_count=entity.total_test_count,
      completed_test_count=entity.completed_test_count,
      failed_test_count=entity.failed_test_count,
      passed_test_count=entity.passed_test_count,
      is_complete=entity.is_complete,
      elapsed_time=entity.elapsed_time,
      failure_message=entity.failure_message)


class InvocationStatus(ndb.Model):
  """A class to store status of a test invocation."""
  test_group_statuses = ndb.LocalStructuredProperty(
      TestGroupStatus, repeated=True)

  def Merge(self, other):
    test_group_status_map = {t.name: t for t in self.test_group_statuses}
    for status in other.test_group_statuses:
      if status.name not in test_group_status_map:
        new_status = TestGroupStatus(name=status.name, is_complete=True)
        self.test_group_statuses.append(new_status)
        test_group_status_map[status.name] = new_status
      test_group_status_map[status.name].Merge(status)


@MessageConverter(InvocationStatus)
def InvocationStatusToMessage(entity):
  return api_messages.InvocationStatus(
      test_group_statuses=[ToMessage(t) for t in entity.test_group_statuses])


class CommandAttempt(ndb.Model):
  """A test command attempt entity.

  Attributes:
    command_id: a command ID.
    task_id: a task ID.
    attempt_id: a attempt ID.
    state: a state of the command attempt.
    hostname: a host name of the command attempt device running on.
    # TODO Deprecated.
    device_serial: a serial of the device which command attempt running on.
    start_time: command attempt execution start time.
    end_time: command attempt execution stop time.
    create_time: time when the command attempt was created.
    update_time: time when the command attempt was last updated.
    status: command attempt status.
    error: error message of the command attempt if it has error.
    summary: a summary of the command attempt.
    total_test_count: total test count in the command attempt.
    failed_test_count: failed test count in the command attempt.
    passed_test_count: passed test count in the command attempt.
    failed_test_run_count: failed test run count in the command attempt.
    device_lost_detected: device lost detected in the command attempt.
    error_reason: a error reason of the error message.
    error_type: a error type of the error reason.
    last_event_time: time when the last TF event arrivaled.
    invocation_status: invocation status.
    device_serials: a list of devices the command uses.
    plugin_data: the plugin data.
    run_index: run index from [0, run_count). The (run_index, attempt_index)
      tuple should be unique for a given command.
    attempt_index: attempt index. The (run_index, attempt_index) tuple should be
      unique for a given command.
  """
  command_id = ndb.StringProperty()
  task_id = ndb.StringProperty()
  attempt_id = ndb.StringProperty()
  state = ndb.EnumProperty(common.CommandState,
                           default=common.CommandState.UNKNOWN)
  hostname = ndb.StringProperty()
  # TODO Deprecated.
  device_serial = ndb.StringProperty()
  start_time = ndb.DateTimeProperty()
  end_time = ndb.DateTimeProperty()
  create_time = ndb.DateTimeProperty(auto_now_add=True)
  update_time = ndb.DateTimeProperty(auto_now=True)
  status = ndb.StringProperty()
  error = ndb.TextProperty()
  summary = ndb.TextProperty()
  total_test_count = ndb.IntegerProperty()
  failed_test_count = ndb.IntegerProperty()
  passed_test_count = ndb.IntegerProperty()
  failed_test_run_count = ndb.IntegerProperty()
  device_lost_detected = ndb.IntegerProperty()
  error_reason = ndb.StringProperty()
  error_type = ndb.EnumProperty(
      common.CommandErrorType,
      default=common.CommandErrorType.UNKNOWN)
  last_event_time = ndb.DateTimeProperty()
  invocation_status = ndb.StructuredProperty(InvocationStatus)
  device_serials = ndb.StringProperty(repeated=True)
  plugin_data = ndb.JsonProperty()
  run_index = ndb.IntegerProperty()
  attempt_index = ndb.IntegerProperty()


@MessageConverter(CommandAttempt)
def CommandAttemptToMessage(command_attempt):
  _, request_id, _, command_id, _, attempt_id = command_attempt.key.flat()
  return api_messages.CommandAttemptMessage(
      request_id=request_id,
      command_id=command_id,
      attempt_id=attempt_id,
      task_id=command_attempt.task_id,
      state=command_attempt.state,
      hostname=command_attempt.hostname,
      device_serial=command_attempt.device_serial,
      start_time=command_attempt.start_time,
      end_time=command_attempt.end_time,
      status=command_attempt.status,
      error=command_attempt.error,
      summary=command_attempt.summary,
      total_test_count=command_attempt.total_test_count,
      failed_test_count=command_attempt.failed_test_count,
      passed_test_count=command_attempt.passed_test_count,
      failed_test_run_count=command_attempt.failed_test_run_count,
      create_time=command_attempt.create_time,
      update_time=command_attempt.update_time,
      device_serials=command_attempt.device_serials,
      run_index=command_attempt.run_index,
      attempt_index=command_attempt.attempt_index)


class Note(ndb.Model):
  """Note entity.

  The note can be attached to a cluster, a host, or a device.

  Attributes:
    user: Author's username.
    timestamp: A timestamp of when this note was last updated.
    message: Message of the note.
    offline_reason: The reason that a cluster/host/device get offline.
    recovery_action: The recovery action.
    type: The type of note -> common.NoteType
    cluster_id: The cluster id, if the note is attached to a cluster.
    hostname: The hostname, if the note is attached to a host.
    device_serial: The device serial, if the note is attached to a device.
  """
  user = ndb.StringProperty()
  timestamp = ndb.DateTimeProperty()
  message = ndb.TextProperty()
  offline_reason = ndb.StringProperty()
  recovery_action = ndb.StringProperty()
  type = ndb.EnumProperty(common.NoteType)
  cluster_id = ndb.StringProperty()
  hostname = ndb.StringProperty()
  device_serial = ndb.StringProperty()


@MessageConverter(Note)
def NoteToMessage(note_entity):
  if note_entity.key:
    note_entity_id = str(note_entity.key.id())
  else:
    note_entity_id = None
  return api_messages.Note(
      id=note_entity_id,
      user=note_entity.user,
      timestamp=note_entity.timestamp,
      message=note_entity.message,
      offline_reason=note_entity.offline_reason,
      recovery_action=note_entity.recovery_action,
      type=note_entity.type,
      cluster_id=note_entity.cluster_id,
      hostname=note_entity.hostname,
      device_serial=note_entity.device_serial)


class ClusterNote(ndb.Model):
  """Cluster note entity.

  Attributes:
    cluster: Cluster ID
    note: A note for this cluster.
  """
  cluster = ndb.StringProperty()
  note = ndb.StructuredProperty(Note)


class HostNote(ndb.Model):
  """Host note entity.

  Attributes:
    hostname: Hostname.
    note: A note for this host.
  """
  hostname = ndb.StringProperty()
  note = ndb.StructuredProperty(Note)


@MessageConverter(HostNote)
def HostNoteToMessage(entity):
  return api_messages.HostNote(
      id=str(entity.key.id()),
      hostname=entity.hostname,
      user=entity.note.user,
      update_timestamp=entity.note.timestamp,
      offline_reason=entity.note.offline_reason,
      recovery_action=entity.note.recovery_action,
      message=entity.note.message)


class DeviceNote(ndb.Model):
  """Device note entity.

  Attributes:
    device_serial: Device serial.
    note: A note for this device.
  """
  device_serial = ndb.StringProperty()
  note = ndb.StructuredProperty(Note)


@MessageConverter(DeviceNote)
def DeviceNoteToMessage(entity):
  return api_messages.DeviceNote(
      id=str(entity.key.id()),
      device_serial=entity.device_serial,
      user=entity.note.user,
      update_timestamp=entity.note.timestamp,
      offline_reason=entity.note.offline_reason,
      recovery_action=entity.note.recovery_action,
      message=entity.note.message)


class PredefinedMessage(ndb.Model):
  """Predefined message entity.

  Attributes:
    lab_name: string, the lab name.
    type: enum, the type of the predefined message.
    content: str, the predefined message content.
    create_timestamp: datetime, time the message is created.
    used_count: int, how many times the message is used.
  """
  lab_name = ndb.StringProperty(required=True)
  type = ndb.EnumProperty(common.PredefinedMessageType, required=True)
  content = ndb.StringProperty(required=True)
  create_timestamp = ndb.DateTimeProperty()
  used_count = ndb.IntegerProperty(default=0)


@MessageConverter(PredefinedMessage)
def PredefinedMessageToMessage(entity):
  return api_messages.PredefinedMessage(
      id=entity.key.id(),
      lab_name=entity.lab_name,
      type=entity.type,
      content=entity.content,
      create_timestamp=entity.create_timestamp,
      used_count=entity.used_count)


class HostConfig(ndb.Model):
  """A host config entity.

  Attributes:
    hostname: a string of a host name.
    tf_global_config_path: a string of the global path of host config xml file.
    host_login_name: login name to for the host
    update_time: the time the config is update.
  """
  hostname = ndb.StringProperty()
  tf_global_config_path = ndb.StringProperty()
  host_login_name = ndb.StringProperty()
  update_time = ndb.DateTimeProperty(auto_now=True)

  @classmethod
  def FromMessage(cls, msg):
    return cls(
        id=msg.hostname,
        hostname=msg.hostname,
        tf_global_config_path=msg.tf_global_config_path,
        host_login_name=msg.host_login_name)


@MessageConverter(HostConfig)
def HostConfigToMessage(host_config_entity):
  """Convert host_config to host config api message."""
  if host_config_entity:
    return api_messages.HostConfig(
        hostname=host_config_entity.hostname,
        tf_global_config_path=host_config_entity.tf_global_config_path,
        host_login_name=host_config_entity.host_login_name)


class ClusterConfig(ndb.Model):
  """A cluster config entity.

  Attributes:
    cluster_name: a string of cluster name.
    host_login_name: a string of the user name of the cluster.
    owners: a list of owners of the cluster.
    tf_global_config_path: a string of the global path of clsuter configs.
    update_time: the time the config is update.
  """
  cluster_name = ndb.StringProperty()
  host_login_name = ndb.StringProperty()
  owners = ndb.StringProperty(repeated=True)
  tf_global_config_path = ndb.StringProperty()
  update_time = ndb.DateTimeProperty(auto_now=True)

  @classmethod
  def FromMessage(cls, msg):
    return cls(
        id=msg.cluster_name,
        cluster_name=msg.cluster_name,
        host_login_name=msg.host_login_name,
        owners=list(msg.owners),
        tf_global_config_path=msg.tf_global_config_path)


class LabConfig(ndb.Model):
  """A lab config entity.

  Attributes:
    lab_name: a string of cluster name.
    owners: a list of owners of the lab.
    update_time: the time the config is update.
  """
  lab_name = ndb.StringProperty()
  owners = ndb.StringProperty(repeated=True)
  update_time = ndb.DateTimeProperty(auto_now=True)

  @classmethod
  def FromMessage(cls, msg):
    return cls(
        id=msg.lab_name,
        lab_name=msg.lab_name,
        owners=list(msg.owners))


class ClusterInfo(ndb.Expando):
  """Cluster information entity. Key should be cluster name.

  Attributes:
    cluster: clsuter name
    total_devices: total devices count
    offline_devices: offline device count
    available_devices: available devices count
    allocated_devices: allocated devices count
    device_count_timestamp: time when the device counts were calculated
  """
  cluster = ndb.StringProperty()
  total_devices = ndb.IntegerProperty(default=0)
  offline_devices = ndb.IntegerProperty(default=0)
  available_devices = ndb.IntegerProperty(default=0)
  allocated_devices = ndb.IntegerProperty(default=0)
  # Time when the device counts were calculated and persisted
  device_count_timestamp = ndb.DateTimeProperty()


class DeviceCountSummary(ndb.Model):
  """Device count for host by run target.

  Attributes:
    run_target: a string of run_target.
    total: total devices count
    offline: offline device count
    available: available devices count
    allocated: allocated devices count
    timestamp: time when the counts were calculated
  """
  run_target = ndb.StringProperty()
  total = ndb.IntegerProperty(default=0)
  offline = ndb.IntegerProperty(default=0)
  available = ndb.IntegerProperty(default=0)
  allocated = ndb.IntegerProperty(default=0)
  timestamp = ndb.DateTimeProperty()


@MessageConverter(DeviceCountSummary)
def DeviceCountSummaryToMessage(device_count):
  """Convert a DeviceCountSummary entity into a DeviceCountSummary Message."""
  return api_messages.DeviceCountSummary(
      run_target=device_count.run_target,
      total=device_count.total,
      offline=device_count.offline,
      available=device_count.available,
      allocated=device_count.allocated,
      timestamp=device_count.timestamp)


def _FlatExtraInfo(entity):
  """Transform extra_info to a list.

  Args:
    entity: Device or host entity.
  Returns:
    A list of string. string format is 'key:value'
  """
  flated_extra_info = []
  if entity.extra_info is not None:
    extra_info_dict = dict(entity.extra_info)
    for key, value in extra_info_dict.items():
      flated_extra_info.append('%s:%s' % (key, value))
  return flated_extra_info


def _IsBadHost(host):
  """Is the host a bad host or not.

  Args:
    host: Host entity.
  Returns:
    true if it's a bad host, otherwise false.
  """
  if host.host_state == api_messages.HostState.GONE:
    return True
  for device_count_summary in host.device_count_summaries or []:
    if device_count_summary.offline:
      return True
  return False


class HostInfo(ndb.Expando):
  """Host information entity. Key should be hostname.

  Attributes:
    hostname: hostname
    lab_name: the name of the lab the host belong to
    physical_cluster: host's physical cluster
    host_group: a group of host using the same host config.
    clusters: all clusters this host belong to
    pools: pools of devices to manage device resources.
    test_runner: test runner
    test_runner_version: test runner version
    timestamp: the timestamp the host is updated.
    total_devices: total devices count
    offline_devices: offline device count
    available_devices: available devices count
    allocated_devices: allocated devices count
    device_count_timestamp: time when the device counts were calculated
    hidden: is the device hidden or not
    extra_info: extra info for the host
    host_state: the state of the host
    tf_start_time: the start time of the host, in seconds.
    assignee: the user who will recover this host.
    device_count_summaries: device count by run target under the host.
    is_bad: is the host bad or not. Right now bad means host offline or there
      are device offline on the host.
    last_recovery_time: last time the host was recovered.
    flated_extra_info: flated extra info for the host.
    recovery_state: recovery state for the host, e.g. assigned, fixed, verified.
  """
  hostname = ndb.StringProperty()
  lab_name = ndb.StringProperty()
  # TODO: deprecate physical_cluster, use host_group.
  physical_cluster = ndb.StringProperty()
  host_group = ndb.StringProperty()
  # The physical cluster and next_cluster_ids.
  # TODO: deprecate clusters, use pools.
  clusters = ndb.StringProperty(repeated=True)
  pools = ndb.StringProperty(repeated=True)
  test_runner = ndb.StringProperty()
  test_runner_version = ndb.StringProperty()
  # TODO: change timestamp to last_event_time.
  timestamp = ndb.DateTimeProperty(auto_now_add=True)
  hidden = ndb.BooleanProperty(default=False)
  host_state = ndb.EnumProperty(
      api_messages.HostState, default=api_messages.HostState.UNKNOWN)
  # extra_info is an object to store extra information related to a host.
  extra_info = ndb.JsonProperty()
  assignee = ndb.StringProperty()
  device_count_summaries = ndb.LocalStructuredProperty(
      DeviceCountSummary, repeated=True)
  is_bad = ndb.ComputedProperty(_IsBadHost)
  # TODO: remove the following fields once
  # we move the fields into extra_info.
  tf_start_time = ndb.DateTimeProperty()
  total_devices = ndb.IntegerProperty(default=0)
  offline_devices = ndb.IntegerProperty(default=0)
  available_devices = ndb.IntegerProperty(default=0)
  allocated_devices = ndb.IntegerProperty(default=0)
  # Time when the device counts were calculated and persisted
  device_count_timestamp = ndb.DateTimeProperty()
  last_recovery_time = ndb.DateTimeProperty()
  flated_extra_info = ndb.ComputedProperty(_FlatExtraInfo, repeated=True)
  recovery_state = ndb.StringProperty()


@MessageConverter(HostInfo)
def HostInfoToMessage(host_info_entity, devices=None):
  """Convert a HostInfo entity into a HostInfoMessage."""
  device_infos = [ToMessage(device) for device in devices or []]
  next_cluster_ids = list(host_info_entity.clusters or [])
  device_count_summaries = [
      ToMessage(c) for c in host_info_entity.device_count_summaries or []]
  if (host_info_entity.physical_cluster and
      host_info_entity.physical_cluster in next_cluster_ids):
    next_cluster_ids.remove(host_info_entity.physical_cluster)
  if host_info_entity.host_state:
    host_state = host_info_entity.host_state.name
  else:
    host_state = 'UNKNOWN'
  return api_messages.HostInfo(
      hostname=host_info_entity.hostname,
      lab_name=host_info_entity.lab_name,
      # TODO: deprecate physical_cluster, use host_group.
      cluster=host_info_entity.physical_cluster,
      host_group=host_info_entity.host_group,
      # TODO: deprecated test runner and test runner version.
      test_runner=host_info_entity.test_runner,
      test_runner_version=host_info_entity.test_runner_version,
      test_harness=host_info_entity.test_runner,
      test_harness_version=host_info_entity.test_runner_version,
      timestamp=host_info_entity.timestamp,
      total_devices=host_info_entity.total_devices,
      offline_devices=host_info_entity.offline_devices,
      available_devices=host_info_entity.available_devices,
      allocated_devices=host_info_entity.allocated_devices,
      device_count_timestamp=host_info_entity.device_count_timestamp,
      hidden=host_info_entity.hidden,
      extra_info=api_messages.MapToKeyValuePairMessages(
          host_info_entity.extra_info),
      device_infos=device_infos,
      # TODO: deprecate clusters, use pools.
      next_cluster_ids=next_cluster_ids,
      pools=host_info_entity.pools,
      tf_start_time=host_info_entity.tf_start_time,
      host_state=host_state,
      assignee=host_info_entity.assignee,
      device_count_summaries=device_count_summaries,
      is_bad=host_info_entity.is_bad,
      last_recovery_time=host_info_entity.last_recovery_time,
      flated_extra_info=host_info_entity.flated_extra_info,
      recovery_state=host_info_entity.recovery_state)


class HostInfoHistory(HostInfo):
  """HostInfo history."""


@MessageConverter(HostInfoHistory)
def HostInfoHistoryToMessage(host_info_history):
  """Convert a HostInfoHistory entity into a HostInfoHistory Message."""
  return HostInfoToMessage(host_info_history)


class HostStateHistory(ndb.Model):
  """Host state history, key is (hostname + timestamp).

  Attreibutes:
    hostname: hostname.
    timestamp: timestamp the state hiestory added.
    state: host state, see HostState in api message.
  """
  hostname = ndb.StringProperty()
  timestamp = ndb.DateTimeProperty()
  state = ndb.EnumProperty(api_messages.HostState)


@MessageConverter(HostStateHistory)
def HostStateHistoryToMessage(host_state_history_entity):
  return api_messages.HostStateHistory(
      hostname=host_state_history_entity.hostname,
      timestamp=host_state_history_entity.timestamp,
      state=host_state_history_entity.state.name)


class HostSync(ndb.Model):
  """Keep track of task that sync host's status.

  We only want 1 task to track host's status. Since taskname are not consistent
  for different libraries, we generate unique id and track host sync tasks with
  the unique id.
  The key will be the hostname.

  Attributes:
    taskname: task name that track host's status.
    update_timestamp: update timestamp.
    host_sync_id: unique id for a sync.
  """
  taskname = ndb.StringProperty()
  update_timestamp = ndb.DateTimeProperty()
  host_sync_id = ndb.StringProperty()


class DeviceInfo(ndb.Expando):
  """Device information entity, Key should be the device serial.

  Attributes:
    device_serial: device serial
    run_target: device run target
    state: device state
    test_harness: test harness
    lab_name: the name of the lab the device belong to
    physical_cluster: physical cluster
    host_group: a group of host using the same host config.
    clusters: all clusters
    pools: pools of devices to manage device resources.
    hostname: hostname
    timestamp: update timestamp
    hidden: device is hidden or not
    device_type: device type
    extra_info: extra info for device
    sdk_version: sdk version
    product: device product
    build_id: device build id
    product_variant: device product variant
    battery_level: device battery_level
    mac_address: device mac address
    last_known_build_id: last known build id
    last_known_product: last known product
    last_known_product_variant: last known product variant
    flated_extra_info: flated extra info for the device
    recovery_state: recovery state for the host, e.g. assigned, fixed, verified.
  """
  device_serial = ndb.StringProperty()
  run_target = ndb.StringProperty()
  state = ndb.StringProperty()
  test_harness = ndb.StringProperty()
  lab_name = ndb.StringProperty()
  # TODO: deprecate physical_cluster, use host_group.
  physical_cluster = ndb.StringProperty()
  host_group = ndb.StringProperty()
  # TODO: deprecate clusters, use pools.
  clusters = ndb.StringProperty(repeated=True)
  pools = ndb.StringProperty(repeated=True)
  hostname = ndb.StringProperty()
  timestamp = ndb.DateTimeProperty()
  hidden = ndb.BooleanProperty(default=False)
  device_type = ndb.EnumProperty(api_messages.DeviceTypeMessage)
  extra_info = ndb.JsonProperty()

  # TODO: remove the following fields once
  # we move the fields into extra_info.
  product = ndb.StringProperty()
  build_id = ndb.StringProperty()
  product_variant = ndb.StringProperty()
  sdk_version = ndb.StringProperty()
  battery_level = ndb.StringProperty()
  mac_address = ndb.StringProperty()
  last_known_build_id = ndb.StringProperty()
  last_known_product = ndb.StringProperty()
  last_known_product_variant = ndb.StringProperty()
  flated_extra_info = ndb.ComputedProperty(_FlatExtraInfo, repeated=True)
  recovery_state = ndb.StringProperty()


@MessageConverter(DeviceInfo)
def DeviceInfoToMessage(device_info_entity):
  """Convert a Device entity into a DeviceInfo message."""
  extra_info = device_info_entity.extra_info or {}
  if device_info_entity.device_type:
    device_type = api_messages.DeviceTypeMessage(device_info_entity.device_type)
  else:
    device_type = None
  return api_messages.DeviceInfo(
      device_serial=device_info_entity.device_serial,
      lab_name=device_info_entity.lab_name,
      cluster=device_info_entity.physical_cluster,
      # TODO: deprecate physical_cluster, use host_group.
      host_group=device_info_entity.host_group,
      hostname=device_info_entity.hostname,
      run_target=device_info_entity.run_target,
      # TODO: deprecate clusters, use pools.
      pools=device_info_entity.pools,
      build_id=device_info_entity.build_id,
      product=device_info_entity.product,
      product_variant=device_info_entity.product_variant,
      sdk_version=device_info_entity.sdk_version,
      state=device_info_entity.state,
      timestamp=device_info_entity.timestamp,
      hidden=device_info_entity.hidden,
      battery_level=device_info_entity.battery_level,
      mac_address=device_info_entity.mac_address,
      sim_state=extra_info.get('sim_state'),
      sim_operator=extra_info.get('sim_operator'),
      device_type=device_type,
      extra_info=api_messages.MapToKeyValuePairMessages(
          device_info_entity.extra_info),
      test_harness=device_info_entity.test_harness,
      recovery_state=device_info_entity.recovery_state)


class DeviceInfoHistory(DeviceInfo):
  """DeviceInfo history."""


@MessageConverter(DeviceInfoHistory)
def DeviceInfoHistoryToMessage(device_info_history):
  """Convert a DeviceInfoHistory entity into a DeviceInfo Message."""
  return DeviceInfoToMessage(device_info_history)


class DeviceStateHistory(ndb.Model):
  """Device state history entity. Its ID is auto generated.

  Keeps track of the state changes of a device.
  """
  device_serial = ndb.StringProperty()
  timestamp = ndb.DateTimeProperty()
  state = ndb.StringProperty()


@MessageConverter(DeviceStateHistory)
def DeviceStateHistoryToMessage(state_history_entity):
  return api_messages.DeviceStateHistory(
      timestamp=state_history_entity.timestamp,
      state=state_history_entity.state)


# TODO: A delimeter should exist after the location to avoid potential
# naming conflicts where 2 different locations have a similar prefix. Eg.:
# A prefix of atp-us-mtv-20 would collide with cluster names such as
# atp-us-mtv-2000 or atp-us-mtv-2011
class ReportEmailConfig(ndb.Model):
  """Eamil configuration for cluster monitoring."""
  cluster_prefix = ndb.StringProperty()
  recipients = ndb.StringProperty(repeated=True)


class LabInfo(ndb.Expando):
  """Lab information entity. Key should be lab name.

  Attributes:
    lab_name: the name of the lab.
    timestamp: the timestamp the entity gets updated.
  """
  lab_name = ndb.StringProperty()
  update_timestamp = ndb.DateTimeProperty(auto_now_add=True)


@MessageConverter(LabInfo)
def LabInfoToMessage(lab_info_entity, lab_config_entity=None):
  owners = lab_config_entity.owners if lab_config_entity else []
  return api_messages.LabInfo(
      lab_name=lab_info_entity.lab_name,
      update_timestamp=lab_info_entity.update_timestamp,
      owners=owners)


class SnapshotJobResult(ndb.Model):
  """Status of a device info snapshot for a given report date."""
  report_date = ndb.DateTimeProperty()
  filename = ndb.StringProperty()
  timestamp = ndb.DateTimeProperty()

  @classmethod
  def FromDate(cls, date):
    """Create a SnapshotJobResult for the given date."""
    # Datastore does not support datetime.date objects so they need to be
    # converted to datetime.datetime
    report_date = datetime.datetime.combine(date, ZERO_TIME)
    return cls(report_date=report_date)

  @classmethod
  def GetByReportDate(cls, date):
    """Get the SnapshotJobResult for the given date."""
    report_date = datetime.datetime.combine(date, ZERO_TIME)
    return cls.query().filter(cls.report_date == report_date).get()


class RunTarget(ndb.Model):
  """RunTarget model.

  The run target will be embedded in Group. It is stored within Group.

  Attributes:
    name: run target's name
  """
  name = ndb.StringProperty()


class Group(ndb.Model):
  """Group model.

  The group will be embedded in Host. It is stored within Host

  Attributes:
    run_targets: the run_targets in the group.
  """
  run_targets = ndb.LocalStructuredProperty(RunTarget, repeated=True)


class Host(ndb.Model):
  """Host entity.

  The host will be embedded in TestBench. It is stored within TestBench.

  Attributes:
    groups: the groups in the host.
  """
  groups = ndb.LocalStructuredProperty(Group, repeated=True)


class TestBench(ndb.Model):
  """TestBench model.

  This TestBench is a ndb model and it's also the object we use
  inside ATP.

  Attributes:
    cluster: cluster id for the test bench
    host: host structure for the test bench
  """
  cluster = ndb.StringProperty()
  host = ndb.LocalStructuredProperty(Host)


def _ListRunTargets(test_bench):
  """List the run targets in the test bench.

  Args:
    test_bench: a test bench
  Returns:
    a sorted list of run_target names
  """
  groups = test_bench.host.groups
  run_targets = []
  for group in groups:
    for run_target in group.run_targets:
      run_targets.append(run_target.name)
  return sorted(run_targets)


class CommandTask(ndb.Model):
  """CommandTask model.

  Attributes:
    request_id: request id
    command_id: command id
    task_id: task id, it's unique and used as the key of the entity
    lease_count: how many time the task has been leased
    command_line: command line
    run_count: run count
    run_index: run index from [0, run_count). The (run_index, attempt_index)
      tuple should be unique for a given command.
    attempt_index: attempt index. The (run_index, attempt_index) tuple should be
      unique for a given command.
    shard_count: shard count
    shard_index: shard index
    test_bench: test_bench that the task requires
    cluster: cluster to run the task
    run_targets: all run_target names in the test_bench
    priority: the priority of the task
    leasable: the command task is leasable or not
    expiration_timestamp: the task's expiration timestamp
    lease_expiration_timestamp: the task's lease expiration timestamp
    create_timestamp: create timestamp
    update_timestamp: update timestamp
    request_type: a request type
    plugin_data: the plugin data.
  """
  request_id = ndb.StringProperty()
  command_id = ndb.StringProperty()
  task_id = ndb.StringProperty()
  lease_count = ndb.IntegerProperty()
  # StringProperty has a limit of 1500 bytes.
  # There are command lines larger than 1500 bytes.
  command_line = ndb.TextProperty()
  run_count = ndb.IntegerProperty()
  run_index = ndb.IntegerProperty()
  attempt_index = ndb.IntegerProperty()
  shard_count = ndb.IntegerProperty()
  shard_index = ndb.IntegerProperty()
  test_bench = ndb.LocalStructuredProperty(TestBench)
  # cluster is the same cluster in test_bench. This field is used for query.
  cluster = ndb.ComputedProperty(lambda self: self.test_bench.cluster)
  # run targets are all run targets in the test bench.
  # Datastore doesn't support query based on LocalStructuredProperty,
  # so we need to add this field to support querying based on
  # run targets.
  run_targets = ndb.ComputedProperty(
      lambda self: _ListRunTargets(self.test_bench), repeated=True)
  priority = ndb.IntegerProperty()
  # initially we want to use expiration timestamp to differentiate leasable task
  # or leased task.
  # Based on
  # https://cloud.google.com/appengine/docs/standard/java/datastore/query-restrictions
  # datastore doesn't support inequality on two properties and the property used
  # in inequality need to be sorted first. We need to sort on priority first and
  # inequality for expiration timestamp, which is not feasible.
  leasable = ndb.BooleanProperty()
  expiration_timestamp = ndb.DateTimeProperty()
  lease_expiration_timestamp = ndb.DateTimeProperty()
  create_timestamp = ndb.DateTimeProperty(auto_now_add=True)
  update_timestamp = ndb.DateTimeProperty(auto_now=True)
  request_type = ndb.EnumProperty(api_messages.RequestType)
  plugin_data = ndb.JsonProperty()


class CommandErrorConfigMapping(ndb.Model):
  """Request Error config model.

  Attributes:
    error_message: error_message string
    reason: standard error reason string
    type_code: enum error type code
  """
  error_message = ndb.StringProperty(required=True)
  reason = ndb.StringProperty()
  type_code = ndb.EnumProperty(common.CommandErrorType)


class DeviceBlocklist(ndb.Model):
  """Blocklist to block devices from running tests."""
  lab_name = ndb.StringProperty()
  # TODO: Add other fields, e.g. cluster, hostname, etc.
  create_timestamp = ndb.DateTimeProperty(auto_now_add=True)
  note = ndb.TextProperty()
  user = ndb.StringProperty()


@MessageConverter(DeviceBlocklist)
def DeviceBlocklistToMessage(device_blocklist):
  """Convert a DeviceBlocklist entity into a DeviceBlocklistMessage."""
  # integer_id() will return None if a user manually sets a string ID.
  key_id = device_blocklist.key.integer_id() if device_blocklist.key else 0
  return api_messages.DeviceBlocklistMessage(
      key_id=key_id,
      lab_name=device_blocklist.lab_name,
      create_timestamp=device_blocklist.create_timestamp,
      note=device_blocklist.note,
      user=device_blocklist.user)


class DeviceBlocklistArchive(ndb.Model):
  """Blocklist history."""
  device_blocklist = ndb.StructuredProperty(DeviceBlocklist, required=True)
  start_timestamp = ndb.DateTimeProperty(required=True)
  end_timestamp = ndb.DateTimeProperty(default=datetime.datetime.utcnow())
  archived_by = ndb.StringProperty(required=True)

  @classmethod
  def FromDeviceBlocklist(cls, device_blocklist, archived_by):
    return cls(device_blocklist=device_blocklist,
               start_timestamp=device_blocklist.create_timestamp,
               archived_by=archived_by)


@MessageConverter(DeviceBlocklistArchive)
def DeviceBlocklistArchiveToMessage(device_blocklist_archive):
  """Convert a DeviceBlocklistArchive entity into a message."""
  return api_messages.DeviceBlocklistArchiveMessage(
      device_blocklist=ToMessage(device_blocklist_archive.device_blocklist),
      start_timestamp=device_blocklist_archive.start_timestamp,
      end_timestamp=device_blocklist_archive.end_timestamp,
      archived_by=device_blocklist_archive.archived_by)
