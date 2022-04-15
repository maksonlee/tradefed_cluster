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
"""Tests for lab management api."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import unittest

from protorpc import protojson
from six.moves import zip

from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util


class LabManagementApiTest(api_test.ApiTest):
  """Unit test for LabManagementApi."""

  def setUp(self):
    api_test.ApiTest.setUp(self)
    self.lab1 = datastore_test_util.CreateLabInfo('lab1')
    self.lab_config1 = datastore_test_util.CreateLabConfig('lab1')
    self.lab2 = datastore_test_util.CreateLabInfo('lab2')
    self.lab_config2 = datastore_test_util.CreateLabConfig('lab2')
    self.lab3 = datastore_test_util.CreateLabInfo('lab3')
    self.lab_config3 = datastore_test_util.CreateLabConfig(
        'lab3', owners=['owner3', 'owner4'])
    self.labs = [self.lab1, self.lab2, self.lab3]
    self.lab_configs = [self.lab_config1, self.lab_config2, self.lab_config3]

  def AssertEqualLabInfo(
      self, lab_message, lab_entity=None, lab_config_entity=None):
    # Helper to compare lab entities and messages
    lab_name = lab_entity.lab_name if lab_entity else lab_config_entity.lab_name
    self.assertEqual(lab_name, lab_message.lab_name)
    if lab_config_entity:
      self.assertEqual(lab_config_entity.owners, lab_message.owners)

  def testListLabs(self):
    """Tests ListLabs returns all labs."""
    api_request = {}
    api_response = self.testapp.post_json(
        '/_ah/api/LabManagementApi.ListLabs', api_request)
    lab_collection = protojson.decode_message(
        api_messages.LabInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(3, len(lab_collection.lab_infos))
    for lab, lab_config, lab_msg in zip(
        self.labs, self.lab_configs, lab_collection.lab_infos):
      self.AssertEqualLabInfo(lab_msg, lab, lab_config)

  def testListLabs_filterByOwner(self):
    """Tests ListLabs returns labs filtered by owner."""
    api_request = {'owner': 'owner3'}
    api_response = self.testapp.post_json(
        '/_ah/api/LabManagementApi.ListLabs', api_request)
    lab_collection = protojson.decode_message(
        api_messages.LabInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(lab_collection.lab_infos))
    self.AssertEqualLabInfo(
        lab_collection.lab_infos[0], self.lab3, self.lab_config3)

  def testListLabs_withCount(self):
    """Tests ListLabs returns labs with count."""
    api_request = {'count': '1'}
    api_response = self.testapp.post_json(
        '/_ah/api/LabManagementApi.ListLabs', api_request)
    lab_collection = protojson.decode_message(
        api_messages.LabInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(lab_collection.lab_infos))
    self.assertTrue(lab_collection.more)
    self.assertIsNotNone(lab_collection.next_cursor)

  def testGetLab(self):
    """Tests GetLab."""
    api_request = {'lab_name': 'lab3'}
    api_response = self.testapp.post_json(
        '/_ah/api/LabManagementApi.GetLab', api_request)
    lab_info = protojson.decode_message(
        api_messages.LabInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual('lab3', lab_info.lab_name)
    self.assertEqual(['owner3', 'owner4'], lab_info.owners)

  def testGetLab_displayHostUpdateStateSummary(self):
    """Test GetLab returns host update state summary."""
    datastore_test_util.CreateLabInfo(
        'lab4',
        host_update_state_summary=datastore_entities.HostUpdateStateSummary(
            total=3,
            syncing=1,
            succeeded=2))
    api_request = {'lab_name': 'lab4'}
    api_response = self.testapp.post_json(
        '/_ah/api/LabManagementApi.GetLab', api_request)
    lab_info = protojson.decode_message(
        api_messages.LabInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual('lab4', lab_info.lab_name)
    self.assertEqual(3, lab_info.host_update_state_summary.total)
    self.assertEqual(1, lab_info.host_update_state_summary.syncing)
    self.assertEqual(2, lab_info.host_update_state_summary.succeeded)

  def testGetLab_displayHostCountByHarnessVersion(self):
    """Test GetLab returns host count by harness version."""
    host_count_by_harness_version = {
        'version1': 12,
        'version2': 1,
        'version3': 668,
    }
    datastore_test_util.CreateLabInfo(
        'lab4',
        host_count_by_harness_version=host_count_by_harness_version)
    api_request = {'lab_name': 'lab4'}
    api_response = self.testapp.post_json(
        '/_ah/api/LabManagementApi.GetLab', api_request)
    lab_info = protojson.decode_message(
        api_messages.LabInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual('lab4', lab_info.lab_name)
    expected_host_counts = [
        api_messages.KeyValuePair(key='version1', value='12'),
        api_messages.KeyValuePair(key='version2', value='1'),
        api_messages.KeyValuePair(key='version3', value='668'),
    ]
    self.assertCountEqual(
        expected_host_counts, lab_info.host_count_by_harness_version)

if __name__ == '__main__':
  unittest.main()
