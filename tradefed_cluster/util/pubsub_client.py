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

"""A utiliy module for Google Cloud Pub/Sub API."""

import logging

from googleapiclient import discovery
from googleapiclient import errors

PUBSUB_API_SCOPES = ('https://www.googleapis.com/auth/pubsub')
PUBSUB_API_NAME = 'pubsub'
PUBSUB_API_VERSION = 'v1'
DEFAULT_ACK_DEADLINE_SECONDS = 120


class PubSubClient(object):
  """A wrapper class for Cloud Pub/Sub API client."""

  def __init__(self, api_client=None):
    """Creates a PubSubClient instance.

    Args:
      api_client: an API client instance. New instance will be created if not
        given.
    """
    self._api_client = api_client
    if not self._api_client:
      self._api_client = discovery.build(PUBSUB_API_NAME, PUBSUB_API_VERSION)

  def CreateTopic(self, topic):
    """Create the topic if it does not exist.

    Args:
      topic: the name of the topic.
    Raises:
      HttpError: fail to create topic
    """
    try:
      self._api_client.projects().topics().create(
          name=topic, body={}
      ).execute()
    except errors.HttpError as e:
      # Ignore 409 because it means the topic already exists.
      if e.resp.status != 409:
        raise
      logging.debug('Topic %s already exists', topic)

  def PublishMessages(self, topic, messages):
    """Publish messages to supplied topic.

    Args:
      topic: the name of a topic.
      messages: the list of messages to publish.
    Returns:
      a list of the message ids of each published message.
    """
    resp = self._api_client.projects().topics().publish(
        topic=topic,
        body={
            'messages': messages
        }
    ).execute()
    return resp.get('messageIds')

  def GetSubscription(self, subscription):
    """Get a subscription.

    Args:
      subscription: the name of a subscription.
    Returns:
      the subscription detail.
    Raises:
      HttpError: fail to get subscription
    """
    try:
      return self._api_client.projects().subscriptions().get(
          subscription=subscription).execute()
    except errors.HttpError as e:
      # 404 means the subscription doesn't exist.
      if e.resp.status != 404:
        raise
      return None

  def CreateSubscription(
      self, subscription, topic,
      ack_deadline_seconds=DEFAULT_ACK_DEADLINE_SECONDS):
    """Creates a subscription if it does not exist.

    Args:
      subscription: the name of a subscription.
      topic: a topic to subscribe.
      ack_deadline_seconds: ack deadline in seconds.
    Raises:
      HttpError: fail to create subscription
    """
    sub = self.GetSubscription(subscription)
    if (sub and sub.get('name') == subscription and
        sub.get('topic') == topic):
      logging.debug('subscription %s for %s already exist,'
                    'will not create a new one',
                    subscription, topic)
      return

    request_body = {'topic': topic}
    if ack_deadline_seconds:
      request_body['ackDeadlineSeconds'] = ack_deadline_seconds
    self._api_client.projects().subscriptions().create(
        name=subscription, body=request_body
    ).execute()

  def PullMessages(self, subscription, max_messages):
    """Pulls messages from a given subscription.

    Args:
      subscription: the name of a subscription.
      max_messages: the maximum number of messages to pull.
    Returns:
      a list of messages pulled from a subscription.
    """
    resp = self._api_client.projects().subscriptions().pull(
        subscription=subscription,
        body={
            # Based on https://b.corp.example.com/issues/155128069#comment7,
            # we should set returnImmediately to False to wait for messages.
            'returnImmediately': False,
            'maxMessages': max_messages
        }
    ).execute()
    return resp.get('receivedMessages')

  def AcknowledgeMessages(self, subscription, ack_ids):
    """Acknowedge messages from a given subscription.

    Args:
      subscription: the name of a subscription.
      ack_ids: the ack IDs of messages to acknowledge.
    """
    self._api_client.projects().subscriptions().acknowledge(
        subscription=subscription,
        body={
            'ackIds': ack_ids
        }
    ).execute()
