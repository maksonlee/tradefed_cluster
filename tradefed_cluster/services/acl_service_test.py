"""Tests for tradefed_cluster.services.host_account_validator."""
from unittest import mock

from absl.testing import absltest

from tradefed_cluster import env_config
from tradefed_cluster.services import acl_service


class AclServiceTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self._acl_plugin = mock.MagicMock()
    env_config.CONFIG.acl_plugin = self._acl_plugin

  def testValidatePrinciples(self):
    self._acl_plugin.CheckMembership.return_value = True
    res = acl_service.CheckMembership('foo', 'mdb/foo-group')
    self.assertTrue(res)
    self._acl_plugin.CheckMembership.assert_called_once_with(
        'foo', 'mdb/foo-group')


if __name__ == '__main__':
  absltest.main()
