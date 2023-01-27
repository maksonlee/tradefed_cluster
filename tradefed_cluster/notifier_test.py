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

"""Unit tests for notifier."""

import datetime
import json
import unittest
import zlib

import mock
from protorpc import protojson
import six
import webtest

from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import notifier
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.services import task_scheduler

from google3.pyglib import stringutil


TIMESTAMP = datetime.datetime(2016, 12, 1, 0, 0, 0)
REQUEST_ID = '1234'
COMMAND_ID = '100'
ATTEMPT_ID = '1'


class NotifierTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super(NotifierTest, self).setUp()
    self.enter_context(mock.patch.object(common, 'Now', return_value=TIMESTAMP))
    self.mock_pubsub_client = self.enter_context(
        mock.patch.object(notifier, '_CreatePubsubClient'))()

    self._request_id = int(REQUEST_ID)
    self._command_id = int(COMMAND_ID)
    self._attempt_id = int(ATTEMPT_ID)
    self.result_link = ('http://sponge.corp.example.com/invocation?'
                        'tab=Test+Cases&show=FAILED&id=12345678-abcd')
    self.testapp = webtest.TestApp(notifier.APP)

  def testHandleObjectStateChangeEvent_requestEvent(self):
    request = self._CreateTestRequest(state=common.RequestState.COMPLETED)
    event_message = api_messages.RequestEventMessage(
        type=common.ObjectEventType.REQUEST_STATE_CHANGED,
        request_id=REQUEST_ID,
        new_state=common.RequestState.COMPLETED,
        request=datastore_entities.ToMessage(request),
        summary='summary',
        total_test_count=0,
        failed_test_count=0,
        passed_test_count=0,
        failed_test_run_count=0,
        result_links=[self.result_link],
        total_run_time_sec=3,
        event_time=TIMESTAMP)

    self.testapp.post(
        notifier.OBJECT_EVENT_QUEUE_HANDLER_PATH,
        protojson.encode_message(event_message))
    self._AssertMessagePublished(
        event_message, notifier.REQUEST_EVENT_PUBSUB_TOPIC)

  def testHandleObjectStateChangeEvent_compressed(self):
    request = self._CreateTestRequest(state=common.RequestState.COMPLETED)
    event_message = api_messages.RequestEventMessage(
        type=common.ObjectEventType.REQUEST_STATE_CHANGED,
        request_id=REQUEST_ID,
        new_state=common.RequestState.COMPLETED,
        request=datastore_entities.ToMessage(request),
        summary='summary',
        total_test_count=0,
        failed_test_count=0,
        passed_test_count=0,
        failed_test_run_count=0,
        result_links=[self.result_link],
        total_run_time_sec=3,
        event_time=TIMESTAMP)
    compressed_message = zlib.compress(six.ensure_binary(
        protojson.encode_message(event_message)))

    self.testapp.post(notifier.OBJECT_EVENT_QUEUE_HANDLER_PATH,
                      compressed_message)
    self._AssertMessagePublished(
        event_message, notifier.REQUEST_EVENT_PUBSUB_TOPIC)

  def testHandleObjectStateChangeEvent_throughNDBAndCompressed(self):
    request = self._CreateTestRequest(state=common.RequestState.COMPLETED)
    event_message = api_messages.RequestEventMessage(
        type=common.ObjectEventType.REQUEST_STATE_CHANGED,
        request_id=REQUEST_ID,
        new_state=common.RequestState.COMPLETED,
        request=datastore_entities.ToMessage(request),
        summary='summary',
        total_test_count=0,
        failed_test_count=0,
        passed_test_count=0,
        failed_test_run_count=0,
        result_links=[self.result_link],
        total_run_time_sec=3,
        event_time=TIMESTAMP)
    compressed_message = zlib.compress(six.ensure_binary(
        protojson.encode_message(event_message)))
    task_entity_key = task_scheduler._TaskEntity(data=compressed_message).put()
    task_queue_payload_dict = {
        task_scheduler.TASK_ENTITY_ID_KEY: task_entity_key.id(),
    }
    task_queue_payload_binary = stringutil.ensure_binary(
        json.dumps(task_queue_payload_dict))

    self.testapp.post(notifier.OBJECT_EVENT_QUEUE_HANDLER_PATH,
                      task_queue_payload_binary)
    self._AssertMessagePublished(
        event_message, notifier.REQUEST_EVENT_PUBSUB_TOPIC)

  def testHandleObjectStateChangeEvent_throughNDBAndNotCompressed(self):
    request = self._CreateTestRequest(state=common.RequestState.COMPLETED)
    event_message = api_messages.RequestEventMessage(
        type=common.ObjectEventType.REQUEST_STATE_CHANGED,
        request_id=REQUEST_ID,
        new_state=common.RequestState.COMPLETED,
        request=datastore_entities.ToMessage(request),
        summary='summary',
        total_test_count=0,
        failed_test_count=0,
        passed_test_count=0,
        failed_test_run_count=0,
        result_links=[self.result_link],
        total_run_time_sec=3,
        event_time=TIMESTAMP)
    event_message_binary = zlib.compress(six.ensure_binary(
        protojson.encode_message(event_message)))
    task_entity_key = task_scheduler._TaskEntity(
        data=event_message_binary).put()
    task_queue_payload_dict = {
        task_scheduler.TASK_ENTITY_ID_KEY: task_entity_key.id(),
    }
    task_queue_payload_binary = stringutil.ensure_binary(
        json.dumps(task_queue_payload_dict))

    self.testapp.post(notifier.OBJECT_EVENT_QUEUE_HANDLER_PATH,
                      task_queue_payload_binary)
    self._AssertMessagePublished(
        event_message, notifier.REQUEST_EVENT_PUBSUB_TOPIC)

  def testHandleObjectStateChangeEvent_attemptEvent(self):
    request = self._CreateTestRequest(state=common.RequestState.COMPLETED)
    command = self._CreateTestCommand(request,
                                      state=common.CommandState.COMPLETED)
    attempt = self._CreateTestCommandAttempt(
        command,
        state=common.CommandState.COMPLETED,
        total_test_count=5,
        failed_test_count=1,
        failed_test_run_count=1,
        start_time=datetime.datetime(2016, 12, 1, 0, 0, 0),
        end_time=datetime.datetime(2016, 12, 1, 0, 0, 1))

    event_message = api_messages.CommandAttemptEventMessage(
        type=common.ObjectEventType.COMMAND_ATTEMPT_STATE_CHANGED,
        attempt=datastore_entities.CommandAttemptToMessage(attempt),
        old_state=common.CommandState.RUNNING,
        new_state=common.CommandState.COMPLETED,
        event_time=TIMESTAMP)

    self.testapp.post(
        notifier.OBJECT_EVENT_QUEUE_HANDLER_PATH,
        protojson.encode_message(event_message))
    self._AssertMessagePublished(
        event_message, notifier.COMMAND_ATTEMPT_EVENT_PUBSUB_TOPIC)

  def _CreateTestRequest(self, state=common.RequestState.UNKNOWN):
    """Creates a Request for testing purposes."""
    request = datastore_test_util.CreateRequest(
        user='user',
        command_infos=[
            datastore_entities.CommandInfo(
                command_line='command_line --request-id %d' % self._request_id,
                cluster='cluster',
                run_target='run_target')
        ],
        request_id=str(self._request_id))
    request.state = state
    request.put()
    self._request_id += 1
    return request

  def _CreateTestCommand(self, request, state, run_count=1):
    """Creates a Command associated with a REQUEST."""
    command = datastore_entities.Command(
        parent=request.key,
        id=str(self._command_id),
        command_line='%s --command-id %d' % (
            request.command_infos[0].command_line, self._command_id),
        cluster='cluster',
        run_target='run_target',
        run_count=run_count,
        state=state)
    command.put()
    self._command_id += 1
    return command

  def _CreateTestCommandAttempt(self, command, state, total_test_count=1,
                                failed_test_count=1, failed_test_run_count=1,
                                start_time=None, end_time=None):
    """Creates a CommandAttempt associated with a Command."""
    command_attempt = datastore_entities.CommandAttempt(
        parent=command.key,
        id=str(self._attempt_id),
        command_id=command.key.id(),
        task_id='task_id',
        attempt_id='attempt_id',
        state=state,
        summary='summary: %s\n' % self.result_link,
        error='error' if state == common.CommandState.ERROR else None,
        total_test_count=total_test_count,
        failed_test_count=failed_test_count,
        failed_test_run_count=failed_test_run_count,
        start_time=start_time,
        end_time=end_time)
    command_attempt.put()
    self._attempt_id += 1
    return command_attempt

  def _AssertMessagePublished(self, message, pubsub_topic):
    data = common.UrlSafeB64Encode(protojson.encode_message(message))
    messages = [{'data': data}]
    self.mock_pubsub_client.PublishMessages.assert_called_once_with(
        pubsub_topic, messages)

if __name__ == '__main__':
  unittest.main()
