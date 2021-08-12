# Lint as: python2, python3
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

from protorpc import protojson

from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import datastore_test_util
from tradefed_cluster.services import acl_service


class AclCheckApiTest(api_test.ApiTest):
  """Unit tests for AclCheckApi."""

  def testAuthAccountPrinciples_jumpHostHaveAccess(self):
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
    datastore_test_util.CreateHostGroupConfig(
        'all',
        'foo-lab',
        account_principals={
            'bar-admin': {
                'principals': ['principalC', 'principalD']
            }
        })
    acl_service.CheckMembership = mock.MagicMock(
        side_effect=[False, False, True])
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
    acl_service.CheckMembership.assert_has_calls([
        mock.call('mock-user', 'principalC'),
        mock.call('mock-user', 'principalD'),
        mock.call('mock-user', 'principalA'),
    ])

  def testAuthAccountPrinciples_jumpHostNoAccess(self):
    datastore_test_util.CreateHostConfig(
        'mock.host.google.com', 'foo-lab', inventory_groups=['jump'])
    datastore_test_util.CreateHostGroupConfig(
        'bar-group',
        'foo-lab',
        account_principals={
            'bar-admin': {
                'principals': ['principalA', 'principalB']
            }
        })
    datastore_test_util.CreateHostGroupConfig('bar-group2', 'foo-lab')
    acl_service.CheckMembership = mock.MagicMock(return_value=False)
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
    acl_service.CheckMembership.assert_has_calls([
        mock.call('mock-user', 'principalA'),
        mock.call('mock-user', 'principalB')
    ])

  def testAuthAccountPrinciples_hostGroupHaveAccess(self):
    datastore_test_util.CreateHostConfig(
        'mock.host.google.com', 'foo-lab', inventory_groups=['bar', 'jump'])
    datastore_test_util.CreateHostGroupConfig(
        'bar',
        'foo-lab',
        account_principals={
            'bar-admin': {
                'principals': ['principalA', 'principalB']
            }
        })
    datastore_test_util.CreateHostGroupConfig(
        'all',
        'foo-lab',
        account_principals={
            'bar-admin': {
                'principals': ['principalC', 'principalD']
            }
        })
    acl_service.CheckMembership = mock.MagicMock(
        side_effect=[False, False, True])
    api_request = {
        'hostname': 'mock.host.google.com',
        'host_account': 'bar-admin',
        'user_name': 'mock-user'
    }
    api_response = self.testapp.post_json('/_ah/api/AclApi.CheckSshAccessible',
                                          api_request)
    account_principals = protojson.decode_message(api_messages.AclCheckResult,
                                                  api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertTrue(account_principals.has_access)
    self.assertEqual(acl_service.CheckMembership.call_count, 3)
    acl_service.CheckMembership.assert_has_calls([
        mock.call('mock-user', 'principalC'),
        mock.call('mock-user', 'principalD'),
        mock.call('mock-user', 'principalA')
    ])

  def testAuthAccountPrinciples_hostGroupNoAccess(self):
    datastore_test_util.CreateHostConfig(
        'mock.host.google.com', 'foo-lab', inventory_groups=['bar', 'server'])
    datastore_test_util.CreateHostGroupConfig('bar', 'foo-lab')
    datastore_test_util.CreateHostGroupConfig('server', 'foo-lab')
    acl_service.CheckMembership = mock.MagicMock(return_value=True)
    api_request = {
        'hostname': 'mock.host.google.com',
        'host_account': 'bar-admin',
        'user_name': 'mock-user'
    }
    api_response = self.testapp.post_json('/_ah/api/AclApi.CheckSshAccessible',
                                          api_request)
    account_principals = protojson.decode_message(api_messages.AclCheckResult,
                                                  api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertFalse(account_principals.has_access)
    acl_service.CheckMembership.assert_not_called()

  def testAuthAccountPrinciples_noHost(self):
    with self.assertRaisesRegex(
        Exception, 'mock.host.google.com host config not found'):
      self.testapp.post_json(
          '/_ah/api/AclApi.CheckSshAccessible',
          {
              'hostname': 'mock.host.google.com',
              'host_account': 'bar-admin',
              'user_name': 'mock-user'
          })

  def testAuthAccountPrinciples_noUser(self):
    datastore_test_util.CreateHostConfig(
        'mock.host.google.com', 'foo-lab', inventory_groups=['bar', 'jump'])
    datastore_test_util.CreateHostGroupConfig(
        'bar',
        'foo-lab',
        account_principals={
            'bar-admin': {
                'principals': ['principalA', 'principalB']
            }
        })
    acl_service.CheckMembership = mock.MagicMock(
        side_effect=acl_service.UserNotFoundError('mock error message'))
    with self.assertRaisesRegex(Exception, 'mock error message'):
      self.testapp.post_json(
          '/_ah/api/AclApi.CheckSshAccessible',
          {
              'hostname': 'mock.host.google.com',
              'host_account': 'bar-admin',
              'user_name': 'mock-user'
          })


if __name__ == '__main__':
  unittest.main()
