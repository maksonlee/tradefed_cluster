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
import functools
import json
import logging
import zlib

import flask

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


@functools.lru_cache()
def _CreatePubsubClient():
  """Create a client for Google Cloud Pub/Sub."""
  client = pubsub_client.PubSubClient()
  client.CreateTopic(REQUEST_EVENT_PUBSUB_TOPIC)
  client.CreateTopic(COMMAND_ATTEMPT_EVENT_PUBSUB_TOPIC)
  return client


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
    _CreatePubsubClient().PublishMessages(pubsub_topic, [{'data': data}])
  elif queue:
    task_scheduler.AddTask(
        queue_name=queue,
        payload=zlib.compress(encoded_message))
  else:
    logging.warning(
        'Unabled to notify events: use_google_api=False and queue is null')


def _TryDecompressMessage(message):
  """Try use zlib to decompress bytes message.

  Args:
    message: bytes, the encoded message payload.

  Returns:
    bytes, the decompressed message; or the original encoded message itself if
      it cannot be decompressed (because it is not a compressed message).
  """
  try:
    return zlib.decompress(message)
  except zlib.error:
    logging.warning(
        'Cannot decompress and returning original message, '
        'because payload may not be compressed: %s', message, exc_info=True)
  return message


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

  # _TryDecompressMessage is for dealing with compressed data.
  # Check TASK_ENTITY_ID_KEY is for dealing with data payload delivered in ndb.
  # Without decompressing, it cannot read the key inside the initial message,
  # so we end up _TryDecompressMessage twice.
  encoded_message = _TryDecompressMessage(encoded_message)
  data = json.loads(encoded_message)

  # The ID is only set when reading task payloads from NDB.
  task_entity_id = None
  if task_scheduler.TASK_ENTITY_ID_KEY in data:
    task_entity_id = data[task_scheduler.TASK_ENTITY_ID_KEY]
    encoded_message = task_scheduler.FetchPayloadFromTaskEntity(
        task_entity_id)
    encoded_message = _TryDecompressMessage(encoded_message)
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
    task_scheduler.DeleteTaskEntity(task_entity_id)
    return common.HTTP_OK
  _SendEventMessage(encoded_message, pubsub_topic)
  task_scheduler.DeleteTaskEntity(task_entity_id)
  return common.HTTP_OK
