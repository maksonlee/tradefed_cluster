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

"""Tests for command attempt API."""

import datetime
import unittest

from protorpc import protojson

from tradefed_cluster.util import ndb_shim as ndb

from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util

TIME = datetime.datetime(2018, 8, 20, 0, 0, 0)
TIME_DELTA = datetime.timedelta(minutes=1)


class CommandAttemptApiTest(api_test.ApiTest):

  def setUp(self):
    api_test.ApiTest.setUp(self)
    request_key = ndb.Key(
        datastore_entities.Request, '1001',
        namespace=common.NAMESPACE)
    request = datastore_test_util.CreateRequest(
        request_id=request_key.id(),
        user='user1',
        command_line='command_line')
    request.put()

    command = datastore_entities.Command(
        parent=request_key,
        id='1',
        command_line='command_line',
        cluster='cluster',
        run_target='run_target',
        state=common.CommandState.RUNNING
    )
    command.put()

    command_attempt_0 = datastore_entities.CommandAttempt(
        parent=command.key,
        id='attempt_id-0',
        task_id='task-id-0',
        attempt_id='attempt_id-0',
        hostname='hostname_0',
        device_serial='device_serial_0',
        create_time=TIME,
        state=common.CommandState.COMPLETED
    )
    command_attempt_0.put()

    command_attempt_1 = datastore_entities.CommandAttempt(
        parent=command.key,
        id='attempt_id-1',
        task_id='task-id-1',
        attempt_id='attempt_id-1',
        hostname='hostname_0',
        device_serial='device_serial_1',
        create_time=TIME + TIME_DELTA,
        state=common.CommandState.RUNNING
    )
    command_attempt_1.put()

    command_attempt_2 = datastore_entities.CommandAttempt(
        parent=command.key,
        id='attempt_id-2',
        task_id='task-id-2',
        attempt_id='attempt_id-2',
        hostname='hostname_1',
        device_serial='device_serial_2',
        create_time=TIME + TIME_DELTA * 2,
        state=common.CommandState.RUNNING
    )
    command_attempt_2.put()

    command_attempt_3 = datastore_entities.CommandAttempt(
        parent=command.key,
        id='attempt_id-3',
        task_id='task-id-3',
        attempt_id='attempt_id-3',
        hostname='hostname_1',
        device_serial='device_serial_2',
        create_time=TIME + TIME_DELTA * 3,
        device_serials=['d2', 'd3'],
        state=common.CommandState.RUNNING
    )
    command_attempt_3.put()

  def _CallListCommandAttempts(self, api_request):
    """Helper to call ListCommandAttempt API."""
    api_response = self.testapp.post_json(
        '/_ah/api/CommandAttemptApi.ListCommandAttempts', api_request)
    return protojson.decode_message(
        api_messages.CommandAttemptMessageCollection,
        api_response.body)

  def testListCommandAttempt(self):
    """Test listing all command attempts. Results should be sorted."""
    api_request = {}
    attempt_collection = self._CallListCommandAttempts(api_request)
    self.assertEqual(4, len(attempt_collection.command_attempts))
    self.assertEqual('task-id-0',
                     attempt_collection.command_attempts[3].task_id)
    self.assertEqual('task-id-1',
                     attempt_collection.command_attempts[2].task_id)
    self.assertEqual('task-id-2',
                     attempt_collection.command_attempts[1].task_id)
    self.assertEqual('task-id-3',
                     attempt_collection.command_attempts[0].task_id)
    self.assertEqual(['d2', 'd3'],
                     attempt_collection.command_attempts[0].device_serials)

  def testListCommandAttempt_byHostname(self):
    """Test listing command attempts for given hostname."""
    api_request = {'hostname': 'hostname_0'}
    attempt_collection = self._CallListCommandAttempts(api_request)
    self.assertEqual(2, len(attempt_collection.command_attempts))
    self.assertEqual('task-id-0',
                     attempt_collection.command_attempts[1].task_id)
    self.assertEqual('task-id-1',
                     attempt_collection.command_attempts[0].task_id)

  def testListCommandAttempt_byHostname_noCommandAttempts(self):
    """Test listing command attempts for given hostname with no attempts."""
    api_request = {'hostname': 'fake_hostname'}
    attempt_collection = self._CallListCommandAttempts(api_request)
    self.assertEqual(0, len(attempt_collection.command_attempts))

  def testListCommandAttempt_byDevice(self):
    """Test listing command attempts for given device."""
    api_request = {'device_serial': 'device_serial_2'}
    attempt_collection = self._CallListCommandAttempts(api_request)
    self.assertEqual(2, len(attempt_collection.command_attempts))
    self.assertEqual('task-id-2',
                     attempt_collection.command_attempts[1].task_id)
    self.assertEqual('task-id-3',
                     attempt_collection.command_attempts[0].task_id)

  def testListCommandAttempt_byDevice_noCommandAttempts(self):
    """Test listing command attempts for given device with no attempts."""
    api_request = {'device_serial': 'fake_serial_2'}
    attempt_collection = self._CallListCommandAttempts(api_request)
    self.assertEqual(0, len(attempt_collection.command_attempts))

  def testListCommandAttempt_byHostnameAndDevice(self):
    """Test listing command attempts for given hostname and device."""
    api_request = {'hostname': 'hostname_1', 'device_serial': 'device_serial_2'}
    attempt_collection = self._CallListCommandAttempts(api_request)
    self.assertEqual(2, len(attempt_collection.command_attempts))

  def testListCommandAttempt_byHostnameAndDevice_noCommandAttempts(self):
    """Test listing attempts for given hostname and device w/o matches."""
    api_request = {'hostname': 'hostname_0', 'device_serial': 'device_serial_2'}
    attempt_collection = self._CallListCommandAttempts(api_request)
    self.assertEqual(0, len(attempt_collection.command_attempts))

if __name__ == '__main__':
  unittest.main()
