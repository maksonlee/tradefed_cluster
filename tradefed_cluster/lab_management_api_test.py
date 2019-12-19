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
import unittest

from protorpc import protojson

from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import datastore_test_util


class LabManagementApiTest(api_test.ApiTest):
  """Unit test for LabManagementApi."""

  def setUp(self):
    api_test.ApiTest.setUp(self)
    self.lab1 = datastore_test_util.CreateLabInfo('lab1')
    self.lab2 = datastore_test_util.CreateLabInfo('lab2')
    self.lab3 = datastore_test_util.CreateLabInfo(
        'lab3', owners=['owner3'])
    self.labs = [self.lab1, self.lab2, self.lab3]

  def AssertEqualLabInfo(self, lab_entity, lab_message):
    # Helper to compare lab entities and messages
    self.assertEqual(lab_entity.lab_name, lab_message.lab_name)
    self.assertEqual(lab_entity.update_timestamp, lab_message.update_timestamp)
    self.assertEqual(lab_entity.owners, lab_message.owners)

  def testListLabs(self):
    """Tests ListLabs returns all labs."""
    api_request = {}
    api_response = self.testapp.post_json(
        '/_ah/api/LabManagementApi.ListLabs', api_request)
    lab_collection = protojson.decode_message(
        api_messages.LabInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(3, len(lab_collection.lab_infos))
    for lab, lab_msg in zip(self.labs, lab_collection.lab_infos):
      self.AssertEqualLabInfo(lab, lab_msg)

  def testListLabs_filterByOwner(self):
    """Tests ListLabs returns labs filtered by owner."""
    api_request = {'owner': 'owner3'}
    api_response = self.testapp.post_json(
        '/_ah/api/LabManagementApi.ListLabs', api_request)
    lab_collection = protojson.decode_message(
        api_messages.LabInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(lab_collection.lab_infos))
    self.AssertEqualLabInfo(self.lab3, lab_collection.lab_infos[0])

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


if __name__ == '__main__':
  unittest.main()
