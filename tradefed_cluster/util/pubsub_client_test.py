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

import threading
import unittest

from googleapiclient import errors
import mock


from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.util import pubsub_client

HTTP_ERROR_409 = errors.HttpError(
    resp=mock.MagicMock(status=409), content='')
HTTP_ERROR_404 = errors.HttpError(
    resp=mock.MagicMock(status=404), content='')


class PubsubClientTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super(PubsubClientTest, self).setUp()
    self.mock_api_client = mock.MagicMock()
    self.pubsub_client = pubsub_client.PubSubClient(
        api_client=self.mock_api_client)

  @mock.patch.object(pubsub_client, 'discovery')
  def testCreatePubsubClient(self, mock_discovery):
    """Tests use pubsub client from multiple thread."""
    api_client1 = mock.MagicMock()
    api_client2 = mock.MagicMock()
    mock_discovery.build.side_effect = [api_client1, api_client2]

    client = pubsub_client.PubSubClient()
    client.CreateTopic('topic')
    # In another thread, it would create another api_client.
    t = threading.Thread(
        target=lambda: client.GetSubscription('subscription'))
    t.start()
    t.join(timeout=1)

    mock_discovery.assert_has_calls([
        mock.call.build('pubsub', 'v1'),
        mock.call.build('pubsub', 'v1')
    ])

    api_client1.assert_has_calls([
        mock.call.projects(),
        mock.call.projects().topics(),
        mock.call.projects().topics().create(
            name='topic',
            body={}),
        mock.call.projects().topics().create().execute()])
    api_client2.assert_has_calls([
        mock.call.projects(),
        mock.call.projects().subscriptions(),
        mock.call.projects().subscriptions().get(
            subscription='subscription'),
        mock.call.projects().subscriptions().get().execute()])

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

  def testGetSubscription(self):
    self.pubsub_client.GetSubscription('subscription')

    self.mock_api_client.assert_has_calls([
        mock.call.projects(),
        mock.call.projects().subscriptions(),
        mock.call.projects().subscriptions().get(
            subscription='subscription'),
        mock.call.projects().subscriptions().get().execute()])

  def testGetSubscription_noExist(self):
    self.mock_api_client.projects().subscriptions().get(
        ).execute.side_effect = [HTTP_ERROR_404]

    sub = self.pubsub_client.GetSubscription('subscription')

    self.mock_api_client.assert_has_calls([
        mock.call.projects(),
        mock.call.projects().subscriptions(),
        mock.call.projects().subscriptions().get(
            subscription='subscription'),
        mock.call.projects().subscriptions().get().execute()])
    self.assertIsNone(sub)

  def testCreateSubscription(self):
    """Tests whether the method makes a correct API request."""
    self.mock_api_client.projects().subscriptions().get(
        ).execute.side_effect = [HTTP_ERROR_404]

    self.pubsub_client.CreateSubscription('subscription', 'topic')

    self.mock_api_client.assert_has_calls([
        mock.call.__bool__(),
        mock.call.projects(),
        mock.call.projects().subscriptions(),
        mock.call.projects().subscriptions().get(
            subscription='subscription'),
        mock.call.projects().subscriptions().get().execute(),
        mock.call.__bool__(),
        mock.call.projects(),
        mock.call.projects().subscriptions(),
        mock.call.projects().subscriptions().create(
            name='subscription',
            body={
                'topic': 'topic',
                'ackDeadlineSeconds': pubsub_client.DEFAULT_ACK_DEADLINE_SECONDS
            }),
        mock.call.projects().subscriptions().create().execute()])

  def testCreateSubscription_alreadyExists(self):
    """Tests whether the method makes a correct API request."""
    self.mock_api_client.projects().subscriptions().get(
        ).execute.side_effect = [{
            'name': 'subscription',
            'topic': 'topic'}]

    self.pubsub_client.CreateSubscription('subscription', 'topic')

    self.mock_api_client.assert_has_calls([
        mock.call.projects(),
        mock.call.projects().subscriptions(),
        mock.call.projects().subscriptions().get(
            subscription='subscription'),
        mock.call.projects().subscriptions().get().execute()])

  def testPullMessages(self):
    """Tests whether the method makes a correct API request."""
    (self.mock_api_client.projects.return_value.subscriptions.return_value
     .pull.return_value.execute.return_value) = {
         'receivedMessages': []
     }

    messages = self.pubsub_client.PullMessages('subscription', 999)

    self.assertEmpty(messages)
    self.mock_api_client.assert_has_calls([
        mock.call.projects(),
        mock.call.projects().subscriptions(),
        mock.call.projects().subscriptions().pull(
            subscription='subscription',
            body={
                'returnImmediately': False,
                'maxMessages': 999
            }),
        mock.call.projects().subscriptions().pull().execute()])

  def testAcknowledgeMessages(self):
    """Tests whether the method makes a correct API request."""
    ack_ids = [1, 2, 3, 4, 5]

    self.pubsub_client.AcknowledgeMessages('subscription', ack_ids)

    self.mock_api_client.assert_has_calls([
        mock.call.projects(),
        mock.call.projects().subscriptions(),
        mock.call.projects().subscriptions().acknowledge(
            subscription='subscription',
            body={'ackIds': ack_ids}),
        mock.call.projects().subscriptions().acknowledge().execute()])


if __name__ == '__main__':
  unittest.main()
