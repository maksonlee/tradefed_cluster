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

"""Unit tests for command_event_handler module."""

import datetime
import unittest

import hamcrest
import mock
import webtest

from google.appengine.ext import db
from google.appengine.ext import ndb

from tradefed_cluster import command_event_handler
from tradefed_cluster import command_event_test_util
from tradefed_cluster import command_manager
from tradefed_cluster import common
from tradefed_cluster import env_config  from tradefed_cluster import metric
from tradefed_cluster import request_manager
from tradefed_cluster import testbed_dependent_test


TIMESTAMP_INT = command_event_test_util.TIMESTAMP_INT
TIMESTAMP = command_event_test_util.TIMESTAMP


class CommandEventHandlerTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    testbed_dependent_test.TestbedDependentTest.setUp(self)
    self.testapp = webtest.TestApp(command_event_handler.APP)
    self.plugin_patcher = mock.patch(
        "__main__.env_config.CONFIG.plugin")
    self.plugin_patcher.start()

    self.request = request_manager.CreateRequest(
        request_id="1001", user="user1", command_line="command_line",
        cluster="cluster", run_target="run_target")
    self.request_2 = request_manager.CreateRequest(
        request_id="1002", user="user1", command_line="command_line",
        cluster="cluster", run_target="run_target")
    self.request_3 = request_manager.CreateRequest(
        request_id="1003", user="user1", command_line="command_line",
        cluster="cluster", run_target="run_target")
    self.command = command_manager.CreateCommands(
        request_id=self.request.key.id(),
        command_lines=["long command line"],
        shard_indexes=range(1),
        run_target="foo",
        run_count=1,
        shard_count=1,
        request_plugin_data={
            "ants_invocation_id": "i123",
            "ants_work_unit_id": "w123"
        },
        cluster="foobar")[0]
    self.command_2 = command_manager.CreateCommands(
        request_id=self.request_2.key.id(),
        command_lines=["command_line"],
        shard_indexes=range(1),
        shard_count=1,
        run_target="run_target",
        run_count=3,
        request_plugin_data={
            "ants_invocation_id": "i123",
            "ants_work_unit_id": "w123"
        },
        cluster="cluster")[0]
    # Clear Datastore cache
    ndb.get_context().clear_cache()

    self.now_patcher = mock.patch.object(command_event_handler, "_Now")
    self.mock_now = self.now_patcher.start()
    self.mock_now.return_value = TIMESTAMP

  def tearDown(self):
    self.plugin_patcher.stop()
    self.now_patcher.stop()
    testbed_dependent_test.TestbedDependentTest.tearDown(self)

  @mock.patch.object(command_event_handler, "ProcessCommandEvent")
  def testEnqueueCommandEvents(self, mock_process):
    event = command_event_test_util.CreateTestCommandEventJson(
        "rid", "cid", "aid", "InvocationCompleted")
    command_event_handler.EnqueueCommandEvents([event])
    tasks = self.taskqueue_stub.get_filtered_tasks()
    self.assertEqual(len(tasks), 1)
    self.testapp.post(command_event_handler.COMMAND_EVENT_HANDLER_PATH,
                      tasks[0].payload)
    mock_process.assert_called_with(
        hamcrest.match_equality(
            hamcrest.has_property("task_id", event["task_id"])))

  @mock.patch.object(command_event_handler, "ProcessCommandEvent")
  def testEnqueueCommandEvents_oldCommandEvents(self, mock_process):
    event = command_event_test_util.CreateTestCommandEventJson(
        "rid", "cid", "aid", "InvocationCompleted")
    self.mock_now.return_value = (
        TIMESTAMP + datetime.timedelta(
            days=command_event_handler.COMMAND_EVENT_TIMEOUT_DAYS + 1))
    command_event_handler.EnqueueCommandEvents([event])
    tasks = self.taskqueue_stub.get_filtered_tasks()
    self.assertEqual(len(tasks), 1)
    self.testapp.post(command_event_handler.COMMAND_EVENT_HANDLER_PATH,
                      tasks[0].payload)
    # Old command event is ignored.
    self.assertFalse(mock_process.called)

  @mock.patch.object(command_event_handler, "ProcessCommandEvent")
  def testEnqueueCommandEvents_multipleEvents(self, mock_process):
    event = command_event_test_util.CreateTestCommandEventJson(
        "rid", "cid", "aid", "InvocationStarted")
    event2 = command_event_test_util.CreateTestCommandEventJson(
        "rid", "cid2", "aid", "InvocationStarted")
    event3 = command_event_test_util.CreateTestCommandEventJson(
        "rid", "cid", "aid", "InvocationCompleted")
    event4 = command_event_test_util.CreateTestCommandEventJson(
        "rid", "cid2", "aid", "InvocationCompleted")
    command_event_handler.EnqueueCommandEvents([event, event2, event3, event4])
    tasks = self.taskqueue_stub.get_filtered_tasks()
    self.assertEqual(len(tasks), 2)
    self.testapp.post(command_event_handler.COMMAND_EVENT_HANDLER_PATH,
                      tasks[0].payload)
    mock_process.assert_has_calls([
        mock.call(
            hamcrest.match_equality(
                hamcrest.all_of(
                    hamcrest.has_property("task_id", event["task_id"]),
                    hamcrest.has_property("type", event["type"])))),
        mock.call(
            hamcrest.match_equality(
                hamcrest.all_of(
                    hamcrest.has_property("task_id", event3["task_id"]),
                    hamcrest.has_property("type", event3["type"]))))
    ])
    self.testapp.post(command_event_handler.COMMAND_EVENT_HANDLER_PATH,
                      tasks[1].payload)
    mock_process.assert_has_calls([
        mock.call(
            hamcrest.match_equality(
                hamcrest.all_of(
                    hamcrest.has_property("task_id", event2["task_id"]),
                    hamcrest.has_property("type", event2["type"])))),
        mock.call(
            hamcrest.match_equality(
                hamcrest.all_of(
                    hamcrest.has_property("task_id", event4["task_id"]),
                    hamcrest.has_property("type", event4["type"]))))
    ])

  @mock.patch.object(command_event_handler, "ProcessCommandEvent")
  def testEnqueueCommandEvents_malformedEvents(self, mock_process):
    """A malformed event should not lose all events."""
    event = command_event_test_util.CreateTestCommandEventJson(
        "rid", "cid", "aid", "InvocationStarted")
    malformed_event = {
        "data": {"total_test_count": 1, "exec_test_count": 1},
        "time": TIMESTAMP_INT,
        "type": "TestRunInProgress",
    }
    command_event_handler.EnqueueCommandEvents([event, malformed_event])
    tasks = self.taskqueue_stub.get_filtered_tasks()
    self.assertEqual(len(tasks), 1)
    self.testapp.post(command_event_handler.COMMAND_EVENT_HANDLER_PATH,
                      tasks[0].payload)
    mock_process.assert_called_once_with(
        hamcrest.match_equality(
            hamcrest.all_of(
                hamcrest.has_property("task_id", event["task_id"]),
                hamcrest.has_property("type", event["type"]))))

  @mock.patch.object(command_event_handler, "ProcessCommandEvent")
  def testEnqueueCommandEvents_partTransactionError(self, mock_process):
    event = command_event_test_util.CreateTestCommandEventJson(
        "rid", "cid", "aid", "InvocationStarted")
    event2 = command_event_test_util.CreateTestCommandEventJson(
        "rid", "cid", "aid", "InvocationCompleted")

    # for the first time, the second event failed due to TransactionFailedError
    # the second event will be reschedule to the queue.
    mock_process.side_effect = [None, db.TransactionFailedError(), None]

    command_event_handler.EnqueueCommandEvents([event, event2])
    tasks = self.taskqueue_stub.get_filtered_tasks()

    self.assertEqual(len(tasks), 1)
    self.taskqueue_stub.DeleteTask(command_event_handler.COMMAND_EVENT_QUEUE,
                                   tasks[0].name)
    response = self.testapp.post(
        command_event_handler.COMMAND_EVENT_HANDLER_PATH, tasks[0].payload)
    self.assertEqual("200 OK", response.status)

    tasks = self.taskqueue_stub.get_filtered_tasks()
    self.assertEqual(len(tasks), 1)
    response = self.testapp.post(
        command_event_handler.COMMAND_EVENT_HANDLER_PATH, tasks[0].payload)
    self.assertEqual("200 OK", response.status)

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

  @mock.patch.object(command_event_handler, "ProcessCommandEvent")
  def testEnqueueCommandEvents_allTransactionError(self, mock_process):
    event = command_event_test_util.CreateTestCommandEventJson(
        "rid", "cid", "aid", "InvocationStarted")
    event2 = command_event_test_util.CreateTestCommandEventJson(
        "rid", "cid", "aid", "InvocationCompleted")

    # for the first time, the second event failed due to TransactionFailedError
    # the second event will be reschedule to the queue.
    mock_process.side_effect = [db.TransactionFailedError(),
                                db.TransactionFailedError()]

    command_event_handler.EnqueueCommandEvents([event, event2])
    tasks = self.taskqueue_stub.get_filtered_tasks()

    self.assertEqual(len(tasks), 1)
    response = self.testapp.post(
        command_event_handler.COMMAND_EVENT_HANDLER_PATH,
        tasks[0].payload,
        expect_errors=True)
    self.assertEqual("500 Internal Server Error", response.status)

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

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(command_manager, "RescheduleTask")
  def testProcessCommandEvent_allocationFailed(
      self, mock_reschedule, mock_command_event_type_count):
    """Should reschedule tasks that send AllocationFailed events.

    Args:
      mock_reschedule: mock function to reschedule tasks.
      mock_command_event_type_count: mock command event type count metric
    """
    _, request_id, _, command_id = self.command.key.flat()
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0000000000000000", "AllocationFailed")

    # Command should stay queued even after 3 different attempts result in an
    # AllocationFailed error.
    num_attempts = command_manager.MAX_CANCELED_COUNT_BASE
    for i in range(num_attempts):
      command_event_test_util.CreateCommandAttempt(
          self.command, str(i), state=common.CommandState.UNKNOWN)
      queried_command = command_manager.GetCommand(request_id, command_id)
      self.assertNotEqual(common.CommandState.ERROR, queried_command.state)
      event.attempt_id = str(i)
      command_event_handler.ProcessCommandEvent(event)
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.CANCELED, queried_command.state)

    mock_reschedule.assert_called_with(
        event.task_id,
        hamcrest.match_equality(
            hamcrest.has_property("key", self.command.key)))
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "AllocationFailed"
    }
    mock_command_event_type_count.Increment.assert_has_calls(
        [mock.call(expected_metric_fields)] * num_attempts)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(command_manager, "DeleteTasks")
  @mock.patch.object(command_manager, "RescheduleTask")
  @mock.patch.object(command_manager, "GetActiveTaskCount")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_FetchFailed(
      self, mock_notify, mock_get_active_task_count, mock_reschedule,
      mock_delete_tasks, mock_command_event_type_count):
    """Should error commands from FetchFailed events."""
    _, request_id, _, command_id = self.command.key.flat()
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "FetchFailed")
    mock_get_active_task_count.return_value = 1

    for i in range(command_manager.MAX_ERROR_COUNT_BASE):
      command_event_test_util.CreateCommandAttempt(
          self.command, str(i + 1), state=common.CommandState.UNKNOWN)
      # It should be marked as error at the MAX_ERROR_COUNT_BASE attempt.
      queried_command = command_manager.GetCommand(request_id, command_id)
      event.attempt_id = str(int(event.attempt_id) + 1)
      self.assertNotEqual(common.CommandState.ERROR, queried_command.state)
      command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.ERROR, queried_command.state)
    mock_reschedule.assert_called_with(
        event.task_id,
        hamcrest.match_equality(
            hamcrest.has_property("key", self.command.key)))
    mock_notify.assert_called_with(request_id)
    mock_delete_tasks.assert_called_with(
        hamcrest.match_equality(
            hamcrest.has_property("key", self.command.key)))
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "FetchFailed"
    }
    mock_command_event_type_count.Increment.assert_has_calls(
        [mock.call(expected_metric_fields)
        ] * command_manager.MAX_ERROR_COUNT_BASE)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(command_manager, "DeleteTasks")
  @mock.patch.object(command_manager, "RescheduleTask")
  @mock.patch.object(command_manager, "GetActiveTaskCount")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_ExecuteFailed(
      self, mock_notify, mock_get_active_task_count, mock_reschedule,
      mock_delete_tasks, mock_command_event_type_count):
    """Should error commands from ExecuteFailed events."""
    _, request_id, _, command_id = self.command.key.flat()
    event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0000000000000000", "ExecuteFailed")
    mock_get_active_task_count.return_value = 1

    for i in range(command_manager.MAX_ERROR_COUNT_BASE):
      # It should be marked as error at the MAX_ERROR_COUNT_BASE attempt.
      command_event_test_util.CreateCommandAttempt(
          self.command, str(i + 1), state=common.CommandState.UNKNOWN)
      queried_command = command_manager.GetCommand(request_id, command_id)
      event.attempt_id = str(int(event.attempt_id) + 1)
      self.assertNotEqual(common.CommandState.ERROR, queried_command.state)
      command_event_handler.ProcessCommandEvent(event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.ERROR, queried_command.state)
    mock_get_active_task_count.assert_called()
    mock_reschedule.assert_called_with(
        event.task_id,
        hamcrest.match_equality(
            hamcrest.has_property("key", self.command.key)))
    mock_notify.assert_called_with(request_id)
    mock_delete_tasks.assert_called_with(
        hamcrest.match_equality(
            hamcrest.has_property("key", self.command.key)))
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "ExecuteFailed"
    }
    mock_command_event_type_count.Increment.assert_has_calls(
        [mock.call(expected_metric_fields)
        ] * command_manager.MAX_ERROR_COUNT_BASE)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(command_manager, "DeleteTasks")
  @mock.patch.object(command_manager, "RescheduleTask")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_InvocationInitiated(
      self, mock_notify, mock_reschedule, mock_delete_tasks,
      mock_command_event_type_count):
    """Should update command state for InvocationInitiated events.

    State should become RUNNING if it isn't already.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_reschedule: mock function to reschedule tasks.
      mock_delete_tasks: mock function to delete tasks.
      mock_command_event_type_count: mock command event type count metric
    """
    _, request_id, _, command_id = self.command.key.flat()
    invocation_started_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "InvocationInitiated")
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertNotEqual(common.CommandState.RUNNING, queried_command.state)
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", state=common.CommandState.UNKNOWN)
    command_event_handler.ProcessCommandEvent(invocation_started_event)
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.RUNNING, queried_command.state)
    self.assertFalse(mock_reschedule.called)
    mock_notify.assert_called_with(request_id)
    self.assertFalse(mock_delete_tasks.called)
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationInitiated"
    }
    mock_command_event_type_count.Increment.assert_called_once_with(
        expected_metric_fields)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(command_manager, "DeleteTasks")
  @mock.patch.object(command_manager, "RescheduleTask")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_InvocationStarted(
      self, mock_notify, mock_reschedule, mock_delete_tasks,
      mock_command_event_type_count):
    """Should update command state for InvocationStarted events.

    State should become RUNNING if it isn't already.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_reschedule: mock function to reschedule tasks.
      mock_delete_tasks: mock function to delete tasks.
      mock_command_event_type_count: mock command event type count metric
    """
    _, request_id, _, command_id = self.command.key.flat()
    invocation_started_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "InvocationStarted")
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertNotEqual(common.CommandState.RUNNING, queried_command.state)
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", state=common.CommandState.UNKNOWN)
    command_event_handler.ProcessCommandEvent(invocation_started_event)
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.RUNNING, queried_command.state)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(1, len(attempts))
    self.assertEqual(["0123456789ABCDEF"], attempts[0].device_serials)
    self.assertFalse(mock_reschedule.called)
    mock_notify.assert_called_with(request_id)
    self.assertFalse(mock_delete_tasks.called)
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationStarted"
    }
    mock_command_event_type_count.Increment.assert_called_once_with(
        expected_metric_fields)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(command_manager, "DeleteTasks")
  @mock.patch.object(command_manager, "RescheduleTask")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_multiDevice(
      self, mock_notify, mock_reschedule, mock_delete_tasks,
      mock_command_event_type_count):
    """Should populate multiple devices."""
    _, request_id, _, command_id = self.command.key.flat()
    invocation_started_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "InvocationStarted",
        device_serials=["d1", "d2"])
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertNotEqual(common.CommandState.RUNNING, queried_command.state)
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", state=common.CommandState.UNKNOWN)
    command_event_handler.ProcessCommandEvent(invocation_started_event)
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.RUNNING, queried_command.state)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(1, len(attempts))
    self.assertEqual(["d1", "d2"], attempts[0].device_serials)
    self.assertFalse(mock_reschedule.called)
    mock_notify.assert_called_with(request_id)
    self.assertFalse(mock_delete_tasks.called)
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationStarted"
    }
    mock_command_event_type_count.Increment.assert_called_once_with(
        expected_metric_fields)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(command_manager, "DeleteTasks")
  @mock.patch.object(command_manager, "RescheduleTask")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_TestRunInProgress(
      self, mock_notify, mock_reschedule, mock_delete_tasks,
      mock_command_event_type_count):
    """Should update command state for TestRunInProgress events.

    State should become RUNNING if it isn't already.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_reschedule: mock function to reschedule tasks.
      mock_delete_tasks: mock function to delete tasks.
      mock_command_event_type_count: mock command event type count metric
    """
    _, request_id, _, command_id = self.command.key.flat()
    test_run_started_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "TestRunInProgress")
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertNotEqual(common.CommandState.RUNNING, queried_command.state)
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", state=common.CommandState.UNKNOWN)
    command_event_handler.ProcessCommandEvent(test_run_started_event)
    queried_command = command_manager.GetCommand(request_id, command_id)

    self.assertEqual(common.CommandState.RUNNING, queried_command.state)
    self.assertFalse(mock_reschedule.called)
    mock_notify.assert_called_with(request_id)
    self.assertFalse(mock_delete_tasks.called)
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "TestRunInProgress"
    }
    mock_command_event_type_count.Increment.assert_called_once_with(
        expected_metric_fields)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(command_manager, "DeleteTasks")
  @mock.patch.object(command_manager, "RescheduleTask")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_InvocationEnded(
      self, mock_notify, mock_reschedule, mock_delete_tasks,
      mock_command_event_type_count):
    """Should update command state for InvocationEnded events.

    State should become RUNNING if it isn't already.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_reschedule: mock function to reschedule tasks.
      mock_delete_tasks: mock function to delete tasks.
      mock_command_event_type_count: mock command event type count metric
    """
    _, request_id, _, command_id = self.command.key.flat()
    invocation_ended_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "InvocationEnded")
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertNotEqual(common.CommandState.RUNNING, queried_command.state)
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", state=common.CommandState.UNKNOWN)
    command_event_handler.ProcessCommandEvent(invocation_ended_event)
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.RUNNING, queried_command.state)
    self.assertFalse(mock_reschedule.called)
    mock_notify.assert_called_with(request_id)
    self.assertFalse(mock_delete_tasks.called)
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationEnded"
    }
    mock_command_event_type_count.Increment.assert_called_once_with(
        expected_metric_fields)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(command_manager, "DeleteTasks")
  @mock.patch.object(command_manager, "RescheduleTask")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_InvocationCompleted(
      self, mock_notify, mock_reschedule, mock_delete_tasks,
      mock_command_event_type_count):
    """Should complete command state for InvocationCompleted events.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_reschedule: mock function to reschedule tasks.
      mock_delete_tasks: mock function to delete tasks.
      mock_command_event_type_count: mock command event type count metric
    """
    _, request_id, _, command_id = self.command.key.flat()
    invocation_completed_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "aid", "InvocationCompleted")
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertNotEqual(common.CommandState.COMPLETED, queried_command.state)
    command_event_test_util.CreateCommandAttempt(
        self.command, "aid", state=common.CommandState.UNKNOWN)
    command_event_handler.ProcessCommandEvent(invocation_completed_event)
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.COMPLETED, queried_command.state)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(1, len(attempts))
    self.assertEqual("summary", attempts[0].summary)
    self.assertEqual(1000, attempts[0].total_test_count)
    self.assertEqual(100, attempts[0].failed_test_count)
    self.assertEqual(10, attempts[0].failed_test_run_count)

    self.assertFalse(mock_reschedule.called)
    mock_notify.assert_called_with(request_id)
    mock_delete_tasks.assert_called_with(
        hamcrest.match_equality(
            hamcrest.has_property("key", self.command.key)))
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationCompleted"
    }
    mock_command_event_type_count.Increment.assert_called_once_with(
        expected_metric_fields)

  @mock.patch.object(command_manager, "DeleteTasks")
  @mock.patch.object(command_manager, "DeleteTask")
  @mock.patch.object(command_manager, "RescheduleTask")
  @mock.patch.object(command_manager, "GetActiveTaskCount")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_InvocationCompleted_multipleRuns(
      self, mock_notify, mock_get_active_task_count, mock_reschedule,
      mock_delete_task, mock_delete_tasks):
    """Should complete command state for InvocationCompleted events.

    It should only be set as COMPLETE if all runs are executed.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_get_active_task_count: mock Command.GetActiveTaskCount function.
      mock_reschedule: mock Command.RescheduleTask function
      mock_delete_task: mock Command.DeleteTask function.
      mock_delete_tasks: mock Command.DeleteTasks function.
    """
    run_count = 3
    _, request_id, _, command_id = self.command.key.flat()
    self.command.run_count = run_count
    self.command.put()

    for i in range(run_count):
      command_event_test_util.CreateCommandAttempt(
          self.command, str(i), state=common.CommandState.UNKNOWN)
      invocation_completed_event = (
          command_event_test_util.CreateTestCommandEvent(
              request_id, command_id, str(i), "InvocationCompleted",
              run_index=i))
      queried_command = command_manager.GetCommand(request_id, command_id)
      self.assertNotEqual(common.CommandState.COMPLETED, queried_command.state)
      mock_get_active_task_count.return_value = run_count - i
      command_event_handler.ProcessCommandEvent(invocation_completed_event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.COMPLETED, queried_command.state)
    mock_get_active_task_count.assert_called_with(
        hamcrest.match_equality(
            hamcrest.has_property("key", self.command.key)))
    mock_delete_task.assert_has_calls(
        [mock.call("%s-%s-%d" % (request_id, command_id, 0)),
         mock.call("%s-%s-%d" % (request_id, command_id, 1))])
    mock_notify.assert_called_with(request_id)
    mock_delete_tasks.assert_called_with(
        hamcrest.match_equality(
            hamcrest.has_property("key", self.command.key)))

  @mock.patch.object(command_manager, "DeleteTasks")
  @mock.patch.object(command_manager, "DeleteTask")
  @mock.patch.object(command_manager, "RescheduleTask")
  @mock.patch.object(command_manager, "GetActiveTaskCount")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_InvocationCompleted_multipleRuns_20(
      self, mock_notify, mock_get_active_task_count, mock_reschedule,
      mock_delete_task, mock_delete_tasks):
    """Should complete command state for InvocationCompleted events.

    This tests a case when a run count is greater than
    command_manager.MAX_TASK_COUNT.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_get_active_task_count: mock Command.GetActiveTaskCount function.
      mock_reschedule: mock Command.RescheduleTask function
      mock_delete_task: mock Command.DeleteTask function.
      mock_delete_tasks: mock Command.DeleteTasks function.
    """
    run_count = 100
    _, request_id, _, command_id = self.command.key.flat()
    self.command.run_count = run_count
    self.command.put()

    attempt_id = 0
    for i in range(run_count):
      command_event_test_util.CreateCommandAttempt(
          self.command, str(i), state=common.CommandState.UNKNOWN)

    for i in range(run_count - command_manager.MAX_TASK_COUNT):
      invocation_completed_event = (
          command_event_test_util.CreateTestCommandEvent(
              request_id, command_id, str(attempt_id),
              "InvocationCompleted", run_index=0))
      attempt_id += 1
      # It should be marked as error at the MAX_ERROR_COUNT attempt.
      queried_command = command_manager.GetCommand(request_id, command_id)
      self.assertNotEqual(common.CommandState.COMPLETED, queried_command.state)
      mock_get_active_task_count.return_value = command_manager.MAX_TASK_COUNT
      command_event_handler.ProcessCommandEvent(invocation_completed_event)

    for i in range(command_manager.MAX_TASK_COUNT):
      invocation_completed_event = (
          command_event_test_util.CreateTestCommandEvent(
              request_id, command_id, str(attempt_id),
              "InvocationCompleted", run_index=i))
      attempt_id += 1
      queried_command = command_manager.GetCommand(request_id, command_id)
      self.assertNotEqual(common.CommandState.COMPLETED, queried_command.state)
      mock_get_active_task_count.return_value = (
          command_manager.MAX_TASK_COUNT - i)
      command_event_handler.ProcessCommandEvent(invocation_completed_event)

    queried_command = command_manager.GetCommand(request_id, command_id)

    self.assertEqual(common.CommandState.COMPLETED, queried_command.state)
    mock_get_active_task_count.assert_called_with(
        hamcrest.match_equality(
            hamcrest.has_property("key", self.command.key)))

    mock_reschedule.assert_has_calls([
        mock.call("%s-%s-%d" % (request_id, command_id, 0),
                  hamcrest.match_equality(
                      hamcrest.has_property("key", self.command.key)))
    ] * (run_count - command_manager.MAX_TASK_COUNT))
    mock_delete_task.assert_has_calls([
        mock.call("%s-%s-%d" % (request_id, command_id, i))
        for i in range(command_manager.MAX_TASK_COUNT - 1)
    ])
    mock_notify.assert_called_with(request_id)
    mock_delete_tasks.assert_called_with(
        hamcrest.match_equality(
            hamcrest.has_property("key", self.command.key)))

  @mock.patch.object(command_manager, "DeleteTasks")
  @mock.patch.object(command_manager, "DeleteTask")
  @mock.patch.object(command_manager, "RescheduleTask")
  @mock.patch.object(command_manager, "GetActiveTaskCount")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_InvocationCompleted_multipleRunsWithErrors(
      self, mock_notify, mock_get_active_task_count, mock_reschedule,
      mock_delete_task, mock_delete_tasks):
    """Should complete command state for InvocationCompleted events.

    This tests a case when a run count is greater than
    command_manager.MAX_TASK_COUNT.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_get_active_task_count: mock Command.GetActiveTaskCount function.
      mock_reschedule: mock Command.RescheduleTask function
      mock_delete_task: mock Command.DeleteTask function.
      mock_delete_tasks: mock Command.DeleteTasks function.
    """
    run_count = 100
    _, request_id, _, command_id = self.command.key.flat()
    self.command.run_count = run_count
    self.command.put()

    max_error_count = (
        command_manager.MAX_ERROR_COUNT_BASE +
        int(run_count * command_manager.MAX_ERROR_COUNT_RATIO))
    for i in range(max_error_count):
      command_event_test_util.CreateCommandAttempt(
          self.command, str(i), state=common.CommandState.UNKNOWN)
      invocation_completed_event = (
          command_event_test_util.CreateTestCommandEvent(
              request_id, command_id, str(i), "InvocationCompleted",
              error="error"))
      # It should be marked as error at the max error count attempts.
      queried_command = command_manager.GetCommand(request_id, command_id)
      self.assertNotEqual(common.CommandState.ERROR, queried_command.state)
      mock_get_active_task_count.return_value = command_manager.MAX_TASK_COUNT
      command_event_handler.ProcessCommandEvent(invocation_completed_event)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.ERROR, queried_command.state)
    mock_get_active_task_count.assert_called_with(
        hamcrest.match_equality(
            hamcrest.has_property("key", self.command.key)))
    mock_reschedule.assert_has_calls([
        mock.call("%s-%s-0" % (request_id, command_id),
                  hamcrest.match_equality(
                      hamcrest.has_property("key", self.command.key)))
    ] * (max_error_count - 1))
    mock_notify.assert_called_with(request_id)
    mock_delete_tasks.assert_called_with(
        hamcrest.match_equality(
            hamcrest.has_property("key", self.command.key)))

  @mock.patch.object(command_manager, "DeleteTasks")
  @mock.patch.object(command_manager, "RescheduleTask")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_UnknownEvent(
      self, mock_notify, mock_reschedule, mock_delete_tasks):
    """Should update command state for unknown events.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_reschedule: mock function to reschedule tasks.
      mock_delete_tasks: mock function to delete tasks.
    """
    _, request_id, _, command_id = self.command.key.flat()
    unknown_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "SomeRandomInexistentType")
    command_event_handler.ProcessCommandEvent(unknown_event)
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.UNKNOWN, queried_command.state)
    self.assertFalse(mock_reschedule.called)
    self.assertFalse(mock_delete_tasks.called)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(command_manager, "DeleteTasks")
  @mock.patch.object(command_manager, "RescheduleTask")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_FatalEvent(
      self, mock_notify, mock_reschedule, mock_delete_tasks,
      mock_command_event_type_count):
    """Should not reschedule a configuration error, request should error out.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_reschedule: mock function to reschedule tasks.
      mock_delete_tasks: mock function to delete tasks.
      mock_command_event_type_count: mock command event type count metric
    """
    _, request_id, _, command_id = self.command.key.flat()
    fatal_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "ConfigurationError")
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertNotEqual(common.CommandState.FATAL, queried_command.state)
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", state=common.CommandState.UNKNOWN)
    command_event_handler.ProcessCommandEvent(fatal_event)
    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.FATAL, queried_command.state)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(1, len(attempts))

    self.assertFalse(mock_reschedule.called)
    mock_notify.assert_called_with(request_id)
    mock_delete_tasks.assert_called_with(
        hamcrest.match_equality(
            hamcrest.has_property("key", self.command.key)))
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "ConfigurationError"
    }
    mock_command_event_type_count.Increment.assert_called_once_with(
        expected_metric_fields)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(command_manager, "DeleteTasks")
  @mock.patch.object(command_manager, "RescheduleTask")
  @mock.patch.object(command_manager, "GetActiveTaskCount")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_TFShutdown(
      self, mock_notify, mock_get_active_task_count, mock_reschedule,
      mock_delete_tasks, mock_command_event_type_count):
    """Mark command events that were terminated by TF shutdown as CANCELED.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_get_active_task_count: mock Command.GetActiveTaskCount function.
      mock_reschedule: mock function to reschedule tasks.
      mock_delete_tasks: mock function to delete tasks.
      mock_command_event_type_count: mock command event type count metric
    """
    _, request_id, _, command_id = self.command.key.flat()
    error = "RunInterruptedException: TF is shutting down."
    cancelled_events = [
        command_event_test_util.CreateTestCommandEvent(
            request_id,
            command_id,
            str(i),
            "InvocationCompleted",
            data={"error": error})
        for i in range(3)
    ]

    mock_get_active_task_count.return_value = 0
    counter = 0
    for cancelled_event in cancelled_events:
      command_event_test_util.CreateCommandAttempt(
          self.command, str(counter), state=common.CommandState.UNKNOWN)
      counter += 1
      command_event_handler.ProcessCommandEvent(cancelled_event)

    # After three cancelled attempts, the command should still be queued.
    queried_command = self.command.key.get()
    self.assertEqual(common.CommandState.QUEUED, queried_command.state)
    attempts = command_manager.GetCommandAttempts(request_id, command_id)
    self.assertEqual(3, len(attempts))
    self.assertEqual(3, mock_reschedule.call_count)
    mock_notify.assert_called_with(request_id)
    expected_metric_fields = {
        metric.METRIC_FIELD_HOSTNAME: "hostname",
        metric.METRIC_FIELD_TYPE: "InvocationCompleted"
    }
    mock_command_event_type_count.Increment.assert_has_calls(
        [mock.call(expected_metric_fields)] * 3)

  @mock.patch.object(metric, "command_event_type_count")
  @mock.patch.object(command_manager, "DeleteTasks")
  @mock.patch.object(command_manager, "RescheduleTask")
  @mock.patch.object(request_manager, "NotifyRequestState")
  def testProcessCommandEvent_ignoreOutOfDateEvent(
      self, mock_notify, mock_reschedule, mock_delete_tasks,
      mock_command_event_type_count):
    """Should complete command state for InvocationCompleted events.

    Args:
      mock_notify: mock function to notify request state changes.
      mock_reschedule: mock function to reschedule tasks.
      mock_delete_tasks: mock function to delete tasks.
      mock_command_event_type_count: mock command event type count metric
    """
    command_event_test_util.CreateCommandAttempt(
        self.command, "0", state=common.CommandState.UNKNOWN)
    _, request_id, _, command_id = self.command.key.flat()
    invocation_completed_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "InvocationCompleted",
        time=TIMESTAMP_INT + 60)
    invocation_started_event = command_event_test_util.CreateTestCommandEvent(
        request_id, command_id, "0", "InvocationStarted",
        time=TIMESTAMP_INT + 30)

    queried_command = command_manager.GetCommand(request_id, command_id)
    self.assertEqual(common.CommandState.UNKNOWN, queried_command.state)

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

    attempts = command_manager.GetCommandAttempts(
        request_id, command_id)
    self.assertEqual(1, len(attempts))
    self.assertEqual("summary", attempts[0].summary)
    self.assertEqual(1000, attempts[0].total_test_count)
    self.assertEqual(100, attempts[0].failed_test_count)

    self.assertFalse(mock_reschedule.called)
    mock_notify.assert_called_with(request_id)
    mock_delete_tasks.assert_called_with(
        hamcrest.match_equality(
            hamcrest.has_property("key", self.command.key)))
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
