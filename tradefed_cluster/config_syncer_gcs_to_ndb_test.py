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
from tradefed_cluster.configs import lab_config as lab_config_util
from tradefed_cluster.configs import unified_lab_config as unified_lab_config_util
from tradefed_cluster.util import ndb_shim as ndb

TEST_DATA_PATH = 'test_yaml'
LAB_CONFIG_FILE = 'dockerized-tf.yaml'
PRESUBMIT_LAB_CONFIG_FILE = 'presubmit-dockerized-tf.yaml'
LAB_INV_FILE = 'hosts'
LAB_GROUP_VAR_FILE = 'dhcp.yaml'


def _GetTestFilePath(filename):
  return os.path.join(os.path.dirname(__file__), TEST_DATA_PATH, filename)


class ConfigSyncerGCSToNdbTest(testbed_dependent_test.TestbedDependentTest):
  """Unit test for config_syncer_gcs_to_ndb."""

  def setUp(self):
    testbed_dependent_test.TestbedDependentTest.setUp(self)

    for lab_config_path in [LAB_CONFIG_FILE, PRESUBMIT_LAB_CONFIG_FILE]:
      file_path = _GetTestFilePath(lab_config_path)
      with self.mock_file_storage.OpenFile(
          (config_syncer_gcs_to_ndb.LAB_CONFIG_DIR_PATH +
           lab_config_path), 'w') as storage_file:
        with open(file_path, 'r') as f:
          for line in f:
            storage_file.write(six.ensure_binary(line))
    file_path = _GetTestFilePath(LAB_INV_FILE)
    with self.mock_file_storage.OpenFile(
        (config_syncer_gcs_to_ndb._LAB_INVENTORY_DIR_PATH + 'lab1/' +
         LAB_INV_FILE), 'w') as storage_file:
      with open(file_path, 'r') as f:
        for line in f:
          storage_file.write(six.ensure_binary(line))
    file_path = _GetTestFilePath(LAB_GROUP_VAR_FILE)
    with self.mock_file_storage.OpenFile(
        (config_syncer_gcs_to_ndb._LAB_INVENTORY_DIR_PATH + 'lab1/group_vars/' +
         LAB_GROUP_VAR_FILE), 'w') as storage_file:
      with open(file_path, 'r') as f:
        for line in f:
          storage_file.write(six.ensure_binary(line))

  def _CreateHostConfigEntity(self,
                              hostname,
                              host_login_user='login_user',
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
        config_syncer_gcs_to_ndb.LAB_CONFIG_DIR_PATH + LAB_CONFIG_FILE)
    config_syncer_gcs_to_ndb._UpdateLabConfig(
        lab_config_pb.lab_name, [lab_config_pb], None)
    ndb.get_context().clear_cache()
    res = datastore_entities.LabConfig.get_by_id(lab_config_pb.lab_name)
    self.assertEqual('lab1', res.lab_name)
    self.assertEqual(['lab_user1', 'user1'], res.owners)
    res = datastore_entities.LabInfo.get_by_id('lab1')
    self.assertEqual('lab1', res.lab_name)

  def testUpdateLabConfig_withMultipleMTTLabConfigs(self):
    """Tests UpdateLabConfig works for lab defined in multiple mtt lab config."""
    lab_config_pb = config_syncer_gcs_to_ndb.GetLabConfigFromGCS(
        config_syncer_gcs_to_ndb.LAB_CONFIG_DIR_PATH + LAB_CONFIG_FILE)
    presubmit_lab_config_pb = config_syncer_gcs_to_ndb.GetLabConfigFromGCS(
        config_syncer_gcs_to_ndb.LAB_CONFIG_DIR_PATH +
        PRESUBMIT_LAB_CONFIG_FILE)
    config_syncer_gcs_to_ndb._UpdateLabConfig(
        lab_config_pb.lab_name, [lab_config_pb, presubmit_lab_config_pb], None)
    ndb.get_context().clear_cache()
    res = datastore_entities.LabConfig.get_by_id(lab_config_pb.lab_name)
    self.assertEqual('lab1', res.lab_name)
    self.assertEqual(['lab_user1', 'user1', 'user2'], res.owners)
    res = datastore_entities.LabInfo.get_by_id('lab1')
    self.assertEqual('lab1', res.lab_name)

  def testUpdateClusterConfigs(self):
    """Tests that check cluster configs are updated."""
    self._CreateClusterConfigEntity(
        'cluster1', tf_global_config_path='old_tf_global_path.xml')
    lab_config_pb = config_syncer_gcs_to_ndb.GetLabConfigFromGCS(
        config_syncer_gcs_to_ndb.LAB_CONFIG_DIR_PATH + LAB_CONFIG_FILE)
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

  def testUpdateClusterConfigs_withDuplicateClusterConfig(self):
    """Tests that check lab configs with duplicated clusters are updated."""
    config_file = 'lab-config-with-duplicated-cluster.yaml'
    file_path = _GetTestFilePath(config_file)
    with self.mock_file_storage.OpenFile(
        (config_syncer_gcs_to_ndb.LAB_CONFIG_DIR_PATH +
         config_file), 'w') as storage_file:
      with open(file_path, 'r') as f:
        for line in f:
          storage_file.write(six.ensure_binary(line))
    self._CreateClusterConfigEntity(
        'cluster1', tf_global_config_path='old_tf_global_path.xml')
    lab_config_pb = config_syncer_gcs_to_ndb.GetLabConfigFromGCS(
        config_syncer_gcs_to_ndb.LAB_CONFIG_DIR_PATH + config_file)
    config_syncer_gcs_to_ndb._UpdateClusterConfigs(
        lab_config_pb.cluster_configs)

    ndb.get_context().clear_cache()
    # Cluster1 is overried.
    res = datastore_entities.ClusterConfig.get_by_id('cluster1')
    self.assertEqual('cluster1', res.cluster_name)
    self.assertEqual('configs/cluster1_duplicated/config.xml',
                     res.tf_global_config_path)

  def testUpdateHostConfigs(self):
    """Tests that check host configs are updated."""
    self._CreateHostConfigEntity(
        'homer-atc1.lab1.google.com', tf_global_config_path='old_path.xml')
    lab_config_pb = config_syncer_gcs_to_ndb.GetLabConfigFromGCS(
        config_syncer_gcs_to_ndb.LAB_CONFIG_DIR_PATH + LAB_CONFIG_FILE)
    host_to_host_config = {}
    for cluster_config_pb in lab_config_pb.cluster_configs:
      for host_config_pb in cluster_config_pb.host_configs:
        host_to_host_config[host_config_pb.hostname] = (
            lab_config_util.HostConfig(
                host_config_pb, cluster_config_pb, lab_config_pb))
    lab_config = unified_lab_config_util.Parse(
        os.path.join(config_syncer_gcs_to_ndb._LAB_INVENTORY_DIR_PATH, 'lab1/',
                     LAB_INV_FILE),
        config_syncer_gcs_to_ndb._GcsDataLoader())
    host_to_unified_host_config = {
        host.name: host for host in lab_config.ListHosts()}

    config_syncer_gcs_to_ndb._UpdateHostConfigs(
        host_to_host_config, host_to_unified_host_config)

    ndb.get_context().clear_cache()
    # homer-atc1 is overrided.
    res = datastore_entities.HostConfig.get_by_id('homer-atc1.lab1.google.com')
    self.assertEqual(res.hostname, 'homer-atc1.lab1.google.com')
    self.assertEqual(res.tf_global_config_path, 'configs/homer-atc1/config.xml')
    self.assertEqual(res.lab_name, 'lab1')
    self.assertEqual(res.cluster_name, 'cluster1')
    self.assertCountEqual(
        res.owners, ['lab_user1', 'user1', 'owner1', 'owner2'])
    self.assertTrue(res.graceful_shutdown)
    self.assertTrue(res.enable_ui_update)
    self.assertEqual(res.shutdown_timeout_sec, 1000)
    self.assertEqual(['all', 'pixellab'], res.inventory_groups)

    res = datastore_entities.HostConfig.get_by_id('homer-atc2.lab1.google.com')
    self.assertEqual(res.hostname, 'homer-atc2.lab1.google.com')
    self.assertEqual(res.tf_global_config_path, 'configs/homer-atc2/config.xml')
    self.assertEqual(res.lab_name, 'lab1')
    self.assertCountEqual(
        res.owners, ['lab_user1', 'user1', 'owner1', 'owner2'])
    self.assertTrue(res.graceful_shutdown)
    self.assertFalse(res.enable_ui_update)
    self.assertEqual(res.shutdown_timeout_sec, 1000)
    self.assertEqual(['all', 'tf', 'dtf'], res.inventory_groups)

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
    host_configs = datastore_entities.HostConfig.query().fetch()
    self.assertEqual(9, len(host_configs))
    self.assertSetEqual(
        set([
            'dhcp1.lab1.google.com',
            'dhcp2.lab1.google.com',
            'homer-atc1.lab1.google.com',
            'homer-atc2.lab1.google.com',
            'homer-atc3.lab1.google.com',
            'homer-atc4.lab1.google.com',
            'presubmit1.lab1.google.com',
            'presubmit2.lab1.google.com',
            'homer-atcmh1.lab1.google.com',
        ]),
        set(host.hostname for host in host_configs))
    res = datastore_entities.HostConfig.get_by_id('homer-atc1.lab1.google.com')
    self.assertEqual('homer-atc1.lab1.google.com', res.hostname)
    self.assertSameElements(['all', 'pixellab'], res.inventory_groups)
    self.assertEqual('configs/homer-atc1/config.xml', res.tf_global_config_path)
    res = datastore_entities.HostConfig.get_by_id('homer-atc2.lab1.google.com')
    self.assertEqual('homer-atc2.lab1.google.com', res.hostname)
    self.assertSameElements(['all', 'dtf', 'tf'], res.inventory_groups)
    self.assertEqual('configs/homer-atc2/config.xml', res.tf_global_config_path)
    res = datastore_entities.HostConfig.get_by_id('homer-atc3.lab1.google.com')
    self.assertEqual('homer-atc3.lab1.google.com', res.hostname)
    self.assertSameElements(['all', 'storage_tf', 'tf'], res.inventory_groups)
    self.assertEqual('configs/homer-atc3/config.xml', res.tf_global_config_path)
    res = datastore_entities.HostConfig.get_by_id('homer-atc4.lab1.google.com')
    self.assertEqual('homer-atc4.lab1.google.com', res.hostname)
    self.assertEmpty(res.inventory_groups)
    self.assertEqual('configs/cluster2/config.xml', res.tf_global_config_path)
    res = datastore_entities.HostConfig.get_by_id(
        'homer-atcmh1.lab1.google.com')
    self.assertEqual('homer-atcmh1.lab1.google.com', res.hostname)
    self.assertSameElements(['all', 'mh'], res.inventory_groups)
    self.assertIsNone(res.tf_global_config_path)
    res = datastore_entities.HostConfig.get_by_id('dhcp1.lab1.google.com')
    self.assertSameElements(
        ['all', 'server', 'jump', 'dhcp', 'pxe'],
        res.inventory_groups)
    res = datastore_entities.HostConfig.get_by_id('dhcp2.lab1.google.com')
    self.assertSameElements(
        ['all', 'server', 'jump', 'dhcp', 'pxe'],
        res.inventory_groups)

  def testLoadInventoryData(self):
    config = unified_lab_config_util.Parse(
        os.path.join(config_syncer_gcs_to_ndb._LAB_INVENTORY_DIR_PATH, 'lab1/',
                     LAB_INV_FILE),
        config_syncer_gcs_to_ndb._GcsDataLoader())

    dhcp_group = config.GetGroup('dhcp')
    self.assertEqual(
        {
            'android-test-admin': {
                'enable_sudo': True,
                'principals': [
                    'group/group-one', 'group/group-two', 'user1', 'user2']
            },
            'android-test': {
                'principals': [
                    'group/group-three', 'user3', 'user4'
                ]
            }
        },
        dhcp_group.direct_vars['accounts'])
    dhcp1 = config.GetHost('dhcp1.lab1.google.com')
    self.assertEqual(
        ['all', 'server', 'dhcp', 'jump', 'pxe'],
        [g.name for g in dhcp1.groups])
    self.assertEqual(
        ['all', 'server', 'dhcp', 'jump', 'pxe'],
        [g.name for g in config.GetHost('dhcp1.lab1.google.com').groups])
    self.assertEqual(
        ['all', 'pixellab'],
        [g.name for g in config.GetHost('homer-atc1.lab1.google.com').groups])
    self.assertEqual(
        ['all', 'tf', 'dtf'],
        [g.name for g in
         config.GetHost('homer-atc2.lab1.google.com').groups])
    self.assertEqual(
        ['all', 'tf', 'storage_tf'],
        [g.name for g in
         config.GetHost('homer-atc3.lab1.google.com').groups])


if __name__ == '__main__':
  unittest.main()
