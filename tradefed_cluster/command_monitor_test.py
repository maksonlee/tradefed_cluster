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

"""Tests for command_monitor."""

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

from tradefed_cluster import command_manager
from tradefed_cluster import command_monitor
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config  from tradefed_cluster import request_manager
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.services import task_scheduler
from tradefed_cluster.util import ndb_shim as ndb


class CommandMonitorTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super(CommandMonitorTest, self).setUp()
    self.testapp = webtest.TestApp(command_monitor.APP)
    self.plugin_patcher = mock.patch(
        '__main__.env_config.CONFIG.plugin')
    self.plugin_patcher.start()

    self.request = request_manager.CreateRequest(
        request_id='1001',
        user='user1',
        command_line='command_line',
        cluster='cluster',
        run_target='run_target')
    self.request_2 = request_manager.CreateRequest(
        request_id='1002',
        user='user1',
        command_line='command_line',
        cluster='cluster',
        run_target='run_target')
    # Clear Datastore cache
    ndb.get_context().clear_cache()

  def tearDown(self):
    super(CommandMonitorTest, self).tearDown()
    self.plugin_patcher.stop()

  @mock.patch.object(command_monitor, 'SyncCommand')
  def testMonitor(self, sync):
    commands = command_manager.CreateCommands(
        request_id=self.request_2.key.id(),
        command_lines=['long command line', 'longer_command_line'],
        shard_indexes=list(range(2)),
        shard_count=2,
        run_target='foo',
        run_count=1,
        cluster='foobar')
    num_monitored = command_monitor.Monitor(commands)
    self.assertEqual(2, num_monitored)
    tasks = self.mock_task_scheduler.GetTasks()
    self.assertEqual(2, len(tasks))
    response_0 = self.testapp.post(
        '/_ah/queue/%s' % command_monitor.COMMAND_SYNC_QUEUE,
        tasks[0].payload)
    self.assertEqual('200 OK', response_0.status)
    response_1 = self.testapp.post(
        '/_ah/queue/%s' % command_monitor.COMMAND_SYNC_QUEUE,
        tasks[1].payload)
    self.assertEqual('200 OK', response_1.status)
    sync.assert_has_calls([
        mock.call(self.request_2.key.id(), commands[0].key.id()),
        mock.call(self.request_2.key.id(), commands[1].key.id())
    ])

  @mock.patch.object(command_monitor, 'AddToSyncQueue')
  @mock.patch.object(command_manager, 'EnsureLeasable')
  def testSyncCommand(self, mock_ensure, sync):
    datastore_entities.Command.update_time._auto_now = False
    now = datetime.datetime.utcnow()
    command = command_manager.CreateCommands(
        request_id=self.request.key.id(),
        command_lines=['long command line'],
        shard_indexes=list(range(1)),
        run_target='foo',
        run_count=1,
        shard_count=1,
        cluster='foobar')[0]
    command.state = common.CommandState.QUEUED
    command.update_time = (
        now - datetime.timedelta(
            minutes=command_monitor.MAX_COMMAND_INACTIVE_TIME_MIN) * 2)
    command.put()
    command_monitor.SyncCommand(command.request_id, command.key.id())
    mock_ensure.assert_called_once_with(
        hamcrest.match_equality(hamcrest.has_property('key', command.key)))
    self.assertEqual(common.CommandState.CANCELED, command.key.get().state)
    self.assertEqual(common.RequestState.CANCELED, self.request.key.get().state)
    sync.assert_not_called()

  @mock.patch.object(command_monitor, 'AddToSyncQueue')
  @mock.patch.object(command_manager, 'EnsureLeasable')
  def testSyncCommand_runningState(self, mock_ensure, sync):
    datastore_entities.Command.update_time._auto_now = False
    now = datetime.datetime.utcnow()
    command = command_manager.CreateCommands(
        request_id=self.request.key.id(),
        command_lines=['long command line'],
        shard_indexes=list(range(1)),
        run_target='foo',
        run_count=1,
        shard_count=1,
        cluster='foobar')[0]
    command.state = common.CommandState.RUNNING
    command.update_time = (
        now - datetime.timedelta(
            minutes=command_monitor.MAX_COMMAND_INACTIVE_TIME_MIN) * 2)
    command.put()
    command_monitor.SyncCommand(command.request_id, command.key.id())
    mock_ensure.assert_not_called()
    self.assertEqual(common.CommandState.RUNNING, command.key.get().state)
    sync.assert_called_once()

  @mock.patch.object(command_monitor, 'AddToSyncQueue')
  @mock.patch.object(command_manager, 'EnsureLeasable')
  def testSyncCommand_runningState_doNotAddToQueue(self, mock_ensure, sync):
    datastore_entities.Command.update_time._auto_now = False
    now = datetime.datetime.utcnow()
    command = command_manager.CreateCommands(
        request_id=self.request.key.id(),
        command_lines=['long command line'],
        shard_indexes=list(range(1)),
        run_target='foo',
        run_count=1,
        shard_count=1,
        cluster='foobar')[0]
    command.state = common.CommandState.RUNNING
    command.update_time = (
        now - datetime.timedelta(
            minutes=command_monitor.MAX_COMMAND_INACTIVE_TIME_MIN) * 2)
    command.put()
    command_monitor.SyncCommand(command.request_id, command.key.id(), False)
    mock_ensure.assert_not_called()
    self.assertEqual(common.CommandState.RUNNING, command.key.get().state)
    sync.assert_not_called()

  @mock.patch.object(command_monitor, 'AddToSyncQueue')
  @mock.patch.object(command_manager, 'EnsureLeasable')
  def testSyncCommand_withCustomQueueTimeout(self, mock_ensure, sync):
    datastore_entities.Command.update_time._auto_now = False
    now = datetime.datetime.utcnow()
    command_1, command_2 = command_manager.CreateCommands(
        request_id=self.request_2.key.id(),
        command_lines=['long command line', 'longer_command_line'],
        shard_indexes=list(range(2)),
        shard_count=2,
        run_target='foo',
        run_count=1,
        cluster='foobar',
        queue_timeout_seconds=command_monitor.MAX_COMMAND_INACTIVE_TIME_MIN *
        2 * 60)
    # Change update times. command_1 should ensure leasable, command_2 should
    # ensure leasable and cancel afterwards
    command_1.state = common.CommandState.QUEUED
    command_1.update_time = (
        now - datetime.timedelta(
            minutes=command_monitor.MAX_COMMAND_INACTIVE_TIME_MIN))
    command_1.put()
    command_2.state = common.CommandState.QUEUED
    command_2.update_time = (
        now - datetime.timedelta(
            minutes=command_monitor.MAX_COMMAND_INACTIVE_TIME_MIN) * 3)
    command_2.put()

    command_monitor.SyncCommand(command_1.request_id, command_1.key.id())
    command_monitor.SyncCommand(command_2.request_id, command_2.key.id())

    mock_ensure.assert_has_calls([
        mock.call(
            hamcrest.match_equality(
                hamcrest.has_property('key', command_1.key))),
        mock.call(
            hamcrest.match_equality(
                hamcrest.has_property('key', command_2.key)))
    ])
    self.assertEqual(common.CommandState.QUEUED, command_1.key.get().state)
    self.assertEqual(common.CommandState.CANCELED, command_2.key.get().state)
    self.assertEqual(common.RequestState.CANCELED,
                     self.request_2.key.get().state)
    sync.assert_called_once_with(command_1)

  @mock.patch.object(common, 'Now')
  @mock.patch.object(task_scheduler, 'AddTask')
  def testAddToSyncQueue(self, mock_add, mock_now):
    # Create a command that was created 5 minutes ago.
    datastore_entities.Command.update_time._auto_now = False
    now = datetime.datetime.utcnow()
    mock_now.return_value = now
    command = command_manager.CreateCommands(
        request_id=self.request.key.id(),
        command_lines=['command line'],
        shard_indexes=list(range(1)),
        run_target='run_target',
        run_count=1,
        shard_count=1,
        cluster='cluster')[0]
    _, request_id, _, command_id = command.key.flat()
    command.state = common.CommandState.QUEUED
    command.update_time = now - datetime.timedelta(minutes=5)
    command.put()

    command_monitor.AddToSyncQueue(command)

    # Command monitor should schedule it to be synced in
    # MAX_COMMAND_EVENT_DELAY_MINs.
    payload = json.dumps({
        command_manager.COMMAND_ID_KEY: command_id,
        command_manager.REQUEST_ID_KEY: request_id,
    })
    mock_add.assert_called_once_with(
        queue_name=command_monitor.COMMAND_SYNC_QUEUE,
        payload=payload,
        eta=now + datetime.timedelta(
            minutes=command_monitor.MAX_COMMAND_EVENT_DELAY_MIN))

  @mock.patch.object(task_scheduler, 'AddTask')
  def testAddToSyncQueue_CancelDeadline(self, mock_add):
    # Create a command that needs to be cancelled in 1 minute.
    datastore_entities.Command.update_time._auto_now = False
    now = datetime.datetime.utcnow()
    command = command_manager.CreateCommands(
        request_id=self.request.key.id(),
        command_lines=['command line'],
        shard_indexes=list(range(1)),
        run_target='run_target',
        run_count=1,
        shard_count=1,
        cluster='cluster')[0]
    _, request_id, _, command_id = command.key.flat()
    command.state = common.CommandState.QUEUED
    command.update_time = now - datetime.timedelta(
        minutes=command_monitor.MAX_COMMAND_INACTIVE_TIME_MIN - 1)
    command.put()

    command_monitor.AddToSyncQueue(command)

    # Command monitor should schedule it to be synced in 1 minute.
    payload = json.dumps({
        command_manager.COMMAND_ID_KEY: command_id,
        command_manager.REQUEST_ID_KEY: request_id,
    })
    mock_add.assert_called_once_with(
        queue_name=command_monitor.COMMAND_SYNC_QUEUE,
        payload=payload,
        eta=now + datetime.timedelta(minutes=1))

  @mock.patch.object(task_scheduler, 'AddTask')
  def testAddToSyncQueue_CustomCancelDeadline(self, mock_add):
    # Create a command with a custom 10 hour command timeout that needs to be
    # cancelled in 1 minute.
    datastore_entities.Command.update_time._auto_now = False
    now = datetime.datetime.utcnow()
    custom_timeout = 10 * 3600
    command = command_manager.CreateCommands(
        request_id=self.request.key.id(),
        command_lines=['command line'],
        shard_indexes=list(range(1)),
        run_target='run_target',
        run_count=1,
        shard_count=1,
        cluster='cluster',
        queue_timeout_seconds=custom_timeout)[0]
    _, request_id, _, command_id = command.key.flat()
    command.state = common.CommandState.QUEUED
    command.update_time = now - datetime.timedelta(seconds=custom_timeout - 60)
    command.put()

    command_monitor.AddToSyncQueue(command)

    # Command monitor should schedule it to be synced in 1 minute.
    payload = json.dumps({
        command_manager.COMMAND_ID_KEY: command_id,
        command_manager.REQUEST_ID_KEY: request_id,
    })
    mock_add.assert_called_once_with(
        queue_name=command_monitor.COMMAND_SYNC_QUEUE,
        payload=payload,
        eta=now + datetime.timedelta(minutes=1))

  @mock.patch.object(common, 'Now')
  @mock.patch.object(task_scheduler, 'AddTask')
  def testAddToSyncQueue_RunningCommand(self, mock_add, mock_now):
    # Create a command that has been running for 3 hours.
    datastore_entities.Command.update_time._auto_now = False
    now = datetime.datetime.utcnow()
    mock_now.return_value = now
    command = command_manager.CreateCommands(
        request_id=self.request.key.id(),
        command_lines=['command line'],
        shard_indexes=list(range(1)),
        run_target='run_target',
        run_count=1,
        shard_count=1,
        cluster='cluster')[0]
    _, request_id, _, command_id = command.key.flat()
    command.state = common.CommandState.RUNNING
    command.update_time = now - datetime.timedelta(hours=3)
    command.put()

    command_monitor.AddToSyncQueue(command)

    # Command monitor should schedule it to be synced in
    # MAX_COMMAND_EVENT_DELAY_MINs.
    payload = json.dumps({
        command_manager.COMMAND_ID_KEY: command_id,
        command_manager.REQUEST_ID_KEY: request_id,
    })
    mock_add.assert_called_once_with(
        queue_name=command_monitor.COMMAND_SYNC_QUEUE,
        payload=payload,
        eta=now + datetime.timedelta(
            minutes=command_monitor.MAX_COMMAND_EVENT_DELAY_MIN))


if __name__ == '__main__':
  unittest.main()
