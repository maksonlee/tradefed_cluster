# Lint as: python2, python3
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

"""Tests for command_attempt_monitor."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import datetime
import json
import unittest

import hamcrest
import mock
from six.moves import range
import webtest

from tradefed_cluster import command_attempt_monitor
from tradefed_cluster import command_event_test_util
from tradefed_cluster import command_manager
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import env_config  from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.util import ndb_shim as ndb


class CommandAttemptMonitorTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super(CommandAttemptMonitorTest, self).setUp()
    self.testapp = webtest.TestApp(command_attempt_monitor.APP)
    self.plugin_patcher = mock.patch(
        '__main__.env_config.CONFIG.plugin')
    self.plugin_patcher.start()

    self.request = datastore_test_util.CreateRequest(
        request_id='1001',
        user='user1',
        command_line='command_line',
        cluster='cluster',
        run_target='run_target')
    self.command = command_manager.CreateCommands(
        request_id=self.request.key.id(),
        command_lines=['long command line'],
        shard_indexes=list(range(1)),
        run_target='foo',
        run_count=1,
        shard_count=1,
        request_plugin_data={
            'ants_invocation_id': 'i123',
            'ants_work_unit_id': 'w123'
        },
        cluster='foobar')[0]
    # Clear Datastore cache
    ndb.get_context().clear_cache()

  def tearDown(self):
    self.plugin_patcher.stop()
    super(CommandAttemptMonitorTest, self).tearDown()

  @mock.patch.object(
      command_manager, 'ProcessCommandEvent', autospec=True)
  def testSyncCommandAttempt_reset(self, mock_update):
    now = datetime.datetime.utcnow()
    update_time = (
        now - datetime.timedelta(
            minutes=command_manager.MAX_COMMAND_EVENT_DELAY_MIN) * 2)
    _, request_id, _, command_id = self.command.key.flat()
    # disable auto_now or update_time will be ignored
    datastore_entities.CommandAttempt.update_time._auto_now = False
    command_event_test_util.CreateCommandAttempt(
        self.command, 'attempt_id', state=common.CommandState.UNKNOWN)

    event = command_event_test_util.CreateTestCommandEvent(
        request_id,
        command_id,
        'attempt_id',
        common.InvocationEventType.INVOCATION_STARTED)
    command_manager.UpdateCommandAttempt(event)
    attempt = command_manager.GetCommandAttempts(request_id, command_id)[0]
    attempt.update_time = update_time
    attempt.put()
    command_attempt_monitor.SyncCommandAttempt(
        request_id, command_id, 'attempt_id')
    mock_update.assert_called_once_with(
        hamcrest.match_equality(
            hamcrest.all_of(
                hamcrest.has_property(
                    'task_id',
                    'task_id'),
                hamcrest.has_property(
                    'error',
                    'A task reset by command attempt monitor.'),
                hamcrest.has_property(
                    'attempt_state', common.CommandState.ERROR))))

  @mock.patch.object(command_attempt_monitor, 'Now', autospec=True)
  @mock.patch.object(
      command_manager, 'AddToSyncCommandAttemptQueue', autospec=True)
  @mock.patch.object(command_manager, 'ProcessCommandEvent', autospec=True)
  def testSyncCommandAttempt_resync(self, mock_update, sync, mock_now):
    now = datetime.datetime.utcnow()
    mock_now.return_value = now
    update_time = (
        now - datetime.timedelta(
            minutes=command_manager.MAX_COMMAND_EVENT_DELAY_MIN - 1))
    _, request_id, _, command_id = self.command.key.flat()
    # disable auto_now or update_time will be ignored
    datastore_entities.CommandAttempt.update_time._auto_now = False
    command_event_test_util.CreateCommandAttempt(
        self.command, 'attempt_id', state=common.CommandState.UNKNOWN)
    event = command_event_test_util.CreateTestCommandEvent(
        request_id,
        command_id,
        'attempt_id',
        common.InvocationEventType.INVOCATION_STARTED,
        time=update_time)
    command_manager.UpdateCommandAttempt(event)
    attempt = command_manager.GetCommandAttempts(request_id, command_id)[0]
    attempt.update_time = update_time
    attempt.put()
    command_attempt_monitor.SyncCommandAttempt(request_id, command_id,
                                               'attempt_id')
    mock_update.assert_not_called()
    sync.assert_has_calls([mock.call(attempt)])

  @mock.patch.object(
      command_manager, 'AddToSyncCommandAttemptQueue', autospec=True)
  @mock.patch.object(
      command_manager, 'ProcessCommandEvent', autospec=True)
  def testSyncCommandAttempt_noAttempt(self, mock_update, sync):
    _, request_id, _, command_id = self.command.key.flat()
    command_attempt_monitor.SyncCommandAttempt(request_id, command_id,
                                               'attempt_id')
    mock_update.assert_not_called()
    sync.assert_not_called()

  @mock.patch.object(command_attempt_monitor, 'Now', autospec=True)
  @mock.patch.object(
      command_manager, 'AddToSyncCommandAttemptQueue', autospec=True)
  @mock.patch.object(
      command_manager, 'ProcessCommandEvent', autospec=True)
  def testSyncCommandAttempt_nonFinalState(self, mock_update, sync, mock_now):
    now = datetime.datetime.utcnow()
    mock_now.return_value = now
    update_time = (
        now - datetime.timedelta(
            minutes=command_manager.MAX_COMMAND_EVENT_DELAY_MIN - 1))
    _, request_id, _, command_id = self.command.key.flat()
    # disable auto_now or update_time will be ignored
    datastore_entities.CommandAttempt.update_time._auto_now = False
    command_event_test_util.CreateCommandAttempt(
        self.command, 'attempt_id', state=common.CommandState.UNKNOWN)
    event = command_event_test_util.CreateTestCommandEvent(
        request_id,
        command_id,
        'attempt_id',
        common.InvocationEventType.INVOCATION_STARTED,
        time=update_time)
    command_manager.UpdateCommandAttempt(event)
    attempt = command_manager.GetCommandAttempts(request_id, command_id)[0]
    attempt.update_time = update_time
    attempt.put()
    command_attempt_monitor.SyncCommandAttempt(request_id, command_id,
                                               'attempt_id')
    mock_update.assert_not_called()
    sync.assert_has_calls([mock.call(attempt)])

  @mock.patch.object(
      command_manager, 'ProcessCommandEvent', autospec=True)
  def testSyncCommandAttempt_finalState(self, mock_update):
    now = datetime.datetime.utcnow()
    update_time = (
        now - datetime.timedelta(
            minutes=command_manager.MAX_COMMAND_EVENT_DELAY_MIN - 1))
    command_event_test_util.CreateCommandAttempt(
        self.command, 'attempt_id', state=common.CommandState.UNKNOWN)
    _, request_id, _, command_id = self.command.key.flat()
    # disable auto_now or update_time will be ignored
    datastore_entities.CommandAttempt.update_time._auto_now = False
    event = command_event_test_util.CreateTestCommandEvent(
        request_id,
        command_id,
        'attempt_id',
        common.InvocationEventType.INVOCATION_COMPLETED,
        time=update_time)
    command_manager.UpdateCommandAttempt(event)
    attempt = command_manager.GetCommandAttempts(request_id, command_id)[0]
    attempt.update_time = update_time
    attempt.put()
    command_attempt_monitor.SyncCommandAttempt(request_id, command_id,
                                               'attempt_id')
    mock_update.assert_not_called()

  @mock.patch.object(command_attempt_monitor, 'SyncCommandAttempt')
  def testHandleCommandAttemptTask(self, sync):
    payload = {
        command_manager.REQUEST_ID_KEY: 'request',
        command_manager.COMMAND_ID_KEY: 'command',
        command_manager.ATTEMPT_ID_KEY: 'attempt'
    }
    response_0 = self.testapp.post(
        '/_ah/queue/%s' % command_manager.COMMAND_ATTEMPT_SYNC_QUEUE,
        json.dumps(payload))
    self.assertEqual('200 OK', response_0.status)
    sync.assert_called_once_with('request', 'command', 'attempt')


if __name__ == '__main__':
  unittest.main()
