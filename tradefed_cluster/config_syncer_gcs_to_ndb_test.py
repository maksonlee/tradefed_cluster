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

import cloudstorage

from tradefed_cluster import config_syncer_gcs_to_ndb
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.configs import lab_config

TEST_DATA_PATH = 'test_yaml'
TEST_CLUSTER_YAML_FILE = 'dockerized-tf.yaml'


def GetTestFilePath(filename):
  return os.path.join(os.path.dirname(__file__), TEST_DATA_PATH, filename)


class ConfigSyncerBsToNdbTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    testbed_dependent_test.TestbedDependentTest.setUp(self)
    datastore_test_util.CreateCluster('free')
    datastore_test_util.CreateCluster('presubmit')
    datastore_test_util.CreateHost('free', 'atl-01.mtv')
    datastore_test_util.CreateHost('presubmit', 'atl-02.mtv')
    file_path = GetTestFilePath(TEST_CLUSTER_YAML_FILE)
    with cloudstorage.open(
        (config_syncer_gcs_to_ndb.LAB_CONFIG_DIR_PATH +
         TEST_CLUSTER_YAML_FILE), 'w') as storage_file:
      with open(file_path, 'r') as f:
        for line in f:
          storage_file.write(line)

  def testUpdateClusterConfigs(self):
    """Tests that check cluster configs are updated."""
    host_config1 = lab_config.CreateHostConfig(
        cluster_name='free',
        hostname='atl-01.mtv',
        host_login_name='log_name0',
        tf_global_config_path='path0')
    host_config2 = lab_config.CreateHostConfig(
        cluster_name='presubmit',
        hostname='atl-02.mtv',
        host_login_name='log_name1',
        tf_global_config_path='path1')
    # this cluster is not in ndb will be created
    host_config3 = lab_config.CreateHostConfig(
        cluster_name='presubmit2',
        hostname='atl-03.mtv',
        host_login_name='log_name2',
        tf_global_config_path='path2')
    cluster_configs = [host_config1.cluster_config_pb,
                       host_config2.cluster_config_pb,
                       host_config3.cluster_config_pb]
    config_syncer_gcs_to_ndb._UpdateClusterConfigs(cluster_configs)
    saved_cluster_config = datastore_entities.ClusterInfo.get_by_id(
        'free').cluster_config
    self.assertEqual(saved_cluster_config.cluster_name, 'free')
    self.assertEqual(saved_cluster_config.host_login_name, 'log_name0')
    saved_cluster_config = datastore_entities.ClusterInfo.get_by_id(
        'presubmit').cluster_config
    self.assertEqual(saved_cluster_config.cluster_name, 'presubmit')
    self.assertEqual(saved_cluster_config.host_login_name, 'log_name1')
    saved_cluster_config = datastore_entities.ClusterInfo.get_by_id(
        'presubmit2').cluster_config
    self.assertEqual(saved_cluster_config.cluster_name, 'presubmit2')
    self.assertEqual(saved_cluster_config.host_login_name, 'log_name2')

  def testUpdateHostConfigs(self):
    """Tests that check host configs are updated."""
    host_config1 = lab_config.CreateHostConfig(
        cluster_name='presubmit',
        hostname='atl-01.mtv',
        host_login_name='log_name0',
        tf_global_config_path='path0')
    host_config2 = lab_config.CreateHostConfig(
        cluster_name='presubmit',
        hostname='atl-02.mtv',
        host_login_name='log_name1',
        tf_global_config_path='path1')
    # this host is not in ndb will be created
    host_config3 = lab_config.CreateHostConfig(
        cluster_name='presubmit',
        hostname='atl-03.mtv',
        host_login_name='log_name2',
        tf_global_config_path='path2')
    host_configs = [host_config1.host_config_pb,
                    host_config2.host_config_pb,
                    host_config3.host_config_pb]
    config_syncer_gcs_to_ndb._UpdateHostConfigs(host_configs, 'presubmit')
    saved_host_config = datastore_entities.HostInfo.get_by_id(
        'atl-01.mtv').host_config
    self.assertEqual(saved_host_config.hostname, 'atl-01.mtv')
    self.assertEqual(saved_host_config.tf_global_config_path, 'path0')
    saved_host_config = datastore_entities.HostInfo.get_by_id(
        'atl-02.mtv').host_config
    self.assertEqual(saved_host_config.hostname, 'atl-02.mtv')
    self.assertEqual(saved_host_config.tf_global_config_path, 'path1')
    saved_host_config = datastore_entities.HostInfo.get_by_id(
        'atl-03.mtv').host_config
    self.assertEqual(saved_host_config.hostname, 'atl-03.mtv')
    self.assertEqual(saved_host_config.tf_global_config_path, 'path2')

  def testsyncToNDB(self):
    """test SyncToNDB."""
    config_syncer_gcs_to_ndb.SyncToNDB()
    cluster = datastore_entities.ClusterInfo.get_by_id('dockerized-tf')
    self.assertIsNotNone(cluster)
    cluster_config = cluster.cluster_config
    self.assertIsNotNone(cluster_config)
    self.assertEqual(cluster_config.cluster_name, 'dockerized-tf')
    self.assertEqual(cluster_config.host_login_name, 'android-test')
    self.assertEqual(cluster_config.tf_global_config_path,
                     'configs/cluster/dockerized-tf/cluster-config.xml')
    self.assertEqual(cluster_config.owners[0], 'android-test')


if __name__ == '__main__':
  unittest.main()
