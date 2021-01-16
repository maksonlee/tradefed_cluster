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
"""Tests for tradefed_cluster.test_harness_image_api."""
import datetime
import unittest

from protorpc import protojson

from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import datastore_test_util

_FAKE_SYNC_TIME = datetime.datetime(2020, 12, 25)


class TestHarnessImageApiTest(api_test.ApiTest):
  """Unit tests for TestHarnessImageApi."""

  def setUp(self):
    super(TestHarnessImageApiTest, self).setUp()
    self._entities = [
        datastore_test_util.CreateTestHarnessImageMetadata(
            digest='sha1',
            test_harness_version='1111111',
            current_tags=['1111111', 'canary', 'staging'],
            create_time=datetime.datetime(2020, 12, 12)),
        datastore_test_util.CreateTestHarnessImageMetadata(
            digest='sha2',
            test_harness_version='2222222',
            current_tags=[
                '2222222', 'golden', 'golden_tradefed_image_20201210_0600_RC00'
            ],
            create_time=datetime.datetime(2020, 12, 10)),
        datastore_test_util.CreateTestHarnessImageMetadata(
            digest='sha3',
            test_harness_version='3333333',
            current_tags=[
                '3333333', 'golden_tradefed_image_20201209_0600_RC00'
            ],
            create_time=datetime.datetime(2020, 12, 9)),
        datastore_test_util.CreateTestHarnessImageMetadata(
            digest='sha4',
            test_harness_version='4444444',
            current_tags=[
                '4444444', 'golden_tradefed_image_20201208_0600_RC00'
            ],
            create_time=datetime.datetime(2020, 12, 8)),
    ]

  def testTestListHarnessImages_allInOnePage(self):

    api_request = {'count': 4}
    api_response = self.testapp.post_json(
        '/_ah/api/TestHarnessImageApi.ListTestHarnessImages', api_request)
    image_collection = protojson.decode_message(
        api_messages.TestHarnessImageMetadataCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)

    images = image_collection.images
    next_cursor = image_collection.next_cursor
    self.assertLen(images, 4)
    self.assertIsNone(next_cursor)

    self.assertEqual(self._entities[0].digest, images[0].digest)
    self.assertEqual(self._entities[0].repo_name, images[0].repo_name)
    self.assertEqual(self._entities[0].test_harness, images[0].test_harness)
    self.assertEqual(self._entities[0].test_harness_version,
                     images[0].test_harness_version)
    self.assertEqual(self._entities[0].current_tags, images[0].tags)
    self.assertEqual(self._entities[0].create_time, images[0].create_time)

    self.assertEqual(self._entities[1].digest, images[1].digest)
    self.assertEqual(self._entities[1].repo_name, images[1].repo_name)
    self.assertEqual(self._entities[1].test_harness, images[1].test_harness)
    self.assertEqual(self._entities[1].test_harness_version,
                     images[1].test_harness_version)
    self.assertEqual(self._entities[1].current_tags, images[1].tags)
    self.assertEqual(self._entities[1].create_time, images[1].create_time)

    self.assertEqual(self._entities[2].digest, images[2].digest)
    self.assertEqual(self._entities[2].repo_name, images[2].repo_name)
    self.assertEqual(self._entities[2].test_harness, images[2].test_harness)
    self.assertEqual(self._entities[2].test_harness_version,
                     images[2].test_harness_version)
    self.assertEqual(self._entities[2].current_tags, images[2].tags)
    self.assertEqual(self._entities[2].create_time, images[2].create_time)

    self.assertEqual(self._entities[3].digest, images[3].digest)
    self.assertEqual(self._entities[3].repo_name, images[3].repo_name)
    self.assertEqual(self._entities[3].test_harness, images[3].test_harness)
    self.assertEqual(self._entities[3].test_harness_version,
                     images[3].test_harness_version)
    self.assertEqual(self._entities[3].current_tags, images[3].tags)
    self.assertEqual(self._entities[3].create_time, images[3].create_time)

  def testTestListHarnessImages_multiplePages(self):

    api_request = {'count': 2}
    api_response = self.testapp.post_json(
        '/_ah/api/TestHarnessImageApi.ListTestHarnessImages', api_request)
    image_collection = protojson.decode_message(
        api_messages.TestHarnessImageMetadataCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)

    images = image_collection.images
    next_cursor = image_collection.next_cursor
    self.assertLen(images, 2)
    self.assertIsNotNone(next_cursor)

    self.assertEqual(self._entities[0].digest, images[0].digest)
    self.assertEqual(self._entities[0].repo_name, images[0].repo_name)
    self.assertEqual(self._entities[0].test_harness, images[0].test_harness)
    self.assertEqual(self._entities[0].test_harness_version,
                     images[0].test_harness_version)
    self.assertEqual(self._entities[0].current_tags, images[0].tags)
    self.assertEqual(self._entities[0].create_time, images[0].create_time)

    self.assertEqual(self._entities[1].digest, images[1].digest)
    self.assertEqual(self._entities[1].repo_name, images[1].repo_name)
    self.assertEqual(self._entities[1].test_harness, images[1].test_harness)
    self.assertEqual(self._entities[1].test_harness_version,
                     images[1].test_harness_version)
    self.assertEqual(self._entities[1].current_tags, images[1].tags)
    self.assertEqual(self._entities[1].create_time, images[1].create_time)

    api_request = {
        'count': 2,
        'cursor': next_cursor,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/TestHarnessImageApi.ListTestHarnessImages', api_request)
    image_collection = protojson.decode_message(
        api_messages.TestHarnessImageMetadataCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)

    images = image_collection.images
    next_cursor = image_collection.next_cursor
    self.assertLen(images, 2)
    self.assertIsNone(next_cursor)

    self.assertEqual(self._entities[2].digest, images[0].digest)
    self.assertEqual(self._entities[2].repo_name, images[0].repo_name)
    self.assertEqual(self._entities[2].test_harness, images[0].test_harness)
    self.assertEqual(self._entities[2].test_harness_version,
                     images[0].test_harness_version)
    self.assertEqual(self._entities[2].current_tags, images[0].tags)
    self.assertEqual(self._entities[2].create_time, images[0].create_time)

    self.assertEqual(self._entities[3].digest, images[1].digest)
    self.assertEqual(self._entities[3].repo_name, images[1].repo_name)
    self.assertEqual(self._entities[3].test_harness, images[1].test_harness)
    self.assertEqual(self._entities[3].test_harness_version,
                     images[1].test_harness_version)
    self.assertEqual(self._entities[3].current_tags, images[1].tags)
    self.assertEqual(self._entities[3].create_time, images[1].create_time)


if __name__ == '__main__':
  unittest.main()
