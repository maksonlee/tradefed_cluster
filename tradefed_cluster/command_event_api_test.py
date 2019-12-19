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

"""Tests for command_event_api module."""

import unittest

import mock

from tradefed_cluster import api_test
from tradefed_cluster import command_event_handler


class CommandEventApiTest(api_test.ApiTest):

  @mock.patch.object(command_event_handler, 'EnqueueCommandEvents')
  def testSubmitCommandEvents(self, mock_enqueue):
    test_ended_event = {
        'hostname': 'example0.mtv.corp.example.com',
        'device_serial': '07a1a240',
        'data': {'total_test_count': 1, 'exec_test_count': 1},
        'attempt_id': 'c8d57bb8-a704-4ae1-9069-22b133370475',
        'task_id': '85157-0',
        'time': 1234567890,
        'type': 'InvocationCompleted'
    }
    api_request = {'command_events': [test_ended_event]}
    self.testapp.post_json('/_ah/api/CommandEventApi.SubmitCommandEvents',
                           api_request)
    mock_enqueue.assert_called_with([test_ended_event])

  @mock.patch.object(command_event_handler, 'EnqueueCommandEvents')
  def testSubmitCommandEvents_multiDevice(self, mock_enqueue):
    test_ended_event = {
        'hostname': 'example0.mtv.corp.example.com',
        'data': {'total_test_count': 1, 'exec_test_count': 1},
        'attempt_id': 'c8d57bb8-a704-4ae1-9069-22b133370475',
        'task_id': '85157-0',
        'time': 1234567890,
        'type': 'InvocationCompleted',
        'device_serials': ['d1', 'd2'],
    }
    api_request = {'command_events': [test_ended_event]}
    self.testapp.post_json('/_ah/api/CommandEventApi.SubmitCommandEvents',
                           api_request)
    mock_enqueue.assert_called_with([test_ended_event])


if __name__ == '__main__':
  unittest.main()
