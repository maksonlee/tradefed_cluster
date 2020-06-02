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
"""Unit tests for note manager module."""

import base64
import datetime
import json
import unittest

import mock

from google.appengine.ext import ndb

from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import note_manager
from tradefed_cluster import testbed_dependent_test


class NoteManagerTest(testbed_dependent_test.TestbedDependentTest):

  def testGetPredefinedMessage_OK(self):
    lab_name = "alab"
    predefined_message_entities = [
        datastore_entities.PredefinedMessage(
            lab_name=lab_name,
            type=api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
            content="offline_reason1",
            used_count=2),
        datastore_entities.PredefinedMessage(
            lab_name=lab_name,
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content="recovery_action1",
            used_count=5),
    ]
    ndb.put_multi(predefined_message_entities)

    message_1 = note_manager.GetPredefinedMessage(
        api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON, lab_name,
        "offline_reason1")
    self.assertEqual("offline_reason1", message_1.content)
    self.assertEqual(api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
                     message_1.type)

    message_2 = note_manager.GetPredefinedMessage(
        api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION, lab_name,
        "recovery_action1")
    self.assertEqual("recovery_action1", message_2.content)
    self.assertEqual(api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
                     message_2.type)

  def testGetPredefinedMessage_None(self):
    nonexistent_message = note_manager.GetPredefinedMessage(
        api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION, "alab",
        "non-existent content")
    self.assertIsNone(nonexistent_message)

  def testGetOrCreatePredefinedMessage_ExistingMessage(self):
    lab_name = "alab"
    content = "content1"
    message_id = 111
    datastore_entities.PredefinedMessage(
        key=ndb.Key(datastore_entities.PredefinedMessage, message_id),
        lab_name=lab_name,
        type=api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
        content=content,
        used_count=2).put()

    message = note_manager.GetOrCreatePredefinedMessage(
        api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON, lab_name,
        content)
    self.assertEqual(message_id, message.key.id())

  def testGetOrCreatePredefinedMessage_NewMessage(self):
    lab_name = "alab"
    content = "content1"

    message = note_manager.GetOrCreatePredefinedMessage(
        api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON, lab_name,
        content)
    self.assertEqual(api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
                     message.type)
    self.assertEqual(lab_name, message.lab_name)
    self.assertEqual(content, message.content)

  def testPreparePredefinedMessageForNote_withValidId(self):
    message_id = 111
    lab_name = "alab"
    content = "content1"
    datastore_entities.PredefinedMessage(
        key=ndb.Key(datastore_entities.PredefinedMessage, message_id),
        lab_name=lab_name,
        type=api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
        content=content,
        used_count=2).put()

    message = note_manager.PreparePredefinedMessageForNote(
        api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
        message_id=message_id)

    self.assertEqual(message_id, message.key.id())
    self.assertEqual(lab_name, message.lab_name)
    self.assertEqual(content, message.content)
    self.assertEqual(3, message.used_count)  # the used_count increases

  def testPreparePredefinedMessageForNote_withInvalidId(self):
    invalid_message_id = 111
    with self.assertRaises(note_manager.InvalidParameterError):
      note_manager.PreparePredefinedMessageForNote(
          api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
          message_id=invalid_message_id)

  def testPreparePredefinedMessageForNote_withExistingContent(self):
    message_id = 111
    lab_name = "alab"
    content = "content1"
    datastore_entities.PredefinedMessage(
        key=ndb.Key(datastore_entities.PredefinedMessage, message_id),
        lab_name=lab_name,
        type=api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
        content=content,
        used_count=2).put()

    message = note_manager.PreparePredefinedMessageForNote(
        api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
        lab_name=lab_name,
        content=content)

    self.assertEqual(message_id, message.key.id())
    self.assertEqual(lab_name, message.lab_name)
    self.assertEqual(content, message.content)
    self.assertEqual(3, message.used_count)  # the used_count increases

  def testPreparePredefinedMessageForNote_withNewContent(self):
    lab_name = "alab"
    content = "content1"

    message = note_manager.PreparePredefinedMessageForNote(
        api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
        lab_name=lab_name,
        content=content)

    self.assertIsNone(message.key)  # new entity without a key yet
    self.assertEqual(lab_name, message.lab_name)
    self.assertEqual(content, message.content)
    self.assertEqual(1, message.used_count)

  @mock.patch.object(note_manager, "_Now")
  @mock.patch.object(note_manager, "_PubsubClient")
  def testPublishMessage(self, mock_pubsub_client, mock_now):
    now = datetime.datetime(2020, 4, 14, 10, 10)
    mock_now.return_value = now
    device_note = datastore_test_util.CreateNote(
        device_serial="serial_1", timestamp=now)
    device_note_msg = api_messages.Note(
        id=str(device_note.key.id()),
        device_serial=device_note.device_serial,
        timestamp=device_note.timestamp,
        user=device_note.user,
        offline_reason=device_note.offline_reason,
        recovery_action=device_note.recovery_action,
        message=device_note.message)
    device_note_event_msg = api_messages.NoteEvent(
        note=device_note_msg,
        hostname="host1",
        lab_name="lab1",
        run_target="run_target1")
    note_manager.PublishMessage(device_note_event_msg,
                                common.PublishEventType.DEVICE_NOTE_EVENT)

    topic, messages = mock_pubsub_client.PublishMessages.call_args[0]
    self.assertEqual(note_manager.DEVICE_NOTE_PUBSUB_TOPIC, topic)
    message = messages[0]
    self.assertEqual("deviceNote", message["attributes"]["type"])
    data = message["data"]
    data = base64.urlsafe_b64decode(data)
    msg_dict = json.loads(data)
    self.assertEqual("2020-04-14T10:10:00", msg_dict["publish_timestamp"])


if __name__ == "__main__":
  unittest.main()
