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

"""A notifier module to publish request events via Cloud Pub/Sub."""

import json
import logging
import zlib

import flask
import lazy_object_proxy

from tradefed_cluster import common
from tradefed_cluster import env_config
from tradefed_cluster.services import task_scheduler
from tradefed_cluster.util import pubsub_client


PUBSUB_API_SCOPES = ['https://www.googleapis.com/auth/pubsub']
PUBSUB_API_NAME = 'pubsub'
PUBSUB_API_VERSION = 'v1beta2'

REQUEST_EVENT_PUBSUB_TOPIC = 'projects/%s/topics/%s' % (
    env_config.CONFIG.app_id, 'request_event')
COMMAND_ATTEMPT_EVENT_PUBSUB_TOPIC = 'projects/%s/topics/%s' % (
    env_config.CONFIG.app_id, 'command_attempt_event')
OBJECT_EVENT_QUEUE_HANDLER_PATH = (
    '/_ah/queue/%s' % common.OBJECT_EVENT_QUEUE)

APP = flask.Flask(__name__)


def _CreatePubsubClient():
  """Create a client for Google Cloud Pub/Sub."""
  client = pubsub_client.PubSubClient()
  client.CreateTopic(REQUEST_EVENT_PUBSUB_TOPIC)
  client.CreateTopic(COMMAND_ATTEMPT_EVENT_PUBSUB_TOPIC)
  return client

_PubsubClient = lazy_object_proxy.Proxy(_CreatePubsubClient)  

def _SendEventMessage(encoded_message, pubsub_topic):
  """Sends a message to the event queue notifying a state change event.

  Args:
    encoded_message: proto-json encoded request or attempt state change message.
    pubsub_topic: pubsub topic to send the message to.
  Returns:
    True is the message was sent successfully, False otherwise
  """
  queue = env_config.CONFIG.event_queue_name
  if env_config.CONFIG.use_google_api:
    data = common.UrlSafeB64Encode(encoded_message)
    _PubsubClient.PublishMessages(pubsub_topic, [{'data': data}])
  elif queue:
    task_scheduler.AddTask(queue_name=queue, payload=encoded_message)
  else:
    logging.warning(
        'Unabled to notify events: use_google_api=False and queue is null')


# The below handler is served in frontend module.
@APP.route(OBJECT_EVENT_QUEUE_HANDLER_PATH, methods=['POST'])
def HandleObjectStateChangeEvent():
  """Process a state change event message.

  This method takes protojson-encoded request or attempt state change event
  messages and passes them on to the event queue configured in env_config.

  Returns:
    return '' since flask requires return non-None.
  """
  encoded_message = flask.request.get_data()
  try:
    encoded_message = zlib.decompress(encoded_message)
  except zlib.error:
    logging.warning(
        'payload may not be compressed: %s', encoded_message, exc_info=True)
  data = json.loads(encoded_message)
  message_type = data.get('type')
  if message_type == common.ObjectEventType.COMMAND_ATTEMPT_STATE_CHANGED:
    pubsub_topic = COMMAND_ATTEMPT_EVENT_PUBSUB_TOPIC
    logging.info('Notifying Attempt %s state changed to %s.',
                 data.get('attempt').get('attempt_id'), data.get('new_state'))
  elif message_type == common.ObjectEventType.REQUEST_STATE_CHANGED:
    pubsub_topic = REQUEST_EVENT_PUBSUB_TOPIC
    logging.info('Notifying Request %s state changed to %s.',
                 data.get('request_id'), data.get('new_state'))
  else:
    logging.warning('Unknown message type (%s), ignore.', message_type)
    return common.HTTP_OK
  _SendEventMessage(encoded_message, pubsub_topic)
  return common.HTTP_OK
