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

"""Tests for device_history_cleaner."""

import datetime
import unittest

import mock
import six
import webtest


from tradefed_cluster import datastore_entities
from tradefed_cluster import device_history_cleaner
from tradefed_cluster import testbed_dependent_test

TIMESTAMP_1 = datetime.datetime(2015, 5, 7)
TIMESTAMP_2 = datetime.datetime(2015, 5, 8)
TIMESTAMP_3 = datetime.datetime(2015, 11, 2)


class DeviceHistoryCleanerTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super(DeviceHistoryCleanerTest, self).setUp()

    device_history_cleaner.BATCH_SIZE = 200
    device_history_0 = datastore_entities.DeviceStateHistory(
        device_serial='serial',
        timestamp=TIMESTAMP_1,
        state='Available')
    device_history_0.put()
    device_history_1 = datastore_entities.DeviceStateHistory(
        device_serial='serial',
        timestamp=TIMESTAMP_2,
        state='Gone')
    device_history_1.put()
    device_history_2 = datastore_entities.DeviceStateHistory(
        device_serial='serial',
        timestamp=TIMESTAMP_3,
        state='Available')
    device_history_2.put()

  def testRetrieveKeys_allKeys(self):
    """Tests retrieving keys for an end date after the latest one."""
    end_date = TIMESTAMP_3 + datetime.timedelta(days=1)
    keys = next(device_history_cleaner.RetrieveKeys(end_date))
    self.assertEqual(3, len(keys))

  def testRetrieveKeys_reachBatchSize(self):
    """Tests retrieving keys when the batch size is reached."""
    end_date = TIMESTAMP_3 + datetime.timedelta(days=1)
    device_history_cleaner.BATCH_SIZE = 2
    keys = next(device_history_cleaner.RetrieveKeys(end_date))
    self.assertEqual(2, len(keys))

  def testRetrieveKeys_singleKey(self):
    """Tests retrieving keys for an end date after a single key."""
    keys = next(
        device_history_cleaner.RetrieveKeys(datetime.datetime(2015, 5, 8)))
    self.assertEqual(1, len(keys))
    entity = keys[0].get()
    self.assertEqual(TIMESTAMP_1, entity.timestamp)

  def testRetrieveKeys_noKeys(self):
    """Tests retrieving keys for an end date older than any available."""
    keys = next(
        device_history_cleaner.RetrieveKeys(datetime.datetime(1970, 1, 1)))
    self.assertEqual(0, len(keys))

  @mock.patch.object(device_history_cleaner, '_Now')
  def testDeleteEntities_keepLast(self, mock_now):
    """Tests deleting keys for a date where only the last one should stay."""
    now = TIMESTAMP_3 + datetime.timedelta(100)
    mock_now.return_value = now
    result = device_history_cleaner.DeleteEntities(100)
    self.assertEqual(2, result)
    count = datastore_entities.DeviceStateHistory.query().count()
    self.assertEqual(1, count)
    entities = datastore_entities.DeviceStateHistory.query().fetch()
    self.assertEqual(TIMESTAMP_3, entities[0].timestamp)

  @mock.patch.object(device_history_cleaner, '_Now')
  def testDeleteEntities_deleteAll(self, mock_now):
    """Tests deleting keys for a date where all should be deleted."""
    now = TIMESTAMP_3 + datetime.timedelta(101)
    mock_now.return_value = now
    result = device_history_cleaner.DeleteEntities(100)
    self.assertEqual(3, result)
    count = datastore_entities.DeviceStateHistory.query().count()
    self.assertEqual(0, count)

  @mock.patch.object(device_history_cleaner, '_Now')
  def testDeleteEntities_deleteAll_reachBatchSize(self, mock_now):
    """Tests deleting keys for a date where all should be deleted."""
    device_history_cleaner.BATCH_SIZE = 2
    now = TIMESTAMP_3 + datetime.timedelta(101)
    mock_now.return_value = now
    result = device_history_cleaner.DeleteEntities(100)
    self.assertEqual(3, result)
    count = datastore_entities.DeviceStateHistory.query().count()
    self.assertEqual(0, count)

  @mock.patch.object(device_history_cleaner, '_Now')
  def testDeleteEntities_singleDay(self, mock_now):
    """Tests deleting keys for 1 retention day."""
    now = datetime.datetime(2015, 5, 9)
    mock_now.return_value = now
    result = device_history_cleaner.DeleteEntities(1)
    self.assertEqual(1, result)
    count = datastore_entities.DeviceStateHistory.query().count()
    self.assertEqual(2, count)

  @mock.patch.object(device_history_cleaner, '_Now')
  def testDeleteEntities_timeout(self, mock_now):
    """Tests the request end after 8 minutes."""
    device_history_cleaner.BATCH_SIZE = 2
    now = TIMESTAMP_3 + datetime.timedelta(101)
    mock_now.side_effect = [
        now,
        now + datetime.timedelta(
            minutes=device_history_cleaner.TIMEOUT_MINUTES + 1),
    ]
    result = device_history_cleaner.DeleteEntities(100)
    self.assertEqual(2, result)

  @mock.patch.object(device_history_cleaner, '_Now')
  def testGet(self, mock_now):
    now = datetime.datetime(2015, 11, 17)
    mock_now.return_value = now
    webapp = webtest.TestApp(device_history_cleaner.APP)

    response = webapp.get('/')

    count = datastore_entities.DeviceStateHistory.query().count()
    self.assertEqual(1, count)
    self.assertEqual(response.status_int, 200)
    self.assertEqual(six.ensure_str(response.normal_body), '2')


if __name__ == '__main__':
  unittest.main()
