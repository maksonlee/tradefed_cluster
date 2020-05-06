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

import unittest

from google.appengine.ext import ndb

from tradefed_cluster import api_messages
from tradefed_cluster import datastore_entities
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
        api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
        lab_name,
        "offline_reason1")
    self.assertEqual("offline_reason1", message_1.content)
    self.assertEqual(api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
                     message_1.type)

    message_2 = note_manager.GetPredefinedMessage(
        api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
        lab_name,
        "recovery_action1")
    self.assertEqual("recovery_action1", message_2.content)
    self.assertEqual(api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
                     message_2.type)

  def testGetPredefinedMessage_None(self):
    nonexistent_message = note_manager.GetPredefinedMessage(
        api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
        "alab",
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
        api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
        lab_name,
        content)
    self.assertEqual(message_id, message.key.id())

  def testGetOrCreatePredefinedMessage_NewMessage(self):
    lab_name = "alab"
    content = "content1"

    message = note_manager.GetOrCreatePredefinedMessage(
        api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
        lab_name,
        content)
    self.assertEqual(api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
                     message.type)
    self.assertEqual(lab_name, message.lab_name)
    self.assertEqual(content, message.content)

if __name__ == "__main__":
  unittest.main()
