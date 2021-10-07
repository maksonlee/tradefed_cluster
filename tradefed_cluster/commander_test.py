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

"""Tests for the commander module."""

import datetime
import unittest

import hamcrest
import mock
import webtest

from tradefed_cluster import command_event_test_util
from tradefed_cluster import command_manager
from tradefed_cluster import command_monitor
from tradefed_cluster import command_task_store
from tradefed_cluster import commander
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import env_config
from tradefed_cluster import metric
from tradefed_cluster import request_manager
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.plugins import base as plugin_base
from tradefed_cluster.util import command_util

REQUEST_ID = "1"
COMMAND_ID = 5629499534213120
TIMESTAMP = datetime.datetime(2017, 3, 8)


class CommanderTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super(CommanderTest, self).setUp()
    datastore_test_util.CreateRequest(
        user="user1",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id=REQUEST_ID)

  @mock.patch.object(command_monitor, "Monitor")
  @mock.patch.object(command_manager, "ScheduleTasks")
  @mock.patch.object(env_config.CONFIG, "plugin")
  def testProcessRequest(self, plugin, schedule_tasks, monitor):
    request_id1 = "1001"
    request_id2 = "1002"
    datastore_test_util.CreateRequest(
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line=(
                    "command_line0 --run-target run_target --cluster cluster"),
                cluster="cluster",
                run_target="run_target")
        ],
        request_id=request_id1,
        plugin_data={"ants_invocation_id": "i123",
                     "ants_work_unit_id": "w123"})
    datastore_test_util.CreateRequest(
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line=(
                    "command_line0 --run-target run_target --cluster cluster"),
                cluster="cluster",
                run_target="run_target")
        ],
        request_id=request_id2,
        priority=100,
        queue_timeout_seconds=86400,
        affinity_tag="affinity_tag")

    commander._ProcessRequest(request_id1)
    commander._ProcessRequest(request_id2)
    self.assertEqual(2, schedule_tasks.call_count)
    self.assertEqual(2, monitor.call_count)

    commands_0 = request_manager.GetCommands(request_id1)
    self.assertEqual(1, len(commands_0))
    command = commands_0[0]
    self.assertEqual("command_line0", command.command_line)
    self.assertEqual("run_target", command.run_target)
    self.assertEqual(1, command.run_count)
    self.assertEqual("cluster", command.cluster)
    self.assertIsNone(command.affinity_tag)

    commands_1 = request_manager.GetCommands(request_id2)
    self.assertEqual(1, len(commands_1))
    command = commands_1[0]
    self.assertEqual("command_line0", command.command_line)
    self.assertEqual("run_target", command.run_target)
    self.assertEqual(1, command.run_count)
    self.assertEqual("cluster", command.cluster)
    self.assertEqual(100, command.priority)
    self.assertEqual(86400, command.queue_timeout_seconds)
    self.assertEqual("affinity_tag", command.affinity_tag)
    monitor.assert_has_calls([mock.call(commands_0), mock.call(commands_1)])
    plugin.assert_has_calls([
        mock.call.OnCreateCommands([
            plugin_base.CommandInfo(
                command_id=5629499534213120,
                command_line="command_line0",
                run_count=1,
                shard_count=1,
                shard_index=0)
        ], {
            "ants_invocation_id": "i123",
            "ants_work_unit_id": "w123"
        }, {}),
        mock.call.OnCreateCommands([
            plugin_base.CommandInfo(
                command_id=5066549580791808,
                command_line="command_line0",
                run_count=1,
                shard_count=1,
                shard_index=0)
        ], None, {}),
    ])

  @mock.patch.object(command_manager, "ScheduleTasks")
  @mock.patch.object(request_manager, "CancelRequest")
  @mock.patch.object(env_config.CONFIG, "plugin")
  def testProcessRequest_invalidRequest(self,
                                        plugin,
                                        cancel_request,
                                        schedule_tasks):
    request_id1 = "1001"
    datastore_test_util.CreateRequest(
        request_id=request_id1,
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line0",
                cluster="cluster",
                run_target=None)
        ])
    commander._ProcessRequest(request_id1)

    self.assertFalse(schedule_tasks.called)
    commands = request_manager.GetCommands(request_id1)
    self.assertEqual(0, len(commands))
    cancel_request.assert_called_once_with(
        request_id1,
        common.CancelReason.INVALID_REQUEST)
    plugin.assert_has_calls([])

  @mock.patch.object(command_manager, "ScheduleTasks")
  @mock.patch.object(env_config.CONFIG, "plugin")
  def testProcessRequests_shardedRequests(self, plugin, schedule_tasks):
    """Tests processing of sharded requests."""
    request_id = "1001"
    datastore_test_util.CreateRequest(
        request_id=request_id,
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line0",
                cluster="cluster",
                run_target="bullhead",
                shard_count=3)
        ])

    commander._ProcessRequest(request_id)

    commands = request_manager.GetCommands(request_id)
    self.assertEqual(3, len(commands))
    shards = []
    for command in commands:
      command_line = command_util.CommandLine(command.command_line)
      shards.append(command_line.GetOption("--shard-index"))
      command_line.RemoveOptions(["--shard-index"])
      self.assertEqual("command_line0 --shard-count 3",
                       command_line.ToTFString())
      self.assertEqual("bullhead", command.run_target)
      self.assertEqual(1, command.run_count)
      self.assertEqual("cluster", command.cluster)
    self.assertCountEqual(["0", "1", "2"], shards)
    plugin.assert_has_calls([])

  @mock.patch.object(command_manager, "ScheduleTasks")
  @mock.patch.object(env_config.CONFIG, "plugin")
  def testProcessRequests_RequestlocalSharding(self, plugin, schedule_tasks):
    """Tests processing of sharded requests with local sharding."""
    request_id = "1001"
    datastore_test_util.CreateRequest(
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line0 --shard-count 3",
                cluster="cluster",
                run_target="bullhead")
        ],
        request_id=request_id)

    commander._ProcessRequest(request_id)

    commands = request_manager.GetCommands(request_id)
    self.assertEqual(1, len(commands))
    for command in commands:
      command_line = command_util.CommandLine(command.command_line)
      command_line.RemoveOptions(["--shard-index"])
      self.assertEqual("command_line0 --shard-count 3",
                       command_line.ToTFString())
      self.assertEqual("bullhead", command.run_target)
      self.assertEqual(1, command.run_count)
      self.assertEqual("cluster", command.cluster)
    plugin.assert_has_calls([])

  @mock.patch.object(command_manager, "ScheduleTasks")
  @mock.patch.object(env_config.CONFIG, "plugin")
  def testProcessRequests_shardedRequests_oneShard(self,
                                                   plugin,
                                                   schedule_tasks):
    """Tests processing of sharded requests with a single shard."""
    request_id = "1001"
    datastore_test_util.CreateRequest(
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line0",
                cluster="cluster",
                run_target="bullhead",
                shard_count=1)
        ],
        request_id=request_id)

    commander._ProcessRequest(request_id)

    commands = request_manager.GetCommands(request_id)
    self.assertEqual(1, len(commands))
    command = commands[0]
    command_line = command_util.CommandLine(command.command_line)
    command_line.RemoveOptions(["--shard-index"])
    # If only one shard is specified, the --shard-count option is removed.
    self.assertEqual("command_line0", command_line.ToTFString())
    self.assertEqual("bullhead", command.run_target)
    self.assertEqual(1, command.run_count)
    self.assertEqual("cluster", command.cluster)
    plugin.assert_has_calls([])

  @mock.patch.object(request_manager, "CancelRequest")
  def testProcessRequests_missingRunTarget(self, cancel_request):
    request_id = "1001"
    datastore_test_util.CreateRequest(
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line0 --shard-count 1",
                cluster="cluster",
                run_target=None)
        ],
        request_id=request_id)

    commander._ProcessRequest(request_id)
    cancel_request.assert_called_once_with(
        request_id, common.CancelReason.INVALID_REQUEST)

  @mock.patch.object(command_manager, "ScheduleTasks")
  @mock.patch.object(env_config.CONFIG, "plugin")
  def testProcessRequest_escapeInCommandLine(self, plugin, schedule_tasks):
    request_id1 = "1001"
    datastore_test_util.CreateRequest(
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line=(
                    "command_line0"' --arg \'option=\'"\'"\'value\'"\'"\'\''),
                cluster="cluster",
                run_target="run_target")
        ],
        request_id=request_id1)

    commander._ProcessRequest(request_id1)
    self.assertEqual(1, schedule_tasks.call_count)

    commands = request_manager.GetCommands(request_id1)
    self.assertEqual(1, len(commands))
    command = commands[0]
    self.assertEqual(
        "command_line0 --arg option='value'",
        command.command_line)
    self.assertEqual("run_target", command.run_target)
    self.assertEqual(1, command.run_count)
    self.assertEqual("cluster", command.cluster)
    plugin.assert_has_calls([])

  @mock.patch.object(command_monitor, "Monitor")
  @mock.patch.object(command_manager, "ScheduleTasks")
  @mock.patch.object(env_config.CONFIG, "plugin")
  def testProcessRequest_withMultipleCommands(
      self, plugin, schedule_tasks, monitor):
    request_id = "1001"
    command_infos = [
        datastore_entities.CommandInfo(              command_line="command_line %04d" % i,
            cluster="cluster %04d" % i,
            run_target="run_target %04d" % i,
            run_count=1,
            shard_count=1)
        for i in range(500)
    ]
    request = datastore_test_util.CreateRequest(
        request_id=request_id,
        user="user",
        command_infos=command_infos,
        max_concurrent_tasks=100,
        plugin_data={
            "FOO": "foo",
            "BAR": "'bar",
        })

    commander._ProcessRequest(request_id)

    commands = request_manager.GetCommands(request_id)
    commands.sort(key=lambda x: x.command_line)
    self.assertEqual(len(command_infos), len(commands))
    for command_info, command in zip(command_infos, commands):
      self.assertEqual(command_info.command_line, command.command_line)
      self.assertEqual(command_info.cluster, command.cluster)
      self.assertEqual(command_info.run_target, command.run_target)
      self.assertEqual(command_info.run_count, command.run_count)
      self.assertIsNone(command.shard_count)
    plugin.OnCreateCommands.assert_has_calls([
        mock.call([
            plugin_base.CommandInfo(                  command_id=int(command.key.id()),
                command_line=command.command_line,
                run_count=command.run_count,
                shard_count=1,
                shard_index=0)
            for command in commands
        ], request.plugin_data, {}),
    ])
    schedule_tasks.assert_called_once_with(
        commands[:request.max_concurrent_tasks], update_request_state=False)
    monitor.assert_called_once_with(
        commands[:request.max_concurrent_tasks])

  @mock.patch.object(command_monitor, "Monitor")
  @mock.patch.object(command_manager, "ScheduleTasks")
  @mock.patch.object(env_config.CONFIG, "plugin")
  def testProcessRequest_withTestBench(self, plugin, schedule_tasks, monitor):
    request_id = "1001"
    test_bench = datastore_test_util.CreateTestBench("cluster", "run_target")
    datastore_test_util.CreateRequest(
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line=(
                    "command_line0"),
                cluster="cluster",
                run_target="run_target",
                test_bench=test_bench)
        ],
        request_id=request_id,
        plugin_data={"ants_invocation_id": "i123",
                     "ants_work_unit_id": "w123"})
    commander._ProcessRequest(request_id)
    self.assertEqual(1, schedule_tasks.call_count)
    self.assertEqual(1, monitor.call_count)

    commands = request_manager.GetCommands(request_id)
    self.assertEqual(1, len(commands))
    command = commands[0]
    self.assertEqual("command_line0", command.command_line)
    self.assertEqual("run_target", command.run_target)
    self.assertEqual(1, command.run_count)
    self.assertEqual("cluster", command.cluster)
    self.assertEqual(test_bench, command.test_bench)

  def _CreateCommand(
      self, request_id=REQUEST_ID, run_count=1, priority=None,
      command_line="command_line1"):
    """Helper to create a command."""
    command = command_manager.CreateCommands(
        request_id=request_id,
        command_infos=[
            datastore_entities.CommandInfo(
                command_line=command_line,
                cluster="cluster",
                run_target="run_target",
                run_count=run_count,
                shard_count=1),
        ],
        priority=priority,
        shard_indexes=[0],
        request_plugin_data={
            "ants_invocation_id": "i123",
            "command_ants_work_unit_id": "w123"
        })[0]
    return command

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
    commander.ProcessCommandEvent(event)

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].leasable, False)
    self.assertEqual(tasks[0].attempt_index, 0)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.QUEUED, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.QUEUED, request.state)
    attempt_metric.assert_not_called()
    plugin.assert_has_calls([
        mock.call.OnCreateCommands([
            plugin_base.CommandInfo(
                command_id=COMMAND_ID,
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
      commander.ProcessCommandEvent(event)

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 0)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.ERROR, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.ERROR, request.state)

    attempt_metric.reset_mock()
    plugin.reset_mock()

    # Process last event again to ensure that we don't update
    commander.ProcessCommandEvent(event)

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 0)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.ERROR, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.ERROR, request.state)
    attempt_metric.assert_called_once_with(
        cluster_id=command.cluster,
        run_target=command.run_target,
        state="ERROR")
    plugin.assert_has_calls([
        mock.call.OnProcessCommandEvent(
            command,
            hamcrest.match_equality(
                hamcrest.all_of(
                    hamcrest.has_property("command_id", attempt.command_id),
                    hamcrest.has_property("attempt_id", attempt.attempt_id),
                    hamcrest.has_property("task_id", attempt.task_id),
                )),
            event_data={
                "summary": "summary",
                "total_test_count": 1000,
                "failed_test_count": 100,
                "passed_test_count": 900,
                "failed_test_run_count": 10,
                "device_lost_detected": 0,
                "error": "error"
            }),
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
    commander.ProcessCommandEvent(event)

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].leasable, True)
    self.assertEqual(tasks[0].attempt_index, 1)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.QUEUED, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.QUEUED, request.state)
    attempt_metric.assert_called_once_with(
        cluster_id=command.cluster,
        run_target=command.run_target,
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
    commander.ProcessCommandEvent(event)

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].task_id, "%s-%s-1" % (request_id, command_id))
    self.assertEqual(tasks[0].leasable, True)
    self.assertEqual(tasks[0].run_index, 1)
    self.assertEqual(tasks[0].attempt_index, 0)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.QUEUED, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.QUEUED, request.state)
    attempt_metric.assert_called_once_with(
        cluster_id=command.cluster,
        run_target=command.run_target,
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
    commander.ProcessCommandEvent(event)

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 0)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.COMPLETED, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.COMPLETED, request.state)
    attempt_metric.assert_called_once_with(
        cluster_id=command.cluster,
        run_target=command.run_target,
        state="COMPLETED")
    plugin.assert_has_calls([
        mock.call.OnCreateCommands([
            plugin_base.CommandInfo(
                command_id=COMMAND_ID,
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
                )),
            event_data={
                "total_test_count": 1000,
                "device_lost_detected": 0,
                "failed_test_run_count": 10,
                "passed_test_count": 900,
                "failed_test_count": 100,
                "summary": "summary"
            }),
    ])

  @mock.patch.object(command_monitor, "Monitor")
  @mock.patch.object(metric, "RecordCommandAttemptMetric")
  def testProcessCommandEvent_pendingCommands(
      self, attempt_metric, monitor):
    # Test ProcessCommandEvent for a non-final state with deletion
    request_id = "1001"
    command_infos = [
        datastore_entities.CommandInfo(              command_line="command_line %04d" % i,
            cluster="cluster %04d" % i,
            run_target="run_target %04d" % i,
            run_count=1,
            shard_count=1)
        for i in range(10)
    ]
    request = datastore_test_util.CreateRequest(
        request_id=request_id,
        user="user",
        command_infos=command_infos,
        max_concurrent_tasks=5,
        plugin_data={
            "FOO": "foo",
            "BAR": "'bar",
        })
    commands = command_manager.CreateCommands(
        request_id=request_id,
        command_infos=command_infos,
        priority=request.priority,
        shard_indexes=[0] * len(command_infos))
    command_manager.ScheduleTasks(commands[:5])
    _, request_id, _, command_id = commands[0].key.flat()
    pending_commands = command_manager.GetCommands(
        request_id, common.CommandState.UNKNOWN)
    self.assertEqual(5, len(pending_commands))
    queued_commands = command_manager.GetCommands(
        request_id, common.CommandState.QUEUED)
    self.assertEqual(5, len(queued_commands))

    tasks = command_manager.GetActiveTasks(commands[0])
    self.assertEqual(1, len(tasks))
    command_task_store.LeaseTask(tasks[0].task_id)
    command_event_test_util.CreateCommandAttempt(
        commands[0], "attempt0", common.CommandState.UNKNOWN, task=tasks[0])
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "attempt0",
        common.InvocationEventType.INVOCATION_COMPLETED,
        task=tasks[0], time=TIMESTAMP)

    commander.ProcessCommandEvent(event)

    tasks = command_manager.GetActiveTasks(commands[0])
    self.assertEqual(0, len(tasks))
    command = commands[0].key.get(use_cache=False)
    self.assertEqual(common.CommandState.COMPLETED, command.state)
    attempt_metric.assert_called_once_with(
        cluster_id=command.cluster,
        run_target=command.run_target,
        state="COMPLETED")
    next_command = pending_commands[0]
    monitor.assert_called_once_with([next_command])
    next_command = pending_commands[0].key.get(use_cache=False)
    self.assertEqual(common.CommandState.QUEUED, next_command.state)
    pending_commands = command_manager.GetCommands(
        request_id, common.CommandState.UNKNOWN)
    self.assertEqual(4, len(pending_commands))
    queued_commands = command_manager.GetCommands(
        request_id, common.CommandState.QUEUED)
    self.assertEqual(5, len(queued_commands))
    completed_commands = command_manager.GetCommands(
        request_id, common.CommandState.COMPLETED)
    self.assertEqual(1, len(completed_commands))

  @mock.patch.object(metric, "RecordCommandAttemptMetric")
  def testProcessCommandEvent_differentAttemptId(self, attempt_metric):
    # Test ProcessCommandEvent for an event that does not match the task attempt
    command = self._CreateCommand()
    command_manager.ScheduleTasks([command])
    _, request_id, _, command_id = command.key.flat()

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    tasks[0].attempt_id = "attempt1"  # different attempt
    tasks[0].put()
    command_task_store.LeaseTask(tasks[0].task_id)
    command_event_test_util.CreateCommandAttempt(
        command, "attempt0", common.CommandState.UNKNOWN, task=tasks[0])
    event = command_event_test_util.CreateTestCommandEvent(
        request_id,
        command_id,
        "attempt0",
        common.InvocationEventType.INVOCATION_COMPLETED,
        error="error",
        task=tasks[0],
        time=TIMESTAMP)
    commander.ProcessCommandEvent(event)

    tasks = command_manager.GetActiveTasks(command)
    self.assertEqual(len(tasks), 1)
    # Task should not be rescheduled
    self.assertEqual(tasks[0].leasable, False)
    self.assertEqual(tasks[0].attempt_index, 0)
    command = command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.QUEUED, command.state)
    request = command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.QUEUED, request.state)
    attempt_metric.assert_called_once_with(
        cluster_id=command.cluster,
        run_target=command.run_target,
        state="ERROR")

  @mock.patch.object(command_monitor, "Monitor")
  @mock.patch.object(command_manager, "ScheduleTasks")
  def testCheckPendingCommands(self, schedule_tasks, monitor):
    request_id = "1001"
    command_infos = [
        datastore_entities.CommandInfo(              command_line="command_line %04d" % i,
            cluster="cluster %04d" % i,
            run_target="run_target %04d" % i,
            run_count=1,
            shard_count=1)
        for i in range(10)
    ]
    request = datastore_test_util.CreateRequest(
        request_id=request_id,
        user="user",
        command_infos=command_infos,
        max_concurrent_tasks=5,
        plugin_data={
            "FOO": "foo",
            "BAR": "'bar",
        })
    command_manager.CreateCommands(
        request_id=request_id,
        command_infos=command_infos,
        priority=request.priority,
        shard_indexes=[0] * len(command_infos))
    commands = command_manager.GetCommands(request_id)
    for i, command in enumerate(commands):
      if i < 2:
        command.state = common.CommandState.COMPLETED
      elif i < 5:
        command.state = common.CommandState.QUEUED
      else:
        command.state = common.CommandState.UNKNOWN
      command.put()
    request_summary = request_manager.RequestSummary()
    request_summary.completed_count = 2
    request_summary.queued_count = 3
    request_summary.pending_count = 5

    commander._CheckPendingCommands(request, request_summary)

    schedule_tasks.assert_called_once_with(commands[5:7])
    monitor.assert_called_once_with(commands[5:7])

  @mock.patch.object(command_monitor, "Monitor")
  @mock.patch.object(command_manager, "ScheduleTasks")
  def testCheckPendingCommands_canceledRequest(
      self, schedule_tasks, monitor):
    request_id = "1001"
    command_infos = [
        datastore_entities.CommandInfo(              command_line="command_line %04d" % i,
            cluster="cluster %04d" % i,
            run_target="run_target %04d" % i,
            run_count=1,
            shard_count=1)
        for i in range(10)
    ]
    request = datastore_test_util.CreateRequest(
        request_id=request_id,
        user="user",
        command_infos=command_infos,
        max_concurrent_tasks=5,
        plugin_data={
            "FOO": "foo",
            "BAR": "'bar",
        })
    command_manager.CreateCommands(
        request_id=request_id,
        command_infos=command_infos,
        priority=request.priority,
        shard_indexes=[0] * len(command_infos))
    request.state = common.RequestState.CANCELED
    request.put()
    commands = command_manager.GetCommands(request_id)
    for i, command in enumerate(commands):
      if i < 2:
        command.state = common.CommandState.COMPLETED
      elif i < 5:
        command.state = common.CommandState.QUEUED
      else:
        command.state = common.CommandState.UNKNOWN
      command.put()
    request_summary = request_manager.RequestSummary()
    request_summary.completed_count = 2
    request_summary.queued_count = 3
    request_summary.pending_count = 5

    commander._CheckPendingCommands(request, request_summary)

    schedule_tasks.assert_not_called()
    monitor.assert_not_called()


class HandleRequestTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super(HandleRequestTest, self).setUp()
    self.testapp = webtest.TestApp(commander.APP)
    self.plugin_patcher = mock.patch(
        "__main__.env_config.CONFIG.plugin")
    self.plugin_patcher.start()

  def tearDown(self):
    super(HandleRequestTest, self).tearDown()
    self.plugin_patcher.stop()

  @mock.patch.object(command_manager, "ScheduleTasks")
  def testPost(self, schedule_tasks):
    request_id = "request_id"
    request = datastore_test_util.CreateRequest(
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line0",
                cluster="cluster",
                run_target="bullhead")
        ],
        request_id=request_id,
        plugin_data={"ants_invocation_id": "i123", "ants_work_unit_id": "w123"})
    request_manager.AddToQueue(request)
    tasks = self.mock_task_scheduler.GetTasks()
    self.assertEqual(len(tasks), 1)
    self.testapp.post(commander.REQUEST_HANDLER_PATH, tasks[0].payload)

    commands = request_manager.GetCommands(request_id)
    self.assertEqual(1, len(commands))
    command = commands[0]
    self.assertEqual("command_line0",
                     command.command_line)
    self.assertEqual("bullhead", command.run_target)
    self.assertEqual(1, command.run_count)
    self.assertEqual("cluster", command.cluster)
    self.assertIsNone(command.priority)
    self.assertIsNone(command.queue_timeout_seconds)


if __name__ == "__main__":
  unittest.main()
