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
"""Tests for datastore_util."""

import unittest

from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import datastore_util
from tradefed_cluster import testbed_dependent_test


class DatastoreUtilTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super(DatastoreUtilTest, self).setUp()
    for i in range(10):
      datastore_test_util.CreateLabInfo('lab' + str(i))

  def testFetchPage(self):
    query = datastore_entities.LabInfo.query()
    query = query.order(datastore_entities.LabInfo.key)
    labs, _, _ = datastore_util.FetchPage(query, 2)
    self.assertEqual(2, len(labs))
    self.assertEqual('lab0', labs[0].lab_name)
    self.assertEqual('lab1', labs[1].lab_name)

  def testFetchPage_withCursor(self):
    query = datastore_entities.LabInfo.query()
    query = query.order(datastore_entities.LabInfo.key)
    labs, _, cursor = datastore_util.FetchPage(query, 2)
    self.assertEqual(2, len(labs))
    labs, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, 2, page_cursor=cursor)
    self.assertEqual(2, len(labs))
    self.assertEqual('lab2', labs[0].lab_name)
    self.assertEqual('lab3', labs[1].lab_name)
    self.assertIsNotNone(next_cursor)
    self.assertEqual(cursor, prev_cursor)

  def testFetchPage_backwards(self):
    query = datastore_entities.LabInfo.query()
    query = query.order(datastore_entities.LabInfo.key)
    labs, _, cursor = datastore_util.FetchPage(query, 2)
    self.assertEqual(2, len(labs))
    labs, _, cursor = datastore_util.FetchPage(
        query, 2, page_cursor=cursor)
    self.assertEqual(2, len(labs))

    labs, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, 2, page_cursor=cursor, backwards=True)
    self.assertEqual(2, len(labs))
    self.assertEqual('lab2', labs[0].lab_name)
    self.assertEqual('lab3', labs[1].lab_name)
    self.assertIsNotNone(prev_cursor)
    self.assertEqual(cursor, next_cursor)

  def testFetchPage_backwardsCountLargeThanRest(self):
    # When FetchPage backwards and the rest is less than 1 page,
    # it will get the first page.
    query = datastore_entities.LabInfo.query()
    query = query.order(datastore_entities.LabInfo.key)
    labs, _, cursor = datastore_util.FetchPage(query, 2)
    self.assertEqual(2, len(labs))

    labs, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, 3, page_cursor=cursor, backwards=True)
    self.assertEqual(3, len(labs))
    self.assertEqual('lab0', labs[0].lab_name)
    self.assertEqual('lab1', labs[1].lab_name)
    self.assertEqual('lab2', labs[2].lab_name)
    self.assertIsNone(prev_cursor)
    self.assertIsNotNone(next_cursor)

  def testBatchQuery(self):
    query = datastore_entities.LabInfo.query()
    labs = list(datastore_util.BatchQuery(query, batch_size=3))
    self.assertEqual(10, len(labs))

  def testBatchQuery_keysOnly(self):
    query = datastore_entities.LabInfo.query()
    lab_keys = datastore_util.BatchQuery(query, batch_size=3, keys_only=True)
    lab_keys = list(lab_keys)
    self.assertEqual(10, len(lab_keys))
    self.assertEqual('lab0', lab_keys[0].id())

  def testBatchQuery_withProjection(self):
    query = datastore_entities.LabInfo.query()
    labs = datastore_util.BatchQuery(
        query, batch_size=3,
        projection=[datastore_entities.LabInfo.lab_name])
    labs = list(labs)
    self.assertEqual(10, len(labs))
    self.assertTrue(hasattr(labs[0], 'lab_name'))
    self.assertFalse(hasattr(labs[0], 'owners'))

  def testGetOrCreateDatastoreEntity_GetWithValidID(self):
    owners = ['owner-1', 'onwer-2']
    datastore_test_util.CreateLabInfo(
        lab_name='lab-name-100',
        owners=owners)
    lab_info_entity = datastore_util.GetOrCreateEntity(
        datastore_entities.LabInfo, entity_id='lab-name-100')
    self.assertEqual('lab-name-100', lab_info_entity.lab_name)
    self.assertItemsEqual(owners, lab_info_entity.owners)

  def testGetOrCreateDatastoreEntity_CreateWithFields(self):
    owners = ['owner-1', 'onwer-2']
    lab_info_entity = datastore_util.GetOrCreateEntity(
        datastore_entities.LabInfo,
        lab_name='lab-name-100',
        owners=owners)
    self.assertEqual('lab-name-100', lab_info_entity.lab_name)
    self.assertItemsEqual(owners, lab_info_entity.owners)


if __name__ == '__main__':
  unittest.main()
