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

"""Tests for config."""
import os
import tempfile
import unittest

import six

from tradefed_cluster.configs import lab_config
from tradefed_cluster.configs import lab_config_pb2

TEST_DATA_PATH = 'testdata'


def GetTestFilePath(filename):
  return os.path.join(os.path.dirname(__file__), TEST_DATA_PATH, filename)


class ConfigTest(unittest.TestCase):
  """Unit test for config."""

  def testParse(self):
    """Test parse a normal config."""
    config_path = GetTestFilePath('valid/config.yaml')
    lab_config_pb = None
    with open(config_path, 'r') as f:
      lab_config_pb = lab_config.Parse(f)

    self.assertEqual('lab1', lab_config_pb.lab_name)
    self.assertEqual('lab_user1', lab_config_pb.host_login_name)
    self.assertEqual(['lab_user1', 'user1'], lab_config_pb.owners)
    self.assertEqual('tfc_url', lab_config_pb.control_server_url)
    self.assertEqual('lab_docker_image', lab_config_pb.docker_image)
    self.assertEqual('docker_server_1', lab_config_pb.docker_server)
    self.assertEqual('AStringToRepresentApiKey', lab_config_pb.engprod_api_key)
    self.assertTrue(lab_config_pb.enable_stackdriver)
    self.assertTrue(lab_config_pb.enable_autoupdate)
    self.assertTrue(lab_config_pb.enable_ui_update)
    self.assertEqual(lab_config_pb2.ON_PREMISE, lab_config_pb.operation_mode)
    self.assertEqual('path/to/key.json',
                     lab_config_pb.service_account_json_key_path)
    self.assertEqual('lab_sv_key',
                     lab_config_pb.service_account_key_secret_id)
    self.assertEqual('secret_project_id',
                     lab_config_pb.secret_project_id)
    self.assertEqual('sa@project.google.com',
                     lab_config_pb.service_account)
    self.assertEqual(
        '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '
        '-F /path/to/ssh/config -C',
        lab_config_pb.ssh_arg)
    self.assertEqual(2, len(lab_config_pb.cluster_configs))
    cluster = lab_config_pb.cluster_configs[0]
    self.assertEqual('cluster1', cluster.cluster_name)
    self.assertEqual('user1', cluster.host_login_name)
    self.assertEqual(['user1', 'user2'], cluster.owners)
    self.assertEqual('path/to/config.xml', cluster.tf_global_config_path)
    self.assertEqual('tfc_url', cluster.control_server_url)
    self.assertTrue(cluster.graceful_shutdown)
    self.assertEqual(600, cluster.shutdown_timeout_sec)
    self.assertTrue(cluster.enable_stackdriver)
    self.assertTrue(cluster.enable_autoupdate)
    self.assertEqual(['--arg1', 'value1'], cluster.extra_docker_args)
    self.assertEqual('gcr.io/dockerized-tradefed/tradefed:golden',
                     cluster.docker_image)
    self.assertEqual('docker_server_2', cluster.docker_server)
    self.assertEqual(2, len(cluster.tmpfs_configs))
    self.assertEqual('/atmpfs', cluster.tmpfs_configs[0].path)
    self.assertEqual(1000, cluster.tmpfs_configs[0].size)
    self.assertEqual('/btmpfs', cluster.tmpfs_configs[1].path)
    self.assertEqual(3, len(cluster.host_configs))
    host = cluster.host_configs[0]
    self.assertEqual('host1', host.hostname)
    self.assertEqual(1, len(host.tmpfs_configs))
    self.assertEqual('/atmpfs', host.tmpfs_configs[0].path)
    self.assertEqual(2000, host.tmpfs_configs[0].size)
    self.assertEqual('750', host.tmpfs_configs[0].mode)
    host = cluster.host_configs[1]
    self.assertEqual('host2', host.hostname)
    self.assertTrue(host.enable_ui_update)
    host = cluster.host_configs[2]
    self.assertEqual('host3', host.hostname)
    self.assertEqual('path/to/new/config.xml',
                     host.tf_global_config_path)

    cluster = lab_config_pb.cluster_configs[1]
    self.assertEqual('cluster2', cluster.cluster_name)
    self.assertEqual('path/to/config.xml', cluster.tf_global_config_path)
    self.assertEqual(0, len(list(cluster.extra_docker_args)))
    self.assertEqual(2, len(cluster.host_configs))
    self.assertEqual('host4', cluster.host_configs[0].hostname)
    self.assertEqual('host5', cluster.host_configs[1].hostname)
    self.assertEqual(3600, cluster.shutdown_timeout_sec)
    self.assertTrue(cluster.enable_ui_update)

  def testParse_invalidYaml(self):
    """Test config file not used lines."""
    config_path = GetTestFilePath('invalid/config_invalid_yaml.yaml')
    with self.assertRaises(lab_config.ConfigError):
      with open(config_path, 'r') as f:
        lab_config.Parse(f)

  def testParse_noClusters(self):
    """Test config file with no 'cluster_configs'."""
    config_path = GetTestFilePath('invalid/config_no_clusters.yaml')
    with self.assertRaises(lab_config.ConfigError):
      with open(config_path, 'r') as f:
        lab_config.Parse(f)

  def testParse_extraLines(self):
    """Test config file not used lines."""
    config_path = GetTestFilePath('invalid/config_extra_lines.yaml')
    with self.assertRaises(lab_config.ConfigError):
      with open(config_path, 'r') as f:
        lab_config.Parse(f)

  def testParse_invalidKey(self):
    """Test config file with invalid key."""
    config_path = GetTestFilePath('invalid/config_invalid_key.yaml')
    with self.assertRaises(lab_config.ConfigError):
      with open(config_path, 'r') as f:
        lab_config.Parse(f)

  def testParse_emptyHostConfigs(self):
    """Test config file with cluster but empty host_configs."""
    # Has host_configs field but the field is empty is invalid.
    # This can not be pased by java's yaml lib.
    config_path = GetTestFilePath('invalid/config_empty_host_configs.yaml')
    with self.assertRaisesRegex(
        lab_config.ConfigError,
        r'when expecting a sequence\nfound a blank string'):
      with open(config_path, 'r') as f:
        lab_config.Parse(f)

  def testParse_noHostConfigs(self):
    """Test config file with cluster but no host_configs."""
    # No host_configs is fine.
    config_path = GetTestFilePath('valid/config_without_host_configs.yaml')
    with open(config_path, 'r') as f:
      lab_config_pb = lab_config.Parse(f)
    self.assertEqual(0, len(lab_config_pb.cluster_configs[0].host_configs))

  def testParse_multipleClusterConfigs(self):
    """Test config file with multiple cluster_configs section."""
    # Config with multiple cluster_configs will only keep the last one.
    config_path = GetTestFilePath(
        'invalid/config_multiple_cluster_configs.yaml')
    with self.assertRaisesRegex(lab_config.ConfigError,
                                r".*Duplicate key 'cluster_configs' found.*"):
      with open(config_path, 'r') as f:
        lab_config.Parse(f)

  def testCreateHostConfig(self):
    host_config = lab_config.CreateHostConfig(
        lab_name='alab',
        cluster_name='acluster',
        hostname='ahost',
        host_login_name='auser',
        tf_global_config_path='apath',
        docker_server='a_docker_server',
        docker_image='a_docker_image',
        graceful_shutdown=True,
        shutdown_timeout_sec=240,
        enable_stackdriver=True,
        enable_autoupdate=True,
        extra_docker_args=['--arg1', 'value1'],
        control_server_url='tfc',
        secret_project_id='secret_project',
        service_account_key_secret_id='sa_key',
        service_account='sa@project.google.com',
        operation_mode='ON_PREMISE')
    self.assertEqual('alab', host_config.lab_name)
    self.assertEqual('acluster', host_config.cluster_name)
    self.assertEqual('ahost', host_config.hostname)
    self.assertEqual('auser', host_config.host_login_name)
    self.assertEqual('apath', host_config.tf_global_config_path)
    self.assertEqual('a_docker_image', host_config.docker_image)
    self.assertEqual('tfc', host_config.control_server_url)
    self.assertEqual('a_docker_server', host_config.docker_server)
    self.assertTrue(host_config.graceful_shutdown)
    self.assertEqual(240, host_config.shutdown_timeout_sec)
    self.assertTrue(host_config.enable_stackdriver)
    self.assertTrue(host_config.enable_autoupdate)
    self.assertEqual(['--arg1', 'value1'], host_config.extra_docker_args)
    self.assertEqual('secret_project', host_config.secret_project_id)
    self.assertEqual('sa_key', host_config.service_account_key_secret_id)
    self.assertEqual('sa@project.google.com', host_config.service_account)
    self.assertEqual(lab_config_pb2.OperationMode.ON_PREMISE,
                     host_config.operation_mode)

  def testCreateHostConfig_noLabName(self):
    host_config = lab_config.CreateHostConfig(
        cluster_name='acluster',
        hostname='ahost',
        host_login_name='auser')
    self.assertEqual('', host_config.lab_name)
    self.assertEqual('acluster', host_config.cluster_name)
    self.assertEqual('ahost', host_config.hostname)
    self.assertEqual('auser', host_config.host_login_name)

  def testCreateHostConfig_empty(self):
    host_config = lab_config.CreateHostConfig()
    self.assertEqual('', host_config.lab_name)
    self.assertEqual('', host_config.cluster_name)
    self.assertEqual('', host_config.hostname)
    self.assertEqual('', host_config.host_login_name)
    self.assertEqual('', host_config.tf_global_config_path)

  def testCreateHostConfig_withTmpfsConfigs(self):
    host_config = lab_config.CreateHostConfig(
        'alab', 'acluster', 'ahost', 'auser', 'apath',
        tmpfs_configs=[lab_config.CreateTmpfsConfig('/atmpfs', 1000, '750')])
    self.assertEqual('alab', host_config.lab_name)
    self.assertEqual('acluster', host_config.cluster_name)
    self.assertEqual('ahost', host_config.hostname)
    self.assertEqual('auser', host_config.host_login_name)
    self.assertEqual('apath', host_config.tf_global_config_path)
    self.assertEqual(1, len(host_config.tmpfs_configs))
    self.assertEqual('/atmpfs', host_config.tmpfs_configs[0].path)
    self.assertEqual(1000, host_config.tmpfs_configs[0].size)
    self.assertEqual('750', host_config.tmpfs_configs[0].mode)

  def testCreateTmpfsConfigs(self):
    tmpfs_config = lab_config.CreateTmpfsConfig('/atmpfs', 1000, '750')
    self.assertEqual('/atmpfs', tmpfs_config.path)
    self.assertEqual(1000, tmpfs_config.size)
    self.assertEqual('750', tmpfs_config.mode)


class LabConfigPoolTest(unittest.TestCase):
  """Unit tests for LabConfigPool."""

  def testLoadConfigs(self):
    """Test ConfigPool LoadConfigs can load one config file."""
    config_path = GetTestFilePath('valid/config.yaml')
    pool = lab_config.LabConfigPool(
        lab_config.LocalFileEnumerator(config_path, lab_config.IsYaml))
    pool.LoadConfigs()
    self.assertIsNotNone(pool._lab_to_lab_config_pb.get('lab1'))
    self.assertIsNotNone(pool._cluster_to_cluster_config_pb.get('cluster1'))
    self.assertIsNotNone(pool._cluster_to_cluster_config_pb.get('cluster2'))

  def testLoadConfigs_loadMultipleLab(self):
    """Test LabConfigPool LoadConfigs can load configs in a folder."""
    config_path = GetTestFilePath('valid/config.yaml')
    pool = lab_config.LabConfigPool(
        lab_config.LocalFileEnumerator(
            os.path.dirname(config_path), lab_config.IsYaml))
    with self.assertRaisesRegex(
        lab_config.ConfigError, r'There are multiple labs configured.*'):
      pool.LoadConfigs()

  def testLoadConfigs_notExist(self):
    """Test LabConfigPool LoadConfigs fail when config doesn't exist."""
    config_path = GetTestFilePath('valid/non_exist_config.yaml')
    with six.assertRaisesRegex(
        self, lab_config.ConfigError, r'.* doesn\'t exist.'):
      pool = lab_config.LabConfigPool(
          lab_config.LocalFileEnumerator(config_path, lab_config.IsYaml))
      pool.LoadConfigs()

  def testLoadConfigs_noConfigs(self):
    """Test LabConfigPool LoadConfigs fail when there is config under path."""
    config_path = GetTestFilePath('no_config')
    with six.assertRaisesRegex(
        self, lab_config.ConfigError,
        r'.* no lab config files under the path.'):
      pool = lab_config.LabConfigPool(
          lab_config.LocalFileEnumerator(config_path, lab_config.IsYaml))
      pool.LoadConfigs()

  def testGetLabConfig(self):
    """Test ConfigPool LoadConfigs can load one config file."""
    config_path = GetTestFilePath('valid/config.yaml')
    pool = lab_config.LabConfigPool(
        lab_config.LocalFileEnumerator(config_path, lab_config.IsYaml))
    pool.LoadConfigs()
    self.assertIsNotNone(pool._lab_to_lab_config_pb.get('lab1'))
    config = pool.GetLabConfig()
    self.assertEqual('lab1', config.lab_name)
    self.assertEqual('lab_user1', config.host_login_name)
    self.assertEqual(['lab_user1', 'user1'], config.owners)
    self.assertEqual('tfc_url', config.control_server_url)
    self.assertEqual('lab_docker_image', config.docker_image)
    self.assertEqual('docker_server_1', config.docker_server)
    self.assertTrue(config.enable_stackdriver)
    self.assertTrue(config.enable_autoupdate)
    self.assertTrue(config.enable_ui_update)
    self.assertEqual('path/to/key.json', config.service_account_json_key_path)
    self.assertEqual('secret_project_id', config.secret_project_id)
    self.assertEqual('lab_sv_key', config.service_account_key_secret_id)
    self.assertEqual('sa@project.google.com', config.service_account)
    self.assertEqual('AStringToRepresentApiKey', config.engprod_api_key)
    self.assertEqual(
        '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '
        '-F /path/to/ssh/config -C',
        config.ssh_arg)

  def testGetHostConfigs(self):
    """Test get hosts from LabConfigPool works."""
    config_path = GetTestFilePath('valid/config.yaml')
    pool = lab_config.LabConfigPool(
        lab_config.LocalFileEnumerator(config_path, lab_config.IsYaml))
    pool.LoadConfigs()
    hosts = pool.GetHostConfigs('cluster1')
    self.assertEqual(3, len(hosts))
    self.assertEqual('lab1', hosts[0].lab_name)
    self.assertEqual('host1', hosts[0].hostname)
    self.assertEqual('user1', hosts[0].host_login_name)
    self.assertEqual('cluster1', hosts[0].cluster_name)
    self.assertEqual('path/to/config.xml', hosts[0].tf_global_config_path)
    self.assertEqual('tfc_url', hosts[0].control_server_url)
    self.assertCountEqual(['lab_user1', 'user1', 'user2'], hosts[0].owners)
    self.assertTrue(hosts[0].graceful_shutdown)
    self.assertTrue(hosts[0].enable_stackdriver)
    self.assertTrue(hosts[0].enable_autoupdate)
    self.assertEqual('gcr.io/dockerized-tradefed/tradefed:golden',
                     hosts[0].docker_image)
    self.assertEqual('docker_server_2', hosts[0].docker_server)
    self.assertEqual(
        ['--arg1', 'value1', '--arg2', 'value2'],
        hosts[0].extra_docker_args)
    self.assertEqual('host2', hosts[1].hostname)
    self.assertEqual('user1', hosts[1].host_login_name)
    self.assertEqual('cluster1', hosts[1].cluster_name)
    self.assertEqual('path/to/config.xml', hosts[1].tf_global_config_path)
    self.assertEqual('tfc_url', hosts[1].control_server_url)
    self.assertCountEqual(['lab_user1', 'user1', 'user2'], hosts[1].owners)
    self.assertEqual('gcr.io/dockerized-tradefed/tradefed:golden',
                     hosts[1].docker_image)
    self.assertEqual('docker_server_2', hosts[1].docker_server)
    self.assertEqual(['--arg1', 'value1'], hosts[1].extra_docker_args)
    self.assertEqual('host3', hosts[2].hostname)
    self.assertEqual('user1', hosts[2].host_login_name)
    self.assertEqual('cluster1', hosts[2].cluster_name)
    self.assertEqual('path/to/new/config.xml', hosts[2].tf_global_config_path)
    self.assertCountEqual(['lab_user1', 'user1', 'user2'], hosts[2].owners)
    self.assertEqual('tfc_url', hosts[2].control_server_url)
    self.assertEqual('gcr.io/dockerized-tradefed/tradefed:canary',
                     hosts[2].docker_image)
    self.assertEqual('docker_server_3', hosts[2].docker_server)
    hosts = pool.GetHostConfigs('cluster2')
    self.assertEqual(2, len(hosts))
    self.assertEqual('lab1', hosts[0].lab_name)
    self.assertEqual('lab_user1', hosts[0].host_login_name)
    self.assertEqual('tfc_control_server_url', hosts[0].control_server_url)
    self.assertEqual('lab_docker_image', hosts[0].docker_image)
    self.assertEqual('docker_server_1', hosts[0].docker_server)
    self.assertTrue(hosts[0].enable_stackdriver)
    self.assertTrue(hosts[0].enable_autoupdate)

  def testGetHostConfigs_all(self):
    """Test get hosts from LabConfigPool works."""
    config_path = GetTestFilePath('valid/config.yaml')
    pool = lab_config.LabConfigPool(
        lab_config.LocalFileEnumerator(config_path, lab_config.IsYaml))
    pool.LoadConfigs()
    hosts = pool.GetHostConfigs()
    self.assertEqual(5, len(hosts))

  def testGetHostConfig(self):
    """Test get host config from LabConfigPool works."""
    config_path = GetTestFilePath('valid/config.yaml')
    pool = lab_config.LabConfigPool(
        lab_config.LocalFileEnumerator(config_path, lab_config.IsYaml))
    pool.LoadConfigs()
    host = pool.GetHostConfig('host1')
    self.assertEqual('host1', host.hostname)
    self.assertEqual('user1', host.host_login_name)
    self.assertEqual('cluster1', host.cluster_name)
    self.assertEqual('path/to/config.xml', host.tf_global_config_path)
    self.assertEqual(2, len(host.tmpfs_configs))
    self.assertEqual('/atmpfs', host.tmpfs_configs[0].path)
    self.assertEqual(2000, host.tmpfs_configs[0].size)
    self.assertEqual('750', host.tmpfs_configs[0].mode)
    self.assertEqual('secret_project_id', host.secret_project_id)
    self.assertEqual('lab_sv_key', host.service_account_key_secret_id)
    self.assertEqual('sa@project.google.com', host.service_account)
    self.assertEqual(
        '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '
        '-F /path/to/ssh/config -C',
        host.ssh_arg)

  def testGetHostConfig_notExist(self):
    """Test get host config for not exist host from LabConfigPool works."""
    config_path = GetTestFilePath('valid/config.yaml')
    pool = lab_config.LabConfigPool(
        lab_config.LocalFileEnumerator(config_path, lab_config.IsYaml))
    pool.LoadConfigs()
    host = pool.GetHostConfig('not_exist')
    self.assertIsNone(host)

  def testBuildHostConfig(self):
    """Test build host config from LabConfigPool works."""
    config_path = GetTestFilePath('valid/config.yaml')
    pool = lab_config.LabConfigPool(
        lab_config.LocalFileEnumerator(config_path, lab_config.IsYaml))
    pool.LoadConfigs()
    host = pool.BuildHostConfig('host1')
    self.assertEqual('host1', host.hostname)
    self.assertEqual('user1', host.host_login_name)
    self.assertEqual('cluster1', host.cluster_name)
    self.assertEqual('lab1', host.lab_name)
    self.assertEqual('path/to/config.xml', host.tf_global_config_path)

  def testBuildHostConfig_useCluster(self):
    """Test build host config with cluster from LabConfigPool works."""
    config_path = GetTestFilePath('valid/config.yaml')
    pool = lab_config.LabConfigPool(
        lab_config.LocalFileEnumerator(config_path, lab_config.IsYaml))
    pool.LoadConfigs()
    host = pool.BuildHostConfig('new_host', cluster_name='cluster1')
    self.assertEqual('new_host', host.hostname)
    self.assertEqual('user1', host.host_login_name)
    self.assertEqual('cluster1', host.cluster_name)
    self.assertEqual('lab1', host.lab_name)
    self.assertEqual('path/to/config.xml', host.tf_global_config_path)

  def testBuildHostConfig_newHostNewCluster(self):
    """Test build new host config from LabConfigPool works."""
    config_path = GetTestFilePath('valid/config.yaml')
    pool = lab_config.LabConfigPool(
        lab_config.LocalFileEnumerator(config_path, lab_config.IsYaml))
    pool.LoadConfigs()
    host = pool.BuildHostConfig(
        'new_host', cluster_name='new_cluster', host_login_name='new_user')
    self.assertEqual('new_user', host.host_login_name)
    self.assertEqual('new_host', host.hostname)
    self.assertEqual('new_cluster', host.cluster_name)
    self.assertEqual('', host.tf_global_config_path)
    self.assertEqual('', host.lab_name)

  def testBuildHostConfig_newHostNewClusterNewLab(self):
    """Test build new host config from LabConfigPool works."""
    config_path = GetTestFilePath('valid/config.yaml')
    pool = lab_config.LabConfigPool(
        lab_config.LocalFileEnumerator(config_path, lab_config.IsYaml))
    pool.LoadConfigs()
    host = pool.BuildHostConfig(
        'new_host', cluster_name='new_cluster', host_login_name='new_user',
        lab_name='new_lab')
    self.assertEqual('new_user', host.host_login_name)
    self.assertEqual('new_host', host.hostname)
    self.assertEqual('new_cluster', host.cluster_name)
    self.assertEqual('new_lab', host.lab_name)
    self.assertEqual('', host.tf_global_config_path)

  def testBuildHostConfig_emptyConfigPool(self):
    """Test build new host config from LabConfigPool works."""
    pool = lab_config.LabConfigPool()
    pool.LoadConfigs()
    host = pool.BuildHostConfig(
        'new_host', cluster_name='new_cluster', host_login_name='new_user')
    self.assertEqual('new_user', host.host_login_name)
    self.assertEqual('new_host', host.hostname)
    self.assertEqual('new_cluster', host.cluster_name)
    self.assertEqual('', host.tf_global_config_path)


class HostConfigTest(unittest.TestCase):
  """Unit tests for HostConfig."""

  def _GetHostConfig(self, config_path, hostname):
    pool = lab_config.LabConfigPool(
        lab_config.LocalFileEnumerator(config_path))
    pool.LoadConfigs()
    return pool.GetHostConfig(hostname)

  def testHostConfigSave(self):
    f = tempfile.NamedTemporaryFile()
    try:
      config_path = GetTestFilePath('valid/config.yaml')
      host = self._GetHostConfig(config_path, 'host1')
      host.Save(f.name)
      res_host = self._GetHostConfig(f.name, 'host1')
      self.assertEqual(host, res_host)
    finally:
      # close will delete the file.
      f.close()

  def testUpdateHostConfig(self):
    host_config = lab_config.CreateHostConfig(
        lab_name='alab',
        cluster_name='acluster',
        hostname='ahost',
        host_login_name='auser',
        tf_global_config_path='apath',
        docker_image='a_docker_image',
        graceful_shutdown=True,
        enable_stackdriver=True,
        enable_autoupdate=True,
        service_account_json_key_path='a_service_keyfile',
        control_server_url='tfc')
    new_host_config = host_config.SetDockerImage('b_docker_image')
    new_host_config = new_host_config.SetServiceAccountJsonKeyPath(
        'b_service_keyfile')

    self.assertEqual('a_service_keyfile',
                     host_config.service_account_json_key_path)
    self.assertEqual('b_service_keyfile',
                     new_host_config.service_account_json_key_path)
    self.assertEqual('a_docker_image', host_config.docker_image)
    self.assertEqual('b_docker_image', new_host_config.docker_image)

    self.assertEqual('alab', new_host_config.lab_name)
    self.assertEqual('acluster', new_host_config.cluster_name)

  def testConfigEquals_equals(self):
    host_config_1 = lab_config.CreateHostConfig(
        lab_name='alab',
        cluster_name='acluster',
        hostname='ahost',
        host_login_name='auser',
        tf_global_config_path='apath',
        docker_server='a_docker_server',
        docker_image='a_docker_image',
        graceful_shutdown=True,
        enable_stackdriver=True,
        enable_autoupdate=True,
        service_account_json_key_path='a_service_keyfile',
        control_server_url='tfc')
    host_config_2 = host_config_1.Copy()
    self.assertEqual(host_config_1, host_config_2)

  def testConfigEquals_notEquals(self):
    host_config_1 = lab_config.CreateHostConfig(
        lab_name='alab',
        cluster_name='acluster',
        hostname='ahost',
        host_login_name='auser',
        tf_global_config_path='apath',
        docker_server='a_docker_server',
        docker_image='a_docker_image',
        graceful_shutdown=True,
        enable_stackdriver=True,
        enable_autoupdate=True,
        service_account_json_key_path='a_service_keyfile',
        control_server_url='tfc')
    host_config_2 = host_config_1.SetDockerImage('b_docker_image')
    self.assertNotEqual(host_config_1, host_config_2)


if __name__ == '__main__':
  unittest.main()
