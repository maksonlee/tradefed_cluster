"""Tests for unified_lab_config."""
import os
import unittest

from tradefed_cluster.configs import unified_lab_config

TEST_DATA_PATH = 'testdata/unified_lab_config'


def _GetTestFilePath(file_path):
  return os.path.join(os.path.dirname(__file__), TEST_DATA_PATH, file_path)


class UnifiedLabConfigTest(unittest.TestCase):

  def testParse(self):
    config = unified_lab_config.Parse(_GetTestFilePath('valid_lab/hosts'))
    self.assertIsNotNone(config)

  def testListGlobalVars(self):
    config = unified_lab_config.Parse(_GetTestFilePath('valid_lab/hosts'))
    self.assertEqual(
        {
            'lab_name': 'atc',
            'domain': 'atc.google.com',
            'enable_stackdriver': True,
            'ssh_arg': '-F path/to/ssh/config',
            'owners': ['mdb-group:some_owner', 'foo', 'bar'],
            'executors': ['mdb-group:some_executor', 'zar'],
            'readers': ['reader_a', 'mdb-group:some_reader'],
        },
        config.ListGlobalVars())

  def testGetGlobalVar(self):
    config = unified_lab_config.Parse(_GetTestFilePath('valid_lab/hosts'))
    self.assertEqual('atc', config.GetGlobalVar('lab_name'))
    self.assertEqual('atc.google.com', config.GetGlobalVar('domain'))
    self.assertEqual('-F path/to/ssh/config', config.GetGlobalVar('ssh_arg'))

  def testListGroups(self):
    config = unified_lab_config.Parse(_GetTestFilePath('valid_lab/hosts'))
    self.assertEqual(
        ['all', 'ungrouped', 'jump', 'dhcp', 'dns', 'pxe', 'server', 'tf',
         'postsubmit', 'crystalball', 'crystalball-power'],
        [g.name for g in config.ListGroups()])

  def testGetGroup(self):
    config = unified_lab_config.Parse(_GetTestFilePath('valid_lab/hosts'))
    group = config.GetGroup('dhcp')
    self.assertEqual('dhcp', group.name)
    self.assertEqual(
        {
            'dhcp_config_path': 'path/to/dhcp/config',
            'pool': '10.0.0.100 - 10.0.0.255',
            'router': '10.0.0.1',
            'subnet': '10.0.0.0/24'
        },
        group.direct_vars)

  def testGetGroup_nonExist(self):
    config = unified_lab_config.Parse(_GetTestFilePath('valid_lab/hosts'))
    self.assertIsNone(config.GetGroup('invalid_group'))

  def testListHosts(self):
    config = unified_lab_config.Parse(_GetTestFilePath('valid_lab/hosts'))
    self.assertEqual(
        [
            'jump1.atc.google.com',
            'jump2.atc.google.com',
            'dhcp1.atc.google.com',
            'dhcp2.atc.google.com',
            'postsubmit1.atc.google.com',
            'postsubmit2.atc.google.com',
            'crystalball1.atc.google.com',
            'crystalball2.atc.google.com',
            'cp1.atc.google.com',
            'cp2.atc.google.com',
        ],
        [h.name for h in config.ListHosts()])

  def testGethost(self):
    config = unified_lab_config.Parse(_GetTestFilePath('valid_lab/hosts'))
    host = config.GetHost('dhcp1.atc.google.com')
    self.assertEqual('dhcp1.atc.google.com', host.name)
    self.assertEqual(
        ['all', 'server', 'dhcp', 'dns', 'pxe'],
        [g.name for g in host.groups])
    self.assertEqual('10.0.0.11', host.direct_vars['ip'])
    self.assertEqual('24:6e:96:53:7d:90', host.direct_vars['mac'])
    self.assertEqual('10.0.0.11', host.GetVar('ip'))
    self.assertEqual('24:6e:96:53:7d:90', host.GetVar('mac'))
    # GetVar will also get inheirted vars.
    self.assertEqual('path/to/dhcp/config', host.GetVar('dhcp_config_path'))
    self.assertEqual('8.8.8.8', host.GetVar('addition_dns'))
    self.assertEqual('atc', host.GetVar('lab_name'))
    self.assertIsNone(host.GetVar('invalid_key'))

  def testGethost_underSubGroup(self):
    config = unified_lab_config.Parse(_GetTestFilePath('valid_lab/hosts'))
    host = config.GetHost('cp1.atc.google.com')
    self.assertEqual('cp1.atc.google.com', host.name)
    self.assertEqual(
        ['all', 'tf', 'crystalball', 'crystalball-power'],
        [g.name for g in host.groups])
    self.assertEqual('10.0.18.137', host.direct_vars['ip'])
    self.assertEqual('a4:bb:6d:c3:be:28', host.direct_vars['mac'])
    self.assertEqual('10.0.18.137', host.GetVar('ip'))
    self.assertEqual('a4:bb:6d:c3:be:28', host.GetVar('mac'))
    # GetVar will also get inheirted vars.
    self.assertEqual(
        ['TF_GLOBAL_CONFIG=configs/cluster/atc/crystalball/power.xml'],
        host.GetVar('docker_envs'))
    self.assertEqual(
        ['/dev:/dev', '/dev/U16S:/dev/U16S'],
        host.GetVar('docker_volumes'))
    self.assertEqual(
        ['mdb-group:crystalball-team', 'user10'],
        host.GetVar('owners'))

  def testGethost_nonExist(self):
    config = unified_lab_config.Parse(_GetTestFilePath('valid_lab/hosts'))
    self.assertIsNone(config.GetHost('invalid'))


if __name__ == '__main__':
  unittest.main()
