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

from absl.testing import parameterized

import mock

from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import harness_image_metadata_syncer
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.util import ndb_shim as ndb


class HarnessImageMetadataSyncerTest(parameterized.TestCase,
                                     testbed_dependent_test.TestbedDependentTest
                                    ):
  """Tests for HarnessImageMetadataSyncer."""

  @mock.patch('tradefed_cluster.harness_image_metadata_syncer.auth')
  @mock.patch('tradefed_cluster.harness_image_metadata_syncer.datetime')
  @mock.patch('tradefed_cluster.harness_image_metadata_syncer.'
              'datastore_util.datetime')
  @mock.patch('tradefed_cluster.harness_image_metadata_syncer.requests')
  def testSyncHarnessImageMetadata_NoExistingEntity(
      self, mock_requests, mock_util_datetime, mock_syncer_datetime,
      unused_mock_auth):
    """Test sync harness image metadata."""
    time_now = datetime.datetime(2020, 12, 24)
    time_created = datetime.datetime(2020, 12, 10)
    time_created_txt = '2020-12-10T00:00:00.000000Z'

    mock_util_datetime.datetime.utcnow.return_value = time_now
    mock_syncer_datetime.datetime.utcnow.return_value = time_now
    mock_syncer_datetime.datetime.strptime = datetime.datetime.strptime
    mock_requests.get().json.side_effect = [
        {'versions': [
            {'name': ('projects/dockerized-tradefed/locations/us/repositories/'
                      'gcr.io/packages/tradefed/versions/sha256:sha1'),
             'createTime': time_created_txt,
             'relatedTags': [
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/111111')
                 },
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/golden')
                 },
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/canary')
                 },
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/'
                           'golden_tradefed_image_20201210_1200_RC00')
                 },
             ],
            },
            {'name': ('projects/dockerized-tradefed/locations/us/repositories/'
                      'gcr.io/packages/tradefed/versions/sha256:sha2'),
             'createTime': time_created_txt,
             'relatedTags': [
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/2222222')
                 },
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/'
                           'golden_tradefed_image_20201210_0600_RC00')
                 },
             ],
            },
        ],
         'nextPageToken': 'sometoken'},
        {'versions': [
            {'name': ('projects/dockerized-tradefed/locations/us/repositories/'
                      'gcr.io/packages/tradefed/versions/sha256:sha3'),
             'createTime': time_created_txt,
             'relatedTags': [
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/3333333')
                 },
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/staging')
                 },
             ],
            },
        ],
         'nextPageToken': ''},
    ]

    harness_image_metadata_syncer.SyncHarnessImageMetadata()

    keys = [
        ndb.Key(datastore_entities.TestHarnessImageMetadata,
                'gcr.io/dockerized-tradefed/tradefed:sha256:sha1'),
        ndb.Key(datastore_entities.TestHarnessImageMetadata,
                'gcr.io/dockerized-tradefed/tradefed:sha256:sha2'),
        ndb.Key(datastore_entities.TestHarnessImageMetadata,
                'gcr.io/dockerized-tradefed/tradefed:sha256:sha3'),
    ]
    entity_1, entity_2, entity_3 = ndb.get_multi(keys)

    self.assertEqual('sha256:sha1', entity_1.digest)
    self.assertEqual('111111', entity_1.test_harness_version)
    self.assertEqual(time_created, entity_1.create_time)
    self.assertEqual(time_now, entity_1.sync_time)
    self.assertCountEqual([
        '111111', 'golden', 'canary', 'golden_tradefed_image_20201210_1200_RC00'
    ], entity_1.current_tags)
    self.assertCountEqual(['golden'], entity_1.historical_tags)

    self.assertEqual('sha256:sha2', entity_2.digest)
    self.assertEqual('2222222', entity_2.test_harness_version)
    self.assertEqual(time_created, entity_2.create_time)
    self.assertEqual(time_now, entity_2.sync_time)
    self.assertCountEqual([
        '2222222',
        'golden_tradefed_image_20201210_0600_RC00',
    ], entity_2.current_tags)
    self.assertCountEqual(['golden'], entity_2.historical_tags)

    self.assertEqual('sha256:sha3', entity_3.digest)
    self.assertEqual('3333333', entity_3.test_harness_version)
    self.assertEqual(time_created, entity_3.create_time)
    self.assertEqual(time_now, entity_3.sync_time)
    self.assertCountEqual(['3333333', 'staging'], entity_3.current_tags)
    self.assertEmpty(entity_3.historical_tags)

  @mock.patch('tradefed_cluster.harness_image_metadata_syncer.auth')
  @mock.patch('tradefed_cluster.harness_image_metadata_syncer.datetime')
  @mock.patch('tradefed_cluster.harness_image_metadata_syncer.'
              'datastore_util.datetime')
  @mock.patch('tradefed_cluster.harness_image_metadata_syncer.requests')
  def testSyncHarnessImageMetadata_OverwriteExistingEntities(
      self, mock_requests, mock_util_datetime, mock_syncer_datetime,
      unused_mock_auth):
    """Test sync harness image metadata."""
    time_now = datetime.datetime(2020, 12, 24)
    time_created = datetime.datetime(2020, 12, 10)
    time_created_txt = '2020-12-10T00:00:00.000000Z'

    mock_util_datetime.datetime.utcnow.return_value = time_now
    mock_syncer_datetime.datetime.utcnow.return_value = time_now
    mock_syncer_datetime.datetime.strptime = datetime.datetime.strptime
    mock_requests.get().json.side_effect = [
        {'versions': [
            {'name': ('projects/dockerized-tradefed/locations/us/repositories/'
                      'gcr.io/packages/tradefed/versions/sha256:sha1'),
             'createTime': time_created_txt,
             'relatedTags': [
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/111111')
                 },
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/golden')
                 },
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/canary')
                 },
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/'
                           'golden_tradefed_image_20201210_1200_RC00')
                 },
             ],
            },
            {'name': ('projects/dockerized-tradefed/locations/us/repositories/'
                      'gcr.io/packages/tradefed/versions/sha256:sha2'),
             'createTime': time_created_txt,
             'relatedTags': [
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/2222222')
                 },
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/'
                           'golden_tradefed_image_20201210_0600_RC00')
                 },
             ],
            },
        ],
         'nextPageToken': 'sometoken'},
        {'versions': [
            {'name': ('projects/dockerized-tradefed/locations/us/repositories/'
                      'gcr.io/packages/tradefed/versions/sha256:sha3'),
             'createTime': time_created_txt,
             'relatedTags': [
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/3333333')
                 },
                 {'name': ('projects/dockerized-tradefed/locations/us/'
                           'repositories/gcr.io/packages/tradefed/tags/staging')
                 },
             ],
            },
        ],
         'nextPageToken': ''},
    ]

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
                'gcr.io/dockerized-tradefed/tradefed:sha256:sha1'),
        ndb.Key(datastore_entities.TestHarnessImageMetadata,
                'gcr.io/dockerized-tradefed/tradefed:sha256:sha2'),
        ndb.Key(datastore_entities.TestHarnessImageMetadata,
                'gcr.io/dockerized-tradefed/tradefed:sha256:sha3'),
    ]
    entity_1, entity_2, entity_3 = ndb.get_multi(keys)

    self.assertEqual('sha256:sha1', entity_1.digest)
    self.assertEqual('111111', entity_1.test_harness_version)
    self.assertEqual(time_created, entity_1.create_time)
    self.assertEqual(time_now, entity_1.sync_time)
    self.assertCountEqual([
        '111111', 'golden', 'canary', 'golden_tradefed_image_20201210_1200_RC00'
    ], entity_1.current_tags)
    self.assertCountEqual(['golden'], entity_1.historical_tags)

    self.assertEqual('sha256:sha2', entity_2.digest)
    self.assertEqual('2222222', entity_2.test_harness_version)
    self.assertEqual(time_created, entity_2.create_time)
    self.assertEqual(time_now, entity_2.sync_time)
    self.assertCountEqual([
        '2222222',
        'golden_tradefed_image_20201210_0600_RC00',
    ], entity_2.current_tags)
    self.assertCountEqual(['golden'], entity_2.historical_tags)

    self.assertEqual('sha256:sha3', entity_3.digest)
    self.assertEqual('3333333', entity_3.test_harness_version)
    self.assertEqual(time_created, entity_3.create_time)
    self.assertEqual(time_now, entity_3.sync_time)
    self.assertCountEqual(['3333333', 'staging'], entity_3.current_tags)
    self.assertEmpty(entity_3.historical_tags)

  @parameterized.named_parameters(
      ('Same image digest.', 'test_repo:t1', 'test_repo:t2', True),
      ('Different image digests.', 'test_repo:t1', 'test_repo:t3', False),
      ('Only split on first delimiter.', 'test_repo:t1:xx', 'test_repo:t1',
       False),
      ('Same url', 'test_repo:t1', 'test_repo:t1', True),
      ('Same url with default tag', 'test_repo:t3', 'test_repo', True),
      ('One is empty', '', 'test_repo:t1', False),
      ('Image not found', 'test_repo:notfound', 'test_repo:t1', False),
  )
  def testAreHarnessImagesEqual(self, image_url_a, image_url_b,
                                expected_result):
    datastore_test_util.CreateTestHarnessImageMetadata(
        repo_name='test_repo', digest='d1', current_tags=['t1', 't2'])
    datastore_test_util.CreateTestHarnessImageMetadata(
        repo_name='test_repo', digest='d2', current_tags=['t3', 'latest'])

    self.assertEqual(
        expected_result,
        harness_image_metadata_syncer.AreHarnessImagesEqual(
            image_url_a, image_url_b))

  @parameterized.named_parameters(
      ('Image URL found.', 'test_repo_1:t1_1', 'v1_1'),
      ('Image URL found with latest tag.', 'test_repo_1', 'v1_1'),
      ('Image URL not found.', 'test_repo_1:t1_3', 'UNKNOWN'),
  )
  def testGetHarnessVersionFromImageUrl(self, image_url, expected_version):
    datastore_test_util.CreateTestHarnessImageMetadata(
        repo_name='test_repo_1',
        digest='d1',
        current_tags=['t1_1', 't1_2', 'latest'],
        test_harness_version='v1_1')

    self.assertEqual(
        expected_version,
        harness_image_metadata_syncer.GetHarnessVersionFromImageUrl(image_url))

  @parameterized.named_parameters(
      ('Image URL found.', 'test_repo_1:t1_1', 'test_repo_1@sha256:d1'),
      ('Image URL not found.', 'test_repo_1:t1_3', None),
  )
  def testGetHarnessImageWithShaFromImageUrlWithTag(
      self, image_url, expected_image_url_with_sha):
    datastore_test_util.CreateTestHarnessImageMetadata(
        repo_name='test_repo_1',
        digest='sha256:d1',
        current_tags=['t1_1', 't1_2', 'latest'],
        test_harness_version='v1_1')

    self.assertEqual(
        expected_image_url_with_sha,
        harness_image_metadata_syncer.GetHarnessImageWithShaFromImageUrlWithTag(
            image_url))


if __name__ == '__main__':
  unittest.main()
