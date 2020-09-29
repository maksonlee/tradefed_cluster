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

"""Tests for pubsub_client."""

import unittest

from googleapiclient import errors
import mock


from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.util import pubsub_client

HTTP_ERROR_409 = errors.HttpError(
    resp=mock.MagicMock(status=409), content='')


class PubsubClientTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super(PubsubClientTest, self).setUp()
    self.mock_api_client = mock.MagicMock()
    self.pubsub_client = pubsub_client.PubSubClient(
        api_client=self.mock_api_client)

  def testCreateTopic(self):
    """Tests whether the method makes a correct API request."""
    self.pubsub_client.CreateTopic('topic')

    self.mock_api_client.assert_has_calls([
        mock.call.projects(),
        mock.call.projects().topics(),
        mock.call.projects().topics().create(
            name='topic',
            body={}),
        mock.call.projects().topics().create().execute()])

  def testCreateTopic_alreadyExist(self):
    """Tests create an already existing topic."""
    (self.mock_api_client.projects().topics().create()
     .execute.side_effect) = [HTTP_ERROR_409]

    self.pubsub_client.CreateTopic('topic')

    self.mock_api_client.assert_has_calls([
        mock.call.projects(),
        mock.call.projects().topics(),
        mock.call.projects().topics().create(
            name='topic',
            body={}),
        mock.call.projects().topics().create().execute()])

  def testPublishMessage(self):
    """Tests whether the method makes a correct API request."""
    self.pubsub_client.PublishMessages('topic', [])

    self.mock_api_client.assert_has_calls([
        mock.call.projects(),
        mock.call.projects().topics(),
        mock.call.projects().topics().publish(
            topic='topic',
            body={'messages': []}),
        mock.call.projects().topics().publish().execute()])


if __name__ == '__main__':
  unittest.main()
