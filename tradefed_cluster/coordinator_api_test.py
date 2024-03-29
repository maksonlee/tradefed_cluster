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

"""Tests for coordinator_api module."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import unittest

import hamcrest
import mock
from six.moves import range


from tradefed_cluster import api_test
from tradefed_cluster import command_manager
from tradefed_cluster import command_monitor
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config  
from tradefed_cluster import request_manager
from tradefed_cluster import request_sync_monitor
from tradefed_cluster.util import ndb_shim as ndb


class CoordinatorApiTest(api_test.ApiTest):

  def setUp(self):
    super(CoordinatorApiTest, self).setUp()
    self.plugin_patcher = mock.patch(
        '__main__.env_config.CONFIG.plugin')
    self.plugin_patcher.start()

    self.request = request_manager.CreateRequest(
        request_id='1001',
        user='user1',
        command_infos=[
            datastore_entities.CommandInfo(
                command_line='command_line',
                cluster='cluster',
                run_target='run_target')
        ])

  def tearDown(self):
    self.plugin_patcher.stop()
    super(CoordinatorApiTest, self).tearDown()

  def _CreateAttempt(self, attempt_id, task_id, state):
    # Helper to create an attempt
    command = command_manager.CreateCommands(
        request_id=self.request.key.id(),
        command_infos=[
            datastore_entities.CommandInfo(
                command_line='long command line',
                run_target='foo',
                run_count=1,
                shard_count=1,
                cluster='foobar')
        ],
        shard_indexes=list(range(1)),
        request_plugin_data={
            'ants_invocation_id': 'i123',
            'ants_work_unit_id': 'w123'
        })[0]
    _, request_id, _, command_id = command.key.flat()
    attempt_key = ndb.Key(
        datastore_entities.Request, request_id,
        datastore_entities.Command, command_id,
        datastore_entities.CommandAttempt, attempt_id,
        namespace=common.NAMESPACE)
    attempt = datastore_entities.CommandAttempt(
        key=attempt_key,
        attempt_id=attempt_id,
        state=state,
        command_id=command_id,
        task_id=task_id)
    attempt.put()
    return attempt

  @mock.patch.object(command_monitor, 'AddToSyncQueue')
  def testBackfillCommands(self, mock_add):
    command_1, command_2, command_3 = command_manager.CreateCommands(
        request_id=self.request.key.id(),
        command_infos=[
            datastore_entities.CommandInfo(
                command_line='long command line',
                shard_count=3,
                run_target='foo',
                run_count=1,
                cluster='foobar'),
            datastore_entities.CommandInfo(
                command_line='longer_command_line',
                shard_count=3,
                run_target='foo',
                run_count=1,
                cluster='foobar'),
            datastore_entities.CommandInfo(
                command_line='short_cmd',
                shard_count=3,
                run_target='foo',
                run_count=1,
                cluster='foobar'),
        ],
        shard_indexes=list(range(3)),
        request_plugin_data={
            'ants_invocation_id': 'i123',
            'ants_work_unit_id': 'w123'
        })
    command_1.state = common.CommandState.QUEUED
    command_1.put()
    command_2.state = common.CommandState.QUEUED
    command_2.put()
    command_3.state = common.CommandState.RUNNING
    command_3.put()
    response = self.testapp.post_json(
        '/_ah/api/CoordinatorApi.BackfillCommands', {})
    self.assertEqual('200 OK', response.status)
    mock_add.assert_has_calls(
        [
            mock.call(
                hamcrest.match_equality(
                    hamcrest.has_property('key', command_1.key))),
            mock.call(
                hamcrest.match_equality(
                    hamcrest.has_property('key', command_2.key))),
        ], any_order=True)
    self.assertEqual(2, mock_add.call_count)

  @mock.patch.object(command_manager, 'AddToSyncCommandAttemptQueue')
  def testBackfillCommandAttempts(self, mock_add):
    attempt_0 = self._CreateAttempt(
        'attempt-0', 'task-0', common.CommandState.RUNNING)
    self._CreateAttempt('attempt-1', 'task-1', common.CommandState.COMPLETED)
    attempt_2 = self._CreateAttempt(
        'attempt-2', 'task-2', common.CommandState.RUNNING)

    response = self.testapp.post_json(
        '/_ah/api/CoordinatorApi.BackfillCommandAttempts', {})
    self.assertEqual('200 OK', response.status)

    mock_add.assert_has_calls(
        [
            mock.call(
                hamcrest.match_equality(
                    hamcrest.has_property('key', attempt_0.key))),
            mock.call(
                hamcrest.match_equality(
                    hamcrest.has_property('key', attempt_2.key))),
        ], any_order=True)
    self.assertEqual(2, mock_add.call_count)

  @mock.patch.object(command_manager, 'AddToSyncCommandAttemptQueue')
  def testBackfillCommandAttempts_notRunning(self, mock_add):
    self._CreateAttempt('attempt-1', 'task-1', common.CommandState.COMPLETED)
    response = self.testapp.post_json(
        '/_ah/api/CoordinatorApi.BackfillCommandAttempts', {})
    self.assertEqual('200 OK', response.status)

    mock_add.assert_not_called()

  @mock.patch.object(request_sync_monitor, 'Monitor')
  def testBackfillRequestSyncs(self, mock_monitor):
    queued_request = request_manager.CreateRequest(
        request_id='queued_id', user='user2', command_infos=[
            datastore_entities.CommandInfo(command_line='command_line2')
        ])
    queued_request.state = common.RequestState.QUEUED
    queued_request.put()

    response = self.testapp.post_json(
        '/_ah/api/CoordinatorApi.BackfillRequestSyncs', {})
    self.assertEqual('200 OK', response.status)
    mock_monitor.assert_has_calls(
        [mock.call(self.request.key.id()),
         mock.call(queued_request.key.id())])

  @mock.patch.object(request_sync_monitor, 'Monitor')
  def testBackfillRequestSyncs_onlyFinal(self, mock_monitor):
    self.request.state = common.RequestState.COMPLETED
    self.request.put()

    response = self.testapp.post_json(
        '/_ah/api/CoordinatorApi.BackfillRequestSyncs', {})
    self.assertEqual('200 OK', response.status)
    mock_monitor.assert_not_called()


if __name__ == '__main__':
  unittest.main()
