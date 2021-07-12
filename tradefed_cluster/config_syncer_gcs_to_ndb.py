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

import logging
import os
import re

import flask

from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config
from tradefed_cluster.configs import lab_config as lab_config_util
from tradefed_cluster.plugins import base as plugins_base
from tradefed_cluster.services import file_storage
from tradefed_cluster.util import ndb_shim as ndb

# Ansible package depends on certain environment variable.
ansible_import_error = None
try:
  os.environ['ANSIBLE_LOCAL_TEMP'] = '/tmp'
  from ansible.inventory import data as inventory_data
  from ansible.parsing import dataloader
  from ansible.plugins.inventory import ini
except Exception as e:    logging.warning('Fail to import ansible package:\n%s', e)
  ansible_import_error = e


BUCKET_NAME = 'tradefed_lab_configs'
LAB_CONFIG_DIR_PATH = '/{}/lab_configs/'.format(BUCKET_NAME)
_LAB_INVENTORY_DIR_PATH = '/{}/lab_inventory/'.format(BUCKET_NAME)
_INVENTORY_GROUPS = 'inventory_groups'
_FileInfo = plugins_base.FileInfo
_APP = flask.Flask(__name__)
_LAB_NAME_PATTERN = re.compile(r'.*\/lab_inventory\/(?P<lab_name>.*)')
_INVENTORY_FILE_PATTERN = re.compile(
    r'.*\/lab_inventory\/(?P<lab_name>.*)\/hosts')
_LAB_GROUP_KEY = 'lab_name'
_INVENTORY_FILE_FORMAT = '{}/hosts'
_INVENTORY_GROUP_VAR_DIR_FORMAT = '{}{}/group_vars/'
_INVENTORY_GROUP_VAR_PATTERN = re.compile(
    r'.*\/lab_inventory\/(?P<lab_name>.*)\/group_vars\/(?P<inventory_group>.*)\.(yml|yaml)'
)
_INVENTORY_GROUP_KEY = 'inventory_group'
_GROUP_VAR_ACCOUNTS = 'accounts'

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
  entity_dict.pop(_INVENTORY_GROUPS, None)
  new_entity_dict.pop(_INVENTORY_GROUPS, None)
  return entity_dict == new_entity_dict


def _UpdateLabConfig(lab_config):
  """Update Lab config to ndb."""
  logging.debug('Updating lab config entity.')
  if not lab_config.lab_name:
    logging.error('Lab has no name: %s.', lab_config)
    return
  lab_info_entity = datastore_entities.LabInfo.get_by_id(lab_config.lab_name)
  if not lab_info_entity:
    logging.debug(
        'No lab info entity for %s, creating one.', lab_config.lab_name)
    lab_info_entity = datastore_entities.LabInfo(
        id=lab_config.lab_name,
        lab_name=lab_config.lab_name)
    lab_info_entity.put()
  lab_config_entity = datastore_entities.LabConfig.get_by_id(
      lab_config.lab_name)
  new_lab_config_entity = datastore_entities.LabConfig.FromMessage(lab_config)
  if not _CheckConfigEntitiesEqual(lab_config_entity, new_lab_config_entity):
    logging.debug('Update lab config entity: %s.',
                  new_lab_config_entity.lab_name)
    new_lab_config_entity.put()
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


def _UpdateHostConfigs(host_config_pbs, cluster_config_pb, lab_config_pb):
  """Update host configs in HostInfo entities to ndb.

  Args:
    host_config_pbs: a list of host config protos.
    cluster_config_pb: the cluster config proto.
    lab_config_pb: the lab config proto.
  """
  logging.debug('Updating host configs for <lab: %s, cluster: %s.>',
                lab_config_pb.lab_name, cluster_config_pb.cluster_name)
  host_config_keys = []
  for host_config_pb in host_config_pbs:
    host_config_keys.append(
        ndb.Key(datastore_entities.HostConfig, host_config_pb.hostname))
  entities = ndb.get_multi(host_config_keys)
  entities_to_update = []
  # Update the exist host config entity.
  for entity, host_config_pb in zip(entities, host_config_pbs):
    host_config_msg = lab_config_util.HostConfig(
        host_config_pb, cluster_config_pb, lab_config_pb)
    new_host_config_entity = datastore_entities.HostConfig.FromMessage(
        host_config_msg)
    if not _CheckConfigEntitiesEqual(entity, new_host_config_entity):
      logging.debug('Updating host config entity: %s.', new_host_config_entity)
      entities_to_update.append(new_host_config_entity)
  ndb.put_multi(entities_to_update)
  logging.debug('Host configs updated.')


def SyncToNDB():
  """Sync file from gcs to ndb."""
  stats = file_storage.ListFiles(LAB_CONFIG_DIR_PATH)
  for stat in stats:
    if stat.filename.endswith('.yaml'):
      logging.debug('Processing cloudstorage file: %s', stat.filename)
      lab_config_pb = GetLabConfigFromGCS(stat.filename)
      _UpdateLabConfig(lab_config_pb)
      _UpdateClusterConfigs(lab_config_pb.cluster_configs)  # pytype: disable=attribute-error
      for cluster_config_pb in lab_config_pb.cluster_configs:  # pytype: disable=attribute-error
        _UpdateHostConfigs(cluster_config_pb.host_configs, cluster_config_pb,
                           lab_config_pb)


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


def _LoadInventoryData(path):
  """Loads inventory data from given path.

  Args:
    path: the inentory file path.
  Returns:
    the ansible InventoryData object.
  """
  data = inventory_data.InventoryData()
  ini.InventoryModule().parse(data, _GcsDataLoader(), path)
  return data


def _CreateHostConfigEntityFromHostInventory(lab_name, host):
  """Creates HostConfig from HostInventory.

  Args:
    lab_name: the lab name.
    host: the ansible inventory Host object.
  Returns:
    the HostConfig entity.
  """
  return datastore_entities.HostConfig(
      id=host.name,
      lab_name=lab_name,
      hostname=host.name,
      inventory_groups=sorted(set([g.name for g in host.groups])))


def _CreateHostGroupConfigEntityFromGroupInventory(lab_name, group):
  """Creates HostGroupConfig from Group model.

  Args:
    lab_name: the lab name.
    group: the ansible inventory Group object.
  Returns:
    the HostGroupConfig entity.
  """
  return datastore_entities.HostGroupConfig(
      id=datastore_entities.HostGroupConfig.CreateId(lab_name, group.name),
      name=group.name,
      lab_name=lab_name,
      parent_groups=[g.name for g in group.parent_groups])


def _SyncInventoryHostGroup(lab_name, file_name):
  """Loads inventory file to updates HostConfig and HostGroupConfig.

  Args:
    lab_name: the lab name.
    file_name: the inventory file name.
  """
  data = _LoadInventoryData(file_name)
  _UpdateHostGroupConfigByInventoryData(lab_name, data)
  _UpdateHostConfigByInventoryData(lab_name, data)


def _UpdateHostGroupConfigByInventoryData(lab_name, data):
  """Updates HostGroupConfig.

  The methods load new HostGroupConfig from inventory file, creates new
  HostGroupConfig, updates exist HostGroupConfig and remove obsolete
  HostGroupConfig.

  Args:
    lab_name: the lab name.
    data: inventory data which was parsed by the ansible inventory module.
  """
  entity_from_file = {
      group.key: group for group in [
          _CreateHostGroupConfigEntityFromGroupInventory(lab_name, group)
          for group in data.groups.values()
      ]
  }
  logging.debug('Loaded %d HostGroupConfigs of lab %s',
                len(entity_from_file), lab_name)
  entity_from_ndb = {
      g.key: g for g in datastore_entities.HostGroupConfig.query(
          datastore_entities.HostGroupConfig.lab_name == lab_name).fetch()
  }
  need_update = []
  for key, group in entity_from_file.items():
    if not _CheckConfigEntitiesEqual(entity_from_ndb.get(key), group):
      need_update.append(group)
  ndb.put_multi(need_update)
  logging.debug('Updated %d HostGroupConfigs.', len(need_update))
  need_delete = set(entity_from_ndb.keys()).difference(entity_from_file.keys())
  ndb.delete_multi(need_delete)
  logging.debug('Removed %d HostGroupConfigs', len(need_delete))


def _UpdateHostConfigByInventoryData(lab_name, data):
  """Updates HostConfig inventory_groups.

  Args:
    lab_name: the lab name.
    data: the InventoryData object.
  """
  keys = []
  entities_from_file = {
      host.name: _CreateHostConfigEntityFromHostInventory(lab_name, host)
      for host in data.hosts.values()
  }
  for hostname in entities_from_file:
    keys.append(ndb.Key(datastore_entities.HostConfig, hostname))
  entities_from_ndb = {}
  for entity in ndb.get_multi(keys):
    if entity:
      entities_from_ndb[entity.hostname] = entity
  need_update = {}
  for hostname in entities_from_file:
    old = entities_from_ndb.get(hostname)
    new = entities_from_file[hostname]
    if not old:
      logging.debug('Creating host config %s', new)
      need_update[hostname] = new
    elif old.inventory_groups != new.inventory_groups:
      old.inventory_groups = new.inventory_groups
      logging.debug('Updating host config %s', old)
      need_update[hostname] = old
  ndb.put_multi(need_update.values())


def _GetLabInventoryFiles():
  """Gets inventory files.

  Yields:
    A tuple contains lab name and the inventory file name.
  """
  logging.debug('list lab dir in %s', _LAB_INVENTORY_DIR_PATH)
  for file in file_storage.ListFiles(_LAB_INVENTORY_DIR_PATH):
    if file.is_dir:
      lab_dir_match = _LAB_NAME_PATTERN.match(file.filename)
      if lab_dir_match and lab_dir_match.group(_LAB_GROUP_KEY):
        yield (lab_dir_match.group(_LAB_GROUP_KEY),
               _INVENTORY_FILE_FORMAT.format(file.filename))
    else:
      inventory_file_match = _INVENTORY_FILE_PATTERN.match(file.filename)
      if inventory_file_match and inventory_file_match.group(_LAB_GROUP_KEY):
        logging.debug('Gets inventory from lab dir: %s', file.filename)
        yield (inventory_file_match.group(_LAB_GROUP_KEY), file.filename)


def SyncInventoryGroupsToNDB():
  """Task to sync lab inventory to NDB."""
  for lab_name, inventory_file_name in _GetLabInventoryFiles():
    _SyncInventoryHostGroup(lab_name, inventory_file_name)


def _GetLabInventoryGroupVarFiles(lab_name):
  """Loads all group_var files for given lab.

  Args:
    lab_name: the lab name.
  Yields:
    A tuple contains lab name, group name and the group_var file object.
  """
  logging.debug('list group vars in %s',
                _INVENTORY_GROUP_VAR_DIR_FORMAT.format(
                    _LAB_INVENTORY_DIR_PATH, lab_name))
  for group_var in file_storage.ListFiles(
      _INVENTORY_GROUP_VAR_DIR_FORMAT.format(
          _LAB_INVENTORY_DIR_PATH, lab_name)):
    m = _INVENTORY_GROUP_VAR_PATTERN.match(group_var.filename)
    if not m or not m.group(_LAB_GROUP_KEY) or not m.group(
        _INVENTORY_GROUP_KEY):
      continue
    try:
      with file_storage.OpenFile(group_var.filename) as f:
        logging.debug('Reading group var file %s', group_var.filename)
        yield (m.group(_LAB_GROUP_KEY), m.group(_INVENTORY_GROUP_KEY), f)
    except plugins_base.ObjectNotFoundError:
      logging.error('group_var file not found in %s', group_var.filename)
      continue


def SyncInventoryGroupVarAccountsToNDB():
  """Task to sync lab inventory group_vars to NDB."""
  labs = datastore_entities.LabConfig.query().fetch()
  for lab in labs:
    for lab_name, group_name, group_var_file in _GetLabInventoryGroupVarFiles(
        lab.lab_name):
      group_var_dict = lab_config_util.ParseGroupVar(group_var_file)
      group = datastore_entities.HostGroupConfig.get_by_id(
          datastore_entities.HostGroupConfig.CreateId(lab_name, group_name))
      if not group:
        continue
      group.account_principals = group_var_dict.get(_GROUP_VAR_ACCOUNTS)
      group.put()


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
    SyncInventoryGroupsToNDB()
    SyncInventoryGroupVarAccountsToNDB()
  return common.HTTP_OK
