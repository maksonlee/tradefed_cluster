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


def _CheckTestHarnessImageEntityAndApiMessageEqual(entity, message):
  """A helper method to check equility.

  Args:
    entity: an instance of datastore_entities.TestHarnessImageMetadata.
    message: an instance of api_messages.TestHarnessImageMetadataMessage.

  Returns:
    A bool, whether the entity and message are considered equal.
  """
  return (entity.repo_name == message.repo_name and
          entity.digest == message.digest and
          entity.test_harness == message.test_harness and
          entity.test_harness_version == message.test_harness_version and
          entity.current_tags == message.tags and
          entity.create_time == message.create_time)


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

    self.assertTrue(
        _CheckTestHarnessImageEntityAndApiMessageEqual(
            self._entities[0], images[0]))
    self.assertTrue(
        _CheckTestHarnessImageEntityAndApiMessageEqual(
            self._entities[1], images[1]))
    self.assertTrue(
        _CheckTestHarnessImageEntityAndApiMessageEqual(
            self._entities[2], images[2]))
    self.assertTrue(
        _CheckTestHarnessImageEntityAndApiMessageEqual(
            self._entities[3], images[3]))

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

    self.assertTrue(
        _CheckTestHarnessImageEntityAndApiMessageEqual(
            self._entities[0], images[0]))
    self.assertTrue(
        _CheckTestHarnessImageEntityAndApiMessageEqual(
            self._entities[1], images[1]))

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

    self.assertTrue(
        _CheckTestHarnessImageEntityAndApiMessageEqual(
            self._entities[2], images[0]))
    self.assertTrue(
        _CheckTestHarnessImageEntityAndApiMessageEqual(
            self._entities[3], images[1]))

  def testTestListHarnessImages_withFilter_goldenImages(self):

    api_request = {
        'count': 4,
        'tag_prefix': 'golden_tradefed',
    }
    api_response = self.testapp.post_json(
        '/_ah/api/TestHarnessImageApi.ListTestHarnessImages', api_request)
    image_collection = protojson.decode_message(
        api_messages.TestHarnessImageMetadataCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)

    images = image_collection.images
    next_cursor = image_collection.next_cursor
    self.assertLen(images, 3)
    self.assertIsNone(next_cursor)

    self.assertTrue(
        _CheckTestHarnessImageEntityAndApiMessageEqual(
            self._entities[1], images[0]))
    self.assertTrue(
        _CheckTestHarnessImageEntityAndApiMessageEqual(
            self._entities[2], images[1]))
    self.assertTrue(
        _CheckTestHarnessImageEntityAndApiMessageEqual(
            self._entities[3], images[2]))

  def testTestListHarnessImages_withFilter_versionNumberPrefix(self):

    api_request = {
        'count': 4,
        'tag_prefix': '3333',
    }
    api_response = self.testapp.post_json(
        '/_ah/api/TestHarnessImageApi.ListTestHarnessImages', api_request)
    image_collection = protojson.decode_message(
        api_messages.TestHarnessImageMetadataCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)

    images = image_collection.images
    next_cursor = image_collection.next_cursor
    self.assertLen(images, 1)
    self.assertIsNone(next_cursor)

    self.assertTrue(
        _CheckTestHarnessImageEntityAndApiMessageEqual(
            self._entities[2], images[0]))


if __name__ == '__main__':
  unittest.main()
