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

from tradefed_cluster import datastore_entities


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
      .filter(datastore_entities.PredefinedMessage.type == message_type)
      .filter(datastore_entities.PredefinedMessage.lab_name == lab_name)
      .filter(datastore_entities.PredefinedMessage.content == content)
      .fetch(1))
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
