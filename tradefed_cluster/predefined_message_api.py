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

"""API module to serve cluster service calls."""

import datetime

import endpoints
from protorpc import messages
from protorpc import remote

from google.appengine.ext import ndb

from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_util


_PREDEFINED_MESSAGE_LIST_DEFAULT_LIMIT = 10


@api_common.tradefed_cluster_api.api_class(
    resource_name="predefined_messages", path="predefined_messages")
class PredefinedMessageApi(remote.Service):
  """A class for predefined messages API service."""

  PREDEFINED_MESSAGE_CREATE_RESOURCE = endpoints.ResourceContainer(
      type=messages.EnumField(
          api_messages.PredefinedMessageType, 1, required=True),
      lab_name=messages.StringField(2, required=True),
      content=messages.StringField(3, required=True))

  @endpoints.method(
      PREDEFINED_MESSAGE_CREATE_RESOURCE,
      api_messages.PredefinedMessage,
      path="/predefined_messages",
      http_method="POST",
      name="createPredefinedMessage")
  def CreatePredefinedMessage(self, request):
    exisiting_predefined_message_entities = (
        datastore_entities.PredefinedMessage.query()
        .filter(datastore_entities.PredefinedMessage.type == request.type)
        .filter(
            datastore_entities.PredefinedMessage.lab_name == request.lab_name)
        .filter(datastore_entities.PredefinedMessage.content
                == request.content)
        .fetch(1))
    if exisiting_predefined_message_entities:
      predefined_message_id = exisiting_predefined_message_entities[0].key.id()
      raise endpoints.ConflictException(
          ("Conflict: this PredefinedMessage<id:%s> already exist."
           % predefined_message_id))
    predefined_message = datastore_entities.PredefinedMessage(
        type=request.type,
        lab_name=request.lab_name,
        content=request.content,
        create_timestamp=datetime.datetime.utcnow())
    predefined_message.put()
    return datastore_entities.ToMessage(predefined_message)

  PREDEFINED_MESSAGE_UPDATE_RESOURCE = endpoints.ResourceContainer(
      id=messages.IntegerField(1, required=True),
      content=messages.StringField(2, required=True))

  @endpoints.method(
      PREDEFINED_MESSAGE_UPDATE_RESOURCE,
      api_messages.PredefinedMessage,
      path="/predefined_messages/{id}",
      http_method="PATCH",
      name="updatePredefinedMessage")
  def UpdatePredefinedMessage(self, request):
    predefined_message = ndb.Key(
        datastore_entities.PredefinedMessage,
        request.id).get()
    if not predefined_message:
      raise endpoints.NotFoundException(
          ("Not Found: PredefinedMessage<id:%s> is invalid."
           % request.id))
    exisiting_predefined_message_entities = (
        datastore_entities.PredefinedMessage.query()
        .filter(datastore_entities.PredefinedMessage.type
                == predefined_message.type)
        .filter(datastore_entities.PredefinedMessage.lab_name
                == predefined_message.lab_name)
        .filter(datastore_entities.PredefinedMessage.content
                == request.content)
        .fetch(1))
    if exisiting_predefined_message_entities:
      raise endpoints.ConflictException(
          "Conflict: a same predefine message<id:%s> already exist." %
          exisiting_predefined_message_entities[0].key.id())
    predefined_message.content = request.content
    predefined_message.put()
    return datastore_entities.ToMessage(predefined_message)

  PREDEFINED_MESSAGE_DELETE_RESOURCE = endpoints.ResourceContainer(
      id=messages.IntegerField(1, required=True))

  @endpoints.method(
      PREDEFINED_MESSAGE_DELETE_RESOURCE,
      api_messages.PredefinedMessage,
      path="/predefined_messages/{id}",
      http_method="DELETE",
      name="deletePredefinedMessage")
  def DeletePredefinedMessage(self, request):
    predefined_message_key = ndb.Key(
        datastore_entities.PredefinedMessage,
        request.id)
    predefined_message = predefined_message_key.get()
    if not predefined_message:
      raise endpoints.NotFoundException(
          ("Not Found: PredefinedMessage<id:%s> is invalid."
           % request.id))
    predefined_message_key.delete()
    return datastore_entities.ToMessage(predefined_message)

  PREDEFINED_MESSAGE_LIST_RESOURCE = endpoints.ResourceContainer(
      type=messages.EnumField(
          api_messages.PredefinedMessageType, 1, required=True),
      lab_name=messages.StringField(2, required=True),
      cursor=messages.StringField(3),
      count=messages.IntegerField(
          4, default=_PREDEFINED_MESSAGE_LIST_DEFAULT_LIMIT),
      backwards=messages.BooleanField(5, default=False))

  @endpoints.method(
      PREDEFINED_MESSAGE_LIST_RESOURCE,
      api_messages.PredefinedMessageCollection,
      path="/predefined_messages",
      http_method="GET",
      name="listPredefinedMessages")
  def ListPredefinedMessages(self, request):
    query = (
        datastore_entities.PredefinedMessage.query()
        .filter(datastore_entities.PredefinedMessage.type == request.type)
        .filter(
            datastore_entities.PredefinedMessage.lab_name == request.lab_name)
        .order(-datastore_entities.PredefinedMessage.used_count))
    predefined_message_entities, prev_cursor, next_cursor = (
        datastore_util.FetchPage(
            query,
            request.count,
            page_cursor=request.cursor,
            backwards=request.backwards))
    predefined_messages = [
        datastore_entities.ToMessage(pred_msg)
        for pred_msg in predefined_message_entities
    ]
    return api_messages.PredefinedMessageCollection(
        predefined_messages=predefined_messages,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor)
