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

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import copy
import datetime
import re
import unittest

import mock

from six.moves import range


from tradefed_cluster import api_messages
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import datastore_util
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.util import ndb_shim as ndb


class DatastoreUtilTest(testbed_dependent_test.TestbedDependentTest):

  TIMESTAMP = datetime.datetime(2015, 10, 9)

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

  def testFetchPage_lastPage(self):
    """Tests that fetching the last page doesn't produce a next cursor."""
    query = datastore_entities.LabInfo.query()
    labs, _, next_cursor = datastore_util.FetchPage(query, 99)
    self.assertEqual(10, len(labs))
    self.assertIsNone(next_cursor)

  def testFetchPage_backwards(self):
    query = datastore_entities.LabInfo.query()
    query = query.order(datastore_entities.LabInfo.key)
    # Fetch 3 results
    labs, _, cursor = datastore_util.FetchPage(query, 3)
    self.assertEqual(3, len(labs))
    self.assertEqual('lab0', labs[0].lab_name)
    self.assertEqual('lab1', labs[1].lab_name)
    self.assertEqual('lab2', labs[2].lab_name)

    # Fetch 2 results backwards
    labs, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, 2, page_cursor=cursor, backwards=True)
    self.assertEqual(2, len(labs))
    self.assertEqual('lab1', labs[0].lab_name)
    self.assertEqual('lab2', labs[1].lab_name)
    self.assertIsNotNone(prev_cursor)
    self.assertEqual(cursor, next_cursor)

  def testFetchPage_backwardsWithAncestorQuery(self):
    self.ndb_host_0 = datastore_test_util.CreateHost(
        cluster='free',
        hostname='host_0',
        timestamp=self.TIMESTAMP,
        host_state=api_messages.HostState.RUNNING,
    )
    self.ndb_host_1 = datastore_test_util.CreateHost(
        cluster='paid',
        hostname='host_1',
        timestamp=self.TIMESTAMP,
        device_count_timestamp=self.TIMESTAMP,
    )
    self._CreateHostInfoHistory(self.ndb_host_1).put()
    self.ndb_host_1.host_state = api_messages.HostState.UNKNOWN
    self.ndb_host_1.timestamp += datetime.timedelta(hours=1)
    self._CreateHostInfoHistory(self.ndb_host_1).put()
    self.ndb_host_1.host_state = api_messages.HostState.GONE
    self.ndb_host_1.timestamp += datetime.timedelta(hours=1)
    self._CreateHostInfoHistory(self.ndb_host_1).put()

    self._CreateHostInfoHistory(self.ndb_host_0).put()
    self.ndb_host_0.host_state = api_messages.HostState.KILLING
    self.ndb_host_0.timestamp += datetime.timedelta(hours=1)
    self._CreateHostInfoHistory(self.ndb_host_0).put()
    self.ndb_host_0.host_state = api_messages.HostState.GONE
    self.ndb_host_0.timestamp += datetime.timedelta(hours=1)
    self._CreateHostInfoHistory(self.ndb_host_0).put()

    # First page
    query = (
        datastore_entities.HostInfoHistory.query(
            ancestor=ndb.Key(datastore_entities.HostInfo,
                             self.ndb_host_0.hostname)).order(
                                 -datastore_entities.HostInfoHistory.timestamp))
    histories, prev_cursor, next_cursor = datastore_util.FetchPage(query, 2)
    self.assertEqual(2, len(histories))
    self.assertIsNone(prev_cursor)
    self.assertIsNotNone(next_cursor)

    # Back to first page (ancestor query with backwards)
    histories, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, 2, backwards=True)
    self.assertEqual(2, len(histories))
    self.assertEqual(self.ndb_host_0.hostname, histories[0].hostname)
    self.assertEqual(api_messages.HostState.GONE, histories[0].host_state)
    self.assertEqual(self.ndb_host_0.hostname, histories[1].hostname)
    self.assertEqual(api_messages.HostState.KILLING, histories[1].host_state)

  def testFetchPage_backwardsCountLargeThanRest(self):
    # When a page is fetched backwards with a cursor, and the remaining results
    # are smaller than one page, the first page should be fetched instead.
    query = datastore_entities.LabInfo.query()
    query = query.order(datastore_entities.LabInfo.key)
    # Fetch 2 results
    labs, _, cursor = datastore_util.FetchPage(query, 2)
    self.assertEqual(2, len(labs))
    self.assertEqual('lab0', labs[0].lab_name)
    self.assertEqual('lab1', labs[1].lab_name)

    # Fetch 3 results backwards
    labs, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, 3, page_cursor=cursor, backwards=True)
    self.assertEqual(3, len(labs))
    self.assertEqual('lab0', labs[0].lab_name)
    self.assertEqual('lab1', labs[1].lab_name)
    self.assertEqual('lab2', labs[2].lab_name)
    self.assertIsNone(prev_cursor)
    self.assertIsNotNone(next_cursor)

  def testFetchPage_withResultFilter(self):
    """Tests that a predicate function can be applied to the query results."""
    even_lab_number_re = re.compile('^lab[02468]$')
    def _Filter(lab):
      return even_lab_number_re.search(lab.lab_name)

    query = datastore_entities.LabInfo.query()
    query = query.order(datastore_entities.LabInfo.key)
    labs, _, _ = datastore_util.FetchPage(query, 4, result_filter=_Filter)
    self.assertEqual(4, len(labs))
    self.assertEqual('lab0', labs[0].lab_name)
    self.assertEqual('lab2', labs[1].lab_name)
    self.assertEqual('lab4', labs[2].lab_name)
    self.assertEqual('lab6', labs[3].lab_name)

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
        query, batch_size=3, projection=[datastore_entities.LabInfo.lab_name])
    labs = list(labs)
    self.assertEqual(10, len(labs))
    self.assertTrue(hasattr(labs[0], 'lab_name'))
    with self.assertRaises(ndb.UnprojectedPropertyError):
      # try to access .update_timestamp will raise an exception
      _ = labs[0].update_timestamp

  def testGetOrCreateDatastoreEntity_GetWithValidID(self):
    datastore_test_util.CreateLabInfo(lab_name='lab-name-100')
    lab_info_entity = datastore_util.GetOrCreateEntity(
        datastore_entities.LabInfo, entity_id='lab-name-100')
    self.assertEqual('lab-name-100', lab_info_entity.lab_name)

  def testGetOrCreateDatastoreEntity_CreateWithFields(self):
    lab_info_entity = datastore_util.GetOrCreateEntity(
        datastore_entities.LabInfo, lab_name='lab-name-100')
    self.assertEqual('lab-name-100', lab_info_entity.lab_name)

  def _CreateHostInfoHistory(self, host_info):
    """Create HostInfoHistory from HostInfo."""
    host_info_dict = copy.deepcopy(host_info.to_dict())
    # is_bad is computed property, can not be assigned.
    host_info_dict.pop('is_bad')
    # flated_extra_info is computed property, can not be assigned.
    host_info_dict.pop('flated_extra_info')
    return datastore_entities.HostInfoHistory(
        parent=host_info.key, **host_info_dict)

  @mock.patch('tradefed_cluster.datastore_util.datetime')
  def testDeleteEntitiesUpdatedEarlyThanSomeTimeAgo(self, mock_datetime):
    time_now = datetime.datetime(2000, 7, 14)
    mock_datetime.datetime.utcnow.return_value = time_now

    datastore_test_util.CreateTestHarnessImageMetadata(
        digest='d1', sync_time=datetime.datetime(1999, 12, 10))
    datastore_test_util.CreateTestHarnessImageMetadata(
        digest='d2', sync_time=datetime.datetime(2000, 7, 10))
    datastore_test_util.CreateTestHarnessImageMetadata(
        digest='d3', sync_time=datetime.datetime(2000, 5, 10))

    datastore_util.DeleteEntitiesUpdatedEarlyThanSomeTimeAgo(
        datastore_entities.TestHarnessImageMetadata,
        datastore_entities.TestHarnessImageMetadata.sync_time,
        datetime.timedelta(days=7))

    remaining_entities = datastore_entities.TestHarnessImageMetadata.query(
        ).fetch()

    self.assertCountEqual(
        ['d2'], [entity.digest for entity in remaining_entities])


if __name__ == '__main__':
  unittest.main()
