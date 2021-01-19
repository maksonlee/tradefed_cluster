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
"""Tests for harness_image_metadata_syncer."""
import datetime
import unittest
import mock

from tradefed_cluster import datastore_entities
from tradefed_cluster import harness_image_metadata_syncer
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.util import ndb_shim as ndb


class HarnessImageMetadataSyncerTest(testbed_dependent_test.TestbedDependentTest
                                    ):
  """Tests for HarnessImageMetadataSyncer."""

  @mock.patch('tradefed_cluster.harness_image_metadata_syncer.auth')
  @mock.patch('tradefed_cluster.harness_image_metadata_syncer.datetime')
  @mock.patch('tradefed_cluster.harness_image_metadata_syncer.requests')
  def testSyncHarnessImageMetadata_NoExistingEntity(self, mock_requests,
                                                    mock_datetime, mock_auth):
    """Test sync harness image metadata."""
    time_now = datetime.datetime(2020, 12, 24)
    time_created = datetime.datetime(2020, 12, 10)
    time_created_ms = str(
        int((time_created - datetime.datetime(1970, 1, 1)).total_seconds() *
            1000))

    mock_datetime.datetime.utcnow.return_value = time_now
    mock_datetime.datetime.utcfromtimestamp = datetime.datetime.utcfromtimestamp
    mock_requests.get().json.return_value = {
        'manifest': {
            'sha1': {
                'tag': [
                    '111111',
                    'golden',
                    'canary',
                    'golden_tradefed_image_20201210_1200_RC00',
                ],
                'timeCreatedMs': time_created_ms,
            },
            'sha2': {
                'tag': [
                    '2222222',
                    'golden_tradefed_image_20201210_0600_RC00',
                ],
                'timeCreatedMs': time_created_ms,
            },
            'sha3': {
                'tag': [
                    '3333333',
                    'staging',
                ],
                'timeCreatedMs': time_created_ms,
            },
        }
    }

    harness_image_metadata_syncer.SyncHarnessImageMetadata()

    keys = [
        ndb.Key(datastore_entities.TestHarnessImageMetadata,
                'gcr.io/dockerized-tradefed/tradefed:sha1'),
        ndb.Key(datastore_entities.TestHarnessImageMetadata,
                'gcr.io/dockerized-tradefed/tradefed:sha2'),
        ndb.Key(datastore_entities.TestHarnessImageMetadata,
                'gcr.io/dockerized-tradefed/tradefed:sha3'),
    ]
    entity_1, entity_2, entity_3 = ndb.get_multi(keys)

    self.assertEqual('sha1', entity_1.digest)
    self.assertEqual('111111', entity_1.test_harness_version)
    self.assertEqual(time_created, entity_1.create_time)
    self.assertEqual(time_now, entity_1.sync_time)
    self.assertCountEqual([
        '111111', 'golden', 'canary', 'golden_tradefed_image_20201210_1200_RC00'
    ], entity_1.current_tags)
    self.assertCountEqual(['golden'], entity_1.historical_tags)

    self.assertEqual('sha2', entity_2.digest)
    self.assertEqual('2222222', entity_2.test_harness_version)
    self.assertEqual(time_created, entity_2.create_time)
    self.assertEqual(time_now, entity_2.sync_time)
    self.assertCountEqual([
        '2222222',
        'golden_tradefed_image_20201210_0600_RC00',
    ], entity_2.current_tags)
    self.assertCountEqual(['golden'], entity_2.historical_tags)

    self.assertEqual('sha3', entity_3.digest)
    self.assertEqual('3333333', entity_3.test_harness_version)
    self.assertEqual(time_created, entity_3.create_time)
    self.assertEqual(time_now, entity_3.sync_time)
    self.assertCountEqual(['3333333', 'staging'], entity_3.current_tags)
    self.assertEmpty(entity_3.historical_tags)

  @mock.patch('tradefed_cluster.harness_image_metadata_syncer.auth')
  @mock.patch('tradefed_cluster.harness_image_metadata_syncer.datetime')
  @mock.patch('tradefed_cluster.harness_image_metadata_syncer.requests')
  def testSyncHarnessImageMetadata_OverwriteExistingEntities(
      self, mock_requests, mock_datetime, mock_auth):
    """Test sync harness image metadata."""
    time_now = datetime.datetime(2020, 12, 24)
    time_created = datetime.datetime(2020, 12, 10)
    time_created_ms = str(
        int((time_created - datetime.datetime(1970, 1, 1)).total_seconds() *
            1000))

    mock_datetime.datetime.utcnow.return_value = time_now
    mock_datetime.datetime.utcfromtimestamp = datetime.datetime.utcfromtimestamp
    mock_requests.get().json.return_value = {
        'manifest': {
            'sha1': {
                'tag': [
                    '111111',
                    'golden',
                    'canary',
                    'golden_tradefed_image_20201210_1200_RC00',
                ],
                'timeCreatedMs': time_created_ms,
            },
            'sha2': {
                'tag': [
                    '2222222',
                    'golden_tradefed_image_20201210_0600_RC00',
                ],
                'timeCreatedMs': time_created_ms,
            },
            'sha3': {
                'tag': [
                    '3333333',
                    'staging',
                ],
                'timeCreatedMs': time_created_ms,
            },
        }
    }

    existing_entities = [
        datastore_entities.TestHarnessImageMetadata(
            key=ndb.Key(datastore_entities.TestHarnessImageMetadata,
                        'gcr.io/dockerized-tradefed/tradefed:sha1'),
            repo_name='gcr.io/dockerized-tradefed/tradefed',
            digest='sha1',
            test_harness=harness_image_metadata_syncer._TRADEFED_HARNESS_NAME,
            test_harness_version='111111',
            current_tags=['111111', 'canary', 'staging'],
            create_time=time_created,
            sync_time=time_now),
        datastore_entities.TestHarnessImageMetadata(
            key=ndb.Key(datastore_entities.TestHarnessImageMetadata,
                        'gcr.io/dockerized-tradefed/tradefed:sha2'),
            repo_name='gcr.io/dockerized-tradefed/tradefed',
            digest='sha2',
            test_harness=harness_image_metadata_syncer._TRADEFED_HARNESS_NAME,
            test_harness_version='2222222',
            current_tags=[
                '2222222', 'golden', 'golden_tradefed_image_20201210_0600_RC00'
            ],
            historical_tags=['golden'],
            create_time=time_created,
            sync_time=time_now),
    ]
    ndb.put_multi(existing_entities)

    harness_image_metadata_syncer.SyncHarnessImageMetadata()

    keys = [
        ndb.Key(datastore_entities.TestHarnessImageMetadata,
                'gcr.io/dockerized-tradefed/tradefed:sha1'),
        ndb.Key(datastore_entities.TestHarnessImageMetadata,
                'gcr.io/dockerized-tradefed/tradefed:sha2'),
        ndb.Key(datastore_entities.TestHarnessImageMetadata,
                'gcr.io/dockerized-tradefed/tradefed:sha3'),
    ]
    entity_1, entity_2, entity_3 = ndb.get_multi(keys)

    self.assertEqual('sha1', entity_1.digest)
    self.assertEqual('111111', entity_1.test_harness_version)
    self.assertEqual(time_created, entity_1.create_time)
    self.assertEqual(time_now, entity_1.sync_time)
    self.assertCountEqual([
        '111111', 'golden', 'canary', 'golden_tradefed_image_20201210_1200_RC00'
    ], entity_1.current_tags)
    self.assertCountEqual(['golden'], entity_1.historical_tags)

    self.assertEqual('sha2', entity_2.digest)
    self.assertEqual('2222222', entity_2.test_harness_version)
    self.assertEqual(time_created, entity_2.create_time)
    self.assertEqual(time_now, entity_2.sync_time)
    self.assertCountEqual([
        '2222222',
        'golden_tradefed_image_20201210_0600_RC00',
    ], entity_2.current_tags)
    self.assertCountEqual(['golden'], entity_2.historical_tags)

    self.assertEqual('sha3', entity_3.digest)
    self.assertEqual('3333333', entity_3.test_harness_version)
    self.assertEqual(time_created, entity_3.create_time)
    self.assertEqual(time_now, entity_3.sync_time)
    self.assertCountEqual(['3333333', 'staging'], entity_3.current_tags)
    self.assertEmpty(entity_3.historical_tags)


if __name__ == '__main__':
  unittest.main()