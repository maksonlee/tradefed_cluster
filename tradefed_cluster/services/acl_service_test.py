"""Tests for tradefed_cluster.services.host_account_validator."""
import unittest
from unittest import mock

import endpoints
from protorpc import message_types
from protorpc import messages
from protorpc import remote
from tradefed_cluster import api_common
from tradefed_cluster import datastore_test_util
from tradefed_cluster import env_config
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.services import acl_service
import webtest


class StubDeviceRequest(messages.Message):
  device_serial = messages.StringField(1, required=True)


@api_common.tradefed_cluster_api.api_class(resource_name='stub', path='stub')
class StubApi(remote.Service):

  @api_common.method(
      StubDeviceRequest,
      message_types.VoidMessage,
      path='{device_serial}',
      http_method='GET',
      name='getDevice')
  def GetDevice(self, request):
    return message_types.VoidMessage()

  @api_common.method(
      StubDeviceRequest,
      message_types.VoidMessage,
      path='{device_serial}',
      http_method='PUT',
      name='updateDevice')
  def UpdateDevice(self, request):
    return message_types.VoidMessage()

  @api_common.method(
      message_types.VoidMessage,
      message_types.VoidMessage,
      path='randomapi',
      http_method='POST',
      name='randomApi')
  def RandomApi(self, request):
    return message_types.VoidMessage()


class AclServiceTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super().setUp()
    self._acl_plugin = mock.MagicMock()
    env_config.CONFIG.acl_plugin = self._acl_plugin
    app = endpoints.api_server([StubApi])
    app = acl_service.PermissionMiddleware(app, r'.*stub/.*')
    self.testapp = webtest.TestApp(app)
    datastore_test_util.CreateLabConfig(
        'stub_lab',
        ('labowner1', 'labowner2'))
    datastore_test_util.CreateHostGroupConfig(
        'stub_inventory',
        'stub_lab')
    datastore_test_util.CreateHostConfig(
        'stub@lab.google.com',
        'stub_lab',
        inventory_groups=['stub_inventory'],
        owners=['mdb-group:foo-group'],)
    datastore_test_util.CreateDevice(
        'stub_cluster',
        'stub@lab.google.com',
        'stub_serial')

  def testSkipCheckWhenNoPlugin(self):
    env_config.CONFIG.acl_plugin = None
    response = self.testapp.get(
        '/_ah/api/tradefed_cluster/v1/stub/random_serial',
        headers={'AUTHENTICATED-USER': 'random_user'})
    self.assertEqual(response.status_code, 204)

  def testValidatePrincipals(self):
    self._acl_plugin.CheckMembership.return_value = True
    res = acl_service.CheckMembership('foo', 'mdb/foo-group')
    self.assertTrue(res)
    self._acl_plugin.CheckMembership.assert_called_once_with(
        'foo', 'mdb/foo-group')

  def testRandomApiWithoutPermissionCheck(self):
    response = self.testapp.post(
        '/_ah/api/tradefed_cluster/v1/stub/randomapi',
        headers={'AUTHENTICATED-USER': 'stub_user'})
    self.assertEqual(response.status_code, 204)
    self._acl_plugin.CheckMembership.assert_not_called()
    self._acl_plugin.CheckPermission.assert_not_called()

  def testSkipPermissionCheck(self):
    response = self.testapp.get(
        '/_ah/api/tradefed_cluster/v1/stub/random_serial')
    self.assertEqual(response.status_code, 204)
    self._acl_plugin.CheckMembership.assert_not_called()
    self._acl_plugin.CheckPermission.assert_not_called()

  def testDeviceReaderPermission(self):
    self._acl_plugin.CheckMembership.return_value = False
    self._acl_plugin.CheckPermission.return_value = None
    response = self.testapp.get(
        '/_ah/api/tradefed_cluster/v1/stub/stub_serial',
        headers={'AUTHENTICATED-USER': 'stub_user'})
    self.assertEqual(response.status_code, 204)
    self._acl_plugin.CheckMembership.assert_called_once_with(
        'stub_user', 'mdb-group:foo-group')
    self._acl_plugin.CheckPermission.assert_called_once_with(
        'stub_lab_stub_inventory',
        acl_service.Permission.reader,
        'stub_user')

  def testDeviceReaderPermission_SkipWhenNoDevice(self):
    self._acl_plugin.CheckPermission.return_value = None

    response = self.testapp.get(
        '/_ah/api/tradefed_cluster/v1/stub/foo_serial',
        headers={'AUTHENTICATED-USER': 'stub_user'})

    self.assertEqual(response.status_code, 204)

  def testDeviceReaderPermission_Forbidden(self):
    self._acl_plugin.CheckPermission.side_effect = [
        endpoints.ForbiddenException]
    self._acl_plugin.CheckMembership.return_value = False
    with self.assertRaisesRegex(
        webtest.AppError,
        r'403 .* stub_user .* stub@lab.google.com .* reader.*'):
      self.testapp.get(
          '/_ah/api/tradefed_cluster/v1/stub/stub_serial',
          headers={'AUTHENTICATED-USER': 'stub_user'})

  def testDeviceOwnerPermission(self):
    self._acl_plugin.CheckMembership.side_effect = [False]
    self._acl_plugin.CheckPermission.return_value = None
    response = self.testapp.put(
        '/_ah/api/tradefed_cluster/v1/stub/stub_serial',
        headers={'AUTHENTICATED-USER': 'stub_user'})
    self.assertEqual(response.status_code, 204)
    self._acl_plugin.CheckPermission.assert_called_once_with(
        'stub_lab_stub_inventory',
        acl_service.Permission.owner,
        'stub_user')

  def testDeviceOwnerPermission_Forbidden(self):
    self._acl_plugin.CheckPermission.side_effect = [
        endpoints.ForbiddenException]
    self._acl_plugin.CheckMembership.return_value = False
    with self.assertRaisesRegex(
        webtest.AppError,
        r'403 .* stub_user .* stub@lab.google.com .* owner.*'):
      self.testapp.put(
          '/_ah/api/tradefed_cluster/v1/stub/stub_serial',
          headers={'AUTHENTICATED-USER': 'stub_user'})

  def testCheckLabOwners_NoUserGroup(self):
    self._acl_plugin.CheckPermission.side_effect = [
        endpoints.ForbiddenException]
    self._acl_plugin.CheckMembership.side_effect = [False, False, True]
    response = self.testapp.get(
        '/_ah/api/tradefed_cluster/v1/stub/stub_serial',
        headers={'AUTHENTICATED-USER': 'stub_user'})
    self.assertEqual(response.status_code, 204)
    self._acl_plugin.CheckPermission.assert_called_once_with(
        'stub_lab_stub_inventory',
        acl_service.Permission.reader,
        'stub_user')
    self.assertEqual([
        mock.call('stub_user', 'mdb-group:foo-group'),
        mock.call('stub_user', 'labowner1'),
        mock.call('stub_user', 'labowner2')
    ], self._acl_plugin.CheckMembership.call_args_list)

  def testCheckLabOwners_Forbidden(self):
    self._acl_plugin.CheckPermission.side_effect = [
        endpoints.ForbiddenException]
    self._acl_plugin.CheckMembership.side_effect = [False, False, False]
    with self.assertRaisesRegex(webtest.AppError, r'403 .*'):
      self.testapp.put(
          '/_ah/api/tradefed_cluster/v1/stub/stub_serial',
          headers={'AUTHENTICATED-USER': 'stub_user'})

  def testCheckLabOwners_ByPassNoOwners(self):
    datastore_test_util.CreateLabConfig(
        'stub_lab2', [])
    datastore_test_util.CreateHostConfig(
        'stub2@lab.google.com',
        'stub_lab2')
    datastore_test_util.CreateDevice(
        'stub_cluster2',
        'stub2@lab.google.com',
        'stub_serial2')

    response = self.testapp.get(
        '/_ah/api/tradefed_cluster/v1/stub/stub_serial2',
        headers={'AUTHENTICATED-USER': 'random_user'})

    self.assertEqual(response.status_code, 204)
    self._acl_plugin.CheckPermission.assert_not_called()


if __name__ == '__main__':
  unittest.main()
