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

"""Tools for tradefed satellite lab configs."""
import abc
import collections
import logging
import os

import six

import strictyaml as syaml


try:
  from google.protobuf import json_format
except ImportError:
  from google3.net.proto2.python.public import json_format


from tradefed_cluster.configs import lab_config_pb2

# Ansible package depends on certain environment variable.
ansible_import_error = None
try:
  os.environ['ANSIBLE_LOCAL_TEMP'] = '/tmp'
  # unified_lab_config depends on ansible.
  from tradefed_cluster.configs import unified_lab_config as unified_lab_config_util
except Exception as e:  
  logging.warning('Fail to import ansible package:\n%s', e)
  ansible_import_error = e


logger = logging.getLogger(__name__)

_DEFAULT_SHUTDOWN_TIMEOUT_SEC = 3600
_TF_GROUP = 'tf'


class ConfigError(Exception):
  """Error raised if config is incorrect."""
  pass


def _ProtoDescriptorToSchema(pb_descriptor):
  """Convert a proto Descriptor to a strictyaml schema."""
  d = {}
  for field in pb_descriptor.fields:
    if field.LABEL_REPEATED == field.label:
      value_schema = syaml.Seq(_ProtoFieldToSchema(field))
    else:
      value_schema = _ProtoFieldToSchema(field)
    d[syaml.Optional(field.name)] = value_schema
  return syaml.Map(d)


def _ProtoFieldToSchema(field):
  """Convert a Proto Field to strictyaml schema."""
  if field.type == field.TYPE_STRING:
    return syaml.Str()
  if field.type == field.TYPE_BOOL:
    return syaml.Bool()
  if field.type in (field.TYPE_INT32, field.TYPE_UINT32,
                    field.TYPE_INT64, field.TYPE_UINT64):
    return syaml.Int()
  if field.type in (field.TYPE_DOUBLE, field.TYPE_FLOAT):
    return syaml.Decimal()
  if field.type == field.TYPE_MESSAGE:
    return _ProtoDescriptorToSchema(field.message_type)
  if field.type == field.TYPE_ENUM:
    return syaml.Str()
  raise ConfigError('Unknown field type in lab_config_pb2: %r.' % field.type)


_YAML_SCHEMA = _ProtoDescriptorToSchema(lab_config_pb2.LabConfig.DESCRIPTOR)


def Parse(yaml_file_obj):
  """Parse yaml config.

  Args:
    yaml_file_obj: yaml file obj.
  Returns:
    a lab_config_pb2.LabConfig proto.
  Raises:
    ConfigError: if the config is incorrect.
  """
  content = six.ensure_str(yaml_file_obj.read())
  try:
    config_dict = syaml.dirty_load(
        content, schema=_YAML_SCHEMA, allow_flow_style=True).data
  except (syaml.YAMLError, TypeError) as e:
    raise ConfigError(e)
  try:
    return json_format.ParseDict(config_dict, lab_config_pb2.LabConfig())
  except json_format.ParseError as e:
    raise ConfigError(e)


class HostConfig(object):
  """A host config object.

  This class is immutable. The setter functions return a new HostConfig object.
  """

  def __init__(
      self,
      host_config_pb,
      cluster_config_pb,
      lab_config_pb):
    self.host_config_pb = lab_config_pb2.HostConfig()
    self.cluster_config_pb = lab_config_pb2.ClusterConfig()
    self.lab_config_pb = lab_config_pb2.LabConfig()

    self.host_config_pb.CopyFrom(host_config_pb)
    self.cluster_config_pb.CopyFrom(cluster_config_pb)
    self.lab_config_pb.CopyFrom(lab_config_pb)

  def Copy(self):
    """Copy the host config."""
    return HostConfig(self.host_config_pb,
                      self.cluster_config_pb,
                      self.lab_config_pb)

  @property
  def hostname(self):
    """Get host's name."""
    return self.host_config_pb.hostname

  @property
  def host_login_name(self):
    """Get host's login username."""
    return (self.host_config_pb.host_login_name or
            self.cluster_config_pb.host_login_name or
            self.lab_config_pb.host_login_name)

  @property
  def tf_global_config_path(self):
    """Get tf global config for the host."""
    return (self.host_config_pb.tf_global_config_path or
            self.cluster_config_pb.tf_global_config_path)

  @property
  def lab_name(self):
    """Get host's lab's name."""
    return self.lab_config_pb.lab_name

  @property
  def cluster_name(self):
    """Get host's cluster's name."""
    return self.cluster_config_pb.cluster_name

  @property
  def control_server_url(self):
    """Get the master server the host connect to."""
    # TODO: Deprecated, use control_server_url instead.
    return (self.cluster_config_pb.control_server_url or
            self.cluster_config_pb.master_url or
            self.lab_config_pb.control_server_url or
            self.lab_config_pb.master_url)

  @property
  def operation_mode(self):
    """Get the operation mode of the host."""
    return self.lab_config_pb.operation_mode

  @property
  def docker_image(self):
    """Get the docker image the host to use."""
    return (self.host_config_pb.docker_image or
            self.cluster_config_pb.docker_image or
            self.lab_config_pb.docker_image)

  def SetDockerImage(self, val):
    """Create a new config with given value of docker_image."""
    host_config = self.Copy()
    host_config.host_config_pb.docker_image = val
    return host_config

  @property
  def graceful_shutdown(self):
    """Graceful shutdown or not."""
    return (self.host_config_pb.graceful_shutdown or
            self.cluster_config_pb.graceful_shutdown or
            False)

  @property
  def shutdown_timeout_sec(self):
    """The dockerized TradeFed shutdown timeouts in seconds."""
    return (self.host_config_pb.shutdown_timeout_sec or
            self.cluster_config_pb.shutdown_timeout_sec)

  @property
  def enable_stackdriver(self):
    """Enable stackdriver logging and monitor."""
    return (self.cluster_config_pb.enable_stackdriver or
            self.lab_config_pb.enable_stackdriver or
            False)

  @property
  def enable_autoupdate(self):
    """Enable autoupdate mtt daemon process."""
    return (self.host_config_pb.enable_autoupdate or
            self.cluster_config_pb.enable_autoupdate or
            self.lab_config_pb.enable_autoupdate)

  @property
  def extra_docker_args(self):
    """Extra docker args."""
    return (list(self.cluster_config_pb.extra_docker_args or []) +
            list(self.host_config_pb.extra_docker_args or []))

  @property
  def service_account_json_key_path(self):
    """The file path of service account json key."""
    return self.lab_config_pb.service_account_json_key_path

  @property
  def docker_server(self):
    """Get the docker server the image is hosted on."""
    return (self.host_config_pb.docker_server or
            self.cluster_config_pb.docker_server or
            self.lab_config_pb.docker_server)

  @property
  def secret_project_id(self):
    """Get secret project id."""
    return self.lab_config_pb.secret_project_id

  @property
  def service_account_key_secret_id(self):
    """Get secret id for service account key."""
    return self.lab_config_pb.service_account_key_secret_id

  @property
  def service_account(self):
    """Get service account."""
    return self.lab_config_pb.service_account

  def SetServiceAccountJsonKeyPath(self, val):
    """Create a new config with given value of service_account_json_key_path."""
    host_config = self.Copy()
    host_config.lab_config_pb.service_account_json_key_path = val
    return host_config

  @property
  def tmpfs_configs(self):
    """Get tmpfs configs to mount into the container.

    Return the tmpfs configs merged the tmpfs configs for the cluster and
    the host. If the path of the tmpfs configs are the same, pick the one from
    the host config.

    Returns:
      a list of tmpfs configs.
    """
    path_to_tmpfs = collections.OrderedDict()
    for tmpfs_config in self.cluster_config_pb.tmpfs_configs or []:
      path_to_tmpfs[tmpfs_config.path] = tmpfs_config
    for tmpfs_config in self.host_config_pb.tmpfs_configs or []:
      path_to_tmpfs[tmpfs_config.path] = tmpfs_config
    return list(path_to_tmpfs.values())

  @property
  def enable_ui_update(self):
    """Whether host update from UI is enabled."""
    return bool(self.host_config_pb.enable_ui_update or
                self.cluster_config_pb.enable_ui_update or
                self.lab_config_pb.enable_ui_update)

  @property
  def owners(self):
    """Inherit the owners field from parent cluster or lab."""
    owners = list(self.lab_config_pb.owners)
    for owner in self.cluster_config_pb.owners:
      if owner not in owners:
        owners.append(owner)
    return owners

  @property
  def engprod_api_key(self):
    """API Key for Android Engprod API discovery."""
    return self.lab_config_pb.engprod_api_key

  @property
  def inventory_groups(self):
    return self.host_config_pb.inventory_groups

  @property
  def max_local_virtual_devices(self):
    return self.host_config_pb.max_local_virtual_devices

  @property
  def ssh_arg(self):
    """Get host's ssh arg."""
    return self.lab_config_pb.ssh_arg

  @property
  def max_concurrent_update_percentage(self):
    """Max concurrent update percentage in cluster level."""
    return self.cluster_config_pb.max_concurrent_update_percentage

  def Save(self, output_file_path):
    """Save the config to a file."""
    lab_config_pb = lab_config_pb2.LabConfig()
    lab_config_pb.CopyFrom(self.lab_config_pb)
    del lab_config_pb.cluster_configs[:]
    cluster_config_pb = lab_config_pb2.ClusterConfig()
    cluster_config_pb.CopyFrom(self.cluster_config_pb)
    del cluster_config_pb.host_configs[:]
    cluster_config_pb.host_configs.add().CopyFrom(self.host_config_pb)
    lab_config_pb.cluster_configs.add().CopyFrom(cluster_config_pb)
    with open(output_file_path, 'w') as f:
      lab_config_dict = json_format.MessageToDict(
          lab_config_pb,
          preserving_proto_field_name=True)
      f.write(syaml.as_document(lab_config_dict, schema=_YAML_SCHEMA).as_yaml())

  def __eq__(self, other):
    if not isinstance(other, HostConfig):
      return False
    property_names = [name for name, obj
                      in vars(HostConfig).items()
                      if isinstance(obj, property)]
    return all(getattr(self, property_name) == getattr(other, property_name)
               for property_name in property_names)

  def __repr__(self):
    lines = []
    for name, obj in vars(HostConfig).items():
      if not isinstance(obj, property):
        continue
      lines.append('%s: %s' % (name, getattr(self, name)))
    return '\n'.join(lines)


def CreateHostConfig(
    lab_name=None,
    cluster_name=None,
    hostname=None,
    host_login_name=None,
    tf_global_config_path=None,
    tmpfs_configs=None,
    docker_image=None,
    graceful_shutdown=False,
    shutdown_timeout_sec=_DEFAULT_SHUTDOWN_TIMEOUT_SEC,
    enable_stackdriver=False,
    enable_autoupdate=False,
    service_account_json_key_path=None,
    docker_server=None,
    extra_docker_args=(),
    control_server_url=None,
    secret_project_id=None,
    service_account_key_secret_id=None,
    service_account=None,
    enable_ui_update=None,
    engprod_api_key=None,
    ssh_arg=None,
    operation_mode=None,
    max_local_virtual_devices=None,
    max_concurrent_update_percentage=None,
):
  """Create a host config from raw data.

  Args:
    lab_name: lab name.
    cluster_name: cluster name.
    hostname: hostname.
    host_login_name: user name to login.
    tf_global_config_path: tf global config path.
    tmpfs_configs: a list of TmpfsConfig proto.
    docker_image: the docker image to use.
    graceful_shutdown: graceful shutdown the host or not.
    shutdown_timeout_sec: int, the dockerized TF shutdown timeout.
    enable_stackdriver: enable stackdriver monitor or not.
    enable_autoupdate: enable auto-update daemon or not.
    service_account_json_key_path: string or None, the file path of service
      account json key.
    docker_server: the docker server that hosts the image.
    extra_docker_args: extra docker args to pass to docker container.
    control_server_url: the control server the host connect to.
    secret_project_id: Google Cloud Project for storing secret.
    service_account_key_secret_id: Secret id for service account key.
    service_account: Service account for the lab.
    enable_ui_update: bool, whether host update from UI is enabled.
    engprod_api_key: string, API Key for Android Engprod API discovery.
    ssh_arg: string, ssh args to the host.
    operation_mode: string, host operation mode.
    max_local_virtual_devices: int, maximum number of virtual devices
    max_concurrent_update_percentage: int, maximum percentage of cluster level
      hosts being updated concurrently.
  Returns:
    a HostConfig have all those data.
  """
  host_config_pb = lab_config_pb2.HostConfig(
      hostname=hostname,
      tf_global_config_path=tf_global_config_path,
      tmpfs_configs=tmpfs_configs,
      enable_autoupdate=enable_autoupdate,
      docker_image=docker_image,
      docker_server=docker_server,
      extra_docker_args=list(extra_docker_args),
      enable_ui_update=enable_ui_update,
      shutdown_timeout_sec=shutdown_timeout_sec,
      max_local_virtual_devices=max_local_virtual_devices,)
  cluster_config_pb = lab_config_pb2.ClusterConfig(
      cluster_name=cluster_name,
      host_login_name=host_login_name,
      host_configs=[host_config_pb],
      docker_image=docker_image,
      graceful_shutdown=graceful_shutdown,
      shutdown_timeout_sec=shutdown_timeout_sec,
      enable_stackdriver=enable_stackdriver,
      control_server_url=control_server_url,
      max_concurrent_update_percentage=max_concurrent_update_percentage)
  lab_config_pb = lab_config_pb2.LabConfig(
      lab_name=lab_name,
      cluster_configs=[cluster_config_pb],
      docker_server=docker_server,
      service_account_json_key_path=service_account_json_key_path,
      secret_project_id=secret_project_id,
      service_account_key_secret_id=service_account_key_secret_id,
      service_account=service_account,
      engprod_api_key=engprod_api_key,
      ssh_arg=ssh_arg,
      operation_mode=operation_mode)
  return HostConfig(host_config_pb, cluster_config_pb, lab_config_pb)


def CreateTmpfsConfig(path, size, mode):
  """Create a TmpfsConfig object."""
  return lab_config_pb2.TmpfsConfig(path=path, size=size, mode=mode)


def IsYaml(path):
  """Is path a yaml file or not."""
  return path.endswith('.yaml')


def IsUnifiedLabConfig(path):
  """Is path a yaml file or not."""
  return path.endswith('hosts') or path.endswith('.ini')


def LocalFileEnumerator(root_path, filename_filter=None):
  """Enumerator files from local path.

  Args:
    root_path: the root of all configs.
    filename_filter: only return files that match the filter
  Yields:
    a file like obj
  Raises:
    ConfigError: raise if the config path doesn't exist.
  """
  logger.debug('Get file from root %s.', root_path)
  if not root_path:
    return
  paths = [root_path]
  while paths:
    path = paths.pop(0)
    if not os.path.exists(path):
      raise ConfigError('%s doesn\'t exist.' % path)
    if os.path.isfile(path):
      if filename_filter and not filename_filter(path):
        continue
      logger.debug('Read from %s.', path)
      with open(path, 'r') as file_obj:
        yield file_obj
    else:
      for root, _, filenames in os.walk(path):
        for filename in filenames:
          subpath = os.path.join(root, filename)
          paths.append(subpath)


class _AbstractLabConfigPool(abc.ABC):
  """Abstract lab config pool interface."""

  def __init__(self):
    self._lab_config_pb = None
    self._host_to_host_config = {}
    self._cluster_to_host_configs = collections.defaultdict(list)
    self._all_host_configs = []

  @abc.abstractmethod
  def LoadConfigs(self):
    """Load configs in the given path."""
    raise NotImplementedError()

  def GetLabConfig(self):
    """Get the lab config.

    Returns:
      a lab_config_pb2.LabConfig.
    """
    return self._lab_config_pb

  def GetHostConfigs(self, cluster_name=None):
    """Get hosts for under a certain cluster.

    Args:
      cluster_name: cluster name
    Returns:
      a list of host configs.
    """
    if cluster_name:
      return self._cluster_to_host_configs.get(cluster_name, [])
    return self._all_host_configs

  def GetHostConfig(self, hostname):
    """Get host config.

    Args:
      hostname: the host's name
    Returns:
      a HostConfig
    """
    return self._host_to_host_config.get(hostname)


class LabConfigPool(_AbstractLabConfigPool):
  """A config pool that can query configs for host and cluster."""

  def __init__(self, file_enumerator=None):
    super().__init__()
    self._file_enumerator = file_enumerator

  def LoadConfigs(self):
    """Load configs in the given path."""
    if not self._file_enumerator:
      logging.debug('Lab config is not set.')
      return
    has_config = False
    for file_obj in self._file_enumerator:
      if not has_config:
        has_config = True
        self._LoadConfig(file_obj)
      else:
        raise ConfigError('There are multiple config files.')
    if not has_config:
      raise ConfigError(
          'Lab config path is set, '
          'but there is no lab config files under the path.')

  def _LoadConfig(self, file_obj):
    """Load one config file."""
    self._lab_config_pb = Parse(file_obj)
    for cluster_config_pb in self._lab_config_pb.cluster_configs:
      for host_config_pb in cluster_config_pb.host_configs:
        host_config = HostConfig(
            host_config_pb, cluster_config_pb, self._lab_config_pb)
        self._host_to_host_config[host_config_pb.hostname] = host_config
        self._cluster_to_host_configs[cluster_config_pb.cluster_name].append(
            host_config)
        self._all_host_configs.append(host_config)


class UnifiedLabConfigPool(_AbstractLabConfigPool):
  """A config pool based on unified lab config."""

  def __init__(self, file_path):
    super().__init__()
    self._file_path = file_path

  def LoadConfigs(self):
    """Load configs in the given path."""
    if not self._file_path:
      logging.debug('Lab config is not set.')
      return
    if not os.path.exists(self._file_path):
      raise ConfigError('Config %s doesn\'t exist.' % self._file_path)
    if ansible_import_error:
      raise ansible_import_error
    unified_config_lab = unified_lab_config_util.Parse(self._file_path)
    self._lab_config_pb = json_format.ParseDict(
        unified_config_lab.ListGlobalVars(), lab_config_pb2.LabConfig(),
        ignore_unknown_fields=True)
    for h in unified_config_lab.ListHosts():
      if _TF_GROUP not in [g.name for g in h.groups]:
        continue
      host_config_pb = json_format.ParseDict(
          h.direct_vars, lab_config_pb2.HostConfig(),
          ignore_unknown_fields=True)
      host_config_pb.hostname = h.name
      cluster_config_dict = {}
      for g in h.groups:
        cluster_config_dict.update(g.direct_vars)
      cluster_config_dict['cluster_name'] = cluster_config_dict.get(
          'cluster_name', h.groups[-1].name)
      cluster_config_pb = json_format.ParseDict(
          cluster_config_dict, lab_config_pb2.ClusterConfig(),
          ignore_unknown_fields=True)
      host_config = HostConfig(
          host_config_pb, cluster_config_pb, self._lab_config_pb)
      self._host_to_host_config[host_config.hostname] = host_config
      for g in h.groups:
        self._cluster_to_host_configs[g.name].append(host_config)
      self._all_host_configs.append(host_config)
