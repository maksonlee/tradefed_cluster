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

"""Tests for config_syncer_bs_to_ndb.py."""
import os
import unittest

import six

from tradefed_cluster import config_syncer_gcs_to_ndb
from tradefed_cluster import datastore_entities
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.util import ndb_shim as ndb

TEST_DATA_PATH = 'test_yaml'
TEST_CLUSTER_YAML_FILE = 'dockerized-tf.yaml'


def _GetTestFilePath(filename):
  return os.path.join(os.path.dirname(__file__), TEST_DATA_PATH, filename)


class ConfigSyncerGCSToNdbTest(testbed_dependent_test.TestbedDependentTest):
  """Unit test for config_syncer_gcs_to_ndb."""

  def setUp(self):
    testbed_dependent_test.TestbedDependentTest.setUp(self)
    file_path = _GetTestFilePath(TEST_CLUSTER_YAML_FILE)
    with self.mock_file_storage.OpenFile(
        (config_syncer_gcs_to_ndb.LAB_CONFIG_DIR_PATH +
         TEST_CLUSTER_YAML_FILE), 'w') as storage_file:
      with open(file_path, 'r') as f:
        for line in f:
          storage_file.write(six.ensure_binary(line))

  def _CreateHostConfigEntity(
      self, hostname, host_login_user='login_user',
      tf_global_config_path='tf_config.xml'):
    """Create HostConfig entity, store in datastore and return."""
    host_config_entity = datastore_entities.HostConfig(
        id=hostname,
        hostname=hostname,
        host_login_name=host_login_user,
        tf_global_config_path=tf_global_config_path)
    host_config_entity.put()
    return host_config_entity

  def _CreateClusterConfigEntity(
      self, cluster_name, host_login_user='login_user',
      owners=('owner1', 'owner2'), tf_global_config_path='cluster_config.xml'):
    """Create ClusterConfig entity, store in datastore and return."""
    cluster_config_entity = datastore_entities.ClusterConfig(
        id=cluster_name,
        cluster_name=cluster_name,
        host_login_name=host_login_user,
        owners=list(owners),
        tf_global_config_path=tf_global_config_path)
    cluster_config_entity.put()
    return cluster_config_entity

  def testUpdateLabConfig(self):
    """Tests that check lab config is updated."""
    lab_config_pb = config_syncer_gcs_to_ndb.GetLabConfigFromGCS(
        config_syncer_gcs_to_ndb.LAB_CONFIG_DIR_PATH + TEST_CLUSTER_YAML_FILE)
    config_syncer_gcs_to_ndb._UpdateLabConfig(lab_config_pb)

    ndb.get_context().clear_cache()
    res = datastore_entities.LabConfig.get_by_id('lab1')
    self.assertEqual('lab1', res.lab_name)
    self.assertEqual(['lab_user1', 'user1'], res.owners)
    res = datastore_entities.LabInfo.get_by_id('lab1')
    self.assertEqual('lab1', res.lab_name)

  def testUpdateClusterConfigs(self):
    """Tests that check cluster configs are updated."""
    self._CreateClusterConfigEntity(
        'cluster1', tf_global_config_path='old_tf_global_path.xml')
    lab_config_pb = config_syncer_gcs_to_ndb.GetLabConfigFromGCS(
        config_syncer_gcs_to_ndb.LAB_CONFIG_DIR_PATH + TEST_CLUSTER_YAML_FILE)
    config_syncer_gcs_to_ndb._UpdateClusterConfigs(
        lab_config_pb.cluster_configs)

    ndb.get_context().clear_cache()
    # Cluster1 is overried.
    res = datastore_entities.ClusterConfig.get_by_id('cluster1')
    self.assertEqual('cluster1', res.cluster_name)
    self.assertEqual('login_user1', res.host_login_name)
    self.assertEqual(['owner1', 'owner2'], res.owners)
    self.assertEqual('configs/cluster1/config.xml', res.tf_global_config_path)
    res = datastore_entities.ClusterConfig.get_by_id('cluster2')
    self.assertEqual('cluster2', res.cluster_name)
    self.assertEqual('login_user2', res.host_login_name)
    self.assertEqual(['owner1'], res.owners)
    self.assertEqual('configs/cluster2/config.xml', res.tf_global_config_path)

  def testUpdateHostConfigs(self):
    """Tests that check host configs are updated."""
    self._CreateHostConfigEntity(
        'homer-atc1', tf_global_config_path='old_path.xml')
    lab_config_pb = config_syncer_gcs_to_ndb.GetLabConfigFromGCS(
        config_syncer_gcs_to_ndb.LAB_CONFIG_DIR_PATH + TEST_CLUSTER_YAML_FILE)
    config_syncer_gcs_to_ndb._UpdateHostConfigs(
        lab_config_pb.cluster_configs[0].host_configs,
        lab_config_pb.cluster_configs[0],
        lab_config_pb)

    ndb.get_context().clear_cache()
    # homer-atc1 is overrided.
    res = datastore_entities.HostConfig.get_by_id('homer-atc1')
    self.assertEqual(res.hostname, 'homer-atc1')
    self.assertEqual(res.tf_global_config_path, 'configs/homer-atc1/config.xml')
    self.assertEqual(res.lab_name, 'lab1')
    self.assertEqual(res.cluster_name, 'cluster1')
    self.assertCountEqual(res.owners, ['owner1', 'owner2'])
    self.assertTrue(res.graceful_shutdown)
    self.assertTrue(res.enable_ui_update)
    self.assertEqual(res.shutdown_timeout_sec, 1000)
    res = datastore_entities.HostConfig.get_by_id('homer-atc2')
    self.assertEqual(res.hostname, 'homer-atc2')
    self.assertEqual(res.tf_global_config_path, 'configs/homer-atc2/config.xml')
    self.assertEqual(res.lab_name, 'lab1')
    self.assertCountEqual(res.owners, ['owner1', 'owner2'])
    self.assertTrue(res.graceful_shutdown)
    self.assertFalse(res.enable_ui_update)
    self.assertEqual(res.shutdown_timeout_sec, 1000)

  def testSyncToNDB(self):
    """test SyncToNDB."""
    config_syncer_gcs_to_ndb.SyncToNDB()

    ndb.get_context().clear_cache()
    res = datastore_entities.LabConfig.get_by_id('lab1')
    self.assertEqual('lab1', res.lab_name)
    res = datastore_entities.ClusterConfig.get_by_id('cluster1')
    self.assertEqual('cluster1', res.cluster_name)
    res = datastore_entities.ClusterConfig.get_by_id('cluster2')
    self.assertEqual('cluster2', res.cluster_name)
    res = datastore_entities.HostConfig.get_by_id('homer-atc1')
    self.assertEqual('homer-atc1', res.hostname)
    res = datastore_entities.HostConfig.get_by_id('homer-atc2')
    self.assertEqual('homer-atc2', res.hostname)
    res = datastore_entities.HostConfig.get_by_id('homer-atc3')
    self.assertEqual('homer-atc3', res.hostname)
    res = datastore_entities.HostConfig.get_by_id('homer-atc4')
    self.assertEqual('homer-atc4', res.hostname)


if __name__ == '__main__':
  unittest.main()
