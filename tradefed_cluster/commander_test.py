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

import unittest

import mock
import webtest

from tradefed_cluster import command_manager
from tradefed_cluster import command_monitor
from tradefed_cluster import commander
from tradefed_cluster import common
from tradefed_cluster import env_config
from tradefed_cluster import request_manager
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.plugins import base as plugin_base
from tradefed_cluster.util import command_util


class CommanderTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    testbed_dependent_test.TestbedDependentTest.setUp(self)

  @mock.patch.object(command_monitor, "Monitor")
  @mock.patch.object(command_manager, "ScheduleTasks")
  @mock.patch.object(env_config.CONFIG, "plugin")
  def testProcessRequest(self, plugin, schedule_tasks, monitor):
    request_id1 = "1001"
    request_id2 = "1002"
    request_manager.CreateRequest(
        "user",
        "command_line0 --run-target run_target --cluster cluster",
        request_id=request_id1,
        plugin_data={"ants_invocation_id": "i123",
                     "ants_work_unit_id": "w123"})
    request_manager.CreateRequest(
        "user",
        "command_line0 --run-target run_target --cluster cluster",
        request_id=request_id2,
        priority=100,
        queue_timeout_seconds=86400)

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

    commands_1 = request_manager.GetCommands(request_id2)
    self.assertEqual(1, len(commands_1))
    command = commands_1[0]
    self.assertEqual("command_line0", command.command_line)
    self.assertEqual("run_target", command.run_target)
    self.assertEqual(1, command.run_count)
    self.assertEqual("cluster", command.cluster)
    self.assertEqual(100, command.priority)
    self.assertEqual(86400, command.queue_timeout_seconds)
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
    request_manager.CreateRequest(
        "user",
        "command_line0 --cluster cluster",
        request_id=request_id1)

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
    request_manager.CreateRequest(
        "user",
        "command_line0 --run-target bullhead --cluster cluster",
        shard_count=3,
        request_id=request_id)

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
    self.assertEqual(["0", "1", "2"], sorted(shards))
    plugin.assert_has_calls([])

  @mock.patch.object(command_manager, "ScheduleTasks")
  @mock.patch.object(env_config.CONFIG, "plugin")
  def testProcessRequests_RequestlocalSharding(self, plugin, schedule_tasks):
    """Tests processing of sharded requests with local sharding."""
    request_id = "1001"
    request_manager.CreateRequest(
        "user",
        "command_line0 --run-target bullhead --cluster cluster --shard-count 3",
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
    request_manager.CreateRequest(
        "user",
        "command_line0 --run-target bullhead --cluster cluster",
        shard_count=1,
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
    request_manager.CreateRequest(
        "user",
        "command_line0 --cluster cluster --shard-count 1",
        request_id=request_id)

    commander._ProcessRequest(request_id)
    cancel_request.assert_called_once_with(
        request_id, common.CancelReason.INVALID_REQUEST)

  @mock.patch.object(command_manager, "ScheduleTasks")
  @mock.patch.object(env_config.CONFIG, "plugin")
  def testProcessRequest_escapeInCommandLine(self, plugin, schedule_tasks):
    request_id1 = "1001"
    request_manager.CreateRequest(
        "user",
        "command_line0 --run-target run_target --cluster cluster"
        ' --arg \'option=\'"\'"\'value\'"\'"\'\'',
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


class HandleReuestTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    testbed_dependent_test.TestbedDependentTest.setUp(self)
    self.testapp = webtest.TestApp(commander.APP)
    self.plugin_patcher = mock.patch(
        "__main__.env_config.CONFIG.plugin")
    self.plugin_patcher.start()

  def tearDown(self):
    self.plugin_patcher.stop()

  @mock.patch.object(command_manager, "ScheduleTasks")
  def testPost(self, schedule_tasks):
    request_id = "request_id"
    request = request_manager.CreateRequest(
        "user",
        "command_line0 --run-target bullhead --cluster cluster",
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
