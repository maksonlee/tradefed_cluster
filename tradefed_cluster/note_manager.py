# Copyright 2020 Google LLC
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

"""A module for note management."""
import datetime
import functools
import logging

from protorpc import protojson


from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config
from tradefed_cluster.util import ndb_shim as ndb
from tradefed_cluster.util import pubsub_client


DEVICE_NOTE_PUBSUB_TOPIC = "projects/%s/topics/%s" % (env_config.CONFIG.app_id,
                                                      "device_note")
HOST_NOTE_PUBSUB_TOPIC = "projects/%s/topics/%s" % (env_config.CONFIG.app_id,
                                                    "host_note")


class InvalidParameterError(ValueError):
  """The error of invalid function parameter."""


def GetPredefinedMessage(message_type, lab_name, content):
  """Get PredefinedMessage from datastore that matches the fields.

  Args:
    message_type: enum, common.PredefinedMessageType, type of PredefinedMessage.
    lab_name: str, the lab where the message is created.
    content: str, content of the message.

  Returns:
    A datastore_entities.PredefinedMessage, or None if not found.
  """
  predefined_message_entities = (
      datastore_entities.PredefinedMessage.query()
      .filter(datastore_entities.PredefinedMessage.type == message_type).filter(
          datastore_entities.PredefinedMessage.lab_name == lab_name).filter(
              datastore_entities.PredefinedMessage.content == content).fetch(1))
  if predefined_message_entities:
    return predefined_message_entities[0]
  else:
    return None


def GetOrCreatePredefinedMessage(message_type, lab_name, content):
  """Get PredefinedMessage datastore entity or create it if not existing.

  Args:
    message_type: enum, common.PredefinedMessageType, type of PredefinedMessage.
    lab_name: str, the lab where the message is created.
    content: str, content of the message.

  Returns:
    An instance of datastore_entities.PredefinedMessage.
  """
  exisiting_predefined_message_entity = GetPredefinedMessage(
      message_type=message_type, lab_name=lab_name, content=content)
  if exisiting_predefined_message_entity:
    return exisiting_predefined_message_entity
  else:
    return datastore_entities.PredefinedMessage(
        type=message_type,
        content=content,
        lab_name=lab_name,
        create_timestamp=datetime.datetime.utcnow())


def PreparePredefinedMessageForNote(
    message_type, message_id=None, lab_name=None, content=None, delta_count=1):
  """Prepare a PredefinedMessage to attach to a Note.

  This method prepares a PredefinedMessage in following ways:
   - if message_id is provided, find the message with id, or
   - if content is provide, get existing message matching the content, or create
     new message with the content
   - if neither is provided, return None

  Args:
    message_type: enum, common.PredefinedMessageType, type of PredefinedMessage.
    message_id: int, the ID of PredefinedMessage.
    lab_name: str, the lab where the message is created.
    content: str, content of the message.
    delta_count: the delta used_count to be added.

  Returns:
    An instance of datastore_entities.PredefinedMessage.

  Raises:
    InvalidParameterError: when the message_id is not valid or it leads to an
      wrong PredefineMessage type.
  """
  predefined_message_entity = None
  if message_id:
    predefined_message_entity = ndb.Key(
        datastore_entities.PredefinedMessage, message_id).get()
    if (not predefined_message_entity
        or predefined_message_entity.type != message_type):
      raise InvalidParameterError(
          "Invalid predefined_message_id: %s" % message_id)
  elif content:
    predefined_message_entity = GetOrCreatePredefinedMessage(
        message_type, lab_name, content)
  if predefined_message_entity:
    predefined_message_entity.used_count += delta_count
  return predefined_message_entity


def _Now():
  """Returns the current time in UTC. Added to allow mocking in our tests."""
  return datetime.datetime.utcnow()


@functools.lru_cache()
def _CreatePubsubClient():
  """Create a client for Google Cloud Pub/Sub."""
  client = pubsub_client.PubSubClient()
  client.CreateTopic(DEVICE_NOTE_PUBSUB_TOPIC)
  client.CreateTopic(HOST_NOTE_PUBSUB_TOPIC)
  return client


def PublishMessage(device_note_message, event_type):
  """Publish device note event message to pubsub."""
  if not env_config.CONFIG.use_google_api:
    logging.warning(
        "Unabled to send device note message to pubsub: use_google_api=False"
    )
    return
  device_note_message.publish_timestamp = _Now()
  encoded_message = protojson.encode_message(device_note_message)  # pytype: disable=module-attr
  data = common.UrlSafeB64Encode(encoded_message)
  if event_type == common.PublishEventType.DEVICE_NOTE_EVENT:
    data_type = "deviceNote"
    topic = DEVICE_NOTE_PUBSUB_TOPIC
  else:
    data_type = "hostNote"
    topic = HOST_NOTE_PUBSUB_TOPIC
  _CreatePubsubClient().PublishMessages(topic, [{
      "data": data,
      "attributes": {
          "type": data_type,
      }
  }])
