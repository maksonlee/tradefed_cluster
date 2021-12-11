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


TIMESTAMP = datetime.datetime(2016, 12, 1, 0, 0, 0)
REQUEST_ID = '1234'


class NotifierTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super(NotifierTest, self).setUp()
    self.patcher = mock.patch('__main__.notifier._PubsubClient')
    self.now_patch = mock.patch.object(common, 'Now', return_value=TIMESTAMP)
    self.now_patch.start()
    self.mock_pubsub_client = self.patcher.start()

    self._request_id = int(REQUEST_ID)
    self.result_link = ('http://sponge.corp.example.com/invocation?'
                        'tab=Test+Cases&show=FAILED&id=12345678-abcd')
    self.testapp = webtest.TestApp(notifier.APP)

  def tearDown(self):
    self.patcher.stop()
    self.now_patch.stop()
    super(NotifierTest, self).tearDown()

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

  def _AssertMessagePublished(self, message, pubsub_topic):
    data = common.UrlSafeB64Encode(protojson.encode_message(message))
    messages = [{'data': data}]
    self.mock_pubsub_client.PublishMessages.assert_called_once_with(
        pubsub_topic, messages)

if __name__ == '__main__':
  unittest.main()
