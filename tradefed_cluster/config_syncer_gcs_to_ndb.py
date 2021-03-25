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
from __future__ import google_type_annotations

import logging
import re
from typing import Generator, Tuple

from ansible.inventory import data as inventory_data
from ansible.inventory import group as inventory_group
from ansible.inventory import host as inventory_host
from ansible.parsing import dataloader
from ansible.plugins.inventory import ini
import flask


from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config
from tradefed_cluster.configs import lab_config as lab_config_util
from tradefed_cluster.plugins import base as plugins_base
from tradefed_cluster.services import file_storage
from tradefed_cluster.util import ndb_shim as ndb


BUCKET_NAME = 'tradefed_lab_configs'
LAB_CONFIG_DIR_PATH = '/{}/lab_configs/'.format(BUCKET_NAME)
_LAB_INVENTORY_DIR_PATH = '/{}/lab_inventory/'.format(BUCKET_NAME)
_INVENTORY_GROUPS = 'inventory_groups'
_FileInfo = plugins_base.FileInfo
_APP = flask.Flask(__name__)
_LAB_NAME_PATTERN = re.compile(r'.*\/lab_inventory\/(?P<lab_name>.*)')
_LAB_GROUP_NAME = 'lab_name'
_INVENTORY_FILE_FORMAT = '{}/hosts'

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
  entity_dict.pop('update_time')
  new_entity_dict = new_entity.to_dict()
  new_entity_dict.pop('update_time')
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
      _UpdateClusterConfigs(lab_config_pb.cluster_configs)
      for cluster_config_pb in lab_config_pb.cluster_configs:
        _UpdateHostConfigs(cluster_config_pb.host_configs, cluster_config_pb,
                           lab_config_pb)


class _GcsDataLoader(dataloader.DataLoader):
  """The data loader use gcs file_storeage to read the files."""

  def _get_file_contents(self, file_name: str) -> Tuple[bytes, bool]:
    """Gets file contents and the show_content flag from given file name."""
    with file_storage.OpenFile(file_name) as f:
      return f.read(), False


def _LoadInventoryData(path: str) -> inventory_data.InventoryData:
  """Loads inventory data from given path."""
  data = inventory_data.InventoryData()
  ini.InventoryModule().parse(data, _GcsDataLoader(), path)
  return data


def _CreateHostConfigEntityFromHostInventory(
    lab_name: str, host: inventory_host.Host) -> datastore_entities.HostConfig:
  """Creates HostConfig from HostInventory."""
  return datastore_entities.HostConfig(
      id=host.name,
      lab_name=lab_name,
      hostname=host.name,
      inventory_groups=sorted(set([g.name for g in host.groups])))


def _CreateGroupConfigEntityFromGroupInventory(
    lab_name: str, group: inventory_group.Group
    ) -> datastore_entities.GroupConfig:
  """Creates GroupConfig from Group model."""
  entity = datastore_entities.GroupConfig(
      id=datastore_entities.GroupConfig.CreateId(lab_name, group.name),
      name=group.name,
      lab=ndb.Key(datastore_entities.LabConfig, lab_name))
  entity.parent_groups = [
      ndb.Key(datastore_entities.GroupConfig,
              datastore_entities.GroupConfig.CreateId(lab_name, g.name)
              ) for g in group.parent_groups]
  return entity


def _SyncInventoryHostGroup(lab_name: str, file_name: str) -> None:
  """Loads inventory file to updates HostConfig and GroupConfig."""
  data = _LoadInventoryData(file_name)
  _UpdateGroupConfigByInventoryData(lab_name, data)
  _UpdateHostConfigByInventoryData(lab_name, data)


def _UpdateGroupConfigByInventoryData(
    lab_name: str, data: inventory_data.InventoryData) -> None:
  """Updates GroupConfig."""
  entity_from_file = {
      group.key: group for group in [
          _CreateGroupConfigEntityFromGroupInventory(lab_name, group)
          for group in data.groups.values()
      ]
  }
  entity_from_ndb = {
      g.key: g for g in datastore_entities.GroupConfig.query(
          datastore_entities.GroupConfig.lab == ndb.Key(
              datastore_entities.LabConfig, lab_name)).fetch()}
  need_update = []
  for key, group in entity_from_file.items():
    if key not in entity_from_ndb:
      need_update.append(group)
      continue
    if group.to_dict() != entity_from_ndb[key]:
      need_update.append(group)
  ndb.put_multi(need_update)
  ndb.delete_multi(
      set(entity_from_ndb.keys()).difference(entity_from_file.keys()))


def _UpdateHostConfigByInventoryData(
    lab_name: str, data: inventory_data.InventoryData) -> None:
  """Updates HostConfig inventory_groups."""
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
      logging.info('Creating host config %s', new)
      need_update[hostname] = new
    elif old.inventory_groups != new.inventory_groups:
      old.inventory_groups = new.inventory_groups
      logging.info('Updating host config %s', old)
      need_update[hostname] = old
  ndb.put_multi(need_update.values())


def _GetLabInventoryFiles() -> Generator[Tuple[str, str], None, None]:
  """Gets inventory files."""
  for lab_dir in file_storage.ListFiles(_LAB_INVENTORY_DIR_PATH):
    logging.info('Gets inventory from lab dir: %s', lab_dir)
    if not lab_dir.is_dir:
      continue
    lab_dir_match = _LAB_NAME_PATTERN.match(lab_dir.filename)
    if not lab_dir_match or not lab_dir_match.group(_LAB_GROUP_NAME):
      continue
    yield (lab_dir_match.group(_LAB_GROUP_NAME),
           _INVENTORY_FILE_FORMAT.format(lab_dir.filename))


def SyncInventoryGroupsToNDB():
  """Task to sync lab inventory to NDB."""
  for lab_name, inventory_file_name in _GetLabInventoryFiles():
    _SyncInventoryHostGroup(lab_name, inventory_file_name)


@APP.route('/cron/syncer/sync_gcs_ndb')
def SyncGCSToNDB():
  """Task to sync cluster and host config from gcs to ndb."""
  if env_config.CONFIG.should_sync_lab_config:
    logging.debug('"should_sync_lab_config" is enabled.')
    SyncToNDB()
    SyncInventoryGroupsToNDB()
  return common.HTTP_OK
