# Lint as: python2, python3
# Copyright 2020 Google LLC
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

"""Unit tests for command_event_handler module."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import datetime
import unittest

import hamcrest
import mock
from six.moves import range
import webtest

from tradefed_cluster import command_event_handler
from tradefed_cluster import command_event_test_util
from tradefed_cluster import command_manager
from tradefed_cluster import command_task_store
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config  from tradefed_cluster import metric
from tradefed_cluster import request_manager
from tradefed_cluster import request_sync_monitor
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.util import ndb_shim as ndb


TIMESTAMP_INT = command_event_test_util.TIMESTAMP_INT
TIMESTAMP = command_event_test_util.TIMESTAMP


class CommandEventHandlerTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super(CommandEventHandlerTest, self).setUp()
    self.testapp = webtest.TestApp(command_event_handler.APP)
    self.plugin_patcher = mock.patch(
        "__main__.env_config.CONFIG.plugin")
    self.plugin_patcher.start()

    self.request = request_manager.CreateRequest(
        request_id="1001", user="user1", command_line="command_line",
        cluster="cluster", run_target="run_target")
    self.command = command_manager.CreateCommands(
        request_id=self.request.key.id(),
        command_lines=["long command line"],
        shard_indexes=list(range(1)),
        run_target="foo",
        run_count=1,
        shard_count=1,
        request_plugin_data={
            "ants_invocation_id": "i123",
            "ants_work_unit_id": "w123"
        },
        cluster="foobar")[0]
    self.now_patcher = mock.patch.object(common, "Now")
    self.mock_now = self.now_patcher.start()
    self.mock_now.return_value = TIMESTAMP

  def tearDown(self):
    self.plugin_patcher.stop()
    self.now_patcher.stop()
    super(CommandEventHandlerTest, self).tearDown()

  def testTruncate(self):
    self.assertEqual("foo", command_event_handler._Truncate("foo"))
    self.assertEqual(
        "foo...(total 3072 chars)",
        command_event_handler._Truncate("foo" * 1024, 3))

  def testEnqueueCommandEvents(self):
    _, request_id, _, command_id = self.command.key.flat()
    command_event_test_util.CreateCommandAttempt(
        self.command, "aid", common.CommandState.QUEUED)
    event = command_event_test_util.CreateTestCommandEventJson(
        request_id, command_id, "aid", "InvocationCompleted")

    command_event_handler.EnqueueCommandEvents([event])
    tasks = self.mock_task_scheduler.GetTasks()
    self.assertEqual(len(tasks), 1)
    self.testapp.post(
        command_event_handler.COMMAND_EVENT_HANDLER_PATH, tasks[0].payload)

    command_attempts = command_manager.GetCommandAttempts(
        request_id, command_id)
    self.assertEqual(len(command_attempts), 1)
    self.assertEqual(common.CommandState.COMPLETED, command_attempts[0].state)

  @mock.patch.object(command_event_handler, "ProcessCommandEvent")
  def testEnqueueCommandEvents_oldCommandEvents(self, mock_process):
    _, request_id, _, command_id = self.command.key.flat()
    command_event_test_util.CreateCommandAttempt(
        self.command, "aid", common.CommandState.QUEUED)
    event = command_event_test_util.CreateTestCommandEventJson(
        request_id, command_id, "aid", "InvocationCompleted")
    self.mock_now.return_value = (
        TIMESTAMP + datetime.timedelta(
            days=command_event_handler.COMMAND_EVENT_TIMEOUT_DAYS + 1))

    command_event_handler.EnqueueCommandEvents([event])
    tasks = self.mock_task_scheduler.GetTasks()
    self.assertEqual(len(tasks), 1)
    self.testapp.post(
        command_event_handler.COMMAND_EVENT_HANDLER_PATH, tasks[0].payload)
    # Old command event is ignored.
    self.assertFalse(mock_process.called)

  def testEnqueueCommandEvents_multipleEvents(self):
    self.request = request_manager.CreateRequest(
        request_id="9999", user="user1", command_line="command_line",
        cluster="cluster", run_target="run_target", shard_count=2)
    command_1, command_2 = command_manager.CreateCommands(
        request_id=self.request.key.id(),
        command_lines=["long command line %d" % i for i in range(2)],
        shard_indexes=list(range(2)),
        run_target="foo",
        run_count=1,
        shard_count=2,
        cluster="foobar")
    _, request_id, _, command_1_id = command_1.key.flat()
    _, _, _, command_2_id = command_2.key.flat()
    command_event_test_util.CreateCommandAttempt(
        command_1, "aid", common.CommandState.QUEUED)
    command_event_test_util.CreateCommandAttempt(
        command_2, "aid", common.CommandState.QUEUED)

    event = command_event_test_util.CreateTestCommandEventJson(
        request_id, command_1_id, "aid", "InvocationStarted")
    event2 = command_event_test_util.CreateTestCommandEventJson(
        request_id, command_2_id, "aid", "InvocationStarted")
    event3 = command_event_test_util.CreateTestCommandEventJson(
        request_id, command_1_id, "aid", "InvocationCompleted")
    event4 = command_event_test_util.CreateTestCommandEventJson(
        request_id, command_2_id, "aid", "InvocationCompleted")
    command_event_handler.EnqueueCommandEvents([event, event2, event3, event4])

    tasks = self.mock_task_scheduler.GetTasks()
    self.assertEqual(len(tasks), 4)
    for task in tasks:
      self.testapp.post(
          command_event_handler.COMMAND_EVENT_HANDLER_PATH, task.payload)

    command_attempts = command_manager.GetCommandAttempts(
        request_id, command_1_id)
    self.assertEqual(len(command_attempts), 1)
    self.assertEqual(common.CommandState.COMPLETED, command_attempts[0].state)
    command_attempts = command_manager.GetCommandAttempts(
        request_id, command_2_id)
    self.assertEqual(len(command_attempts), 1)
    self.assertEqual(common.CommandState.COMPLETED, command_attempts[0].state)

  def testEnqueueCommandEvents_malformedEvents(self):
    """A malformed event should not lose all events."""
    _, request_id, _, command_id = self.command.key.flat()
    command_event_test_util.CreateCommandAttempt(
        self.command, "aid", common.CommandState.QUEUED)
    event = command_event_test_util.CreateTestCommandEventJson(
        request_id, command_id, "aid", "InvocationStarted")
    malformed_event = {
        "data": {"total_test_count": 1, "exec_test_count": 1},
        "time": TIMESTAMP_INT,
        "type": "TestRunInProgress",
    }

    command_event_handler.EnqueueCommandEvents([event, malformed_event])
    tasks = self.mock_task_scheduler.GetTasks()
    self.assertEqual(len(tasks), 2)
    self.testapp.post(
        command_event_handler.COMMAND_EVENT_HANDLER_PATH, tasks[0].payload)
    with self.assertRaises(webtest.app.AppError):
      self.testapp.post(
          command_event_handler.COMMAND_EVENT_HANDLER_PATH, tasks[1].payload)

    command_attempts = command_manager.GetCommandAttempts(
        request_id, command_id)
    self.assertEqual(len(command_attempts), 1)
    self.assertEqual(common.CommandState.RUNNING, command_attempts[0].state)

  @mock.patch.object(command_event_handler, "ProcessCommandEvent")
  def testEnqueueCommandEvents_transactionError(self, mock_process):
    event = command_event_test_util.CreateTestCommandEventJson(
        "rid", "cid", "aid", "InvocationStarted")
    event2 = command_event_test_util.CreateTestCommandEventJson(
        "rid", "cid", "aid", "InvocationCompleted")

    # for the first time, the second event failed due to TransactionFailedError
    # the second event will be reschedule to the queue.
    mock_process.side_effect = [None, ndb.exceptions.ContextError(), None]

    command_event_handler.EnqueueCommandEvents([event, event2])
    tasks = self.mock_task_scheduler.GetTasks()
    self.assertEqual(len(tasks), 2)
    self.testapp.post(
        command_event_handler.COMMAND_EVENT_HANDLER_PATH, tasks[0].payload)
    with self.assertRaises(webtest.app.AppError):
      self.testapp.post(
          command_event_handler.COMMAND_EVENT_HANDLER_PATH, tasks[1].payload)
    # Simulate a task retry.
    self.testapp.post(
        command_event_handler.COMMAND_EVENT_HANDLER_PATH, tasks[1].payload)

    mock_process.assert_has_calls([
        mock.call(
            hamcrest.match_equality(
                hamcrest.all_of(
                    hamcrest.has_property("task_id", event["task_id"]),
                    hamcrest.has_property("type", event["type"])))),
        mock.call(
            hamcrest.match_equality(
                hamcrest.all_of(
                    hamcrest.has_property("task_id", event2["task_id"]),
                    hamcrest.has_property("type", event2["type"])))),
        # this is the retry.
        mock.call(
            hamcrest.match_equality(
                hamcrest.all_of(
                    hamcrest.has_property("task_id", event2["task_id"]),
                    hamcrest.has_property("type", event2["type"]))))
    ])

  @mock.patch.object(metric, "RecordCommandTimingMetric")
  @mock.patch.object(metric, "command_event_type_count")
  def testLogCommandEventMetrics_noInvocationTiming(
      self, event_type_metric, command_timing_metric):
    _, request_id, _, command_id = self.command.key.flat()
    invocation_completed_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0000000", "InvocationCompleted")

    command_event_handler.LogCommandEventMetrics(
        command=self.command, event=invocation_completed_event)

    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationCompleted"
    }
    event_type_metric.Increment.assert_called_once_with(expected_metric_fields)
    command_timing_metric.assert_not_called()

  @mock.patch.object(metric, "RecordCommandTimingMetric")
  @mock.patch.object(metric, "command_event_type_count")
  def testLogCommandEventMetrics_logInvocationComplete(
      self, event_type_metric, command_timing_metric):
    _, request_id, _, command_id = self.command.key.flat()
    self.command.start_time = TIMESTAMP
    self.command.put()
    invocation_completed_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0000000", "InvocationCompleted")

    command_event_handler.LogCommandEventMetrics(
        command=self.command, event=invocation_completed_event)

    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationCompleted",
    }
    event_type_metric.Increment.assert_called_once_with(expected_metric_fields)
    command_timing_metric.assert_called_once_with(
        cluster_id="foobar",
        run_target="foo",
        command_action=metric.CommandAction.INVOCATION_COMPLETED,
        hostname="hostname",
        create_timestamp=TIMESTAMP)

  @mock.patch.object(metric, "RecordCommandTimingMetric")
  @mock.patch.object(metric, "command_event_type_count")
  def testLogCommandEventMetrics_noCommand(
      self, event_type_metric, command_timing_metric):
    _, request_id, _, command_id = self.command.key.flat()
    invocation_completed_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0000000", "InvocationCompleted",
        data={"fetch_build_time_millis": "123"})

    command_event_handler.LogCommandEventMetrics(
        command=None, event=invocation_completed_event)

    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationCompleted"
    }
    event_type_metric.Increment.assert_called_once_with(expected_metric_fields)
    command_timing_metric.assert_not_called()

  @mock.patch.object(metric, "RecordCommandTimingMetric")
  @mock.patch.object(metric, "command_event_type_count")
  def testLogCommandEventMetrics_badEvent(
      self, event_type_metric, command_timing_metric):
    _, request_id, _, command_id = self.command.key.flat()
    invocation_completed_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0000000", "InvocationCompleted",
        data={"fetch_build_time_millis": "abcd"})  # Not a number

    # ValueError should be caught and this should not crash
    command_event_handler.LogCommandEventMetrics(
        command=self.command, event=invocation_completed_event)

    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationCompleted"
    }
    event_type_metric.Increment.assert_called_once_with(expected_metric_fields)
    command_timing_metric.assert_not_called()

  @mock.patch.object(metric, "RecordCommandTimingMetric")
  @mock.patch.object(metric, "command_event_type_count")
  def testLogCommandEventMetrics_withFetchBuildTiming(
      self, event_type_metric, command_timing_metric):
    _, request_id, _, command_id = self.command.key.flat()
    invocation_completed_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0000000", "InvocationCompleted",
        data={"fetch_build_time_millis": "101500"})  # 101.5 seconds

    command_event_handler.LogCommandEventMetrics(
        command=self.command, event=invocation_completed_event)

    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationCompleted",
        metric.METRIC_FIELD_HOSTNAME: "hostname"
    }
    event_type_metric.Increment.assert_called_once_with(expected_metric_fields)
    command_timing_metric.assert_called_once_with(
        cluster_id="foobar",
        run_target="foo",
        command_action=metric.CommandAction.INVOCATION_FETCH_BUILD,
        hostname="hostname",
        latency_secs=101.5)

  @mock.patch.object(metric, "RecordCommandTimingMetric")
  @mock.patch.object(metric, "command_event_type_count")
  def testLogCommandEventMetrics_withSetupTiming(
      self, event_type_metric, command_timing_metric):
    _, request_id, _, command_id = self.command.key.flat()
    invocation_completed_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0000000", "InvocationCompleted",
        data={"setup_time_millis": "10500"})  # 10.5 seconds

    command_event_handler.LogCommandEventMetrics(
        command=self.command, event=invocation_completed_event)

    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationCompleted",
        metric.METRIC_FIELD_HOSTNAME: "hostname"
    }
    event_type_metric.Increment.assert_called_once_with(expected_metric_fields)
    command_timing_metric.assert_called_once_with(
        cluster_id="foobar",
        run_target="foo",
        command_action=metric.CommandAction.INVOCATION_SETUP,
        hostname="hostname",
        latency_secs=10.5)

  @mock.patch.object(metric, "command_event_legacy_processing_count")
  @mock.patch.object(request_sync_monitor, "StoreCommandEvent")
  def testProcessCommandEvent_withRequestSync(self, mock_store_event,
                                              mock_event_legacy_count):
    _, request_id, _, command_id = self.command.key.flat()
    sync_key = ndb.Key(
        datastore_entities.RequestSyncStatus,
        request_id,
        namespace=common.NAMESPACE)
    sync_status = datastore_entities.RequestSyncStatus(
        key=sync_key, request_id=request_id)
    sync_status.put()

    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0000000", "InvocationCompleted")
    command_event_handler.ProcessCommandEvent(event)

    mock_store_event.assert_called_once_with(event)
    mock_event_legacy_count.assert_not_called()

  @mock.patch.object(metric, "command_event_legacy_processing_count")
  @mock.patch.object(metric, "command_event_type_count")
  def testProcessCommandEvent_allocationFailed(self,
                                               mock_command_event_type_count,
                                               mock_event_legacy_count):
    """Should reschedule tasks that send AllocationFailed events."""
    _, request_id, _, command_id = self.command.key.flat()
    command_manager.ScheduleTasks([self.command])

    # Command should stay queued even after MAX_CANCELED_COUNT_BASE different
    # attempts result in an AllocationFailed error.
    num_attempts = command_manager.MAX_CANCELED_COUNT_BASE
    for i in range(num_attempts):
      tasks = command_manager.GetActiveTasks(self.command)
      self.assertEqual(len(tasks), 1)
      command_task_store.LeaseTask(tasks[0].task_id)
      command_event_test_util.CreateCommandAttempt(
          self.command, str(i), common.CommandState.UNKNOWN, task=tasks[0])
      queried_command = command_manager.GetCommand(request_id, command_id)
      self.assertNotEqual(common.CommandState.ERROR, queried_command.state)
      event = command_event_test_util.CreateTestCommandEvent(
          request_id, command_id, str(i), "AllocationFailed", task=tasks[0])
      command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.CANCELED, queried_command.state)
    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 0)
    command_attempts = command_manager.GetCommandAttempts(
        request_id, command_id)
    self.assertEqual(
        len(command_attempts), command_manager.MAX_CANCELED_COUNT_BASE)
    self.assertSetEqual(
        set(attempt.attempt_index for attempt in command_attempts),
        set(range(command_manager.MAX_CANCELED_COUNT_BASE)))
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "AllocationFailed"
    }
    mock_command_event_type_count.Increment.assert_has_calls(
        [mock.call(expected_metric_fields)] * num_attempts)
    mock_event_legacy_count.Increment.assert_has_calls([mock.call({})] *
                                                       num_attempts)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_fetchFailed(
      self, mock_notify, mock_command_event_type_count):
    """Should error commands from FetchFailed events."""
    _, request_id, _, command_id = self.command.key.flat()
    command_manager.ScheduleTasks([self.command])

    # It should be marked as error at the MAX_ERROR_COUNT_BASE attempt.
    for i in range(command_manager.MAX_ERROR_COUNT_BASE):
      tasks = command_manager.GetActiveTasks(self.command)
      self.assertEqual(len(tasks), 1)
      self.assertEqual(tasks[0].attempt_index, i)
      command_task_store.LeaseTask(tasks[0].task_id)
      command_event_test_util.CreateCommandAttempt(
          self.command, str(i), common.CommandState.UNKNOWN, task=tasks[0])
      queried_command = command_manager.GetCommand(request_id, command_id)
      self.assertNotEqual(common.CommandState.ERROR, queried_command.state)
      event = command_event_test_util.CreateTestCommandEvent(
          request_id, command_id, str(i), "FetchFailed", task=tasks[0])
      command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.ERROR, queried_command.state)
    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 0)
    command_attempts = command_manager.GetCommandAttempts(
        request_id, command_id)
    self.assertEqual(
        len(command_attempts), command_manager.MAX_ERROR_COUNT_BASE)
    self.assertSetEqual(
        set(attempt.attempt_index for attempt in command_attempts),
        set(range(command_manager.MAX_ERROR_COUNT_BASE)))
    mock_notify.assert_called_with(request_id)
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "FetchFailed"
    }
    mock_command_event_type_count.Increment.assert_has_calls(
        [mock.call(expected_metric_fields)
        ] * command_manager.MAX_ERROR_COUNT_BASE)

  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_TooMuchContentionGetsRetried(self, mock_notify):
    """Should error commands from FetchFailed events."""
    _, request_id, _, command_id = self.command.key.flat()
    command_manager.ScheduleTasks([self.command])
    tasks = command_manager.GetActiveTasks(self.command)
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, 123, "FetchFailed", task=tasks[0])
    mock_notify.side_effect = Exception(
        '<_MultiThreadedRendezvous of RPC that terminated with: '
        'status = StatusCode.ABORTED details = "too much content'
        'ion on these datastore entities. please try again. enti'
        'ty groups: [(app=p~ee-cloud-datastore, Asset, "NOAA/GOE'
        'S/17/FDCC/2020195084117700000")]" debug_error_string = '
        '"{"created":"@1594629864.343436240","description":"Erro'
        'r received from peer ipv6:[2607:f8b0:4001:c01::5f]:443"'
        ',"file":"third_party/grpc/src/core/lib/surface/call.cc"'
        ',"file_line":1062,"grpc_message":"too much contention o'
        'n these datastore entities. please try again. entity gr'
        'oups: [(app=p~ee-cloud-datastore, Asset, "NOAA/GOES/17/'
        'FDCC/2020195084117700000")]","grpc_status":10}" >')

    with self.assertRaises(common.TooMuchContentionError):
      command_event_handler.ProcessCommandEvent(event)
    self.assertEqual(4, mock_notify.call_count)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_executeFailed(
      self, mock_notify, mock_command_event_type_count):
    """Should error commands from ExecuteFailed events."""
    _, request_id, _, command_id = self.command.key.flat()
    command_manager.ScheduleTasks([self.command])

    # It should be marked as error at the MAX_ERROR_COUNT_BASE attempt.
    for i in range(command_manager.MAX_ERROR_COUNT_BASE):
      tasks = command_manager.GetActiveTasks(self.command)
      self.assertEqual(len(tasks), 1)
      command_task_store.LeaseTask(tasks[0].task_id)
      command_event_test_util.CreateCommandAttempt(
          self.command, str(i), common.CommandState.UNKNOWN, task=tasks[0])
      queried_command = command_manager.GetCommand(request_id, command_id)
      self.assertNotEqual(common.CommandState.ERROR, queried_command.state)
      event = command_event_test_util.CreateTestCommandEvent(
          request_id, command_id, str(i), "ExecuteFailed", task=tasks[0])
      command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.ERROR, queried_command.state)
    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 0)
    mock_notify.assert_called_with(request_id)
    command_attempts = command_manager.GetCommandAttempts(
        request_id, command_id)
    self.assertEqual(
        len(command_attempts), command_manager.MAX_ERROR_COUNT_BASE)
    self.assertSetEqual(
        set(attempt.attempt_index for attempt in command_attempts),
        set(range(command_manager.MAX_ERROR_COUNT_BASE)))
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "ExecuteFailed"
    }
    mock_command_event_type_count.Increment.assert_has_calls(
        [mock.call(expected_metric_fields)
        ] * command_manager.MAX_ERROR_COUNT_BASE)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_invocationInitiated(
      self, mock_notify, mock_command_event_type_count):
    """Should update command state for InvocationInitiated events.

    State should become RUNNING if it isn't already.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_command_event_type_count: mock command event type count metric
    """
    _, request_id, _, command_id = self.command.key.flat()
    command_manager.ScheduleTasks([self.command])

    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 1)
    command_task_store.LeaseTask(tasks[0].task_id)
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", common.CommandState.UNKNOWN, task=tasks[0])
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertNotEqual(common.CommandState.RUNNING, queried_command.state)
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "InvocationInitiated", task=tasks[0])
    command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.RUNNING, queried_command.state)
    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].attempt_index, 0)
    self.assertEqual(tasks[0].leasable, False)
    mock_notify.assert_called_with(request_id)
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationInitiated"
    }
    mock_command_event_type_count.Increment.assert_called_once_with(
        expected_metric_fields)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_InvocationStarted(
      self, mock_notify, mock_command_event_type_count):
    """Should update command state for InvocationStarted events.

    State should become RUNNING if it isn't already.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_command_event_type_count: mock command event type count metric
    """
    _, request_id, _, command_id = self.command.key.flat()
    command_manager.ScheduleTasks([self.command])

    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 1)
    command_task_store.LeaseTask(tasks[0].task_id)
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", common.CommandState.UNKNOWN, task=tasks[0])
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertNotEqual(common.CommandState.RUNNING, queried_command.state)
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "InvocationStarted", task=tasks[0])
    command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.RUNNING, queried_command.state)
    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].attempt_index, 0)
    self.assertEqual(tasks[0].leasable, False)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(1, len(attempts))
    self.assertEqual(["0123456789ABCDEF"], attempts[0].device_serials)
    mock_notify.assert_called_with(request_id)
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationStarted"
    }
    mock_command_event_type_count.Increment.assert_called_once_with(
        expected_metric_fields)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_multiDevice(
      self, mock_notify, mock_command_event_type_count):
    """Should populate multiple devices."""
    _, request_id, _, command_id = self.command.key.flat()
    command_manager.ScheduleTasks([self.command])

    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 1)
    command_task_store.LeaseTask(tasks[0].task_id)
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", common.CommandState.UNKNOWN, task=tasks[0])
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertNotEqual(common.CommandState.RUNNING, queried_command.state)
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "InvocationStarted",
        task=tasks[0], device_serials=["d1", "d2"])
    command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.RUNNING, queried_command.state)
    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].attempt_index, 0)
    self.assertEqual(tasks[0].leasable, False)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(1, len(attempts))
    self.assertEqual(["d1", "d2"], attempts[0].device_serials)
    mock_notify.assert_called_with(request_id)
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationStarted"
    }
    mock_command_event_type_count.Increment.assert_called_once_with(
        expected_metric_fields)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_testRunInProgress(
      self, mock_notify, mock_command_event_type_count):
    """Should update command state for TestRunInProgress events.

    State should become RUNNING if it isn't already.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_command_event_type_count: mock command event type count metric
    """
    _, request_id, _, command_id = self.command.key.flat()
    command_manager.ScheduleTasks([self.command])

    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 1)
    command_task_store.LeaseTask(tasks[0].task_id)
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", common.CommandState.UNKNOWN, task=tasks[0])
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertNotEqual(common.CommandState.RUNNING, queried_command.state)
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "TestRunInProgress", task=tasks[0])
    command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.RUNNING, queried_command.state)
    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].attempt_index, 0)
    self.assertEqual(tasks[0].leasable, False)
    mock_notify.assert_called_with(request_id)
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "TestRunInProgress"
    }
    mock_command_event_type_count.Increment.assert_called_once_with(
        expected_metric_fields)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_invocationEnded(
      self, mock_notify, mock_command_event_type_count):
    """Should update command state for InvocationEnded events.

    State should become RUNNING if it isn't already.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_command_event_type_count: mock command event type count metric
    """
    _, request_id, _, command_id = self.command.key.flat()
    command_manager.ScheduleTasks([self.command])

    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 1)
    command_task_store.LeaseTask(tasks[0].task_id)
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", common.CommandState.UNKNOWN, task=tasks[0])
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertNotEqual(common.CommandState.RUNNING, queried_command.state)
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "InvocationEnded", task=tasks[0])
    command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.RUNNING, queried_command.state)
    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].attempt_index, 0)
    self.assertEqual(tasks[0].leasable, False)
    mock_notify.assert_called_with(request_id)
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationEnded"
    }
    mock_command_event_type_count.Increment.assert_called_once_with(
        expected_metric_fields)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_invocationCompleted(
      self, mock_notify, mock_command_event_type_count):
    """Should complete command state for InvocationCompleted events.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_command_event_type_count: mock command event type count metric
    """
    _, request_id, _, command_id = self.command.key.flat()
    command_manager.ScheduleTasks([self.command])

    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 1)
    command_task_store.LeaseTask(tasks[0].task_id)
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", common.CommandState.UNKNOWN, task=tasks[0])
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertNotEqual(common.CommandState.COMPLETED, queried_command.state)
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "InvocationCompleted", task=tasks[0])
    command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.COMPLETED, queried_command.state)
    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 0)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(1, len(attempts))
    self.assertEqual("summary", attempts[0].summary)
    self.assertEqual(1000, attempts[0].total_test_count)
    self.assertEqual(100, attempts[0].failed_test_count)
    self.assertEqual(10, attempts[0].failed_test_run_count)
    mock_notify.assert_called_with(request_id)
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationCompleted"
    }
    mock_command_event_type_count.Increment.assert_called_once_with(
        expected_metric_fields)

  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_InvocationCompleted_multipleRuns(
      self, mock_notify):
    """Should complete command state for InvocationCompleted events.

    It should only be set as COMPLETE if all runs are executed.

    Args:
      mock_notify: mock function to notify request state changes.
    """
    run_count = 3
    _, request_id, _, command_id = self.command.key.flat()
    self.command.run_count = run_count
    self.command.put()
    command_manager.ScheduleTasks([self.command])

    for i in range(run_count):
      tasks = command_manager.GetActiveTasks(self.command)
      self.assertEqual(
          len(tasks), run_count - i)
      next_leasable_task = next((t for t in tasks if t.leasable), None)
      command_task_store.LeaseTask(next_leasable_task.task_id)
      command_event_test_util.CreateCommandAttempt(
          self.command, str(i), common.CommandState.UNKNOWN,
          task=next_leasable_task)
      queried_command = command_manager.GetCommand(request_id, command_id)
      self.assertNotEqual(common.CommandState.COMPLETED, queried_command.state)
      event = command_event_test_util.CreateTestCommandEvent(
          request_id, command_id, str(i), "InvocationCompleted",
          task=next_leasable_task)
      command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.COMPLETED, queried_command.state)
    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 0)
    command_attempts = command_manager.GetCommandAttempts(
        request_id, command_id)
    self.assertEqual(len(command_attempts), run_count)
    self.assertSetEqual(
        set(attempt.run_index for attempt in command_attempts),
        set(range(run_count)))
    mock_notify.assert_called_with(request_id)

  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_invocationCompleted_multipleRuns_20(
      self, mock_notify):
    """Should complete command state for InvocationCompleted events.

    This tests a case when a run count is greater than
    command_manager.MAX_TASK_COUNT.

    Args:
      mock_notify: mock function to notify request state changes.
    """
    run_count = 100
    _, request_id, _, command_id = self.command.key.flat()
    self.command.run_count = run_count
    self.command.put()
    command_manager.ScheduleTasks([self.command])

    for i in range(run_count):
      tasks = command_manager.GetActiveTasks(self.command)
      self.assertEqual(
          len(tasks), min(run_count - i, command_manager.MAX_TASK_COUNT))
      next_leasable_task = next((t for t in tasks if t.leasable), None)
      command_task_store.LeaseTask(next_leasable_task.task_id)
      queried_command = command_manager.GetCommand(request_id, command_id)
      self.assertNotEqual(common.CommandState.COMPLETED, queried_command.state)
      command_event_test_util.CreateCommandAttempt(
          self.command, str(i), common.CommandState.UNKNOWN,
          task=next_leasable_task)
      event = command_event_test_util.CreateTestCommandEvent(
          request_id, command_id, str(i), "InvocationCompleted",
          task=next_leasable_task)
      command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.COMPLETED, queried_command.state)
    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 0)
    command_attempts = command_manager.GetCommandAttempts(
        request_id, command_id)
    self.assertEqual(len(command_attempts), run_count)
    self.assertSetEqual(
        set(attempt.run_index for attempt in command_attempts),
        set(range(run_count)))
    mock_notify.assert_called_with(request_id)

  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_invocationCompleted_multipleRunsWithErrors(
      self, mock_notify):
    """Should complete command state for InvocationCompleted events.

    This tests a case when a run count is greater than
    command_manager.MAX_TASK_COUNT.

    Args:
      mock_notify: mock function to notify request state changes.
    """
    run_count = 100
    _, request_id, _, command_id = self.command.key.flat()
    self.command.run_count = run_count
    self.command.put()
    command_manager.ScheduleTasks([self.command])

    max_error_count = (
        command_manager.MAX_ERROR_COUNT_BASE +
        int(run_count * command_manager.MAX_ERROR_COUNT_RATIO))
    for i in range(max_error_count):
      tasks = command_manager.GetActiveTasks(self.command)
      self.assertEqual(
          len(tasks), min(run_count - i, command_manager.MAX_TASK_COUNT))
      next_leasable_task = next((t for t in tasks if t.leasable), None)
      command_task_store.LeaseTask(next_leasable_task.task_id)
      command_event_test_util.CreateCommandAttempt(
          self.command, str(i), common.CommandState.UNKNOWN,
          task=next_leasable_task)
      # It should be marked as error at the max error count attempts.
      queried_command = command_manager.GetCommand(request_id, command_id)
      self.assertNotEqual(common.CommandState.ERROR, queried_command.state)
      event = command_event_test_util.CreateTestCommandEvent(
          request_id, command_id, str(i), "InvocationCompleted",
          task=next_leasable_task, error="error")
      command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.ERROR, queried_command.state)
    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 0)
    command_attempts = command_manager.GetCommandAttempts(
        request_id, command_id)
    self.assertEqual(len(command_attempts), max_error_count)
    run_attempt_pairs = [
        (attempt.run_index, attempt.attempt_index)
        for attempt in command_attempts]
    self.assertEqual(len(set(run_attempt_pairs)), len(command_attempts))
    mock_notify.assert_called_with(request_id)

  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_unknownEvent(self, mock_notify):
    """Should update command state for unknown events."""
    _, request_id, _, command_id = self.command.key.flat()
    command_manager.ScheduleTasks([self.command])

    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 1)
    command_task_store.LeaseTask(tasks[0].task_id)
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", common.CommandState.UNKNOWN, task=tasks[0])
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.QUEUED, queried_command.state)
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "SomeRandomInexistentType", task=tasks[0])
    command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.QUEUED, queried_command.state)
    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 1)
    mock_notify.not_called()

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_fatalEvent(
      self, mock_notify, mock_command_event_type_count):
    """Should not reschedule a configuration error, request should error out.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_command_event_type_count: mock command event type count metric
    """
    _, request_id, _, command_id = self.command.key.flat()
    command_manager.ScheduleTasks([self.command])

    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 1)
    command_task_store.LeaseTask(tasks[0].task_id)
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", common.CommandState.UNKNOWN, task=tasks[0])
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertNotEqual(common.CommandState.FATAL, queried_command.state)
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "ConfigurationError", task=tasks[0])
    command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.FATAL, queried_command.state)
    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 0)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(1, len(attempts))
    mock_notify.assert_called_with(request_id)
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "ConfigurationError"
    }
    mock_command_event_type_count.Increment.assert_called_once_with(
        expected_metric_fields)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_TFShutdown(
      self, mock_notify, mock_command_event_type_count):
    """Mark command events that were terminated by TF shutdown as CANCELED."""
    _, request_id, _, command_id = self.command.key.flat()
    command_manager.ScheduleTasks([self.command])
    error = "RunInterruptedException: Tradefed is shutting down."

    for i in range(3):
      tasks = command_manager.GetActiveTasks(self.command)
      self.assertEqual(len(tasks), 1)
      command_task_store.LeaseTask(tasks[0].task_id)
      command_event_test_util.CreateCommandAttempt(
          self.command, str(i), common.CommandState.UNKNOWN, task=tasks[0])
      event = command_event_test_util.CreateTestCommandEvent(
          request_id, command_id, str(i), "InvocationCompleted",
          task=tasks[0], data={"error": error})
      command_event_handler.ProcessCommandEvent(event)

    # After three cancelled attempts, the command should still be queued.
    queried_command = self.command.key.get()
    self.assertEqual(common.CommandState.QUEUED, queried_command.state)
    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 1)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(3, len(attempts))
    mock_notify.assert_called_with(request_id)
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationCompleted"
    }
    mock_command_event_type_count.Increment.assert_has_calls(
        [mock.call(expected_metric_fields)] * 3)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_ignoreOutOfDateEvent(
      self, mock_notify, mock_command_event_type_count):
    """Should complete command state for InvocationCompleted events."""
    _, request_id, _, command_id = self.command.key.flat()
    command_manager.ScheduleTasks([self.command])

    tasks = command_manager.GetActiveTasks(self.command)
    command_task_store.LeaseTask(tasks[0].task_id)
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", common.CommandState.UNKNOWN, task=tasks[0])
    invocation_completed_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "InvocationCompleted",
        task=tasks[0], time=TIMESTAMP_INT + 60)
    invocation_started_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "InvocationStarted",
        task=tasks[0], time=TIMESTAMP_INT + 30)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.QUEUED, queried_command.state)

    command_event_handler.ProcessCommandEvent(invocation_completed_event)
    queried_command = command_manager.GetCommand(request_id, command_id)
    command_attempt = command_manager.GetCommandAttempts(
        request_id, command_id)[0]
    self.assertEqual(
        TIMESTAMP + datetime.timedelta(seconds=60),
        command_attempt.last_event_time)
    self.assertEqual(common.CommandState.COMPLETED, queried_command.state)

    # The second event is ignored.
    command_event_handler.ProcessCommandEvent(invocation_started_event)
    queried_command = command_manager.GetCommand(request_id, command_id)
    command_attempt = command_manager.GetCommandAttempts(
        request_id, command_id)[0]
    self.assertEqual(
        TIMESTAMP + datetime.timedelta(seconds=60),
        command_attempt.last_event_time)
    self.assertEqual(common.CommandState.COMPLETED, queried_command.state)

    tasks = command_manager.GetActiveTasks(self.command)
    self.assertEqual(len(tasks), 0)
    attempts = command_manager.GetCommandAttempts(
        request_id, command_id)
    self.assertEqual(1, len(attempts))
    self.assertEqual("summary", attempts[0].summary)
    self.assertEqual(1000, attempts[0].total_test_count)
    self.assertEqual(100, attempts[0].failed_test_count)
    mock_notify.assert_called_with(request_id)
    # Metrics should still be logged for out of order events
    started_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationStarted"
    }
    completed_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationCompleted"
    }
    mock_command_event_type_count.Increment.assert_has_calls(
        [mock.call(completed_metric_fields),
         mock.call(started_metric_fields)])


if __name__ == "__main__":
  unittest.main()
