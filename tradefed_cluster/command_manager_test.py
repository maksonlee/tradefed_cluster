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

"""Unit tests for command_manager."""

import collections
import datetime
import json
import logging
import threading
import unittest
import zlib

import hamcrest
import mock
from protorpc import protojson

from tradefed_cluster.util import ndb_shim as ndb

from tradefed_cluster import api_messages
from tradefed_cluster import command_event_test_util
from tradefed_cluster import command_manager
from tradefed_cluster import command_task_store
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config
from tradefed_cluster import metric
from tradefed_cluster import request_manager
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.plugins import base as plugin_base

TIMESTAMP = datetime.datetime(2017, 3, 8)
TIMEDELTA = datetime.timedelta(seconds=30)
REQUEST_ID = "1"


class CommandManagerTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super(CommandManagerTest, self).setUp()
    request_manager.CreateRequest(user="user1",
                                  command_line="command_line",
                                  request_id=REQUEST_ID)
    self.plugin_patcher = mock.patch(
        "__main__.env_config.CONFIG.plugin")
    self.plugin_patcher.start()

  def tearDown(self):
    self.plugin_patcher.stop()
    super(CommandManagerTest, self).tearDown()

  def _CreateCommand(
      self, request_id=REQUEST_ID, run_count=1, priority=None,
      command_line="command_line1"):
    """Helper to create a command."""
    command = command_manager.CreateCommands(
        request_id=request_id,
        run_target="run_target",
        run_count=run_count,
        cluster="cluster",
        priority=priority,
        shard_count=1,
        shard_indexes=[0],
        request_plugin_data={
            "ants_invocation_id": "i123",
            "command_ants_work_unit_id": "w123"},
        command_lines=[command_line])[0]
    return command

  def testCreateCommands(self):
    commands = command_manager.CreateCommands(
        request_id=REQUEST_ID,
        command_lines=["foo bar1", "foo bar2"],
        shard_count=2,
        shard_indexes=range(2),
        run_target="run_target",
        run_count=1,
        cluster="cluster",
        priority=100,
        request_plugin_data={
            "ants_invocation_id": "i123",
            "ants_work_unit_id": "w123"
        },
        queue_timeout_seconds=1000)

    self.assertEqual(2, len(commands))
    self.assertEqual("foo bar1", commands[0].command_line)
    self.assertEqual("foo bar2", commands[1].command_line)

    commands = command_manager.GetCommands(REQUEST_ID)
    self.assertEqual(2, len(commands))
    self.assertEqual("foo bar1", commands[0].command_line)
    self.assertEqual(REQUEST_ID, commands[0].request_id)
    self.assertEqual("foo bar1", commands[0].command_line)
    self.assertEqual("cluster", commands[0].cluster)
    self.assertEqual("run_target", commands[0].run_target)
    self.assertEqual(2, commands[0].shard_count)
    self.assertEqual(0, commands[0].shard_index)
    self.assertEqual(1, commands[0].run_count)
    self.assertEqual(100, commands[0].priority)
    self.assertEqual(1000, commands[0].queue_timeout_seconds)
    self.assertEqual("foo bar2", commands[1].command_line)
    self.assertEqual(2, commands[1].shard_count)
    self.assertEqual(1, commands[1].shard_index)

  def testCreateCommands_singleShard(self):
    commands = command_manager.CreateCommands(
        request_id=REQUEST_ID,
        request_plugin_data={},
        command_lines=["foo bar"],
        shard_count=1,
        shard_indexes=range(1),
        run_target="run_target",
        run_count=1,
        cluster="cluster",
        priority=100,
        queue_timeout_seconds=1000)

    self.assertEqual(1, len(commands))
    self.assertEqual("foo bar", commands[0].command_line)

    commands = command_manager.GetCommands(REQUEST_ID)
    self.assertEqual(1, len(commands))
    self.assertEqual(REQUEST_ID, commands[0].request_id)
    self.assertEqual("foo bar", commands[0].command_line)
    self.assertEqual("cluster", commands[0].cluster)
    self.assertEqual("run_target", commands[0].run_target)
    self.assertEqual(None, commands[0].shard_count)
    self.assertEqual(None, commands[0].shard_index)
    self.assertEqual(1, commands[0].run_count)
    self.assertEqual(100, commands[0].priority)
    self.assertEqual(1000, commands[0].queue_timeout_seconds)

  @mock.patch.object(request_manager, "NotifyRequestState")
  def testScheduleTasks(self, notify):
    command = self._CreateCommand(run_count=2)
    _, request_id, _, command_id = command.key.flat()

    command_manager.ScheduleTasks([command])

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 2)
    self.assertEqual(tasks[0].request_id, request_id)
    self.assertEqual(tasks[0].command_id, command_id)
    self.assertEqual(tasks[0].task_id, "%s-%s-0" % (request_id, command_id))
    self.assertEqual(tasks[0].command_line, command.command_line)
    self.assertEqual(tasks[0].run_count, command.run_count)
    self.assertEqual(tasks[0].shard_count, command.shard_count)
    self.assertEqual(tasks[0].shard_index, command.shard_index)
    self.assertEqual(tasks[0].cluster, command.cluster)
    self.assertEqual(
        tasks[0].test_bench,
        command_task_store._GetTestBench(command.cluster, command.run_target))
    self.assertEqual(tasks[0].priority, 0)
    self.assertEqual(tasks[0].request_type, command.request_type)
    self.assertEqual(tasks[0].plugin_data, command.plugin_data)
    self.assertEqual(tasks[1].task_id, "%s-%s-1" % (request_id, command_id))

    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.QUEUED, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.QUEUED, request.state)
    notify.assert_called_once_with(REQUEST_ID)

  @mock.patch.object(request_manager, "NotifyRequestState")
  def testScheduleTasks_withPriority(self, _):
    request_manager.CreateRequest(
        user="user1", command_line="low priority command", request_id="1001")
    request_manager.CreateRequest(
        user="user1", command_line="medium priority command", request_id="1002")
    request_manager.CreateRequest(
        user="user1", command_line="high priority command", request_id="1003")
    commands = [
        self._CreateCommand(
            request_id="1001",
            command_line="low priority command",
            priority=50),
        self._CreateCommand(
            request_id="1002",
            command_line="medium priority command",
            priority=150),
        self._CreateCommand(
            request_id="1003",
            command_line="high priority command",
            priority=250),
    ]
    command_manager.ScheduleTasks(commands)

    for command in commands:
      _, request_id, _, command_id = command.key.flat()
      tasks = command_manager.GetActiveTasks(command)
      self.assertEqual(len(tasks), 1)
      self.assertEqual(tasks[0].request_id, request_id)
      self.assertEqual(tasks[0].command_id, command_id)
      self.assertEqual(tasks[0].task_id, "%s-%s-0" % (request_id, command_id))
      self.assertEqual(tasks[0].command_line, command.command_line)
      self.assertEqual(tasks[0].run_count, command.run_count)
      self.assertEqual(tasks[0].shard_count, command.shard_count)
      self.assertEqual(tasks[0].shard_index, command.shard_index)
      self.assertEqual(tasks[0].cluster, command.cluster)
      self.assertEqual(
          tasks[0].test_bench,
          command_task_store._GetTestBench(command.cluster, command.run_target))
      self.assertEqual(tasks[0].priority, command.priority)
      self.assertEqual(tasks[0].request_type, command.request_type)
      self.assertEqual(tasks[0].plugin_data, command.plugin_data)
      c = command.key.get(use_cache=False)
      self.assertEqual(common.CommandState.QUEUED, c.state)
      r = command.key.parent().get(use_cache=False)
      self.assertEqual(common.RequestState.QUEUED, r.state)

  @mock.patch.object(request_manager, "NotifyRequestState")
  def testScheduleTasks_withInvalidPriority(self, _):
    command = self._CreateCommand(
        command_line="invalid priority command",
        priority=1500)

    with self.assertRaises(ValueError):
      command_manager.ScheduleTasks([command])

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 0)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.UNKNOWN, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.UNKNOWN, request.state)

  def testEnsureLeasable(self):
    command = self._CreateCommand()
    command_manager.ScheduleTasks([command])
    command_manager.EnsureLeasable(command)
    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].task_id, "1-1-0")
    self.assertEqual(tasks[0].leasable, True)

  def testEnsureLeasable_invalidTask(self):
    command = self._CreateCommand()
    with self.assertRaises(command_manager.CommandTaskNotFoundError):
      command_manager.EnsureLeasable(command)

  def testEnsureLeasable_multipleRuns(self):
    command = self._CreateCommand()
    command.run_count = 2
    command_manager.ScheduleTasks([command])
    command_task_store.DeleteTask("1-1-0")
    command_manager.EnsureLeasable(command)
    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].task_id, "1-1-1")
    self.assertEqual(tasks[0].leasable, True)

  def testGetActiveTaskCount(self):
    command = self._CreateCommand(run_count=2)
    command_manager.ScheduleTasks([command])
    count = command_manager.GetActiveTaskCount(command)
    self.assertEqual(2, count)

  def testRescheduleTask(self):
    command = self._CreateCommand()
    task_id = "1-1-0"
    command_manager.ScheduleTasks([command])
    command_task_store.LeaseTask(task_id)
    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].task_id, task_id)
    self.assertEqual(tasks[0].leasable, False)

    command_manager.RescheduleTask(task_id, command)
    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].task_id, task_id)
    self.assertEqual(tasks[0].leasable, True)

  def testGetCommandSummary_noCommandAttempts(self):
    """Tests command_manager.GetCommandSummary() with no command attempts."""
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    summary = command_manager.GetCommandSummary(
        request_id, command_id, command.run_count)
    self.assertIsNone(summary)

  def testGetCommandSummary_badCommandAttempts(self):
    """Tests command_manager.GetCommandSummary() with no command attempts."""
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    # State is UNKNOWN
    command_event_test_util.CreateCommandAttempt(
        command, "attempt0", common.CommandState.UNKNOWN)
    command_event_test_util.CreateCommandAttempt(
        command, "attempt1", common.CommandState.RUNNING)
    command_event_test_util.CreateCommandAttempt(
        command, "attempt2", common.CommandState.CANCELED)
    # No state.
    command_event_test_util.CreateCommandAttempt(
        command, "attempt3", None)

    summary = command_manager.GetCommandSummary(
        request_id, command_id, command.run_count)
    self.assertEqual(4, summary.total_count)
    self.assertEqual(1, summary.running_count)
    self.assertEqual(1, summary.canceled_count)
    self.assertEqual(0, summary.completed_count)
    self.assertEqual(0, summary.error_count)
    self.assertEqual(0, summary.fatal_count)
    self.assertIsNone(summary.start_time)
    self.assertIsNone(summary.end_time)

  def testGetCommandSummary_afterCommandAttempts(self):
    """Tests Command.GetCommandSummary() summary with command attempts."""
    datetime_0 = datetime.datetime(2015, 1, 1)
    datetime_1 = datetime.datetime(1989, 5, 7)
    datetime_2 = datetime.datetime(2015, 5, 6)
    datetime_3 = datetime.datetime(2015, 7, 18)

    commands = command_manager.CreateCommands(
        REQUEST_ID,
        run_target="foo",
        run_count=1,
        cluster="foobar",
        command_lines=["command_line",
                       "short command line"],
        shard_count=2,
        shard_indexes=range(2))
    command_1 = commands[0]
    _, request_id1, _, command_id1 = command_1.key.flat()
    command_2 = commands[1]
    _, request_id2, _, command_id2 = command_2.key.flat()

    command_event_test_util.CreateCommandAttempt(
        command_1, "attempt0", common.CommandState.RUNNING,
        start_time=datetime_0, end_time=datetime_1)
    command_event_test_util.CreateCommandAttempt(
        command_1, "attempt1", common.CommandState.COMPLETED,
        start_time=datetime_2, end_time=datetime_3)
    command_event_test_util.CreateCommandAttempt(
        command_2, "attempt2", common.CommandState.RUNNING,
        start_time=datetime_2, end_time=datetime_3)

    summary = command_manager.GetCommandSummary(
        request_id1, command_id1, command_1.run_count)
    self.assertEqual(2, summary.total_count)
    self.assertEqual(1, summary.running_count)
    self.assertEqual(1, summary.completed_count)
    self.assertEqual(0, summary.error_count)
    self.assertEqual(datetime_0, summary.start_time)
    self.assertEqual(datetime_3, summary.end_time)
    summary = command_manager.GetCommandSummary(
        request_id2, command_id2, command_2.run_count)
    self.assertEqual(1, summary.total_count)
    self.assertEqual(1, summary.running_count)
    self.assertEqual(0, summary.completed_count)
    self.assertEqual(datetime_2, summary.start_time)
    self.assertEqual(datetime_3, summary.end_time)

  def testEvaluateState(self):
    """Tests command_manager.EvaluateState."""
    datetime_0 = datetime.datetime(2015, 1, 1)
    datetime_1 = datetime.datetime(2015, 7, 18)

    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()

    command_event_test_util.CreateCommandAttempt(
        command, "attempt0", common.CommandState.RUNNING)
    command_event_test_util.CreateCommandAttempt(
        command, "attempt1", common.CommandState.RUNNING)
    event1 = command_event_test_util.CreateTestCommandEvent(
        request_id,
        command_id,
        "attempt0",
        common.InvocationEventType.INVOCATION_STARTED,
        time=datetime_0)
    event2 = command_event_test_util.CreateTestCommandEvent(
        request_id,
        command_id,
        "attempt1",
        common.InvocationEventType.INVOCATION_COMPLETED,
        time=datetime_1)

    command_manager.UpdateCommandAttempt(event1)
    command_manager.UpdateCommandAttempt(event2)

    command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.UNKNOWN, command.state)
    self.assertTrue(command.dirty)

    command, remaining_run_count = command_manager.EvaluateState(
        request_id, command_id)
    self.assertEqual(0, remaining_run_count)
    self.assertEqual(common.CommandState.COMPLETED, command.state)
    self.assertEqual(datetime_0, command.start_time)
    self.assertEqual(datetime_1, command.end_time)
    self.assertFalse(command.dirty)
    request = request_manager.GetRequest(request_id)
    self.assertTrue(request.dirty)

  @mock.patch.object(command_manager, "GetCommandSummary")
  def testCommandUpdateState_atomicTransaction(self, mock_get_summary):
    """Tests atomicity of database transactions when updating the state."""
    command = self._CreateCommand()
    counts = collections.defaultdict(int)
    semaphore = threading.Semaphore(0)
    def Blocked(*args, **kwargs):         counts[threading.current_thread().name] += 1
      if threading.current_thread().name == "thread1":
        try:
          semaphore.acquire()
          summary = command_manager.CommandSummary()
          summary.running_count = 1
          return summary
        finally:
          semaphore.release()
      else:
        return command_manager.CommandSummary()
    mock_get_summary.side_effect = Blocked
    t1 = threading.Thread(
        name="thread1",
        target=command_manager._UpdateState,
        kwargs={"request_id": REQUEST_ID,
                "command_id": command.key.id(),
                "state": common.CommandState.RUNNING,
                "force": True})
    t2 = threading.Thread(
        name="thread2",
        target=command_manager._UpdateState,
        kwargs={"request_id": REQUEST_ID,
                "command_id": command.key.id(),
                "state": common.CommandState.QUEUED,
                "force": True})

    # Wait for first thread to be ready to commit, before trying to update the
    # same command in a separate thread.
    t1.start()  # t1 will block
    t2.start()  # t2 will not block
    t2.join(timeout=5)
    self.assertTrue(t1.is_alive())
    self.assertFalse(t2.is_alive())

    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.QUEUED, command.state)
    semaphore.release()
    t1.join(timeout=5)
    self.assertFalse(t1.is_alive())
    self.assertFalse(t2.is_alive())
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.RUNNING, command.state)
    self.assertEqual(1, counts["thread2"])
    # Thread1 first transcation failed, and the second attempt succeeded.
    self.assertEqual(2, counts["thread1"])

  def testEvaluateState_commandAttemptCompletion(self):
    """Update a command up to completion."""
    start_time = datetime.datetime(2015, 1, 1)
    end_time = datetime.datetime(2015, 5, 6)
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()

    event1 = command_event_test_util.CreateTestCommandEvent(
        request_id,
        command_id,
        "attempt_id",
        common.InvocationEventType.INVOCATION_STARTED,
        time=start_time)
    command_event_test_util.CreateCommandAttempt(
        command, "attempt_id", common.CommandState.QUEUED)
    command_manager.UpdateCommandAttempt(event1)

    command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.UNKNOWN, command.state)
    self.assertTrue(command.dirty)

    command, remaining_run_count = command_manager.EvaluateState(
        request_id, command_id)
    self.assertEqual(1, remaining_run_count)
    self.assertEqual(common.CommandState.RUNNING, command.state)
    self.assertEqual(start_time, command.start_time)
    self.assertEqual(None, command.end_time)
    self.assertFalse(command.dirty)

    event2 = command_event_test_util.CreateTestCommandEvent(
        request_id,
        command_id,
        "attempt_id",
        common.InvocationEventType.INVOCATION_COMPLETED,
        time=end_time)
    command_manager.UpdateCommandAttempt(event2)

    command, remaining_run_count = command_manager.EvaluateState(
        request_id, command_id)
    self.assertEqual(0, remaining_run_count)
    self.assertEqual(common.CommandState.COMPLETED, command.state)
    self.assertEqual(start_time, command.start_time)
    self.assertEqual(end_time, command.end_time)
    self.assertFalse(command.dirty)
    request = request_manager.GetRequest(request_id)
    self.assertTrue(request.dirty)

  def testCommandCancel(self):
    """Test cancelling a command."""
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    command = command_manager.Cancel(
        request_id, command_id,
        cancel_reason=common.CancelReason.QUEUE_TIMEOUT)
    self.assertEqual(common.CommandState.CANCELED, command.state)
    self.assertEqual(common.CancelReason.QUEUE_TIMEOUT, command.cancel_reason)
    request = request_manager.GetRequest(request_id)
    self.assertTrue(request.dirty)

  def testEvaluateState_cancelCompletedCommand(self):
    """Cancelling a completed command won't change its state."""
    end_time = datetime.datetime(2015, 5, 6)
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()

    event1 = command_event_test_util.CreateTestCommandEvent(
        request_id,
        command_id,
        "attempt_id",
        common.InvocationEventType.INVOCATION_COMPLETED,
        time=end_time)

    command_event_test_util.CreateCommandAttempt(
        command, "attempt_id", common.CommandState.RUNNING)
    command_manager.UpdateCommandAttempt(event1)

    command, _ = command_manager.EvaluateState(request_id, command_id)
    self.assertEqual(common.CommandState.COMPLETED, command.state)
    self.assertEqual(end_time, command.end_time)

    command = command_manager.Cancel(request_id, command_id)
    self.assertEqual(common.CommandState.COMPLETED, command.state)
    self.assertEqual(end_time, command.end_time)

  def testEvaluateState_completeCancelledCommand(self):
    """Completing a cancelled command triggers a state update."""
    start_time = datetime.datetime(2015, 1, 1)
    end_time = datetime.datetime(2015, 5, 6)
    command = self._CreateCommand()
    command_event_test_util.CreateCommandAttempt(
        command, "attempt_id", common.CommandState.UNKNOWN)
    _, request_id, _, command_id = command.key.flat()

    # Command is initially running.
    event1 = command_event_test_util.CreateTestCommandEvent(
        request_id,
        command_id,
        "attempt_id",
        common.InvocationEventType.INVOCATION_STARTED,
        time=start_time)
    command_manager.UpdateCommandAttempt(event1)
    command, remaining_run_count = command_manager.EvaluateState(
        request_id, command_id)
    self.assertEqual(1, remaining_run_count)
    self.assertEqual(common.CommandState.RUNNING, command.state)
    self.assertEqual(start_time, command.start_time)
    self.assertEqual(None, command.end_time)

    # Command is cancelled before command attempt completes.
    command = command_manager.Cancel(
        request_id, command_id)
    self.assertEqual(common.CommandState.CANCELED, command.state)

    # Command attempt completes
    event2 = command_event_test_util.CreateTestCommandEvent(
        request_id,
        command_id,
        "attempt_id",
        common.InvocationEventType.INVOCATION_COMPLETED,
        time=end_time)
    command_manager.UpdateCommandAttempt(event2)
    command, remaining_run_count = command_manager.EvaluateState(
        request_id, command_id)
    self.assertEqual(0, remaining_run_count)
    self.assertEqual(common.CommandState.COMPLETED, command.state)
    self.assertEqual(start_time, command.start_time)
    self.assertEqual(end_time, command.end_time)
    request = request_manager.GetRequest(request_id)
    self.assertTrue(request.dirty)

  def testEvaluateState_cancelledCommandAttempts(self):
    """Commands with cancelled attempts should eventually get cancelled."""
    start_time = datetime.datetime(2015, 1, 1)
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    command.state = common.CommandState.QUEUED

    # Command should remain QUEUED until the number of canceled attempts
    # exceeds the base threshold.
    for i in range(command_manager.MAX_CANCELED_COUNT_BASE):
      command_event_test_util.CreateCommandAttempt(
          command, "attempt-" + str(i), common.CommandState.QUEUED)
      self.assertEqual(common.CommandState.QUEUED, command.state)
      event = command_event_test_util.CreateTestCommandEvent(
          request_id,
          command_id,
          "attempt-%d" % i,
          common.InvocationEventType.ALLOCATION_FAILED,
          time=start_time)
      command_manager.UpdateCommandAttempt(event)
      command, _ = command_manager.EvaluateState(
          request_id, command_id, force=True)
    self.assertEqual(common.CommandState.CANCELED, command.state)

  def testCommandUpdateCommandAttempt_noAttempt(self):
    """Tests Command.UpdateCommandAttempt() when no attempts exist."""
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(0, len(attempts))
    self.assertEqual(common.CommandState.UNKNOWN, command.state)
    event = command_event_test_util.CreateTestCommandEvent(
        request_id,
        command_id,
        "attempt_id",
        common.InvocationEventType.INVOCATION_STARTED,
        time=TIMESTAMP)
    is_updated = command_manager.UpdateCommandAttempt(event)

    self.assertFalse(is_updated)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(0, len(attempts))

  def testCommandUpdateCommandAttempt_existingAttempt(self):
    """Tests Command.UpdateCommandAttempt() when attempts exist."""
    command = self._CreateCommand(run_count=2)
    _, request_id, _, command_id = command.key.flat()
    attempt_id = "attempt_id"
    start_time = datetime.datetime(1989, 5, 6)
    update_time = datetime.datetime(1989, 5, 7)
    command_event_test_util.CreateCommandAttempt(
        command, attempt_id, common.CommandState.RUNNING,
        start_time=start_time, update_time=update_time)

    event1 = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, attempt_id,
        common.InvocationEventType.INVOCATION_STARTED,
        time=start_time)
    command_manager.UpdateCommandAttempt(event1)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(1, len(attempts))

    event2 = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, attempt_id,
        common.InvocationEventType.INVOCATION_COMPLETED,
        time=TIMESTAMP)
    is_updated = command_manager.UpdateCommandAttempt(event2)
    self.assertTrue(command.key.get(use_cache=False).dirty)
    self.assertTrue(is_updated)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(1, len(attempts))
    self.assertEqual("task_id", attempts[0].task_id)
    self.assertEqual("attempt_id", attempts[0].attempt_id)
    self.assertEqual(common.CommandState.COMPLETED, attempts[0].state)
    self.assertEqual(1000, attempts[0].total_test_count)
    self.assertEqual(100, attempts[0].failed_test_count)
    self.assertEqual(10, attempts[0].failed_test_run_count)
    self.assertEqual(1, attempts[0].device_lost_detected)
    self.assertEqual(TIMESTAMP, attempts[0].last_event_time)
    self.assertGreaterEqual(
        attempts[0].update_time, update_time,
        "Attempt update time %s was changed to before %s" %
        (attempts[0].update_time, update_time))
    # State should be queued because 1 (completed attempts) < 2 (run count)
    command_manager.EvaluateState(request_id, command_id)
    self.assertEqual(common.CommandState.QUEUED, command.key.get().state)

  def testCommandUpdateCommandAttempt_laterTimestamp(self):
    """Tests updating an attempt with a later start time."""
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    attempt_id = "attempt_id"

    start_time = datetime.datetime(1989, 5, 6)
    update_time = datetime.datetime(1989, 5, 7)
    command_attempt = datastore_entities.CommandAttempt(
        key=ndb.Key(
            datastore_entities.Request, request_id,
            datastore_entities.Command, command_id,
            datastore_entities.CommandAttempt, attempt_id,
            namespace=common.NAMESPACE),
        task_id="task_id",
        attempt_id=attempt_id,
        command_id=command_id,
        state=common.CommandState.RUNNING,
        start_time=start_time,
        update_time=update_time,
    )
    command_attempt.put()
    event1 = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, attempt_id,
        common.InvocationEventType.INVOCATION_STARTED,
        time=start_time)
    command_manager.UpdateCommandAttempt(event1)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(1, len(attempts))

    # An update with a later start time should not change the start time.
    event2 = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, attempt_id,
        common.InvocationEventType.TEST_RUN_IN_PROGRESS,
        time=datetime.datetime(1989, 5, 8))
    is_updated = command_manager.UpdateCommandAttempt(event2)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertTrue(is_updated)
    self.assertEqual(1, len(attempts))
    self.assertEqual(start_time, attempts[0].start_time)
    self.assertGreaterEqual(
        attempts[0].update_time, update_time,
        "Attempt update time %s was changed to before %s" %
        (attempts[0].update_time, update_time))

  def testCommandUpdateCommandAttempt_noChanges(self):
    """Tests UpdateCommandAttempt() when there are no changes (b/22761890)."""
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    attempt_id = "attempt_id"
    command_attempt = datastore_entities.CommandAttempt(
        key=ndb.Key(
            datastore_entities.Request, request_id,
            datastore_entities.Command, command_id,
            datastore_entities.CommandAttempt, attempt_id,
            namespace=common.NAMESPACE),
        task_id="task_id",
        attempt_id=attempt_id,
        command_id=command_id,
        state=common.CommandState.RUNNING)
    command_attempt.put()
    before = command_attempt.update_time

    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(1, len(attempts))
    self.assertEqual(common.CommandState.RUNNING, attempts[0].state)
    self.assertEqual(before, attempts[0].update_time)
    event1 = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, attempt_id,
        common.InvocationEventType.TEST_RUN_IN_PROGRESS)
    is_updated = command_manager.UpdateCommandAttempt(event1)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertTrue(is_updated)
    self.assertEqual(1, len(attempts))
    self.assertEqual(common.CommandState.RUNNING, attempts[0].state)
    self.assertNotEqual(before, attempts[0].update_time)
    self.assertFalse(command.key.get(use_cache=False).dirty)

  def testCommandUpdateCommandAttempt_canceledCommand(self):
    """Tests UpdateCommandAttempt() when command is canceled."""
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    attempt_id = "attempt_id"
    command_event_test_util.CreateCommandAttempt(
        command, "attempt_id", common.CommandState.RUNNING)

    command_manager.Cancel(request_id, command_id)

    self.assertEqual(common.CommandState.CANCELED,
                     command.key.get(use_cache=False).state)

    event1 = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, attempt_id,
        common.InvocationEventType.TEST_RUN_IN_PROGRESS)
    is_updated = command_manager.UpdateCommandAttempt(event1)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertTrue(is_updated)
    self.assertEqual(1, len(attempts))
    self.assertEqual(common.CommandState.CANCELED,
                     command.key.get(use_cache=False).state)

  def testCommandUpdateCommandAttempt_updateFinalState(self):
    """UpdateCommandAttempt() should not update attempts in a final state."""
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    attempt_id = "attempt_id"
    command_attempt = datastore_entities.CommandAttempt(
        key=ndb.Key(
            datastore_entities.Request, request_id,
            datastore_entities.Command, command_id,
            datastore_entities.CommandAttempt, attempt_id,
            namespace=common.NAMESPACE),
        task_id="task_id",
        attempt_id=attempt_id,
        command_id=command_id,
        state=common.CommandState.COMPLETED)
    command_attempt.put()

    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(1, len(attempts))
    self.assertEqual(common.CommandState.COMPLETED, attempts[0].state)

    event1 = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, attempt_id,
        common.InvocationEventType.TEST_RUN_IN_PROGRESS)
    is_updated = command_manager.UpdateCommandAttempt(event1)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertFalse(is_updated)
    self.assertEqual(1, len(attempts))
    self.assertEqual(common.CommandState.COMPLETED, attempts[0].state)

  def testCommandUpdateCommandAttempt_ignoreOldEvent(self):
    """Tests UpdateCommandAttempt() ignore old events."""
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    attempt_id = "attempt_id"
    command_event_test_util.CreateCommandAttempt(
        command, attempt_id, common.CommandState.RUNNING)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(1, len(attempts))
    self.assertEqual(common.CommandState.UNKNOWN, command.state)
    event1 = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, attempt_id,
        common.InvocationEventType.TEST_RUN_IN_PROGRESS,
        time=TIMESTAMP)
    is_updated = command_manager.UpdateCommandAttempt(event1)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertTrue(is_updated)
    self.assertEqual(1, len(attempts))
    self.assertEqual("task_id", attempts[0].task_id)
    self.assertEqual("attempt_id", attempts[0].attempt_id)
    self.assertEqual(common.CommandState.RUNNING, attempts[0].state)
    self.assertEqual(TIMESTAMP, attempts[0].last_event_time)

    # An old event for a non-final state is ignored.
    event2 = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, attempt_id,
        common.InvocationEventType.TEST_RUN_IN_PROGRESS,
        time=TIMESTAMP - TIMEDELTA)
    is_updated = command_manager.UpdateCommandAttempt(event2)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertFalse(is_updated)
    self.assertEqual(common.CommandState.RUNNING, attempts[0].state)
    self.assertEqual(TIMESTAMP, attempts[0].last_event_time)

    # An old event for a final state is processed. Last event time should not
    # change.
    event3 = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, attempt_id,
        common.InvocationEventType.INVOCATION_COMPLETED,
        time=TIMESTAMP - TIMEDELTA)
    is_updated = command_manager.UpdateCommandAttempt(event3)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertTrue(is_updated)
    self.assertEqual(common.CommandState.COMPLETED, attempts[0].state)
    self.assertEqual(TIMESTAMP, attempts[0].last_event_time)

  def testGetCommand(self):
    """Tests getting an existing command."""
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual("command_line1", command.command_line)
    self.assertEqual("cluster", command.cluster)

  def testGetCommand_nonExistent(self):
    """Tests getting a non existing command."""
    command = command_manager.GetCommand("1001", "invalid")
    self.assertIsNone(command)

  def _CreateCommands(self):
    self._CreateCommand("1001", command_line="command_line1")
    self._CreateCommand("1002", command_line="command_line2")
    self._CreateCommand("1003", command_line="command_line3")
    self._CreateCommand("1004", command_line="command_line4")

  def testGetCommands_byExistingRequestId(self):
    """Tests getting all commands for given request id."""
    self._CreateCommands()
    commands = command_manager.GetCommands(request_id="1001")
    self.assertEqual(1, len(commands))
    self.assertEqual("command_line1", commands[0].command_line)

  def testGetCommands_byNonExistingRequestId(self):
    """Tests getting all commands for a non existent request ID."""
    self._CreateCommands()
    commands = command_manager.GetCommands(request_id="2001")
    self.assertEqual(0, len(commands))

  def testGetCommands_byExistingState(self):
    """Tests getting all commands for given state."""
    self._CreateCommands()
    command = command_manager.GetCommands(request_id="1001")[0]
    command.state = common.CommandState.RUNNING
    command.put()

    commands = command_manager.GetCommands(
        request_id="1001",
        state=common.CommandState.RUNNING)
    self.assertEqual(1, len(commands))
    self.assertEqual("command_line1", commands[0].command_line)

  def testGetCommands_byNonExistingState(self):
    """Tests getting all commands for given state with no commands."""
    self._CreateCommands()
    commands = command_manager.GetCommands(
        request_id="1001",
        state=common.CommandState.CANCELED)
    self.assertEqual(0, len(commands))

  def testGetCommandAttempts(self):
    """Tests getting all command attempts for given command Id."""
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(0, len(attempts))
    event1 = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "attempt_id",
        common.InvocationEventType.INVOCATION_COMPLETED)
    command_event_test_util.CreateCommandAttempt(
        command, "attempt_id", common.CommandState.RUNNING)
    command_manager.UpdateCommandAttempt(event1)
    attempts = command_manager.GetCommandAttempts(
        request_id="12345",
        command_id="12345")
    self.assertEqual(0, len(attempts))
    attempts = command_manager.GetCommandAttempts(
        request_id, command_id)
    self.assertEqual(1, len(attempts))

  def testGetCommandAttempts_multipleAttempts(self):
    """Tests getting all command attempts for given command Id."""
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    attempt_count = 10
    for i in range(attempt_count):
      command_event_test_util.CreateCommandAttempt(
          command, "attempt_" + str(i), common.CommandState.RUNNING)
      event = command_event_test_util.CreateTestCommandEvent(
          request_id, command_id, "attempt_%d" % i,
          common.InvocationEventType.INVOCATION_COMPLETED)
      command_manager.UpdateCommandAttempt(event)

    attempts = command_manager.GetCommandAttempts(request_id, command_id)

    self.assertEqual(attempt_count, len(attempts))
    prev = None
    for i in range(attempt_count):
      if prev:
        self.assertLessEqual(prev.create_time, attempts[i].create_time)
      prev = attempts[i]

  def testGetCommandAttempts_byState(self):
    """Tests getting all command attempts for given state."""
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "attempt_id",
        common.InvocationEventType.INVOCATION_COMPLETED)
    command_event_test_util.CreateCommandAttempt(
        command, "attempt_id", common.CommandState.RUNNING)
    command_manager.UpdateCommandAttempt(event)
    attempts = command_manager.GetCommandAttempts(
        request_id, command_id,
        state=common.CommandState.RUNNING)
    self.assertEqual(0, len(attempts))
    attempts = command_manager.GetCommandAttempts(
        request_id, command_id,
        state=common.CommandState.COMPLETED)
    self.assertEqual(1, len(attempts))

  def testGetLastCommandActiveTime_noAttempts(self):
    """Tests getting the last active time for a command with no attempts."""
    datastore_entities.Command.update_time._auto_now = False
    command_update_time = datetime.datetime(2018, 1, 1)
    command = self._CreateCommand()
    command.update_time = command_update_time
    last_active_time = command_manager.GetLastCommandActiveTime(command)
    self.assertEqual(command_update_time, last_active_time)

  def testGetLastCommandActiveTime_withRecentAttempts(self):
    """Tests getting the last active time for a command with recent attempts."""
    datastore_entities.Command.update_time._auto_now = False
    command_update_time = datetime.datetime(2018, 1, 1)
    event_time = datetime.datetime(2018, 1, 2)
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    command.update_time = command_update_time
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "attempt_id",
        common.InvocationEventType.INVOCATION_STARTED,
        time=event_time)
    command_event_test_util.CreateCommandAttempt(
        command, "attempt_id", common.CommandState.QUEUED)
    command_manager.UpdateCommandAttempt(event)
    last_active_time = command_manager.GetLastCommandActiveTime(command)
    self.assertEqual(event_time, last_active_time)

  def testGetLastCommandActiveTime_withRecentAndNoneLastEventTimeAttempts(self):
    """Tests getting the last active time for a command with recent attempts."""
    datastore_entities.Command.update_time._auto_now = False
    command_update_time = datetime.datetime(2018, 1, 1)
    event_time = datetime.datetime(2018, 1, 2)
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    command.update_time = command_update_time
    event = command_event_test_util.CreateTestCommandEvent(
        request_id,
        command_id,
        "attempt_id_0",
        common.InvocationEventType.INVOCATION_STARTED,
        time=event_time)
    command_event_test_util.CreateCommandAttempt(
        command, "attempt_id_0", common.CommandState.QUEUED)
    command_manager.UpdateCommandAttempt(event)

    attempts = command_manager._GetCommandAttemptsFromCommandKey(command.key)
    self.assertEqual(1, len(attempts))

    # Create attempt without last_event_time.
    none_last_event_time_attempt_key = ndb.Key(
        datastore_entities.Request, request_id,
        datastore_entities.Command, command_id,
        datastore_entities.CommandAttempt, "attempt_id_1",
        namespace=common.NAMESPACE)
    none_last_event_time_attempt_entity = datastore_entities.CommandAttempt(
        key=none_last_event_time_attempt_key,
        attempt_id="attempt_id_1",
        state=common.CommandState.UNKNOWN,
        command_id=command_id)
    none_last_event_time_attempt_entity.put()

    attempts = command_manager._GetCommandAttemptsFromCommandKey(command.key)
    self.assertEqual(2, len(attempts))

    last_active_time = command_manager.GetLastCommandActiveTime(command)
    self.assertEqual(event_time, last_active_time)

  def testGetLastCommandActiveTime_withOldAttempts(self):
    """Tests getting the last active time for a command with old attempts."""
    datastore_entities.Command.update_time._auto_now = False
    command_update_time = datetime.datetime(2018, 1, 2)
    event_time = datetime.datetime(2018, 1, 1)
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    command.update_time = command_update_time
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "attempt_id",
        common.InvocationEventType.INVOCATION_STARTED,
        time=event_time)
    command_manager.UpdateCommandAttempt(event)
    last_active_time = command_manager.GetLastCommandActiveTime(command)
    self.assertEqual(command_update_time, last_active_time)

  @mock.patch.object(request_manager, "CancelRequest")
  def testCancelCommands(self, cancel_request):
    """Tests cancelling all commands for a request ID."""
    command = self._CreateCommand(run_count=2)
    self.assertNotEqual(common.CommandState.CANCELED, command.state)
    command_manager.CancelCommands(request_id=REQUEST_ID)
    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 0)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.CANCELED, command.state)
    cancel_request.assert_called_once_with("1", common.CancelReason.UNKNOWN)

  @mock.patch.object(common, "Now")
  def testTouch(self, mock_now):
    """Tests that touching a command renews update_time of a command."""
    mock_now.return_value = TIMESTAMP
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    res = command_manager.Touch(request_id, command_id)
    mock_now.assert_called_once_with()
    self.assertEqual(command.key, res.key)

  def testDeleteTasks(self):
    command = self._CreateCommand(run_count=2)
    command_manager.ScheduleTasks([command])
    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 2)

    command_manager.DeleteTasks(command)
    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 0)

  def testDeleteTask(self):
    command = self._CreateCommand(run_count=2)
    command_manager.ScheduleTasks([command])
    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 2)

    command_manager.DeleteTask("1-1-0")
    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].task_id, "1-1-1")

  def testAddToSyncCommandAttemptQueue(self):
    command = self._CreateCommand()
    _, request_id, _, command_id = command.key.flat()
    attempt = command_event_test_util.CreateCommandAttempt(
        command, "attempt0", common.CommandState.UNKNOWN)
    command_manager.AddToSyncCommandAttemptQueue(attempt)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    self.assertEqual(1, len(tasks))
    expected_payload = {
        command_manager.REQUEST_ID_KEY: request_id,
        command_manager.COMMAND_ID_KEY: command_id,
        command_manager.ATTEMPT_ID_KEY: "attempt0"
    }
    payload = json.loads(tasks[0].payload)
    self.assertEqual(expected_payload, payload)

  @mock.patch.object(metric, "RecordCommandAttemptMetric")
  @mock.patch.object(env_config.CONFIG, "plugin")
  def testProcessCommandEvent_notUpdated(
      self, plugin, attempt_metric):
    """Test ProcessCommandEvent with no update."""
    command = self._CreateCommand()
    command_manager.ScheduleTasks([command])

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    command_task_store.LeaseTask(tasks[0].task_id)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.QUEUED, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.QUEUED, request.state)

    _, request_id, _, command_id = command.key.flat()
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "attempt0",
        common.InvocationEventType.INVOCATION_STARTED, time=TIMESTAMP)
    command_manager.ProcessCommandEvent(event)

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].leasable, False)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.QUEUED, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.QUEUED, request.state)
    attempt_metric.assert_not_called()
    plugin.assert_has_calls([
        mock.call.OnCreateCommands([
            plugin_base.CommandInfo(
                command_id=1,
                command_line="command_line1",
                run_count=1,
                shard_count=1,
                shard_index=0)
        ], {
            "ants_invocation_id": "i123",
            "command_ants_work_unit_id": "w123"
        }, {}),
    ])

  @mock.patch.object(metric, "RecordCommandAttemptMetric")
  @mock.patch.object(env_config.CONFIG, "plugin")
  def testProcessCommandEvent_notUpdatedButFinal(self, plugin, attempt_metric):
    command = self._CreateCommand()
    command_manager.ScheduleTasks([command])
    _, request_id, _, command_id = command.key.flat()
    # Setup to ensure we are properly in the error state
    for i in range(command_manager.MAX_ERROR_COUNT_BASE):
      tasks = command_manager.GetActiveTasks(command)
      self.assertEqual(len(tasks), 1)
      command_task_store.LeaseTask(tasks[0].task_id)
      attempt = command_event_test_util.CreateCommandAttempt(
          command, str(i), common.CommandState.RUNNING, task=tasks[0])
      event = command_event_test_util.CreateTestCommandEvent(
          request_id, command_id, str(i),
          common.InvocationEventType.INVOCATION_COMPLETED,
          error="error", task=tasks[0], time=TIMESTAMP)
      command_manager.ProcessCommandEvent(event)

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 0)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.ERROR, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.ERROR, request.state)

    attempt_metric.reset_mock()
    plugin.reset_mock()

    # Process last event again to ensure that we don't update
    command_manager.ProcessCommandEvent(event)

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 0)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.ERROR, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.ERROR, request.state)
    attempt_metric.assert_called_once_with(
        cluster_id=command.cluster,
        run_target=command.run_target,
        hostname="hostname",
        state="ERROR")
    plugin.assert_has_calls([
        mock.call.OnProcessCommandEvent(
            command,
            hamcrest.match_equality(
                hamcrest.all_of(
                    hamcrest.has_property("command_id", attempt.command_id),
                    hamcrest.has_property("attempt_id", attempt.attempt_id),
                    hamcrest.has_property("task_id", attempt.task_id),
                ))),
    ])

  @mock.patch.object(metric, "RecordCommandAttemptMetric")
  def testProcessCommandEvent_nonFinal_reschedule(self, attempt_metric):
    # Test ProcessCommandEvent for a non-final state with rescheduling
    command = self._CreateCommand()
    command_manager.ScheduleTasks([command])
    _, request_id, _, command_id = command.key.flat()

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    command_task_store.LeaseTask(tasks[0].task_id)
    command_event_test_util.CreateCommandAttempt(
        command, "attempt0", common.CommandState.UNKNOWN, task=tasks[0])
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "attempt0",
        common.InvocationEventType.INVOCATION_COMPLETED,
        error="error", task=tasks[0], time=TIMESTAMP)
    command_manager.ProcessCommandEvent(event)

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].leasable, True)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.QUEUED, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.QUEUED, request.state)
    attempt_metric.assert_called_once_with(
        cluster_id=command.cluster,
        run_target=command.run_target,
        hostname="hostname",
        state="ERROR")

  @mock.patch.object(metric, "RecordCommandAttemptMetric")
  def testProcessCommandEvent_nonFinal_delete(self, attempt_metric):
    # Test ProcessCommandEvent for a non-final state with deletion
    command = self._CreateCommand(run_count=2)
    command_manager.ScheduleTasks([command])
    _, request_id, _, command_id = command.key.flat()

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 2)
    command_task_store.LeaseTask(tasks[0].task_id)
    command_event_test_util.CreateCommandAttempt(
        command, "attempt0", common.CommandState.UNKNOWN, task=tasks[0])
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "attempt0",
        common.InvocationEventType.INVOCATION_COMPLETED,
        task=tasks[0], time=TIMESTAMP)
    command_manager.ProcessCommandEvent(event)

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].task_id, "%s-%s-1" % (request_id, command_id))
    self.assertEqual(tasks[0].leasable, True)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.QUEUED, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.QUEUED, request.state)
    attempt_metric.assert_called_once_with(
        cluster_id=command.cluster,
        run_target=command.run_target,
        hostname="hostname",
        state="COMPLETED")

  @mock.patch.object(metric, "RecordCommandAttemptMetric")
  @mock.patch.object(env_config.CONFIG, "plugin")
  def testProcessCommandEvent_final(self, plugin, attempt_metric):
    # Test ProcessCommandEvent for a final state
    command = self._CreateCommand()
    command_manager.ScheduleTasks([command])
    _, request_id, _, command_id = command.key.flat()

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    command_task_store.LeaseTask(tasks[0].task_id)
    attempt = command_event_test_util.CreateCommandAttempt(
        command, "attempt0", common.CommandState.UNKNOWN, task=tasks[0])
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "attempt0",
        common.InvocationEventType.INVOCATION_COMPLETED,
        task=tasks[0], time=TIMESTAMP)
    command_manager.ProcessCommandEvent(event)

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 0)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.COMPLETED, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.COMPLETED, request.state)
    attempt_metric.assert_called_once_with(
        cluster_id=command.cluster,
        run_target=command.run_target,
        hostname="hostname",
        state="COMPLETED")
    plugin.assert_has_calls([
        mock.call.OnCreateCommands([
            plugin_base.CommandInfo(
                command_id=1,
                command_line="command_line1",
                run_count=1,
                shard_count=1,
                shard_index=0)
        ], {
            "ants_invocation_id": "i123",
            "command_ants_work_unit_id": "w123"
        }, {}),
        mock.call.OnProcessCommandEvent(
            command,
            hamcrest.match_equality(
                hamcrest.all_of(
                    hamcrest.has_property("command_id", attempt.command_id),
                    hamcrest.has_property("attempt_id", attempt.attempt_id),
                    hamcrest.has_property("task_id", attempt.task_id),
                ))),
    ])

  def testNotifyAttemptState(self):
    env_config.CONFIG.object_event_filter = [
        common.ObjectEventType.REQUEST_STATE_CHANGED,
        common.ObjectEventType.COMMAND_ATTEMPT_STATE_CHANGED]
    command = self._CreateCommand()
    attempt = command_event_test_util.CreateCommandAttempt(
        command, "attempt0", common.CommandState.COMPLETED)
    command_manager._NotifyAttemptState(attempt,
                                        common.CommandState.RUNNING,
                                        datetime.datetime(1989, 5, 7))
    tasks = self.taskqueue_stub.get_filtered_tasks()
    self.assertEqual(len(tasks), 1)
    payload = zlib.decompress(tasks[0].payload)
    message = protojson.decode_message(api_messages.CommandAttemptEventMessage,
                                       payload)
    self.assertEqual(common.ObjectEventType.COMMAND_ATTEMPT_STATE_CHANGED,
                     message.type)
    self.assertEqual(datastore_entities.ToMessage(attempt), message.attempt)
    self.assertEqual(common.CommandState.RUNNING, message.old_state)
    self.assertEqual(common.CommandState.COMPLETED, message.new_state)
    self.assertEqual(datetime.datetime(1989, 5, 7), message.event_time)

  def testNotifyAttemptState_disabled(self):
    env_config.CONFIG.object_event_filter = [
        common.ObjectEventType.REQUEST_STATE_CHANGED]
    command = self._CreateCommand()
    attempt = command_event_test_util.CreateCommandAttempt(
        command, "attempt0", common.CommandState.COMPLETED)
    command_manager._NotifyAttemptState(attempt,
                                        common.CommandState.RUNNING,
                                        datetime.datetime(1989, 5, 7))
    tasks = self.taskqueue_stub.get_filtered_tasks()
    self.assertEqual(len(tasks), 0)


class CommandSummaryTest(unittest.TestCase):

  def setUp(self):
    super(CommandSummaryTest, self).setUp()
    self.summary = command_manager.CommandSummary(3)

  def testAddCommandTask_queued(self):
    command_attempt = datastore_entities.CommandAttempt(
        state=common.CommandState.QUEUED,
        run_index=1)
    self.summary.AddCommandTask(command_attempt)
    self.assertEqual(self.summary.total_count, 1)
    self.assertEqual(self.summary.queued_count, 1)
    self.assertEqual(self.summary.runs[1].attempt_count, 1)
    self.assertEqual(self.summary.runs[1].queued_count, 1)

  def testAddCommandTask_running(self):
    command_attempt = datastore_entities.CommandAttempt(
        state=common.CommandState.RUNNING,
        run_index=1)
    self.summary.AddCommandTask(command_attempt)
    self.assertEqual(self.summary.total_count, 1)
    self.assertEqual(self.summary.running_count, 1)
    self.assertEqual(self.summary.runs[1].attempt_count, 1)
    self.assertEqual(self.summary.runs[1].running_count, 1)

  def testAddCommandTask_canceled(self):
    command_attempt = datastore_entities.CommandAttempt(
        state=common.CommandState.CANCELED,
        run_index=1)
    self.summary.AddCommandTask(command_attempt)
    self.assertEqual(self.summary.total_count, 1)
    self.assertEqual(self.summary.canceled_count, 1)
    self.assertEqual(self.summary.runs[1].attempt_count, 1)
    self.assertEqual(self.summary.runs[1].canceled_count, 1)

  def testAddCommandTask_completed(self):
    command_attempt = datastore_entities.CommandAttempt(
        state=common.CommandState.COMPLETED,
        run_index=1)
    self.summary.AddCommandTask(command_attempt)
    self.assertEqual(self.summary.total_count, 1)
    self.assertEqual(self.summary.completed_count, 1)
    self.assertEqual(self.summary.completed_fail_count, 0)
    self.assertEqual(self.summary.runs[1].attempt_count, 1)
    self.assertEqual(self.summary.runs[1].completed_count, 1)
    self.assertEqual(self.summary.runs[1].completed_fail_count, 0)

  def testAddCommandTask_completed_with_test_failure(self):
    command_attempt = datastore_entities.CommandAttempt(
        state=common.CommandState.COMPLETED,
        failed_test_count=1,
        run_index=1)
    self.summary.AddCommandTask(command_attempt)
    self.assertEqual(self.summary.total_count, 1)
    self.assertEqual(self.summary.completed_count, 1)
    self.assertEqual(self.summary.completed_fail_count, 1)
    self.assertEqual(self.summary.runs[1].attempt_count, 1)
    self.assertEqual(self.summary.runs[1].completed_count, 1)
    self.assertEqual(self.summary.runs[1].completed_fail_count, 1)

  def testAddCommandTask_completed_with_test_run_failure(self):
    command_attempt = datastore_entities.CommandAttempt(
        state=common.CommandState.COMPLETED,
        failed_test_run_count=1,
        run_index=1)
    self.summary.AddCommandTask(command_attempt)
    self.assertEqual(self.summary.total_count, 1)
    self.assertEqual(self.summary.completed_count, 1)
    self.assertEqual(self.summary.completed_fail_count, 1)
    self.assertEqual(self.summary.runs[1].attempt_count, 1)
    self.assertEqual(self.summary.runs[1].completed_count, 1)
    self.assertEqual(self.summary.runs[1].completed_fail_count, 1)

  def testAddCommandTask_error(self):
    command_attempt = datastore_entities.CommandAttempt(
        state=common.CommandState.ERROR,
        run_index=1)
    self.summary.AddCommandTask(command_attempt)
    self.assertEqual(self.summary.total_count, 1)
    self.assertEqual(self.summary.error_count, 1)
    self.assertEqual(self.summary.runs[1].attempt_count, 1)
    self.assertEqual(self.summary.runs[1].error_count, 1)

  def testAddCommandTask_fatal(self):
    command_attempt = datastore_entities.CommandAttempt(
        state=common.CommandState.FATAL,
        run_index=1)
    self.summary.AddCommandTask(command_attempt)
    self.assertEqual(self.summary.total_count, 1)
    self.assertEqual(self.summary.fatal_count, 1)
    self.assertEqual(self.summary.runs[1].attempt_count, 1)
    self.assertEqual(self.summary.runs[1].fatal_count, 1)

  def testAddCommandTask_mixed_status(self):
    command_attempts = [
        datastore_entities.CommandAttempt(
            state=common.CommandState.QUEUED, run_index=0),
        datastore_entities.CommandAttempt(
            state=common.CommandState.RUNNING, run_index=1),
        datastore_entities.CommandAttempt(
            state=common.CommandState.CANCELED, run_index=2),
        datastore_entities.CommandAttempt(
            state=common.CommandState.COMPLETED, run_index=0),
        datastore_entities.CommandAttempt(
            state=common.CommandState.COMPLETED,
            failed_test_count=1,
            run_index=1),
        datastore_entities.CommandAttempt(
            state=common.CommandState.ERROR, run_index=2),
        datastore_entities.CommandAttempt(
            state=common.CommandState.FATAL, run_index=0),
    ]
    for attempt in command_attempts:
      self.summary.AddCommandTask(attempt)

    self.assertEqual(self.summary.total_count, 7)
    self.assertEqual(self.summary.queued_count, 1)
    self.assertEqual(self.summary.running_count, 1)
    self.assertEqual(self.summary.canceled_count, 1)
    self.assertEqual(self.summary.completed_count, 2)
    self.assertEqual(self.summary.completed_fail_count, 1)
    self.assertEqual(self.summary.error_count, 1)
    self.assertEqual(self.summary.fatal_count, 1)
    self.assertEqual(self.summary.runs[0].attempt_count, 3)
    self.assertEqual(self.summary.runs[0].queued_count, 1)
    self.assertEqual(self.summary.runs[0].running_count, 0)
    self.assertEqual(self.summary.runs[0].canceled_count, 0)
    self.assertEqual(self.summary.runs[0].completed_count, 1)
    self.assertEqual(self.summary.runs[0].completed_fail_count, 0)
    self.assertEqual(self.summary.runs[0].error_count, 0)
    self.assertEqual(self.summary.runs[0].fatal_count, 1)
    self.assertEqual(self.summary.runs[1].attempt_count, 2)
    self.assertEqual(self.summary.runs[1].queued_count, 0)
    self.assertEqual(self.summary.runs[1].running_count, 1)
    self.assertEqual(self.summary.runs[1].canceled_count, 0)
    self.assertEqual(self.summary.runs[1].completed_count, 1)
    self.assertEqual(self.summary.runs[1].completed_fail_count, 1)
    self.assertEqual(self.summary.runs[1].error_count, 0)
    self.assertEqual(self.summary.runs[1].fatal_count, 0)
    self.assertEqual(self.summary.runs[2].attempt_count, 2)
    self.assertEqual(self.summary.runs[2].queued_count, 0)
    self.assertEqual(self.summary.runs[2].running_count, 0)
    self.assertEqual(self.summary.runs[2].canceled_count, 1)
    self.assertEqual(self.summary.runs[2].completed_count, 0)
    self.assertEqual(self.summary.runs[2].completed_fail_count, 0)
    self.assertEqual(self.summary.runs[2].error_count, 1)
    self.assertEqual(self.summary.runs[2].fatal_count, 0)

  def testAddCommandTask_timestamps(self):
    self.assertEqual(self.summary.start_time, None)
    self.assertEqual(self.summary.start_time, None)

    command_attempt = datastore_entities.CommandAttempt(
        state=common.CommandState.COMPLETED,
        start_time=TIMESTAMP,
        end_time=TIMESTAMP + TIMEDELTA)
    self.summary.AddCommandTask(command_attempt)
    self.assertEqual(self.summary.start_time, TIMESTAMP)
    self.assertEqual(self.summary.end_time, TIMESTAMP + TIMEDELTA)

    command_attempt = datastore_entities.CommandAttempt(
        state=common.CommandState.COMPLETED,
        start_time=TIMESTAMP - TIMEDELTA,
        end_time=TIMESTAMP + 2 * TIMEDELTA)
    self.summary.AddCommandTask(command_attempt)
    self.assertEqual(self.summary.start_time, TIMESTAMP - TIMEDELTA)
    self.assertEqual(self.summary.end_time, TIMESTAMP + 2 * TIMEDELTA)

  def testScheduleTask_no_retry_on_failure(self):
    # Summary has 4 slots, with the 4th being the empty spot with 3 attempts
    self.summary = command_manager.CommandSummary(run_count=4)
    self.summary.total_count = 6
    self.summary.queued_count = 1
    self.summary.running_count = 1
    self.summary.completed_count = 1
    self.summary.canceled_count = 1
    self.summary.error_count = 1
    self.summary.runs[0].attempt_count = 1
    self.summary.runs[0].queued_count = 1
    self.summary.runs[1].attempt_count = 1
    self.summary.runs[1].running_count = 1
    self.summary.runs[2].attempt_count = 1
    self.summary.runs[2].completed_count = 1
    self.summary.runs[3].attempt_count = 2
    self.summary.runs[3].canceled_count = 1
    self.summary.runs[3].error_count = 1

    run_index, attempt_index = self.summary.ScheduleTask()

    self.assertEqual(run_index, 3)
    self.assertEqual(attempt_index, 2)
    self.assertEqual(self.summary.total_count, 7)
    self.assertEqual(self.summary.queued_count, 2)
    self.assertEqual(self.summary.runs[3].attempt_count, 3)
    self.assertEqual(self.summary.runs[3].queued_count, 1)

  def testScheduleTask_retry_on_failure(self):
    self.summary = command_manager.CommandSummary(run_count=2)
    self.summary.total_count = 6
    self.summary.completed_count = 3
    self.summary.completed_fail_count = 3
    self.summary.canceled_count = 3
    self.summary.runs[0].attempt_count = 3
    self.summary.runs[0].completed_count = 3
    self.summary.runs[0].completed_fail_count = 3
    self.summary.runs[1].attempt_count = 3
    self.summary.runs[1].canceled_count = 3

    run_index, attempt_index = self.summary.ScheduleTask(
        max_retry_on_test_failures=3)

    self.assertEqual(run_index, 0)
    self.assertEqual(attempt_index, 3)
    self.assertEqual(self.summary.total_count, 7)
    self.assertEqual(self.summary.queued_count, 1)
    self.assertEqual(self.summary.runs[0].attempt_count, 4)
    self.assertEqual(self.summary.runs[0].queued_count, 1)

  def testScheduleTask_over_retry_on_failure(self):
    self.summary = command_manager.CommandSummary(run_count=2)
    self.summary.total_count = 6
    self.summary.completed_count = 3
    self.summary.completed_fail_count = 3
    self.summary.canceled_count = 3
    self.summary.runs[0].attempt_count = 3
    self.summary.runs[0].completed_count = 3
    self.summary.runs[0].completed_fail_count = 3
    self.summary.runs[1].attempt_count = 3
    self.summary.runs[1].canceled_count = 3

    run_index, attempt_index = self.summary.ScheduleTask(
        max_retry_on_test_failures=2)

    self.assertEqual(run_index, 1)
    self.assertEqual(attempt_index, 3)
    self.assertEqual(self.summary.total_count, 7)
    self.assertEqual(self.summary.queued_count, 1)
    self.assertEqual(self.summary.runs[1].attempt_count, 4)
    self.assertEqual(self.summary.runs[1].queued_count, 1)

  def testScheduleTask_overflow(self):
    self.summary = command_manager.CommandSummary(run_count=2)
    self.summary.total_count = 2
    self.summary.completed_count = 2
    self.summary.runs[0].attempt_count = 1
    self.summary.runs[0].completed_count = 1
    self.summary.runs[1].attempt_count = 1
    self.summary.runs[1].completed_count = 1

    run_index, attempt_index = self.summary.ScheduleTask()

    self.assertEqual(run_index, 0)
    self.assertEqual(attempt_index, 1)
    self.assertEqual(self.summary.total_count, 3)
    self.assertEqual(self.summary.queued_count, 1)
    self.assertEqual(self.summary.runs[0].attempt_count, 2)
    self.assertEqual(self.summary.runs[0].queued_count, 1)

  def testGetState_completed(self):
    self.summary.total_count = 3
    self.summary.completed_count = 3
    state = self.summary.GetState(common.CommandState.UNKNOWN)
    self.assertEqual(state, common.CommandState.COMPLETED)

  def testGetState_completed_retry_on_test_failure(self):
    self.summary.total_count = 3
    self.summary.completed_count = 3
    self.summary.completed_fail_count = 3
    state = self.summary.GetState(
        common.CommandState.UNKNOWN, max_retry_on_test_failures=2)
    self.assertEqual(state, common.CommandState.COMPLETED)

  def testGetState_not_completed_retry_on_test_failure(self):
    self.summary.total_count = 3
    self.summary.completed_count = 3
    self.summary.completed_fail_count = 3
    state = self.summary.GetState(
        common.CommandState.UNKNOWN, max_retry_on_test_failures=3)
    self.assertEqual(state, common.CommandState.QUEUED)

  def testGetState_fatal(self):
    self.summary.total_count = 1
    self.summary.fatal_count = 1
    state = self.summary.GetState(common.CommandState.UNKNOWN)
    self.assertEqual(state, common.CommandState.FATAL)

  def testGetState_canceled(self):
    self.summary.total_count = 1
    self.summary.canceled_count = 1
    state = self.summary.GetState(
        common.CommandState.UNKNOWN, max_canceled_count=1)
    self.assertEqual(state, common.CommandState.CANCELED)

  def testGetState_not_canceled(self):
    self.summary.total_count = 1
    self.summary.canceled_count = 1
    state = self.summary.GetState(
        common.CommandState.UNKNOWN, max_canceled_count=2)
    self.assertEqual(state, common.CommandState.QUEUED)

  def testGetState_error(self):
    self.summary.total_count = 1
    self.summary.error_count = 1
    state = self.summary.GetState(
        common.CommandState.UNKNOWN, max_error_count=1)
    self.assertEqual(state, common.CommandState.ERROR)

  def testGetState_not_error(self):
    self.summary.total_count = 1
    self.summary.error_count = 1
    state = self.summary.GetState(
        common.CommandState.UNKNOWN, max_error_count=2)
    self.assertEqual(state, common.CommandState.QUEUED)

  def testGetState_override(self):
    self.summary.total_count = 1
    self.summary.running_count = 1
    state = self.summary.GetState(common.CommandState.COMPLETED)
    self.assertEqual(state, common.CommandState.COMPLETED)

  def testGetState_running(self):
    self.summary.total_count = 1
    self.summary.running_count = 1
    state = self.summary.GetState(common.CommandState.UNKNOWN)
    self.assertEqual(state, common.CommandState.RUNNING)

  def testGetState_queued(self):
    self.summary.total_count = 0
    self.summary.running_count = 0
    state = self.summary.GetState(common.CommandState.UNKNOWN)
    self.assertEqual(state, common.CommandState.QUEUED)

  def testRemainingRunCount_no_retry_on_test_failure(self):
    # Command has run_count = 3
    self.summary.total_count = 3
    self.summary.completed_count = 3
    self.summary.completed_fail_count = 3
    run_count = self.summary.RemainingRunCount()
    self.assertEqual(run_count, 0)

  def testRemainingRunCount_retry_on_test_failure(self):
    # Command has run_count = 3
    self.summary.total_count = 3
    self.summary.completed_count = 3
    self.summary.completed_fail_count = 3
    run_count = self.summary.RemainingRunCount(max_retry_on_test_failures=2)
    self.assertEqual(run_count, 0)

  def testRemainingRunCount_more_retry_on_test_failure(self):
    # Command has run_count = 3
    self.summary.total_count = 3
    self.summary.completed_count = 3
    self.summary.completed_fail_count = 3
    run_count = self.summary.RemainingRunCount(max_retry_on_test_failures=4)
    self.assertEqual(run_count, 3)


if __name__ == "__main__":
  logging.getLogger().setLevel(logging.DEBUG)
  unittest.main()
