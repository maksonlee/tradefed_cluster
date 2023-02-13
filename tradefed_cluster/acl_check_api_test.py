# Copyright 2021 Google LLC
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
"""Tests for acl checking api."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import unittest
from unittest import mock

import endpoints
from protorpc import protojson

from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import datastore_test_util


class AclCheckApiTest(api_test.ApiTest):
  """Unit tests for AclCheckApi."""

  def setUp(self, extra_apis=None):
    super().setUp()
    datastore_test_util.CreateLabConfig('foo-lab', ('groupA', 'groupB'))
    datastore_test_util.CreateHostConfig(
        'mock.host.google.com', 'foo-lab', inventory_groups=['jump', 'dhcp'])
    datastore_test_util.CreateHostGroupConfig(
        'bar-group',
        'foo-lab',
        account_principals={
            'bar-admin': {
                'principals': ['principalA', 'principalB']
            }
        })
    datastore_test_util.CreateDevice('stub_cluster', 'mock.host.google.com',
                                     'stub_serial')

  def createRootGroup(self):
    datastore_test_util.CreateHostGroupConfig(
        'all',
        'foo-lab',
        account_principals={
            'bar-admin': {
                'principals': ['principalC', 'principalD']
            }
        })

  @mock.patch('tradefed_cluster.services.acl_service.CheckMembership')
  def testAuthAccountPrinciples_jumpHostHaveAccess(self, mock_check_membership):
    self.createRootGroup()
    mock_check_membership.side_effect = [False, False, True]
    api_request = {
        'hostname': 'mock.host.google.com',
        'host_account': 'android-test',
        'user_name': 'mock-user'
    }
    api_response = self.testapp.post_json('/_ah/api/AclApi.CheckSshAccessible',
                                          api_request)
    account_principals = protojson.decode_message(api_messages.AclCheckResult,
                                                  api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertTrue(account_principals.has_access)
    self.assertEqual(mock_check_membership.call_count, 3)
    mock_check_membership.assert_has_calls([
        mock.call('mock-user', 'principalC'),
        mock.call('mock-user', 'principalD'),
        mock.call('mock-user', 'principalA'),
    ])

  @mock.patch('tradefed_cluster.services.acl_service.CheckMembership')
  def testAuthAccountPrinciples_jumpHostNoAccess(self, mock_check_membership):
    mock_check_membership.return_value = False
    api_request = {
        'hostname': 'mock.host.google.com',
        'host_account': 'android-test',
        'user_name': 'mock-user'
    }
    api_response = self.testapp.post_json('/_ah/api/AclApi.CheckSshAccessible',
                                          api_request)
    account_principals = protojson.decode_message(api_messages.AclCheckResult,
                                                  api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertFalse(account_principals.has_access)
    mock_check_membership.assert_has_calls([
        mock.call('mock-user', 'principalA'),
        mock.call('mock-user', 'principalB'),
    ])

  @mock.patch('tradefed_cluster.services.acl_service.CheckMembership')
  def testAuthAccountPrinciples_hostGroupHaveAccess(
      self, mock_check_membership
  ):
    datastore_test_util.CreateHostConfig(
        'mock2.host.google.com',
        'foo-lab',
        inventory_groups=[
            'bar-group',
            'jump',
        ])
    self.createRootGroup()
    mock_check_membership.side_effect = [False, False, True]
    api_request = {
        'hostname': 'mock2.host.google.com',
        'host_account': 'bar-admin',
        'user_name': 'mock-user'
    }
    api_response = self.testapp.post_json('/_ah/api/AclApi.CheckSshAccessible',
                                          api_request)
    account_principals = protojson.decode_message(api_messages.AclCheckResult,
                                                  api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertTrue(account_principals.has_access)
    self.assertEqual(mock_check_membership.call_count, 3)
    mock_check_membership.assert_has_calls([
        mock.call('mock-user', 'principalC'),
        mock.call('mock-user', 'principalD'),
        mock.call('mock-user', 'principalA'),
    ])

  @mock.patch('tradefed_cluster.services.acl_service.CheckMembership')
  def testAuthAccountPrinciples_hostGroupNoAccess(self, mock_check_membership):
    datastore_test_util.CreateHostConfig(
        'mock2.host.google.com', 'foo-lab', inventory_groups=['bar', 'server'])
    datastore_test_util.CreateHostGroupConfig('bar', 'foo-lab')
    datastore_test_util.CreateHostGroupConfig('server', 'foo-lab')
    mock_check_membership.return_value = True
    api_request = {
        'hostname': 'mock2.host.google.com',
        'host_account': 'bar-admin',
        'user_name': 'mock-user'
    }
    api_response = self.testapp.post_json('/_ah/api/AclApi.CheckSshAccessible',
                                          api_request)
    account_principals = protojson.decode_message(api_messages.AclCheckResult,
                                                  api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertFalse(account_principals.has_access)
    mock_check_membership.assert_not_called()

  def testAuthAccountPrinciples_noHost(self):
    with self.assertRaisesRegex(Exception,
                                'mock3.host.google.com host config not found'):
      self.testapp.post_json(
          '/_ah/api/AclApi.CheckSshAccessible', {
              'hostname': 'mock3.host.google.com',
              'host_account': 'bar-admin',
              'user_name': 'mock-user'
          })

  @mock.patch('tradefed_cluster.services.acl_service.CheckMembership')
  def testAuthAccountPrinciples_noUser(self, mock_check_membership):
    self.createRootGroup()
    mock_check_membership.side_effect = endpoints.NotFoundException(
        message='mock error message'
    )
    with self.assertRaisesRegex(Exception, 'mock error message'):
      self.testapp.post_json(
          '/_ah/api/AclApi.CheckSshAccessible',
          {
              'hostname': 'mock.host.google.com',
              'host_account': 'bar-admin',
              'user_name': 'mock-user'
          })

  @mock.patch('tradefed_cluster.services.acl_service.CheckResourcePermission')
  def testCheckAccessPermission_deviceOwner(self, mock_check_permission):
    mock_check_permission.return_value = None
    response = self.testapp.post_json(
        '/_ah/api/AclApi.CheckAccessPermission', {
            'resource_type': 'device',
            'permission': 'owner',
            'user_name': 'stub_user',
            'resource_id': 'stub_serial'
        })
    account_principals = protojson.decode_message(api_messages.AclCheckResult,
                                                  response.body)
    self.assertEqual('200 OK', response.status)
    self.assertTrue(account_principals.has_access)

  @mock.patch('tradefed_cluster.services.acl_service.CheckResourcePermission')
  def testCheckAccessPermission_deviceNoAccess(self, mock_check_permission):
    mock_check_permission.side_effect = endpoints.ForbiddenException
    response = self.testapp.post_json(
        '/_ah/api/AclApi.CheckAccessPermission', {
            'resource_type': 'device',
            'permission': 'owner',
            'user_name': 'stub_user',
            'resource_id': 'stub_serial'
        })
    account_principals = protojson.decode_message(api_messages.AclCheckResult,
                                                  response.body)
    self.assertEqual('200 OK', response.status)
    self.assertFalse(account_principals.has_access)

  def testCheckAccessPermission_badResource(self):
    with self.assertRaisesRegex(Exception, '400 Bad Request.*'):
      self.testapp.post_json(
          '/_ah/api/AclApi.CheckAccessPermission', {
              'resource_type': 'invalid_resource',
              'permission': 'owner',
              'user_name': 'stub_user',
              'resource_id': 'stub_serial'
          })
    with self.assertRaisesRegex(Exception, '400 Bad Request.*'):
      self.testapp.post_json(
          '/_ah/api/AclApi.CheckAccessPermission', {
              'resource_type': 'device',
              'permission': 'invalid_permission',
              'user_name': 'stub_user',
              'resource_id': 'stub_serial'
          })

  @mock.patch('tradefed_cluster.services.acl_service.CheckMembership')
  @mock.patch('logging.error')
  def testCheckAccessPermission_unformattedPrinciple(
      self, mock_log, mock_check_membership):
    mock_check_membership.return_value = True
    datastore_test_util.CreateLabConfig('unformatted-lab', ('groupA', 'groupB'))
    datastore_test_util.CreateHostGroupConfig(
        'unformatted-group',
        'unformatted-lab',
        account_principals={
            'bar-admin': {'principals': [{'foo': 'bar'}, {'bar': 'baz'}]}
        },
    )
    self.createRootGroup()
    datastore_test_util.CreateHostConfig(
        'mock2.host.google.com',
        'unformatted-lab',
        inventory_groups=[
            'unformatted-group',
        ],
    )
    api_request = {
        'hostname': 'mock2.host.google.com',
        'host_account': 'bar-admin',
        'user_name': 'mock-user',
    }

    api_response = self.testapp.post_json(
        '/_ah/api/AclApi.CheckSshAccessible', api_request
    )

    account_principals = protojson.decode_message(
        api_messages.AclCheckResult, api_response.body
    )
    mock_log.assert_called_once_with(
        'host group %s got wrong account principle formate', 'unformatted-group'
    )
    self.assertEqual('200 OK', api_response.status)
    self.assertFalse(account_principals.has_access)


if __name__ == '__main__':
  unittest.main()
