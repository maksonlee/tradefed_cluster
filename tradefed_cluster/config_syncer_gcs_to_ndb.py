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

import cloudstorage
import webapp2

from google.appengine.ext import ndb

from tradefed_cluster import datastore_entities
from tradefed_cluster.configs import lab_config

BUCKET_NAME = 'tradefed_lab_configs'
LAB_CONFIG_DIR_PATH = '/{}/lab_configs/'.format(BUCKET_NAME)


def GetLabConfigFromGCS(lab_config_path):
  """Get lab config from GCS.

  Args:
    lab_config_path: a string of the file path on Google Cloud Storage.
  Returns:
    a lab config proto
  """
  try:
    return lab_config.Parse(cloudstorage.open(lab_config_path))
  except cloudstorage.NotFoundError as err:
    logging.error('Cannot open lab config file: %s due to: %s',
                  lab_config_path, err)
  except lab_config.ConfigError as err:
    logging.error('Fail to parse file: %s due to: %s', lab_config_path, err)


def _UpdateClusterConfigs(cluster_configs):
  """Update cluster configs in ClusterInfo entity to ndb.

  Args:
    cluster_configs: a list of cluster configs proto.
  """
  logging.debug('Updating cluster configs.')
  cluster_entity_keys = []
  cluster_to_config_obj = {}
  for cluster_config in cluster_configs:
    config_obj = datastore_entities.ClusterConfig.FromMessage(cluster_config)
    cluster_entity_keys.append(
        ndb.Key(datastore_entities.ClusterInfo, cluster_config.cluster_name))
    cluster_to_config_obj[cluster_config.cluster_name] = config_obj
  entities = ndb.get_multi(cluster_entity_keys)
  entities_to_update = []
  # Update the exist cluster infos' config.
  for cluster_info in entities:
    if not cluster_info:
      continue
    new_config = cluster_to_config_obj.pop(cluster_info.cluster)
    if cluster_info.cluster_config != new_config:
      logging.debug('Updating cluster with config: %s.', new_config)
      cluster_info.cluster_config = new_config
      entities_to_update.append(cluster_info)
  # Create and add new cluster infos.
  while cluster_to_config_obj:
    _, new_config = cluster_to_config_obj.popitem()
    logging.debug('Creating new cluster with config: %s.', new_config)
    new_cluster = datastore_entities.ClusterInfo(
        id=new_config.cluster_name,
        cluster=new_config.cluster_name,
        cluster_config=new_config)
    entities_to_update.append(new_cluster)

  ndb.put_multi(entities_to_update)
  logging.debug('Cluster configs updated.')


def _UpdateHostConfigs(host_configs, cluster_name):
  """Update host configs in HostInfo entities to ndb.

  Args:
    host_configs: a list of host configs.
    cluster_name: the name of cluster the hosts belong to.
  """
  logging.debug('Updating host configs for cluster: %s.', cluster_name)
  host_entity_keys = []
  host_to_config_obj = {}
  for host_config in host_configs:
    config_obj = datastore_entities.HostConfig.FromMessage(host_config)
    host_entity_keys.append(
        ndb.Key(datastore_entities.HostInfo, host_config.hostname))
    host_to_config_obj[host_config.hostname] = config_obj
  entities = ndb.get_multi(host_entity_keys)
  entities_to_update = []
  # Update the exist cluster infos' config.
  for host_info in entities:
    if not host_info:
      continue
    new_config = host_to_config_obj.pop(host_info.hostname)
    if host_info.host_config != new_config:
      logging.debug('Updating host with config: %s.', new_config)
      host_info.host_config = new_config
      entities_to_update.append(host_info)
      # Create and add new cluster infos.
  while host_to_config_obj:
    _, new_config = host_to_config_obj.popitem()
    logging.debug('Creating new host with config: %s.', new_config)
    new_host = datastore_entities.HostInfo(
        id=new_config.hostname,
        hostname=new_config.hostname,
        physical_cluster=cluster_name,
        host_config=new_config)
    entities_to_update.append(new_host)
  ndb.put_multi(entities_to_update)
  logging.debug('Host configs updated.')


def SyncToNDB():
  """Sync file from gcs to ndb."""
  stats = cloudstorage.listbucket(LAB_CONFIG_DIR_PATH)
  for stat in stats:
    if stat.filename.endswith('.yaml'):
      logging.debug('Processing cloudstorage file: %s', stat.filename)
      lab_config_pb = GetLabConfigFromGCS(stat.filename)
      _UpdateClusterConfigs(lab_config_pb.cluster_configs)
      for cluster_config in lab_config_pb.cluster_configs:
        _UpdateHostConfigs(
            cluster_config.host_configs, cluster_config.cluster_name)


class GCSToNDBSyncer(webapp2.RequestHandler):
  """Task to sync cluster and host config from gcs to ndb."""

  def get(self):
    SyncToNDB()


APP = webapp2.WSGIApplication([(r'/.*', GCSToNDBSyncer)], debug=True)
