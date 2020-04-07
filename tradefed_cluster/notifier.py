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

import base64
import json
import logging
import zlib

import lazy_object_proxy
from protorpc import protojson
import webapp2

from google.appengine.api import taskqueue

from tradefed_cluster import common
from tradefed_cluster import env_config
from tradefed_cluster import request_manager
from tradefed_cluster.util import pubsub_client


PUBSUB_API_SCOPES = ['https://www.googleapis.com/auth/pubsub']
PUBSUB_API_NAME = 'pubsub'
PUBSUB_API_VERSION = 'v1beta2'

OBJECT_EVENT_PUBSUB_TOPIC = 'projects/%s/topics/%s' % (
    env_config.CONFIG.app_id, 'request_event')
OBJECT_EVENT_QUEUE_HANDLER_PATH = (
    '/_ah/queue/%s' % common.OBJECT_EVENT_QUEUE)


def _CreatePubsubClient():
  """Create a client for Google Cloud Pub/Sub."""
  client = pubsub_client.PubSubClient()
  client.CreateTopic(OBJECT_EVENT_PUBSUB_TOPIC)
  return client

_PubsubClient = lazy_object_proxy.Proxy(_CreatePubsubClient)  

def _SendEventMessage(encoded_message):
  """Sends a message to the event queue notifying a state change event.

  Args:
    encoded_message: proto-json encoded request or attempt state change message
  Returns:
    True is the message was sent successfully, False otherwise
  """
  queue = env_config.CONFIG.event_queue_name
  if env_config.CONFIG.use_google_api:
    data = base64.urlsafe_b64encode(encoded_message)
    _PubsubClient.PublishMessages(OBJECT_EVENT_PUBSUB_TOPIC, [{'data': data}])
  elif queue:
    taskqueue.add(queue_name=queue, payload=encoded_message)
  else:
    logging.warn(
        'Unabled to notify events: use_google_api=False and queue is null')


class ObjectStateChangeEventHandler(webapp2.RequestHandler):
  """A web request handler to handle state change event messages."""

  def post(self):
    """Process a state change event message.

    This method takes protojson-encoded request or attempt state change event
    messages and passes them on to the event queue configured in env_config.

    Prior to cl/220835423, this queue only received data with an 'id' field and
    retrieved the request info later.
    """
    encoded_message = self.request.body
    try:
      encoded_message = zlib.decompress(encoded_message)
    except zlib.error:
      logging.warn(
          'payload may not be compressed: %s', encoded_message, exc_info=True)

    data = json.loads(encoded_message)

    # TODO: Remove legacy id later.
    legacy_id = data.get('id')
    message_type = data.get('type')
    if message_type == common.ObjectEventType.COMMAND_ATTEMPT_STATE_CHANGED:
      typed_id = 'Attempt %s' % data.get('attempt').get('attempt_id')
    elif message_type == common.ObjectEventType.REQUEST_STATE_CHANGED:
      typed_id = 'Request %s' % data.get('request_id')
    elif legacy_id:
      request = request_manager.GetRequest(legacy_id)
      message = request_manager.CreateRequestEventMessage(request)
      encoded_message = protojson.encode_message(message)
      typed_id = 'Request %s' % legacy_id
    else:
      typed_id = 'Unknown message type (%s)' % message_type
    logging.info('Notifying %s state changed to %s', typed_id,
                 data.get('new_state'))

    _SendEventMessage(encoded_message)


APP = webapp2.WSGIApplication([
    # The below handler is served in frontend module.
    (OBJECT_EVENT_QUEUE_HANDLER_PATH,
     ObjectStateChangeEventHandler)
])
