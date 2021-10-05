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

"""Sync Cluster or Host configs from google cloud storage to TFC NDB."""
import collections
import datetime
import logging
import os
import re

import flask

from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_util
from tradefed_cluster import env_config
from tradefed_cluster.configs import lab_config as lab_config_util
from tradefed_cluster.plugins import base as plugins_base
from tradefed_cluster.services import acl_service
from tradefed_cluster.services import file_storage
from tradefed_cluster.util import ndb_shim as ndb

# Ansible package depends on certain environment variable.
ansible_import_error = None
try:
  os.environ['ANSIBLE_LOCAL_TEMP'] = '/tmp'
  from ansible.parsing import dataloader
  # unified_lab_config depends on ansible, so need to import after ansible.
  from tradefed_cluster.configs import unified_lab_config as unified_lab_config_util
except Exception as e:    logging.warning('Fail to import ansible package:\n%s', e)
  ansible_import_error = e


BUCKET_NAME = 'tradefed_lab_configs'
LAB_CONFIG_DIR_PATH = '/{}/lab_configs/'.format(BUCKET_NAME)
_LAB_INVENTORY_DIR_PATH = '/{}/lab_inventory/'.format(BUCKET_NAME)
_FileInfo = plugins_base.FileInfo
_APP = flask.Flask(__name__)
_LAB_NAME_PATTERN = re.compile(r'.*\/lab_inventory\/(?P<lab_name>.*)')
_INVENTORY_FILE_PATTERN = re.compile(
    r'.*\/lab_inventory\/(?P<lab_name>.*)\/hosts')
_LAB_NAME_KEY = 'lab_name'
_INVENTORY_FILE_FORMAT = '{}/hosts'
_GROUP_VAR_ACCOUNTS = 'accounts'
_GROUP_VAR_LAB_NAME = 'lab_name'
_STATLE_CONFIG_MAX_AGE = datetime.timedelta(days=7)
_OWNERS = 'owners'
_READERS = 'readers'

APP = flask.Flask(__name__)


def GetLabConfigFromGCS(lab_config_path):
  """Get lab config from GCS.

  Args:
    lab_config_path: a string of the file path on Google Cloud Storage.
  Returns:
    a lab config proto
  """
  try:
    return lab_config_util.Parse(file_storage.OpenFile(lab_config_path))
  except file_storage.ObjectNotFoundError:
    logging.exception('Cannot open lab config file: %s', lab_config_path)
  except lab_config_util.ConfigError:
    logging.exception('Fail to parse file: %s', lab_config_path)


def _CheckConfigEntitiesEqual(entity, new_entity):
  """Check if two entities are the same.

  Ignore 'update_time' fields, since it changed when entity is updated.

  Args:
    entity: HostConfig or ClusterConfig entity from datatore.
    new_entity: HostConfig or ClusterConfig entity from proto.
  Returns:
    true if they are the same, otherwise false.
  """
  if not entity:
    return False
  entity_dict = entity.to_dict()
  entity_dict.pop('update_time', None)
  new_entity_dict = new_entity.to_dict()
  new_entity_dict.pop('update_time', None)
  return entity_dict == new_entity_dict


def _UpdateLabConfig(lab_name, lab_config_pbs, unified_lab_config):
  """Update Lab config to ndb."""
  logging.debug('Updating lab config entity for %s.', lab_name)
  owners = set()
  if lab_config_pbs:
    for lab_config_pb in lab_config_pbs:
      owners = owners.union(lab_config_pb.owners)
  # TODO: Get owners information from unified_lab_config.
  del unified_lab_config
  owners = sorted(owners)
  lab_info_entity = datastore_entities.LabInfo.get_by_id(lab_name)
  if not lab_info_entity:
    logging.debug(
        'No lab info entity for %s, creating one.', lab_name)
    lab_info_entity = datastore_entities.LabInfo(
        id=lab_name,
        lab_name=lab_name)
    lab_info_entity.put()
  lab_config_entity = datastore_entities.LabConfig.get_by_id(
      lab_name)
  if not lab_config_entity:
    logging.debug(
        'No lab config entity for %s, creating one.', lab_name)
    lab_config_entity = datastore_entities.LabConfig(
        id=lab_name,
        lab_name=lab_name,
        owners=owners)
    lab_config_entity.put()
    return
  if lab_config_entity.owners == owners:
    return
  # TODO: Add other informations.
  logging.debug('Update lab info entity for %s.', lab_name)
  lab_info_entity.owners = owners
  lab_info_entity.put()
  logging.debug('Lab config updated.')


def _UpdateClusterConfigs(cluster_configs):
  """Update cluster configs in ClusterInfo entity to ndb.

  Args:
    cluster_configs: a list of cluster configs proto.
  """
  logging.debug('Updating cluster configs.')
  cluster_config_keys = set()
  for cluster_config in cluster_configs:
    cluster_config_keys.add(
        ndb.Key(datastore_entities.ClusterConfig, cluster_config.cluster_name))
  entities = ndb.get_multi(cluster_config_keys)
  name_to_cluster = {}
  for entity in entities:
    if entity:
      name_to_cluster[entity.cluster_name] = entity

  name_to_entity = {}
  for cluster_config in cluster_configs:
    new_config_entity = datastore_entities.ClusterConfig.FromMessage(
        cluster_config)
    if not _CheckConfigEntitiesEqual(
        name_to_cluster.get(cluster_config.cluster_name), new_config_entity):
      logging.debug('Updating cluster config entity: %s.', new_config_entity)
      if cluster_config.cluster_name in name_to_entity:
        logging.warning(
            '%s has duplicated configs.', cluster_config.cluster_name)
      name_to_entity[cluster_config.cluster_name] = new_config_entity
  ndb.put_multi(name_to_entity.values())
  logging.debug('Cluster configs updated.')


def _UpdateHostConfigs(host_to_host_config, host_to_unified_host_config):
  """Update host configs in HostInfo entities to ndb.

  Args:
    host_to_host_config: host to HostConfig mapping.
    host_to_unified_host_config: host to unified host config mapping.
  """
  logging.debug('Updating host configs.')
  hostnames = set(host_to_host_config.keys()).union(
      host_to_unified_host_config.keys())

  entities_from_config = []
  for hostname in hostnames:
    host_config = host_to_host_config.get(hostname)
    unified_host_config = host_to_unified_host_config.get(hostname)
    entities_from_config.append(_HostConfigEntityFromHostConfig(
        host_config, unified_host_config))

  entities = ndb.get_multi([
      ndb.Key(datastore_entities.HostConfig,
              hostname) for hostname in hostnames])
  entities_to_update = []
  # Update the exist host config entity.
  for entity_from_config, entity in zip(entities_from_config, entities):
    if not _CheckConfigEntitiesEqual(entity, entity_from_config):
      logging.debug('Updating host config entity: %s.', entity_from_config)
      entities_to_update.append(entity_from_config)
  ndb.put_multi(entities_to_update)
  logging.debug('Host configs updated.')


def SyncToNDB():
  """Sync file from gcs to ndb."""
  lab_to_unified_lab_config = {
      lab_name: unified_lab_config_util.Parse(inventory_file, _GcsDataLoader())
      for lab_name, inventory_file in _GetLabInventoryFiles()
  }

  stats = file_storage.ListFiles(LAB_CONFIG_DIR_PATH)
  # A lab can splited into multiple mtt lab config.
  lab_to_lab_pbs = collections.defaultdict(list)
  for stat in stats:
    if stat.filename.endswith('.yaml'):
      logging.debug('Processing cloudstorage file: %s', stat.filename)
      lab_config_pb = GetLabConfigFromGCS(stat.filename)
      if not lab_config_pb:
        continue
      lab_name = lab_config_pb.lab_name or common.UNKNOWN_LAB_NAME
      lab_to_lab_pbs[lab_name].append(lab_config_pb)

  lab_names = set(lab_to_unified_lab_config.keys()).union(lab_to_lab_pbs.keys())
  for lab_name in lab_names:
    _UpdateLabConfig(
        lab_name, lab_to_lab_pbs.get(lab_name),
        lab_to_unified_lab_config.get(lab_name))

  host_to_host_config = {}
  for lab_name, lab_config_pbs in lab_to_lab_pbs.items():
    for lab_config_pb in lab_config_pbs:
      _UpdateClusterConfigs(lab_config_pb.cluster_configs)
      for cluster_config_pb in lab_config_pb.cluster_configs:
        for host_config_pb in cluster_config_pb.host_configs:
          host_to_host_config[host_config_pb.hostname] = (
              lab_config_util.HostConfig(
                  host_config_pb, cluster_config_pb, lab_config_pb))

  for lab_name, unified_lab_config in lab_to_unified_lab_config.items():
    _UpdateHostGroupConfigByInventoryData(lab_name, unified_lab_config)

  host_to_unified_host_config = {}
  for lab_name, unified_lab_config in lab_to_unified_lab_config.items():
    for host in unified_lab_config.ListHosts():
      host_to_unified_host_config[host.name] = host
  _UpdateHostConfigs(host_to_host_config, host_to_unified_host_config)

  # TODO: change to delete host config entities based on existence.
  datastore_util.DeleteEntitiesUpdatedEarlyThanSomeTimeAgo(
      datastore_entities.LabConfig,
      datastore_entities.LabConfig.update_time,
      _STATLE_CONFIG_MAX_AGE)
  datastore_util.DeleteEntitiesUpdatedEarlyThanSomeTimeAgo(
      datastore_entities.ClusterConfig,
      datastore_entities.ClusterConfig.update_time,
      _STATLE_CONFIG_MAX_AGE)
  datastore_util.DeleteEntitiesUpdatedEarlyThanSomeTimeAgo(
      datastore_entities.HostConfig,
      datastore_entities.HostConfig.update_time,
      _STATLE_CONFIG_MAX_AGE)
  datastore_util.DeleteEntitiesUpdatedEarlyThanSomeTimeAgo(
      datastore_entities.HostGroupConfig,
      datastore_entities.HostConfig.update_time,
      _STATLE_CONFIG_MAX_AGE)
  # TODO: Uncomment when fixed.
  # _UpdateHostGroupPermissions(lab_to_unified_lab_config)


class _GcsDataLoader(dataloader.DataLoader):
  """The data loader use gcs file_storeage to read the files."""

  def _get_file_contents(self, file_name):
    """Gets file contents and the show_content flag from given file name.

    Args:
      file_name: the file name.
    Returns:
      A tuple contains file content and a boolean value indicates if the file
      is encrypt or not.
    """
    with file_storage.OpenFile(file_name) as f:
      return f.read(), False

  def list_directory(self, path):
    """Get filenames under a directory in gcs."""
    return [os.path.basename(file_info.filename)
            for file_info in file_storage.ListFiles(path)]


def _HostConfigEntityFromHostConfig(host_config, unified_host_config):
  """Creates HostConfig entity from HostConfig and unified host config.

  Args:
    host_config: a HostConfig object.
    unified_host_config: a unified_host_config object.
  Returns:
    the HostConfig entity.
  """
  lab_name = common.UNKNOWN_LAB_NAME
  if host_config and host_config.lab_name:
    lab_name = host_config.lab_name
  if (unified_host_config and
      unified_host_config.GetVar(_GROUP_VAR_LAB_NAME) and
      lab_name == common.UNKNOWN_LAB_NAME):
    lab_name = unified_host_config.GetVar(_GROUP_VAR_LAB_NAME)

  if host_config:
    entity = datastore_entities.HostConfig.FromMessage(host_config)
  else:
    entity = datastore_entities.HostConfig(
        id=unified_host_config.name,
        hostname=unified_host_config.name)
  entity.lab_name = lab_name
  if unified_host_config:
    entity.inventory_groups = [g.name for g in unified_host_config.groups]
  return entity


def _CreateHostGroupConfigEntityFromGroupInventory(lab_name, group):
  """Creates HostGroupConfig from Group model.

  Args:
    lab_name: the lab name.
    group: unified_lab_config._Group object.
  Returns:
    the HostGroupConfig entity.
  """
  return datastore_entities.HostGroupConfig(
      id=datastore_entities.HostGroupConfig.CreateId(lab_name, group.name),
      name=group.name,
      lab_name=lab_name,
      parent_groups=[g.name for g in group.parent_groups],
      account_principals=group.direct_vars.get(_GROUP_VAR_ACCOUNTS),
      owners=group.direct_vars.get(_OWNERS, []),
      readers=group.direct_vars.get(_READERS, []))


def _UpdateHostGroupConfigByInventoryData(lab_name, lab_config):
  """Updates HostGroupConfig.

  The methods load new HostGroupConfig from inventory file, creates new
  HostGroupConfig, updates exist HostGroupConfig and remove obsolete
  HostGroupConfig.

  Args:
    lab_name: the lab name from path.
    lab_config: a UnifiedLabConfig object.
  """
  # Use the configued lab name first, only use the lab name from
  # file path if no lab name is configured.
  lab_name = lab_config.GetGlobalVar(_LAB_NAME_KEY) or lab_name
  entity_from_file = {
      group.key: group for group in [
          _CreateHostGroupConfigEntityFromGroupInventory(lab_name, group)
          for group in lab_config.ListGroups()
      ]
  }
  logging.debug('Loaded %d HostGroupConfigs of lab %s',
                len(entity_from_file), lab_name)
  entity_from_ndb = {
      g.key: g for g in ndb.get_multi(entity_from_file.keys()) if g
  }
  need_update = []
  for key, group in entity_from_file.items():
    if not _CheckConfigEntitiesEqual(entity_from_ndb.get(key), group):
      need_update.append(group)
  ndb.put_multi(need_update)
  logging.debug('Updated %d HostGroupConfigs.', len(need_update))


def _GetLabInventoryFiles():
  """Gets inventory files.

  Yields:
    A tuple contains lab name and the inventory file name.
  """
  logging.debug('list lab dir in %s', _LAB_INVENTORY_DIR_PATH)
  for file in file_storage.ListFiles(_LAB_INVENTORY_DIR_PATH):
    if file.is_dir:
      lab_dir_match = _LAB_NAME_PATTERN.match(file.filename)
      if lab_dir_match and lab_dir_match.group(_LAB_NAME_KEY):
        yield (lab_dir_match.group(_LAB_NAME_KEY),
               _INVENTORY_FILE_FORMAT.format(file.filename))
    else:
      inventory_file_match = _INVENTORY_FILE_PATTERN.match(file.filename)
      if inventory_file_match and inventory_file_match.group(_LAB_NAME_KEY):
        logging.debug('Gets inventory from lab dir: %s', file.filename)
        yield (inventory_file_match.group(_LAB_NAME_KEY), file.filename)


def _UpdateHostGroupPermissions(lab_to_unified_lab_config):
  """Updates parent relations and group permissions."""
  for lab_name, lab_config in lab_to_unified_lab_config.items():
    for group in lab_config.ListGroups():
      group_id = datastore_entities.HostGroupConfig.CreateId(
          lab_name, group.name)
      acl_service.SyncParentObjects(
          group_id,
          [datastore_entities.HostGroupConfig.CreateId(
              lab_name, group.name) for group in group.parent_groups])
      if group.direct_vars.get(_OWNERS):
        acl_service.SyncUserPermissions(
            group_id,
            acl_service.Permission.owner.value,
            group.direct_vars[_OWNERS])
      if group.direct_vars.get(_READERS):
        acl_service.SyncUserPermissions(
            group_id,
            acl_service.Permission.reader.value,
            group.direct_vars[_READERS])


@APP.route('/cron/syncer/sync_gcs_ndb')
def SyncGCSToNDB():
  """Task to sync cluster and host config from gcs to ndb."""
  if env_config.CONFIG.should_sync_lab_config:
    logging.debug('"should_sync_lab_config" is enabled.')
    global ansible_import_error
    if ansible_import_error:
      logging.error('Failed to import ansible package:\n%s',
                    ansible_import_error)
      raise ansible_import_error
    SyncToNDB()
  return common.HTTP_OK
