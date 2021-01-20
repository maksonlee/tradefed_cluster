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

import flask

from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config
from tradefed_cluster.configs import lab_config as lab_config_util
from tradefed_cluster.services import file_storage
from tradefed_cluster.util import ndb_shim as ndb


BUCKET_NAME = 'tradefed_lab_configs'
LAB_CONFIG_DIR_PATH = '/{}/lab_configs/'.format(BUCKET_NAME)

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
  cluster_config_keys = []
  for cluster_config in cluster_configs:
    cluster_config_keys.append(
        ndb.Key(datastore_entities.ClusterConfig, cluster_config.cluster_name))

  entities = ndb.get_multi(cluster_config_keys)
  entities_to_update = []
  for entity, cluster_config in zip(entities, cluster_configs):
    new_config_entity = datastore_entities.ClusterConfig.FromMessage(
        cluster_config)
    if not _CheckConfigEntitiesEqual(entity, new_config_entity):
      logging.debug('Updating cluster config entity: %s.', new_config_entity)
      entities_to_update.append(new_config_entity)
  ndb.put_multi(entities_to_update)
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
        _UpdateHostConfigs(
            cluster_config_pb.host_configs, cluster_config_pb, lab_config_pb)


@APP.route('/cron/syncer/sync_gcs_ndb')
def SyncGCSToNDB():
  """Task to sync cluster and host config from gcs to ndb."""
  if env_config.CONFIG.should_sync_lab_config:
    logging.debug('"should_sync_lab_config" is enabled.')
    SyncToNDB()

  return common.HTTP_OK
