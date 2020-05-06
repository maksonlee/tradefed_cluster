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

"""Tests predefined_message_api module."""

import unittest

from protorpc import protojson

from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import datastore_entities
from google.appengine.ext import ndb


class PredefinedMessageApiTest(api_test.ApiTest):

  def testCreatePredefinedMessage_succeed(self):
    lab_name = 'lab_1'
    content = 'device went down'
    api_request = {
        'type': 'DEVICE_OFFLINE_REASON',
        'lab_name': lab_name,
        'content': content,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/PredefinedMessageApi.CreatePredefinedMessage', api_request)
    self.assertEqual('200 OK', api_response.status)
    created_predefined_message = protojson.decode_message(
        api_messages.PredefinedMessage, api_response.body)
    self.assertEqual(api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
                     created_predefined_message.type)
    self.assertEqual(lab_name, created_predefined_message.lab_name)
    self.assertEqual(content, created_predefined_message.content)
    self.assertIsNotNone(created_predefined_message.id)
    self.assertEqual(0, created_predefined_message.used_count)

  def testCreatePredefinedMessage_failConflict(self):
    lab_name = 'lab_1'
    content = 'device went down'
    datastore_entities.PredefinedMessage(
        lab_name=lab_name,
        type=api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
        content=content).put()
    api_request = {
        'type': 'DEVICE_OFFLINE_REASON',
        'lab_name': lab_name,
        'content': content,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/PredefinedMessageApi.CreatePredefinedMessage', api_request,
        expect_errors=True)
    self.assertEqual('409 Conflict', api_response.status)

  def testUpdatePredefinedMessage_succeed(self):
    old_content = 'old content'
    new_content = 'new content'
    lab_name = 'lab_1'
    entity = datastore_entities.PredefinedMessage(
        lab_name=lab_name,
        type=api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
        content=old_content)
    key = entity.put()
    api_request = {
        'id': key.id(),
        'content': new_content,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/PredefinedMessageApi.UpdatePredefinedMessage', api_request)
    self.assertEqual('200 OK', api_response.status)
    created_predefined_message = protojson.decode_message(
        api_messages.PredefinedMessage, api_response.body)
    self.assertEqual(api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
                     created_predefined_message.type)
    self.assertEqual(lab_name, created_predefined_message.lab_name)
    self.assertEqual(new_content, created_predefined_message.content)

  def testUpdatePredefinedMessage_failNotFound(self):
    api_request = {
        'id': 123,  # a non-existent id
        'content': 'some content',
    }
    api_response = self.testapp.post_json(
        '/_ah/api/PredefinedMessageApi.UpdatePredefinedMessage', api_request,
        expect_errors=True)
    self.assertEqual('404 Not Found', api_response.status)

  def testUpdatePredefinedMessage_failAlreadyExist(self):
    predefined_messages = [
        datastore_entities.PredefinedMessage(
            lab_name='lab1',
            type=api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
            content='content-1'),
        datastore_entities.PredefinedMessage(
            lab_name='lab1',
            type=api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
            content='content-2'),
    ]
    keys = ndb.put_multi(predefined_messages)
    api_request = {
        'id': keys[0].id(),  # the id of the 1st message
        'content': 'content-2',  # the content of the 2nd message
    }
    api_response = self.testapp.post_json(
        '/_ah/api/PredefinedMessageApi.UpdatePredefinedMessage', api_request,
        expect_errors=True)
    self.assertEqual('409 Conflict', api_response.status)

  def testDeletePredefinedMessage_succeed(self):
    content = 'some content'
    lab_name = 'lab_1'
    entity = datastore_entities.PredefinedMessage(
        lab_name=lab_name,
        type=api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
        content=content)
    key = entity.put()
    api_request = {
        'id': key.id(),
    }
    api_response = self.testapp.post_json(
        '/_ah/api/PredefinedMessageApi.DeletePredefinedMessage', api_request)
    self.assertEqual('200 OK', api_response.status)
    created_predefined_message = protojson.decode_message(
        api_messages.PredefinedMessage, api_response.body)
    self.assertEqual(api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
                     created_predefined_message.type)
    self.assertEqual(lab_name, created_predefined_message.lab_name)
    self.assertEqual(content, created_predefined_message.content)

  def testDeletePredefinedMessage_failNotFound(self):
    api_request = {
        'id': 123,  # a non-existent id
    }
    api_response = self.testapp.post_json(
        '/_ah/api/PredefinedMessageApi.DeletePredefinedMessage', api_request,
        expect_errors=True)
    self.assertEqual('404 Not Found', api_response.status)

  def testListPredefinedMessages_filtersAndOrdering(self):
    """Test list PredefinedMessages."""
    pred_msg_entities = [
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-1',
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content='content-1',
            used_count=2),
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-2',
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content='content-2',
            used_count=1),
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-2',
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content='content-3',
            used_count=3),
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-4',
            type=api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
            content='content-4',
            used_count=3),
    ]
    ndb.put_multi(pred_msg_entities)
    api_request = {'type': 'DEVICE_RECOVERY_ACTION',
                   'lab_name': 'lab-name-2'}
    api_response = self.testapp.post_json(
        '/_ah/api/PredefinedMessageApi.ListPredefinedMessages', api_request)
    pred_msgs = protojson.decode_message(
        api_messages.PredefinedMessageCollection,
        api_response.body).predefined_messages
    # The results are filtered by type and lab name.
    self.assertEqual(2, len(pred_msgs))
    # The results are sorted by count in descending order.
    self.assertEqual(pred_msg_entities[1].lab_name, pred_msgs[1].lab_name)
    self.assertEqual(pred_msg_entities[1].content, pred_msgs[1].content)
    self.assertEqual(pred_msg_entities[1].type, pred_msgs[1].type)
    self.assertEqual(pred_msg_entities[1].used_count, pred_msgs[1].used_count)
    self.assertEqual(pred_msg_entities[2].lab_name, pred_msgs[0].lab_name)
    self.assertEqual(pred_msg_entities[2].content, pred_msgs[0].content)
    self.assertEqual(pred_msg_entities[2].type, pred_msgs[0].type)
    self.assertEqual(pred_msg_entities[2].used_count, pred_msgs[0].used_count)

  def testListPredefinedMessages_countAndCursor(self):
    """Test list PredefinedMessages."""
    pred_msg_entities = [
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-2',
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content='content-1',
            used_count=4),
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-2',
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content='content-2',
            used_count=3),
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-2',
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content='content-3',
            used_count=2),
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-2',
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content='content-4',
            used_count=1),
    ]
    ndb.put_multi(pred_msg_entities)
    # look up the first page
    api_request = {
        'type': 'DEVICE_RECOVERY_ACTION',
        'lab_name': 'lab-name-2',
        'count': 2,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/PredefinedMessageApi.ListPredefinedMessages', api_request)
    pred_msg_collection = protojson.decode_message(
        api_messages.PredefinedMessageCollection,
        api_response.body)
    pred_msgs = pred_msg_collection.predefined_messages
    self.assertEqual(2, len(pred_msgs))
    self.assertEqual(pred_msg_entities[0].content, pred_msgs[0].content)
    self.assertEqual(pred_msg_entities[1].content, pred_msgs[1].content)
    # look up the second page with next_cursor
    api_request = {
        'type': 'DEVICE_RECOVERY_ACTION',
        'lab_name': 'lab-name-2',
        'count': 2,
        'cursor': pred_msg_collection.next_cursor,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/PredefinedMessageApi.ListPredefinedMessages', api_request)
    pred_msg_collection = protojson.decode_message(
        api_messages.PredefinedMessageCollection,
        api_response.body)
    pred_msgs = pred_msg_collection.predefined_messages
    self.assertEqual(2, len(pred_msgs))
    self.assertEqual(pred_msg_entities[2].content, pred_msgs[0].content)
    self.assertEqual(pred_msg_entities[3].content, pred_msgs[1].content)
    # look up the first page again with prev_cursor of the second page
    api_request = {
        'type': 'DEVICE_RECOVERY_ACTION',
        'lab_name': 'lab-name-2',
        'count': 2,
        'cursor': pred_msg_collection.prev_cursor,
        'backwards': True,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/PredefinedMessageApi.ListPredefinedMessages', api_request)
    pred_msg_collection = protojson.decode_message(
        api_messages.PredefinedMessageCollection,
        api_response.body)
    pred_msgs = pred_msg_collection.predefined_messages
    self.assertEqual(2, len(pred_msgs))
    self.assertEqual(pred_msg_entities[0].content, pred_msgs[0].content)
    self.assertEqual(pred_msg_entities[1].content, pred_msgs[1].content)


if __name__ == '__main__':
  unittest.main()
