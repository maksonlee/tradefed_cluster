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
