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
import json
import re

import dateutil.parser
import six
from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster.util import ndb_shim as ndb
from tradefed_cluster.util import ndb_util



# Constant to hold a time of 0 (0 hours, 0 minutes, 0 seconds)
ZERO_TIME = datetime.time()

# A dispatch dictionary mapping entity classes to message converter functions.
_CONVERTER_DISPATCH_DICT = {}

# Index all the extra info will trigger b/181262288:
# "The value of property "flated_extra_info" is longer than 1500 bytes." error.
_HOST_EXTRA_INFO_INDEX_ALLOWLIST = ('host_ip', 'label')
_DEVICE_EXTRA_INFO_INDEX_ALLOWLIST = ('product', 'sim_state', 'mac_address')
_EXTRA_INFO_INDEXED_VALUE_SIZE = 80
_ATTRIBUTE_REQUIREMENT_PATTERN = re.compile(
    r'(?P<name>[^><=]+)(?P<operator>=|>|>=|<|<=)(?P<value>[^><=]+)')


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


class TestResourceParameters(ndb.Model):
  """Repeated properties of TestResource.

  Because TestResource is a StructuredProperty of TestContext, it cannot
  directly contain repeated properties. The test resource model uses this class
  to wrap the repeated properties in a LocalStructuredProperty.

  Attribtues:
    decompress_files: the files to be decompressed from the downloaded file.
  """
  decompress_files = ndb.StringProperty(repeated=True)

  @classmethod
  def FromMessage(cls, msg):
    return TestResourceParameters(decompress_files=msg.decompress_files)


@MessageConverter(TestResourceParameters)
def TestResourceParametersToMessage(entity):
  """Converts a TestResourceParameters entity to a message."""
  return api_messages.TestResourceParameters(
      decompress_files=entity.decompress_files)


class TestResource(ndb.Model):
  """A test resource entity.

  Attributes:
    url: a test resource download url.
    name: an expected filename in a test working directory.
    path: an expected path in a test working directory.
    decompress: whether the host should decompress the downloaded file.
    decompress_dir: the directory where the host decompresses the file.
    mount_zip: whether to mount a zip file.
    params: test resource parameters.
  """
  url = ndb.StringProperty()
  name = ndb.StringProperty()
  path = ndb.StringProperty()
  decompress = ndb.BooleanProperty()
  decompress_dir = ndb.StringProperty()
  mount_zip = ndb.BooleanProperty()
  params = ndb.LocalStructuredProperty(TestResourceParameters)

  def CopyFrom(self, obj):
    """Copy values from another TestResource object.

    Args:
      obj: a TestResource object to copy from.
    """
    self.populate(**obj.to_dict())
    if obj.params is None:
      self.params = None
    else:
      self.params = TestResourceParameters()
      self.params.populate(**obj.params.to_dict())

  @classmethod
  def FromMessage(cls, msg):
    return cls(
        url=msg.url,
        name=msg.name,
        path=msg.path,
        decompress=msg.decompress,
        decompress_dir=msg.decompress_dir,
        mount_zip=msg.mount_zip,
        params=(
            TestResourceParameters.FromMessage(msg.params)
            if msg.params else None))


@MessageConverter(TestResource)
def TestResourceToMessage(entity):
  """Converts a TestResource entity to a message."""
  return api_messages.TestResource(
      name=entity.name,
      url=entity.url,
      path=entity.path,
      decompress=entity.decompress,
      decompress_dir=entity.decompress_dir,
      mount_zip=entity.mount_zip,
      params=ToMessage(entity.params) if entity.params else None)


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
    if msg is None:
      return None
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
    test_resources = [ToMessage(r) for r in entity.test_resources]
  return api_messages.TestContext(
      command_line=entity.command_line,
      env_vars=env_vars,
      test_resources=test_resources)


class Attribute(ndb.Model):
  """Device attribute requirement.

  Attributes:
    name: attribute's name.
    value: attribute's value.
    operator: attribute's operator
  """
  name = ndb.StringProperty()
  value = ndb.StringProperty()
  operator = ndb.StringProperty()

  @classmethod
  def FromMessage(cls, msg):
    return Attribute(name=msg.name, value=msg.value, operator=msg.operator)

  @classmethod
  def FromJson(cls, attribute_json):
    return Attribute(
        name=attribute_json[common.TestBenchKey.ATTRIBUTE_NAME],
        value=attribute_json[common.TestBenchKey.ATTRIBUTE_VALUE],
        operator=attribute_json.get(common.TestBenchKey.ATTRIBUTE_OPERATOR))

  @classmethod
  def FromString(cls, attribute):
    """Parse the attribute requirement.

    Args:
      attribute: a string represents attribute requirement.
    Returns:
      a Attribute object
    """
    m = _ATTRIBUTE_REQUIREMENT_PATTERN.match(attribute)
    if not m:
      raise ValueError(
          "Only 'name[=|>|>=|<|<=]value' format attribute is supported. "
          "%s is not supported." % attribute)
    name = m.group(common.TestBenchKey.ATTRIBUTE_NAME)
    value = m.group(common.TestBenchKey.ATTRIBUTE_VALUE)
    operator = m.group(common.TestBenchKey.ATTRIBUTE_OPERATOR)
    if name in common.NUMBER_DEVICE_ATTRIBUTES:
      if common.ParseFloat(value) is None:
        raise ValueError(
            "%s can not compare to a non-number value '%s'" % (name, value))
    return Attribute(name=name, value=value, operator=operator)


@MessageConverter(Attribute)
def AttributeToMessage(entity):
  """Attribute entity to api_messages.DeviceAttributeRequirement."""
  return api_messages.DeviceAttributeRequirement(
      name=entity.name,
      value=entity.value,
      operator=entity.operator)


class RunTarget(ndb.Model):
  """RunTarget model.

  The run target will be embedded in Group. It is stored within Group.

  Attributes:
    name: run target's name
    device_attributes: other than run target what device attribute the test task
        requires.
  """
  name = ndb.StringProperty()
  device_attributes = ndb.LocalStructuredProperty(Attribute, repeated=True)

  @classmethod
  def FromMessage(cls, msg):
    return RunTarget(
        name=msg.name,
        device_attributes=[
            Attribute.FromMessage(a) for a in msg.device_attributes])

  @classmethod
  def FromJson(cls, run_target_json):
    return RunTarget(
        name=run_target_json.get(common.TestBenchKey.RUN_TARGET_NAME),
        device_attributes=[
            Attribute.FromJson(a) for a in run_target_json.get(
                common.TestBenchKey.DEVICE_ATTRIBUTES, [])])

  @classmethod
  def FromLegacyString(cls, run_target_str, test_bench_attributes):
    return RunTarget(
        name=run_target_str,
        device_attributes=[
            Attribute.FromString(a)
            for a in (test_bench_attributes or ())])


@MessageConverter(RunTarget)
def RunTargetToMessage(entity):
  """RunTarget entity to api_messages.RunTargetRequirement."""
  return api_messages.RunTargetRequirement(
      name=entity.name,
      device_attributes=[ToMessage(a) for a in entity.device_attributes])


class Group(ndb.Model):
  """Group model.

  The group will be embedded in Host. It is stored within Host

  Attributes:
    run_targets: the run_targets in the group.
  """
  run_targets = ndb.LocalStructuredProperty(RunTarget, repeated=True)

  @classmethod
  def FromMessage(cls, msg):
    return Group(
        run_targets=[RunTarget.FromMessage(rt) for rt in msg.run_targets])

  @classmethod
  def FromJson(cls, group_json):
    return  Group(
        run_targets=[RunTarget.FromJson(rt) for rt in group_json.get(
            common.TestBenchKey.RUN_TARGETS)])

  @classmethod
  def FromLegacyString(cls, group_str, test_bench_attributes):
    return Group(
        run_targets=[RunTarget.FromLegacyString(rt, test_bench_attributes)
                     for rt in group_str.split(',')])


@MessageConverter(Group)
def GroupToMessage(entity):
  """Group entity to api_messages.GroupRequirement."""
  return api_messages.GroupRequirement(
      run_targets=[ToMessage(rt) for rt in entity.run_targets])


class Host(ndb.Model):
  """Host entity.

  The host will be embedded in TestBench. It is stored within TestBench.

  Attributes:
    groups: the groups in the host.
  """
  groups = ndb.LocalStructuredProperty(Group, repeated=True)

  @classmethod
  def FromMessage(cls, msg):
    return Host(
        groups=[Group.FromMessage(group) for group in msg.groups])

  @classmethod
  def FromJson(cls, host_json):
    return Host(
        groups=[Group.FromJson(group)
                for group in host_json.get(common.TestBenchKey.GROUPS, [])])

  @classmethod
  def FromLegacyString(cls, run_target, test_bench_attributes):
    return Host(
        groups=[Group.FromLegacyString(g, test_bench_attributes)
                for g in run_target.split(';')])


@MessageConverter(Host)
def HostToMessage(entity):
  """Host entity to api_messages.HostRequirement."""
  return api_messages.HostRequirement(
      groups=[ToMessage(g) for g in entity.groups])


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

  @classmethod
  def FromMessage(cls, msg):
    return TestBench(cluster=msg.cluster, host=Host.FromMessage(msg.host))

  @classmethod
  def FromJson(cls, test_bench_json, cluster):
    return TestBench(
        cluster=cluster,
        host=Host.FromJson(test_bench_json.get(common.TestBenchKey.HOST, {})))

  @classmethod
  def FromLegacyString(cls, run_target, cluster, test_bench_attributes=None):
    return TestBench(
        cluster=cluster,
        host=Host.FromLegacyString(
            run_target,
            test_bench_attributes=test_bench_attributes))


@MessageConverter(TestBench)
def TestBenchToMessage(entity):
  """TestBench entity to api_messages.TestBenchRequirement."""
  if not entity:
    return None
  return api_messages.TestBenchRequirement(
      cluster=entity.cluster, host=ToMessage(entity.host))


def _TestBenchToLegacyRunTarget(test_bench):
  """Transform a test bench to a legacy run target."""
  group_strs = []
  for group in test_bench.host.groups:
    group_strs.append(','.join(rt.name for rt in group.run_targets))
  return ';'.join(group_strs)


def BuildTestBench(
    cluster=None, run_target=None,
    test_bench_attributes=None,
    test_bench=None):
  """Build test bench object from given information.

    There are 3 types of input right now:
    1. cluster, legacy run target.
    2. cluster, json format run target.
    3. test bench object.
    Going forward we will keep maintaining 1, but we are going to
    deprecate 2. 3 will be used for complicated use cases.
    This is because of b/198413277, there is a limitation on the length
    of a field.
    We will still keep cluster and run target fields for querying
    (not for scheduling tests) and the run target will always be legacy format.
  Args:
    cluster: cluster to schedule the test to.
    run_target: a run target.
    test_bench_attributes: device attribute requirements.
    test_bench: a TestBenchRequirement message or TestBench entity
  Returns:
    test_bench object
  """
  if test_bench:
    if not isinstance(test_bench, TestBench):
      test_bench = TestBench.FromMessage(test_bench)
  else:
    run_target = run_target.strip()
    if not run_target.startswith('{'):
      test_bench = TestBench.FromLegacyString(
          run_target, cluster, test_bench_attributes)
    else:
      test_bench = TestBench.FromJson(
          json.loads(run_target), cluster)

  return test_bench


class CommandInfo(ndb.Model):
  """A command info."""
  name = ndb.StringProperty()
  command_line = ndb.TextProperty()
  cluster = ndb.StringProperty()
  run_target = ndb.StringProperty()
  run_count = ndb.IntegerProperty(default=1)
  shard_count = ndb.IntegerProperty(default=1)
  allow_partial_device_match = ndb.BooleanProperty(default=False)
  test_bench = ndb.LocalStructuredProperty(TestBench)

  @classmethod
  def FromMessage(cls, msg):
    if msg is None:
      return None
    test_bench = BuildTestBench(
        cluster=msg.cluster, run_target=msg.run_target,
        test_bench_attributes=msg.test_bench_attributes,
        test_bench=msg.test_bench)
    return cls(
        name=msg.name,
        command_line=msg.command_line,
        cluster=test_bench.cluster,
        run_target=_TestBenchToLegacyRunTarget(test_bench),
        run_count=msg.run_count,
        shard_count=msg.shard_count,
        allow_partial_device_match=msg.allow_partial_device_match,
        test_bench=test_bench)


@MessageConverter(CommandInfo)
def CommandInfoToMessage(entity):
  """Converts a CommandInfo entity to a message."""
  return api_messages.CommandInfo(
      name=entity.name,
      command_line=entity.command_line,
      cluster=entity.cluster,
      run_target=entity.run_target,
      run_count=entity.run_count,
      shard_count=entity.shard_count,
      allow_partial_device_match=entity.allow_partial_device_match,
      test_bench=ToMessage(entity.test_bench))


def _Request_AddCommandInfo(obj):    """Upgrade function for legacy Request objects."""
  obj.command_infos = [
      CommandInfo(
          command_line=obj.depr_command_line,
          cluster=obj.depr_cluster,
          run_target=obj.depr_run_target,
          run_count=obj.depr_run_count,
          shard_count=obj.depr_shard_count)
  ]


class Request(ndb_util.UpgradableModel):
  """A test request entity.

  Attributes:
    type: a request type.
    user: email of an user who made the request.
    command_infos: a list of command infos.
    priority: a priority value. Should be in range [0-1000].
    queue_timeout_seconds: a queue timeout in seconds. A request will time out
        if it stays in QUEUED state longer than a given timeout.
    cancel_reason: a machine readable enum cancel reason.
    max_retry_on_test_failures: the max number of retries on test failure per
        each command.
    prev_test_context: a previous test context.
    max_concurrent_tasks: the max number of concurrent tasks.

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
  command_infos = ndb.LocalStructuredProperty(
      CommandInfo, compressed=True, repeated=True)

  # priority should be an integer. The larger, the higher priority.
  # The lowest priority is 0, it's the default priority.
  priority = ndb.IntegerProperty()
  queue_timeout_seconds = ndb.IntegerProperty()
  cancel_reason = ndb.EnumProperty(common.CancelReason)
  max_retry_on_test_failures = ndb.IntegerProperty()
  prev_test_context = ndb.LocalStructuredProperty(TestContext)
  max_concurrent_tasks = ndb.IntegerProperty()

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

  # Deprecated fields
  depr_command_line = ndb.TextProperty('command_line')
  depr_cluster = ndb.StringProperty('cluster')
  depr_run_target = ndb.StringProperty('run_target')
  depr_run_count = ndb.IntegerProperty('run_count')
  depr_shard_count = ndb.IntegerProperty('shard_count')

  _upgrade_steps = [
      _Request_AddCommandInfo,
  ]


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
  first_command_info = (
      request.command_infos[0] if request.command_infos else CommandInfo())
  return api_messages.RequestMessage(
      id=request_id,
      type=request.type,
      user=request.user,
      command_infos=[ToMessage(obj) for obj in request.command_infos or []],
      max_retry_on_test_failures=request.max_retry_on_test_failures,
      prev_test_context=ToMessage(request.prev_test_context),
      max_concurrent_tasks=request.max_concurrent_tasks,
      state=request.state,
      start_time=request.start_time,
      end_time=request.end_time,
      create_time=request.create_time,
      update_time=request.update_time,
      command_attempts=[ToMessage(ca) for ca in command_attempts],
      commands=[ToMessage(command) for command in commands],
      cancel_message=request.cancel_message,
      cancel_reason=request.cancel_reason,
      command_line=first_command_info.command_line,
      cluster=first_command_info.cluster,
      run_target=first_command_info.run_target,
      run_count=first_command_info.run_count,
      shard_count=first_command_info.shard_count)


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
  invocation_timeout_millis = ndb.IntegerProperty()
  output_idle_timeout_millis = ndb.IntegerProperty()
  jvm_options = ndb.StringProperty(repeated=True)
  java_properties = ndb.JsonProperty()
  context_file_pattern = ndb.StringProperty()
  extra_context_files = ndb.StringProperty(repeated=True)
  retry_command_line = ndb.StringProperty()
  log_level = ndb.EnumProperty(common.LogLevel)
  tradefed_config_objects = ndb.LocalStructuredProperty(
      TradefedConfigObject, repeated=True)
  use_parallel_setup = ndb.BooleanProperty()

  @classmethod
  def FromMessage(cls, msg):
    return cls(
        env_vars={p.key: p.value for p in msg.env_vars},
        setup_scripts=msg.setup_scripts,
        output_file_upload_url=msg.output_file_upload_url,
        output_file_patterns=msg.output_file_patterns,
        use_subprocess_reporting=msg.use_subprocess_reporting,
        invocation_timeout_millis=msg.invocation_timeout_millis,
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
        ],
        use_parallel_setup=msg.use_parallel_setup)


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
      invocation_timeout_millis=entity.invocation_timeout_millis,
      output_idle_timeout_millis=entity.output_idle_timeout_millis,
      jvm_options=entity.jvm_options,
      java_properties=java_properties,
      context_file_pattern=entity.context_file_pattern,
      extra_context_files=entity.extra_context_files,
      retry_command_line=entity.retry_command_line,
      log_level=entity.log_level,
      tradefed_config_objects=[
          ToMessage(t) for t in entity.tradefed_config_objects
      ],
      use_parallel_setup=entity.use_parallel_setup)


class Command(ndb.Model):
  """A test command entity.

  Attributes:
    request_id: a request ID.
    name: a human friendly name.
    command_hash: a hash of the command line.
    command_line: a command line.
    cluster: a target cluster ID.
    run_target: a target run target.
    run_count: a target run count.
    state: a state of the command.
    error_reason: readable reason for error.
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
    allow_partial_device_match: a boolean field indicating whether partial
         device match is allowed or not
    test_bench: a TestBench object.
  """
  request_id = ndb.StringProperty()
  name = ndb.StringProperty()
  command_hash = ndb.StringProperty()
  command_line = ndb.TextProperty()
  cluster = ndb.StringProperty()
  run_target = ndb.StringProperty()
  run_count = ndb.IntegerProperty()
  state = ndb.EnumProperty(common.CommandState,
                           default=common.CommandState.UNKNOWN)
  error_reason = ndb.EnumProperty(common.ErrorReason)
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
  allow_partial_device_match = ndb.BooleanProperty(default=False)
  test_bench = ndb.LocalStructuredProperty(TestBench)


@MessageConverter(Command)
def CommandToMessage(command):
  _, request_id, _, command_id = command.key.flat()
  return api_messages.CommandMessage(
      id=command_id,
      request_id=request_id,
      name=command.name,
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
      shard_index=command.shard_index,
      error_reason=command.error_reason,
      allow_partial_device_match=command.allow_partial_device_match,
      test_bench=ToMessage(command.test_bench))


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
    subprocess_command_error: an error from a subprocess command if exists.
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
  subprocess_command_error = ndb.TextProperty()
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
      subprocess_command_error=command_attempt.subprocess_command_error,
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
    event_time: The timestamp when offline/recovery event happens.
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
  event_time = ndb.DateTimeProperty()


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
      device_serial=note_entity.device_serial,
      event_time=note_entity.event_time)


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
  lab_name = ndb.StringProperty()
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
    lab_name: string, the lab where the host is.
    cluster_name: string, the physical cluster(host group) of the host.
    graceful_shutdown: bool, whether to gracefully shutdown the host.
    shutdown_timeout_sec: int, customized shutdown timeout in seconds.
    enable_ui_update: bool, whether the host can be updated from UI.
    owners: list of string, the lab owners.
    update_time: the time the config is update.
    inventory_groups: the inventory groups and the parent groups the host belong
      to.
    docker_image: string, the docker image to run test harness.
  """
  hostname = ndb.StringProperty()
  tf_global_config_path = ndb.StringProperty()
  host_login_name = ndb.StringProperty()
  lab_name = ndb.StringProperty()
  cluster_name = ndb.StringProperty()
  graceful_shutdown = ndb.BooleanProperty()
  shutdown_timeout_sec = ndb.IntegerProperty()
  enable_ui_update = ndb.BooleanProperty()
  owners = ndb.StringProperty(repeated=True)
  update_time = ndb.DateTimeProperty(auto_now=True)
  inventory_groups = ndb.StringProperty(repeated=True)
  docker_image = ndb.StringProperty()

  @classmethod
  def FromMessage(cls, msg):

    return cls(
        id=msg.hostname,
        hostname=msg.hostname,
        tf_global_config_path=msg.tf_global_config_path,
        host_login_name=msg.host_login_name,
        lab_name=msg.lab_name,
        cluster_name=msg.cluster_name,
        graceful_shutdown=msg.graceful_shutdown,
        shutdown_timeout_sec=msg.shutdown_timeout_sec,
        enable_ui_update=msg.enable_ui_update,
        owners=list(msg.owners),
        inventory_groups=list(msg.inventory_groups),
        docker_image=msg.docker_image)


@MessageConverter(HostConfig)
def HostConfigToMessage(host_config_entity):
  """Convert host_config to host config api message."""
  if host_config_entity:
    return api_messages.HostConfig(
        hostname=host_config_entity.hostname,
        tf_global_config_path=host_config_entity.tf_global_config_path,
        host_login_name=host_config_entity.host_login_name,
        lab_name=host_config_entity.lab_name,
        cluster_name=host_config_entity.cluster_name,
        graceful_shutdown=host_config_entity.graceful_shutdown,
        shutdown_timeout_sec=host_config_entity.shutdown_timeout_sec,
        enable_ui_update=host_config_entity.enable_ui_update,
        owners=list(host_config_entity.owners),
        inventory_groups=list(host_config_entity.inventory_groups),
        docker_image=host_config_entity.docker_image)


class HostMetadata(ndb.Model):
  """HostMetadata stored dynamic host configs.

  Attributes:
    hostname: string, a host name.
    test_harness_image: string, url to test harness docker image.
    update_time: time when the host metadata is changed.
    allow_to_update: bool, whether the harness update is allowed based on
      the cluster-level concurrency control.
  """
  hostname = ndb.StringProperty()
  test_harness_image = ndb.StringProperty()
  update_time = ndb.DateTimeProperty(auto_now=True)
  allow_to_update = ndb.BooleanProperty(default=False)


@MessageConverter(HostMetadata)
def HostMetadataToMessage(entity):
  """Convert host metadata entity to host metadata api message."""
  return api_messages.HostMetadata(
      hostname=entity.hostname,
      test_harness_image=entity.test_harness_image,
      update_time=entity.update_time,
      allow_to_update=entity.allow_to_update)


class ClusterConfig(ndb.Model):
  """A cluster config entity.

  Attributes:
    cluster_name: a string of cluster name.
    host_login_name: a string of the user name of the cluster.
    owners: a list of owners of the cluster.
    tf_global_config_path: a string of the global path of clsuter configs.
    update_time: the time the config is update.
    max_concurrent_update_percentage: int from 1 to 100, the percentage of hosts
      that can be updated concurrently in the cluster.
  """
  cluster_name = ndb.StringProperty()
  host_login_name = ndb.StringProperty()
  owners = ndb.StringProperty(repeated=True)
  tf_global_config_path = ndb.StringProperty()
  update_time = ndb.DateTimeProperty(auto_now=True)
  max_concurrent_update_percentage = ndb.IntegerProperty()

  @classmethod
  def FromMessage(cls, msg):
    return cls(
        id=msg.cluster_name,
        cluster_name=msg.cluster_name,
        host_login_name=msg.host_login_name,
        owners=list(msg.owners),
        max_concurrent_update_percentage=msg.max_concurrent_update_percentage,
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


class HostGroupConfig(ndb.Model):
  """Lab inventory group config entity.

  Attributes:
    name: the group name.
    lab_name: the lab name.
    parent_groups: the parent goup name list.
    account_principals: the account to account principals map.
    update_time: the time the config is update.
    owners: the owner user/group names.
    readers: the reader user/group names.
  """
  name = ndb.StringProperty()
  lab_name = ndb.StringProperty()
  parent_groups = ndb.StringProperty(repeated=True)
  account_principals = ndb.JsonProperty()
  update_time = ndb.DateTimeProperty(auto_now=True)
  owners = ndb.StringProperty(repeated=True)
  readers = ndb.StringProperty(repeated=True)

  @classmethod
  def CreateId(cls, lab_name, name):
    """Creates GroupConfig id."""
    return '{}_{}'.format(lab_name, name)


class HostUpdateStateSummary(ndb.Model):
  """Summary of host update states under a lab or a host group.

  Attributes:
    total: total number of hosts.
    unknown: number of host with HostUpdateState.UNKNOWN .
    pending: number of host with HostUpdateState.PENDING .
    syncing: number of host with HostUpdateState.SYNCING .
    shutting_down: number of host with HostUpdateState.SHUTTING_DOWN .
    restarting: number of host with HostUpdateState.RESTARTING .
    timed_out: number of host with HostUpdateState.TIMED_OUT .
    errored: number of host with HostUpdateState.ERRORED .
    succeeded: number of host with HostUpdateState.SUCCEEDED .
    summary_update_timestamp: time when the summary is calculated.
    target_version: the test harness version number that the current update
      task is running with.
  """
  total = ndb.IntegerProperty(default=0)
  unknown = ndb.IntegerProperty(default=0)
  pending = ndb.IntegerProperty(default=0)
  syncing = ndb.IntegerProperty(default=0)
  shutting_down = ndb.IntegerProperty(default=0)
  restarting = ndb.IntegerProperty(default=0)
  timed_out = ndb.IntegerProperty(default=0)
  errored = ndb.IntegerProperty(default=0)
  succeeded = ndb.IntegerProperty(default=0)
  summary_update_timestamp = ndb.DateTimeProperty(auto_now=True)
  target_version = ndb.StringProperty(
      default=common.UNKNOWN_TEST_HARNESS_VERSION)

  def __add__(self, other):

    if (self.target_version == common.UNKNOWN_TEST_HARNESS_VERSION and
        other.target_version == common.UNKNOWN_TEST_HARNESS_VERSION):
      target_version = common.UNKNOWN_TEST_HARNESS_VERSION
    elif self.target_version == common.UNKNOWN_TEST_HARNESS_VERSION:
      target_version = other.target_version
    elif other.target_version == common.UNKNOWN_TEST_HARNESS_VERSION:
      target_version = self.target_version
    elif self.target_version != other.target_version:
      target_version = common.UNKNOWN_TEST_HARNESS_VERSION
    else:
      target_version = self.target_version

    return HostUpdateStateSummary(
        total=self.total+other.total,
        unknown=self.unknown+other.unknown,
        pending=self.pending+other.pending,
        syncing=self.syncing+other.syncing,
        shutting_down=self.shutting_down+other.shutting_down,
        restarting=self.restarting+other.restarting,
        timed_out=self.timed_out+other.timed_out,
        errored=self.errored+other.errored,
        succeeded=self.succeeded+other.succeeded,
        target_version=target_version)


@MessageConverter(HostUpdateStateSummary)
def HostUpdateStateSummaryToMessage(host_update_state_summary_entity):
  """Convert HostUpdateStateSummary from entity to message."""
  if not host_update_state_summary_entity:
    return None
  return api_messages.HostUpdateStateSummary(
      total=host_update_state_summary_entity.total,
      unknown=host_update_state_summary_entity.unknown,
      pending=host_update_state_summary_entity.pending,
      syncing=host_update_state_summary_entity.syncing,
      shutting_down=host_update_state_summary_entity.shutting_down,
      restarting=host_update_state_summary_entity.restarting,
      timed_out=host_update_state_summary_entity.timed_out,
      errored=host_update_state_summary_entity.errored,
      succeeded=host_update_state_summary_entity.succeeded,
      update_timestamp=(
          host_update_state_summary_entity.summary_update_timestamp),
      target_version=host_update_state_summary_entity.target_version)


class ClusterInfo(ndb.Expando):
  """Cluster information entity. Key should be cluster name.

  Attributes:
    cluster: clsuter name
    lab_name: the lab name
    total_devices: total devices count
    offline_devices: offline device count
    available_devices: available devices count
    allocated_devices: allocated devices count
    device_count_timestamp: time when the device counts were calculated
    host_update_state_summary: host update states summary under the cluster
    host_count_by_harness_version: count hosts by test harness version
    host_update_state_summaries_by_version: host update state summary by
      versions.
  """
  cluster = ndb.StringProperty()
  lab_name = ndb.StringProperty()
  total_devices = ndb.IntegerProperty(default=0)
  offline_devices = ndb.IntegerProperty(default=0)
  available_devices = ndb.IntegerProperty(default=0)
  allocated_devices = ndb.IntegerProperty(default=0)
  # Time when the device counts were calculated and persisted
  device_count_timestamp = ndb.DateTimeProperty()
  host_update_state_summary = ndb.StructuredProperty(HostUpdateStateSummary)
  host_count_by_harness_version = ndb.JsonProperty()
  host_update_state_summaries_by_version = ndb.LocalStructuredProperty(
      HostUpdateStateSummary, repeated=True)


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


def _FlatExtraInfo(entity, allowlist):
  """Transform extra_info to a list.

  Args:
    entity: Device or host entity.
    allowlist: extra info keys allowed to be indexed.
  Returns:
    A list of string. string format is 'key:value'
  """
  flated_extra_info = []
  if not entity.extra_info:
    return []
  extra_info_dict = dict(entity.extra_info)
  for key, value in extra_info_dict.items():
    if key not in allowlist:
      continue
    value = value[:_EXTRA_INFO_INDEXED_VALUE_SIZE] if value else ''
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
    timestamp: the timestamp the host is updated.
    total_devices: total devices count
    offline_devices: offline device count
    available_devices: available devices count
    allocated_devices: allocated devices count
    device_count_timestamp: time when the device counts were calculated
    hidden: is the device hidden or not
    extra_info: extra info for the host
    host_state: the state of the host
    assignee: the user who will recover this host.
    device_count_summaries: device count by run target under the host.
    is_bad: is the host bad or not. Right now bad means host offline or there
      are device offline on the host.
    last_recovery_time: last time the host was recovered.
    flated_extra_info: flated extra info for the host.
    recovery_state: recovery state for the host, e.g. assigned, fixed, verified.
    test_harness: test harness
    test_harness_version: test harness version
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
  total_devices = ndb.IntegerProperty(default=0)
  offline_devices = ndb.IntegerProperty(default=0)
  available_devices = ndb.IntegerProperty(default=0)
  allocated_devices = ndb.IntegerProperty(default=0)
  # Time when the device counts were calculated and persisted
  device_count_timestamp = ndb.DateTimeProperty()
  last_recovery_time = ndb.DateTimeProperty()
  flated_extra_info = ndb.ComputedProperty(
      lambda entity: _FlatExtraInfo(entity, _HOST_EXTRA_INFO_INDEX_ALLOWLIST),
      repeated=True)
  recovery_state = ndb.StringProperty()
  test_harness = ndb.StringProperty()
  test_harness_version = ndb.StringProperty()


@MessageConverter(HostInfo)
def HostInfoToMessage(
    host_info_entity, devices=None, host_update_state_entity=None):
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
  if host_update_state_entity:
    update_state = host_update_state_entity.state.name
    update_state_display_message = host_update_state_entity.display_message
  else:
    update_state = None
    update_state_display_message = None
  test_harness = host_info_entity.test_harness
  test_harness_version = host_info_entity.test_harness_version
  return api_messages.HostInfo(
      hostname=host_info_entity.hostname,
      lab_name=host_info_entity.lab_name,
      # TODO: deprecate physical_cluster, use host_group.
      cluster=host_info_entity.physical_cluster,
      host_group=host_info_entity.host_group,
      # TODO: deprecated test runner and test runner version.
      test_runner=test_harness,
      test_runner_version=test_harness_version,
      test_harness=test_harness,
      test_harness_version=test_harness_version,
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
      host_state=host_state,
      assignee=host_info_entity.assignee,
      device_count_summaries=device_count_summaries,
      is_bad=host_info_entity.is_bad,
      last_recovery_time=host_info_entity.last_recovery_time,
      flated_extra_info=host_info_entity.flated_extra_info,
      recovery_state=host_info_entity.recovery_state,
      update_state=update_state,
      update_state_display_message=update_state_display_message)


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


class HostResource(ndb.Expando):
  """Host resource entity. Key should be hostname.

  Attributes:
    hostname: hostname
    resource: josn object of the host resource.
    update_time: when the  object is updated.
    event_timestamp: last host resource event timestamp.
  """
  hostname = ndb.StringProperty()
  resource = ndb.JsonProperty(compressed=True)
  update_timestamp = ndb.DateTimeProperty(auto_now=True)
  event_timestamp = ndb.DateTimeProperty()

  @classmethod
  def FromJson(cls, d):
    hostname = d['identifier']['hostname']
    key = ndb.Key(cls, hostname)
    event_timestamp = None
    for resource in d.get('resource', []):
      timestamp = dateutil.parser.parse(
          resource['timestamp']).replace(tzinfo=None)
      if not event_timestamp or timestamp > event_timestamp:
        event_timestamp = timestamp
    return HostResource(
        key=key,
        hostname=hostname,
        resource=d,
        event_timestamp=event_timestamp or datetime.datetime.utcnow())


@MessageConverter(HostResource)
def HostResourceToMessage(host_resource_entity):
  """Convert a HostResource entity into a HostResource message."""
  return api_messages.HostResource(
      hostname=host_resource_entity.hostname,
      resource=json.dumps(host_resource_entity.resource),
      update_timestamp=host_resource_entity.update_timestamp,
      event_timestamp=host_resource_entity.event_timestamp)


class HostUpdateState(ndb.Model):
  """Host update state.

  Attreibutes:
    hostname: hostname.
    update_timestamp: timestamp the update state is changed.
    update_task_id: the host update task ID.
    state: host update state, see HostUpdateState in api message.
    display_message: the optional display message to further clarify the current
      host update state.
    target_version: the target test harness version to which the host is
      going to update.
  """
  hostname = ndb.StringProperty()
  state = ndb.EnumProperty(
      api_messages.HostUpdateState,
      default=api_messages.HostUpdateState.UNKNOWN)
  update_timestamp = ndb.DateTimeProperty()
  update_task_id = ndb.StringProperty()
  display_message = ndb.TextProperty()
  target_version = ndb.StringProperty()


class HostUpdateStateHistory(HostUpdateState):
  """The host update state history."""


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
    last_recovery_time: last time the device was recovered.
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
  flated_extra_info = ndb.ComputedProperty(
      lambda entity: _FlatExtraInfo(entity, _DEVICE_EXTRA_INFO_INDEX_ALLOWLIST),
      repeated=True)
  recovery_state = ndb.StringProperty()
  last_recovery_time = ndb.DateTimeProperty()


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
      recovery_state=device_info_entity.recovery_state,
      flated_extra_info=device_info_entity.flated_extra_info,
      last_recovery_time=device_info_entity.last_recovery_time)


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
    host_update_state_summary: host update states summary under the cluster
    host_count_by_harness_version: count hosts by test harness version
    host_update_state_summaries_by_version: host update state summary by
      versions.
  """
  lab_name = ndb.StringProperty()
  update_timestamp = ndb.DateTimeProperty(auto_now_add=True)
  host_update_state_summary = ndb.StructuredProperty(HostUpdateStateSummary)
  host_count_by_harness_version = ndb.JsonProperty()
  host_update_state_summaries_by_version = ndb.LocalStructuredProperty(
      HostUpdateStateSummary, repeated=True)


@MessageConverter(LabInfo)
def LabInfoToMessage(lab_info_entity, lab_config_entity=None):
  owners = lab_config_entity.owners if lab_config_entity else []
  return api_messages.LabInfo(
      lab_name=lab_info_entity.lab_name,
      update_timestamp=lab_info_entity.update_timestamp,
      owners=owners,
      host_update_state_summary=ToMessage(
          lab_info_entity.host_update_state_summary),
      host_count_by_harness_version=api_messages.MapToKeyValuePairMessages(
          lab_info_entity.host_count_by_harness_version),
      host_update_state_summaries_by_version=[
          ToMessage(summary) for summary
          in lab_info_entity.host_update_state_summaries_by_version
      ])


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
    schedule_timestamp: the last timestamp the task become leasable.
    lease_timestamp: the last timestamp the task is leased.
    request_type: a request type
    plugin_data: the plugin data.
    allow_partial_device_match: a boolean field indicating whether partial
         device match is allowed or not
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
  schedule_timestamp = ndb.DateTimeProperty()
  lease_timestamp = ndb.DateTimeProperty()
  request_type = ndb.EnumProperty(api_messages.RequestType)
  plugin_data = ndb.JsonProperty()
  allow_partial_device_match = ndb.BooleanProperty(default=False)


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


class TestHarnessImageMetadata(ndb.Model):
  """Test harness image metadata."""
  repo_name = ndb.StringProperty(required=True)
  digest = ndb.StringProperty(required=True)
  test_harness = ndb.StringProperty()
  test_harness_version = ndb.StringProperty()
  create_time = ndb.DateTimeProperty()
  sync_time = ndb.DateTimeProperty()
  current_tags = ndb.StringProperty(repeated=True)
  historical_tags = ndb.StringProperty(repeated=True)


@MessageConverter(TestHarnessImageMetadata)
def TestHarnessImageMetadataToMessage(entity):
  """Convert a TradefedImageMetadata entity to a message."""
  return api_messages.TestHarnessImageMetadataMessage(
      repo_name=entity.repo_name,
      digest=entity.digest,
      test_harness=entity.test_harness,
      test_harness_version=entity.test_harness_version,
      create_time=entity.create_time,
      tags=entity.current_tags)


class RequestSyncStatus(ndb.Model):
  """Tracks request syncs."""
  request_id = ndb.StringProperty(required=True)
  has_new_command_events = ndb.BooleanProperty(default=False)
  last_sync_time = ndb.DateTimeProperty()
  create_time = ndb.DateTimeProperty(auto_now_add=True)
  update_time = ndb.DateTimeProperty(auto_now=True)


class RawCommandEvent(ndb.Model):
  """Command event data as received from the test harness."""
  request_id = ndb.StringProperty(required=True)
  command_id = ndb.StringProperty(required=True)
  attempt_id = ndb.StringProperty(required=True)
  payload = ndb.JsonProperty(compressed=True)
  event_timestamp = ndb.DateTimeProperty()
  create_time = ndb.DateTimeProperty(auto_now_add=True)
