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

"""Tests for Notifier Handler."""

import json
import unittest
import zlib

from googleapiclient import errors
import mock


from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import notification_handler
from tradefed_cluster import request_manager
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.services import task_scheduler


class NotificationHandlerTest(testbed_dependent_test.TestbedDependentTest):

  def testNotifyEmptyList(self):
    notification_handler.NotifyPendingRequestStateChanges()
    tasks = self.mock_task_scheduler.GetTasks()
    self.assertEqual(0, len(tasks))

  def testDoNotProcessRequest(self):
    request = datastore_test_util.CreateRequest(
        request_id="1",
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        state=common.RequestState.UNKNOWN,
        notify_state_change=False)
    request.put()
    notification_handler.NotifyPendingRequestStateChanges()
    tasks = self.mock_task_scheduler.GetTasks()
    self.assertEqual(0, len(tasks))

  def testProcessDirtyRequest(self):
    request = datastore_test_util.CreateRequest(
        request_id="1",
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        state=common.RequestState.UNKNOWN,
        notify_state_change=True)
    request.put()
    notification_handler.NotifyPendingRequestStateChanges()
    tasks = self.mock_task_scheduler.GetTasks()
    self.assertEqual(1, len(tasks))

  def testNotifyNoDirtyRequest(self):
    request = datastore_test_util.CreateRequest(
        request_id="1",
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        state=common.RequestState.UNKNOWN,
        notify_state_change=False)
    request.put()
    notification_handler.NotifyRequestState(request_id="1")
    tasks = self.mock_task_scheduler.GetTasks()
    self.assertEqual(0, len(tasks))

  @mock.patch.object(task_scheduler, "AddTask")
  def testNotifyNoDirtyRequest_force(self, mock_add_task):
    request = datastore_test_util.CreateRequest(
        request_id="1",
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        state=common.RequestState.UNKNOWN,
        notify_state_change=False)
    request.put()
    notification_handler.NotifyRequestState(request_id="1", force=True)
    mock_add_task.assert_called_once_with(
        queue_name=common.OBJECT_EVENT_QUEUE,
        payload=mock.ANY,
        transactional=True,
        ndb_store_oversized_task=True)
    payload = zlib.decompress(mock_add_task.call_args[1]["payload"])
    task = json.loads(payload)
    self.assertEqual("1", task["request_id"])

  @mock.patch.object(task_scheduler, "AddTask")
  def testNotifyDirtyRequest(self, mock_add_task):
    request = datastore_test_util.CreateRequest(
        request_id="1",
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        state=common.RequestState.UNKNOWN,
        notify_state_change=True)
    request.put()
    notification_handler.NotifyRequestState(request_id="1")
    mock_add_task.assert_called_once_with(
        queue_name=common.OBJECT_EVENT_QUEUE,
        payload=mock.ANY,
        transactional=True,
        ndb_store_oversized_task=True)
    payload = zlib.decompress(mock_add_task.call_args[1]["payload"])
    task = json.loads(payload)
    self.assertEqual("1", task["request_id"])
    # The dirty bit should be set.
    r = request_manager.GetRequest("1")
    self.assertFalse(r.notify_state_change)

  @mock.patch.object(task_scheduler, "AddTask")
  def testNotifyDirtyRequest_Error(self, add):
    request = datastore_test_util.CreateRequest(
        request_id="1",
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        state=common.RequestState.UNKNOWN,
        notify_state_change=True)
    request.put()
    # Make sure that notify fails.
    add.side_effect = errors.Error()
    try:
      notification_handler.NotifyRequestState(request_id="1")
      self.fail("apiclient.errors.Error should have been thrown")
    except errors.Error:
      # expected failure
      pass
    # Since the pub sub failed, we should have the dirty bit still set.
    r = request_manager.GetRequest("1")
    self.assertTrue(r.notify_state_change)


if __name__ == "__main__":
  unittest.main()
