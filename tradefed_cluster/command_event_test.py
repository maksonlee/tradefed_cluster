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

"""Tests for command_event."""

import unittest

import mock

from tradefed_cluster import command_error_type_config
from tradefed_cluster import command_event
from tradefed_cluster import command_event_test_util
from tradefed_cluster import common


REQUEST_ID = "1001"
COMMAND_ID = "1"
ATTEMPT_ID = "attempt_id"


class CommandEventTest(unittest.TestCase):
  """Unit test for CommandEvent."""

  def testInit(self):
    event = command_event_test_util.CreateTestCommandEvent(
        REQUEST_ID,
        COMMAND_ID,
        ATTEMPT_ID,
        common.InvocationEventType.INVOCATION_COMPLETED,
        invocation_status={
            "test_group_statuses": [{
                "name": "test1"
            }, {
                "name": "test2"
            }]
        },
        device_serials=["s1", "s2"],
        device_lost_detected=1)
    self.assertEqual("%s-%s-0" % (REQUEST_ID, COMMAND_ID),
                     event.task_id)
    self.assertEqual(REQUEST_ID, event.request_id)
    self.assertEqual(COMMAND_ID, event.command_id)
    self.assertEqual(ATTEMPT_ID, event.attempt_id)
    self.assertEqual(common.InvocationEventType.INVOCATION_COMPLETED,
                     event.type)
    self.assertEqual(command_event_test_util.TIMESTAMP, event.time)
    self.assertEqual("hostname", event.hostname)
    self.assertEqual(["s1", "s2"], event.device_serials)
    self.assertEqual("summary", event.summary)
    self.assertEqual(1000, event.total_test_count)
    self.assertEqual(100, event.failed_test_count)
    self.assertEqual(900, event.passed_test_count)
    self.assertEqual(10, event.failed_test_run_count)
    self.assertEqual(1, event.device_lost_detected)
    self.assertEqual(command_event_test_util.TIMESTAMP, event.attempt_end_time)
    self.assertEqual(common.CommandState.COMPLETED, event.attempt_state)
    self.assertIsNone(event.error)
    self.assertIsNone(event.error_reason)
    self.assertIsNone(event.error_type)
    self.assertEqual(
        "test1", event.invocation_status.test_group_statuses[0].name)
    self.assertEqual(
        "test2", event.invocation_status.test_group_statuses[1].name)

  @mock.patch.object(command_error_type_config, "GetConfig")
  def testInit_withError(self, get_config):
    get_config.return_value = ("error_reason", "error_type")
    event = command_event_test_util.CreateTestCommandEvent(
        REQUEST_ID, COMMAND_ID, ATTEMPT_ID,
        common.InvocationEventType.INVOCATION_COMPLETED,
        error="error")
    self.assertEqual(common.CommandState.ERROR, event.attempt_state)
    self.assertEqual("error", event.error)
    self.assertEqual("error_reason", event.error_reason)
    self.assertEqual("error_type", event.error_type)
    self.assertEqual(command_event_test_util.TIMESTAMP, event.attempt_end_time)

  @mock.patch.object(command_error_type_config, "GetConfig")
  def testInit_allocationFail(self, get_config):
    get_config.return_value = ("error_reason", "error_type")
    event = command_event_test_util.CreateTestCommandEvent(
        REQUEST_ID, COMMAND_ID, ATTEMPT_ID,
        common.InvocationEventType.ALLOCATION_FAILED)
    self.assertEqual(common.CommandState.CANCELED, event.attempt_state)
    self.assertEqual(
        "Device allocation failed: Device did not meet command requirements",
        event.error)
    self.assertEqual("error_reason", event.error_reason)
    self.assertEqual("error_type", event.error_type)

  def testInit_configurationError(self):
    event = command_event_test_util.CreateTestCommandEvent(
        REQUEST_ID, COMMAND_ID, ATTEMPT_ID,
        common.InvocationEventType.CONFIGURATION_ERROR)
    self.assertEqual(common.CommandState.FATAL, event.attempt_state)

  def testInit_fetchFailed(self):
    event = command_event_test_util.CreateTestCommandEvent(
        REQUEST_ID, COMMAND_ID, ATTEMPT_ID,
        common.InvocationEventType.FETCH_FAILED)
    self.assertEqual(common.CommandState.ERROR, event.attempt_state)

  def testInit_executeFailed(self):
    event = command_event_test_util.CreateTestCommandEvent(
        REQUEST_ID, COMMAND_ID, ATTEMPT_ID,
        common.InvocationEventType.EXECUTE_FAILED)
    self.assertEqual(common.CommandState.ERROR, event.attempt_state)

  def testInit_invocationInitiated(self):
    event = command_event_test_util.CreateTestCommandEvent(
        REQUEST_ID, COMMAND_ID, ATTEMPT_ID,
        common.InvocationEventType.INVOCATION_INITIATED)
    self.assertEqual(command_event_test_util.TIMESTAMP,
                     event.attempt_start_time)
    self.assertEqual(common.CommandState.RUNNING, event.attempt_state)

  def testInit_invocationStarted(self):
    event = command_event_test_util.CreateTestCommandEvent(
        REQUEST_ID, COMMAND_ID, ATTEMPT_ID,
        common.InvocationEventType.INVOCATION_STARTED)
    self.assertEqual(command_event_test_util.TIMESTAMP,
                     event.attempt_start_time)
    self.assertEqual(common.CommandState.RUNNING, event.attempt_state)

  def testInit_testRunProgress(self):
    event = command_event_test_util.CreateTestCommandEvent(
        REQUEST_ID, COMMAND_ID, ATTEMPT_ID,
        common.InvocationEventType.TEST_RUN_IN_PROGRESS)
    self.assertEqual(command_event_test_util.TIMESTAMP,
                     event.attempt_start_time)
    self.assertEqual(common.CommandState.RUNNING, event.attempt_state)

  def testInit_invocationEnded(self):
    event = command_event_test_util.CreateTestCommandEvent(
        REQUEST_ID, COMMAND_ID, ATTEMPT_ID,
        common.InvocationEventType.INVOCATION_ENDED)
    self.assertEqual(command_event_test_util.TIMESTAMP,
                     event.attempt_start_time)
    self.assertEqual(common.CommandState.RUNNING, event.attempt_state)

  @mock.patch.object(command_error_type_config, "GetConfig")
  def testInit_tfShutDown(self, get_config):
    get_config.return_value = ("error_reason", "error_type")
    error = "RunInterruptedException: Tradefed is shutting down."
    event = command_event_test_util.CreateTestCommandEvent(
        REQUEST_ID, COMMAND_ID, ATTEMPT_ID,
        common.InvocationEventType.INVOCATION_COMPLETED,
        error=error)
    self.assertEqual(common.CommandState.CANCELED, event.attempt_state)

  def testTruncate(self):
    value = "12345678"
    self.assertEqual(value, command_event.Truncate(value))
    self.assertEqual(value, command_event.Truncate(value, 8))
    self.assertEqual("1", command_event.Truncate(value, 1))
    self.assertEqual("12345", command_event.Truncate(value, 5))

  def testTruncate_empty(self):
    self.assertEqual("", command_event.Truncate(""))
    self.assertIsNone(command_event.Truncate(None))


if __name__ == "__main__":
  unittest.main()
