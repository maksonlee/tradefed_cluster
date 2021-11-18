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

"""Unit tests for request_manager."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import datetime
import json
import unittest
import zlib

import mock
from protorpc import protojson
from six.moves import range

from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import request_manager
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.services import task_scheduler
from tradefed_cluster.util import ndb_shim as ndb


REQUEST_ID = "1001"
COMMAND_ID = "1010"
ATTEMPT_ID = "1100"


class RequestManagerTest(testbed_dependent_test.TestbedDependentTest):

  START_TIME = datetime.datetime(2015, 1, 1)
  END_TIME = datetime.datetime(2015, 5, 7)
  START_TIME_ALT = datetime.datetime(2016, 1, 1)
  END_TIME_ALT = datetime.datetime(2016, 5, 7)

  def setUp(self):
    testbed_dependent_test.TestbedDependentTest.setUp(self)
    self.request = datastore_test_util.CreateRequest(
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id=REQUEST_ID)
    datastore_test_util.CreateRequest(
        user="foo",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="short command line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id="2")
    datastore_test_util.CreateRequest(
        user="bar",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="long command line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id="3")
    self._request_id = int(REQUEST_ID)
    self._command_id = int(COMMAND_ID)
    self._attempt_id = int(ATTEMPT_ID)
    self.v1_result_link = ("http://sponge.corp.example.com/invocation?"
                           "tab=Test+Cases&show=FAILED&id=12345678-abcd")
    self.v2_result_link = ("https://g3c.corp.example.com/results/invocations/"
                           "b585e699-ae52-4c9f-b7d2-4a8b2d35c72f")

  def testAddToQueue(self):
    request = ndb.Key(datastore_entities.Request, REQUEST_ID,
                      namespace=common.NAMESPACE).get(use_cache=False)
    request_manager.AddToQueue(request)
    tasks = self.mock_task_scheduler.GetTasks()
    self.assertEqual(len(tasks), 1)
    request_task = json.loads(zlib.decompress(tasks[0].payload))
    self.assertEqual(REQUEST_ID, request_task["id"])

  @mock.patch.object(task_scheduler, "DeleteTask")
  def testDeleteFromQueue(self, mock_delete):
    request_manager.DeleteFromQueue(REQUEST_ID)

    mock_delete.assert_called_once_with(
        request_manager.REQUEST_QUEUE, REQUEST_ID)

  @mock.patch.object(common, "Now")
  def testCreateRequestEventMessage(self, mock_now):
    mock_now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id="1234567")
    request.state = common.RequestState.CANCELED
    request.put()
    command = datastore_entities.Command(
        parent=request.key,
        command_line="command_line",
        cluster="cluster",
        run_target="run_target",
        run_count=2,
        state=common.CommandState.CANCELED,
        start_time=self.START_TIME,
        end_time=self.END_TIME)
    command.put()
    command_attempt = datastore_entities.CommandAttempt(
        parent=command.key,
        task_id="task_id",
        attempt_id="attempt_id",
        state=common.CommandState.CANCELED,
        hostname="hostname",
        device_serial="device_serial",
        start_time=self.START_TIME,
        end_time=self.END_TIME,
        status="status",
        error="error",
        summary="summary")
    command_attempt.put()

    actual = request_manager.CreateRequestEventMessage(request)

    expected = api_messages.RequestEventMessage(
        type=common.ObjectEventType.REQUEST_STATE_CHANGED,
        request_id="1234567",
        new_state=common.RequestState.CANCELED,
        request=datastore_entities.ToMessage(request),
        summary="Attempt attempt_id: error (CANCELED)",
        total_run_time_sec=int(
            (self.END_TIME - self.START_TIME).total_seconds()),
        event_time=self.END_TIME,
        total_test_count=0,
        failed_test_count=0,
        passed_test_count=0,
        failed_test_run_count=0,
        device_lost_detected=0,
    )

    self.assertEqual(expected, actual)

  @mock.patch.object(task_scheduler, "DeleteTask")
  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testCancelExistRequest(self, now, mock_add, mock_delete):
    now.return_value = self.END_TIME

    request_manager.CancelRequest(REQUEST_ID, common.CancelReason.QUEUE_TIMEOUT)

    persisted_request = request_manager.GetRequest(REQUEST_ID)
    self.assertEqual(common.RequestState.CANCELED, persisted_request.state)
    self.assertEqual(common.CancelReason.QUEUE_TIMEOUT,
                     persisted_request.cancel_reason)
    self._AssertRequestEventMessageIsQueued(
        request_manager.CreateRequestEventMessage(persisted_request), mock_add)
    mock_delete.assert_called_once_with(
        request_manager.REQUEST_QUEUE, REQUEST_ID)

  @mock.patch.object(request_manager, "DeleteFromQueue")
  def testCancelNonExistRequest(self, delete_from_queue):
    request_manager.CancelRequest("8888")
    self.assertFalse(delete_from_queue.called)

  def testGetRequests(self):
    """Tests getting multiple requests from request_manager.GetRequests()."""
    requests = request_manager.GetRequests()
    self.assertEqual(3, len(requests))

  def testGetRequests_withUser(self):
    """Tests request_manager.GetRequests() with a given user."""
    requests = request_manager.GetRequests(user="foo")
    self.assertEqual(1, len(requests))
    self.assertEqual("foo", requests[0].user)

    requests = request_manager.GetRequests(user="idontexist")
    self.assertEqual(0, len(requests))

  def testGetRequests_withState(self):
    """Tests request_manager.GetRequests() with a given state."""
    for request_id in range(1, 11):
      request = datastore_test_util.CreateRequest(
          user="user",
          command_infos=[
              datastore_entities.CommandInfo(
                  command_line="command_line",
                  cluster="cluster",
                  run_target="run_target")
          ],
          request_id=request_id)
      request.state = common.RequestState.CANCELED
      request.put()
    for request_id in range(11, 16):
      request = datastore_test_util.CreateRequest(
          user="user",
          command_infos=[
              datastore_entities.CommandInfo(
                  command_line="command_line",
                  cluster="cluster",
                  run_target="run_target")
          ],
          request_id=request_id)
      request.state = common.RequestState.QUEUED
      request.put()

    canceled = request_manager.GetRequests(state=common.RequestState.CANCELED)
    self.assertEqual(10, len(canceled))
    queued = request_manager.GetRequests(state=common.RequestState.QUEUED)
    self.assertEqual(5, len(queued))
    running = request_manager.GetRequests(state=common.RequestState.RUNNING)
    self.assertEqual(0, len(running))

  def testGetRequests_withUserAndState(self):
    """Tests request_manager.GetRequests() with a given user and state."""
    for request_id in range(1, 11):
      request = datastore_test_util.CreateRequest(
          user="user2",
          command_infos=[
              datastore_entities.CommandInfo(
                  command_line="command_line",
                  cluster="cluster",
                  run_target="run_target")
          ],
          request_id=request_id)
      request.state = common.RequestState.CANCELED
      request.put()
    for request_id in range(11, 16):
      request = datastore_test_util.CreateRequest(
          user="user1",
          command_infos=[
              datastore_entities.CommandInfo(
                  command_line="command_line",
                  cluster="cluster",
                  run_target="run_target")
          ],
          request_id=request_id)
      request.state = common.RequestState.RUNNING
      request.put()
    for request_id in range(16, 31):
      request = datastore_test_util.CreateRequest(
          user="user2",
          command_infos=[
              datastore_entities.CommandInfo(
                  command_line="command_line",
                  cluster="cluster",
                  run_target="run_target")
          ],
          request_id=request_id)
      request.state = common.RequestState.RUNNING
      request.put()

    requests = request_manager.GetRequests(
        user="user2",
        state=common.RequestState.RUNNING)
    self.assertEqual(15, len(requests))
    requests = request_manager.GetRequests(
        user="user1",
        state=common.RequestState.CANCELED)
    self.assertEqual(0, len(requests))

  def testGetRequestSummary(self):
    """Tests request_manager.GetRequestSummary()."""
    for _ in range(10):
      for state in [common.CommandState.UNKNOWN,
                    common.CommandState.RUNNING,
                    common.CommandState.QUEUED,
                    common.CommandState.CANCELED,
                    common.CommandState.COMPLETED,
                    common.CommandState.ERROR]:
        command = datastore_entities.Command(
            parent=self.request.key,
            command_line="command_line",
            cluster="cluster",
            run_target="run_target",
            run_count=2,
            state=state,
            start_time=self.START_TIME,
            end_time=self.END_TIME)
        command.put()

    summary = request_manager.GetRequestSummary(self.request.key.id())
    self.assertEqual(10, summary.running_count)
    self.assertEqual(10, summary.canceled_count)
    self.assertEqual(10, summary.completed_count)
    self.assertEqual(10, summary.error_count)
    self.assertEqual(60, summary.total_count)
    self.assertEqual(self.START_TIME, summary.start_time)
    self.assertEqual(self.END_TIME, summary.end_time)

  def testGetRequestSummary_multipleRequests(self):
    """Tests GetRequestSummary() with multiple requests. b/24210248."""
    datetime_0 = datetime.datetime(2015, 1, 1)
    datetime_1 = datetime.datetime(1989, 5, 7)
    datetime_2 = datetime.datetime(2015, 5, 6)
    datetime_3 = datetime.datetime(2015, 7, 18)

    request_1 = datastore_test_util.CreateRequest(
        user="user1",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id="1111")
    for _ in range(10):
      command_entity = datastore_entities.Command(
          parent=request_1.key,
          command_line="command_line",
          cluster="cluster",
          run_target="run_target",
          run_count=5,
          state=common.CommandState.RUNNING,
          start_time=datetime_0,
          end_time=datetime_2)
      command_entity.put()

    request_2 = datastore_test_util.CreateRequest(
        user="user2",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id="2222")
    for _ in range(5):
      command_entity = datastore_entities.Command(
          parent=request_2.key,
          command_line="command_line",
          cluster="cluster",
          run_target="run_target",
          run_count=5,
          state=common.CommandState.ERROR,
          start_time=datetime_1,
          end_time=datetime_3)
      command_entity.put()

    summary = request_manager.GetRequestSummary(request_1.key.id())
    self.assertEqual(10, summary.running_count)
    self.assertEqual(0, summary.error_count)
    self.assertEqual(datetime_0, summary.start_time)
    self.assertEqual(datetime_2, summary.end_time)
    summary = request_manager.GetRequestSummary(request_2.key.id())
    self.assertEqual(0, summary.running_count)
    self.assertEqual(5, summary.error_count)
    self.assertEqual(datetime_1, summary.start_time)
    self.assertEqual(datetime_3, summary.end_time)

  def _CreateRequestKey(self, request_id):
    """A help method to create request key from request_id."""
    request_id = str(request_id)
    key = ndb.Key(datastore_entities.Request, request_id,
                  namespace=common.NAMESPACE)
    return key

  @mock.patch.object(task_scheduler, "AddTask")
  def testEvaluateState_noCommands(self, mock_add):
    """Tests request_manager.EvaluateState() when there are no commands."""
    request = datastore_test_util.CreateRequest(
        user="user1",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id="1")
    self.assertEqual(common.RequestState.UNKNOWN, request.state)
    self.assertIsNone(request.start_time)
    self.assertIsNone(request.end_time)

    request, _ = request_manager.EvaluateState(request.key.id(), force=True)
    self.assertEqual(common.RequestState.UNKNOWN, request.state)
    self.assertIsNone(request.start_time)
    self.assertIsNone(request.end_time)
    # No state change. Should not notify.
    self.assertFalse(mock_add.called)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testEvaluateState_singleCommandCompletion(self, now, mock_add):
    """Tests updating a request with a single command up to completion."""
    now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        user="user1",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id="1")
    command_entity = datastore_entities.Command(
        parent=request.key,
        request_id=request.key.id(),
        command_line="command_line",
        cluster="cluster",
        run_target="run_target",
        run_count=5,
        state=common.CommandState.QUEUED,
        start_time=None,
        end_time=None)
    command_entity.put()

    # Command queued. Request should be updated to QUEUED state.
    self.assertEqual(common.RequestState.UNKNOWN, request.state)
    self.assertIsNone(request.start_time)
    self.assertIsNone(request.end_time)

    request, _ = request_manager.EvaluateState(request.key.id(), force=True)
    self.assertEqual(common.RequestState.QUEUED, request.state)
    self.assertIsNone(request.start_time)
    self.assertIsNone(request.end_time)
    self._AssertRequestEventMessageIsQueued(
        request_manager.CreateRequestEventMessage(request), mock_add)
    mock_add.reset_mock()

    # Command running. Request should be updated to RUNNING state.
    command_entity.state = common.CommandState.RUNNING
    command_entity.start_time = self.START_TIME
    command_entity.put()
    request, _ = request_manager.EvaluateState(request.key.id(), force=True)
    self.assertEqual(common.RequestState.RUNNING, request.state)
    self.assertEqual(self.START_TIME, request.start_time)
    self.assertIsNone(request.end_time)
    self._AssertRequestEventMessageIsQueued(
        request_manager.CreateRequestEventMessage(request), mock_add)
    mock_add.reset_mock()

    # Command completed. Request should be updated to COMPLETED state.
    command_entity.state = common.CommandState.COMPLETED
    command_entity.end_time = self.END_TIME
    command_entity.put()
    request, _ = request_manager.EvaluateState(request.key.id(), force=True)
    self.assertEqual(common.RequestState.COMPLETED, request.state)
    self.assertEqual(self.START_TIME, request.start_time)
    self.assertEqual(self.END_TIME, request.end_time)
    self._AssertRequestEventMessageIsQueued(
        request_manager.CreateRequestEventMessage(request), mock_add)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testEvaluateState_multiCommandCompletion(self, now, mock_add):
    """Tests updating a request with multiple commands up to completion."""
    now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        user="user1",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id="1")
    command_entity1 = datastore_entities.Command(
        parent=request.key,
        request_id=request.key.id(),
        command_hash="command_hash_complete1",
        command_line="command_line1",
        cluster="cluster",
        run_target="run_target",
        run_count=5,
        state=common.CommandState.QUEUED,
        start_time=None,
        end_time=None)
    command_entity1.put()
    command_entity2 = datastore_entities.Command(
        parent=request.key,
        request_id=request.key.id(),
        command_hash="command_hash_complete2",
        command_line="command_line2",
        cluster="cluster",
        run_target="run_target",
        run_count=5,
        state=common.CommandState.QUEUED,
        start_time=None,
        end_time=None)
    command_entity2.put()

    # Commands queued. Request should be updated to QUEUED state.
    request, _ = request_manager.EvaluateState(request.key.id(), force=True)
    self.assertEqual(common.RequestState.QUEUED, request.state)
    self.assertIsNone(request.start_time)
    self.assertIsNone(request.end_time)
    self._AssertRequestEventMessageIsQueued(
        request_manager.CreateRequestEventMessage(request), mock_add)
    mock_add.reset_mock()

    # Command1 running. Request should be updated to RUNNING state.
    command_entity1.state = common.CommandState.RUNNING
    command_entity1.start_time = self.START_TIME
    command_entity1.put()
    request, _ = request_manager.EvaluateState(request.key.id(), force=True)
    self.assertEqual(common.RequestState.RUNNING, request.state)
    self.assertEqual(self.START_TIME, request.start_time)
    self.assertIsNone(request.end_time)
    self._AssertRequestEventMessageIsQueued(
        request_manager.CreateRequestEventMessage(request), mock_add)
    mock_add.reset_mock()

    # Command1 completed. Request should be updated back to QUEUED state.
    command_entity1.state = common.CommandState.COMPLETED
    command_entity1.end_time = self.END_TIME
    command_entity1.put()
    request, _ = request_manager.EvaluateState(request.key.id(), force=True)
    self.assertEqual(common.RequestState.QUEUED, request.state)
    self.assertEqual(self.START_TIME, request.start_time)
    self.assertIsNone(request.end_time)
    self._AssertRequestEventMessageIsQueued(
        request_manager.CreateRequestEventMessage(request), mock_add)
    mock_add.reset_mock()

    # Command2 running. Request should be updated to RUNNING state.
    command_entity2.state = common.CommandState.RUNNING
    command_entity2.start_time = self.START_TIME
    command_entity2.put()
    request, _ = request_manager.EvaluateState(request.key.id(), force=True)
    self.assertEqual(common.RequestState.RUNNING, request.state)
    self.assertEqual(self.START_TIME, request.start_time)
    self.assertIsNone(request.end_time)
    self._AssertRequestEventMessageIsQueued(
        request_manager.CreateRequestEventMessage(request), mock_add)
    mock_add.reset_mock()

    # Command2 completed. Request should be updated to COMPLETED state.
    command_entity2.state = common.CommandState.COMPLETED
    command_entity2.end_time = self.END_TIME
    command_entity2.put()
    request, _ = request_manager.EvaluateState(request.key.id(), force=True)
    self.assertEqual(common.RequestState.COMPLETED, request.state)
    self.assertEqual(self.START_TIME, request.start_time)
    self.assertEqual(self.END_TIME, request.end_time)
    self._AssertRequestEventMessageIsQueued(
        request_manager.CreateRequestEventMessage(request), mock_add)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testEvaluateState_withCompleteCommand(self, now, mock_add):
    """Tests Request.UpdateState() when all commands are complete."""
    now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        user="user1",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id="1")
    command_entity = datastore_entities.Command(
        parent=request.key,
        request_id=request.key.id(),
        command_hash="command_hash_complete",
        command_line="command_line",
        cluster="cluster",
        run_target="run_target",
        run_count=5,
        state=common.CommandState.COMPLETED,
        start_time=self.START_TIME,
        end_time=self.END_TIME)
    command_entity.put()
    request, _ = request_manager.EvaluateState(request.key.id(), force=True)
    self.assertEqual(common.RequestState.COMPLETED, request.state)
    self.assertEqual(self.START_TIME, request.start_time)
    self.assertEqual(self.END_TIME, request.end_time)
    self._AssertRequestEventMessageIsQueued(
        request_manager.CreateRequestEventMessage(request), mock_add)

  @mock.patch.object(task_scheduler, "AddTask")
  def testEvaluateState_withCompleteCommand_notifyError(self, mock_add):
    """Tests request_manager.EvaluateState() when it gets a notify error."""
    request = datastore_test_util.CreateRequest(
        user="user1",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id="1")
    command_entity = datastore_entities.Command(
        parent=request.key,
        request_id=request.key.id(),
        command_hash="command_hash_complete",
        command_line="command_line",
        cluster="cluster",
        run_target="run_target",
        run_count=5,
        state=common.CommandState.COMPLETED,
        start_time=self.START_TIME,
        end_time=self.END_TIME)
    command_entity.put()
    mock_add.side_effect = ValueError()

    with self.assertRaises(ValueError):
      request_manager.EvaluateState(request.key.id(), force=True)

    mock_add.assert_called()
    request = request_manager.GetRequest(request.key.id())
    # Since we failed to notify in the first place, we still need to notify.
    self.assertTrue(request.notify_state_change)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testEvaluateState_withErrorCommand(self, now, mock_add):
    """Tests EvaluateState() when a command is in error state."""
    now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        user="user1",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id="1")
    command_complete = datastore_entities.Command(
        parent=request.key,
        request_id=request.key.id(),
        command_hash="command_hash_complete",
        command_line="command_line",
        cluster="cluster",
        run_target="run_target",
        run_count=5,
        state=common.CommandState.COMPLETED,
        start_time=self.START_TIME,
        end_time=self.END_TIME)
    command_complete.put()
    command_error = datastore_entities.Command(
        parent=request.key,
        request_id=request.key.id(),
        command_hash="command_hash_error",
        command_line="command_line",
        cluster="cluster",
        run_target="run_target",
        run_count=5,
        state=common.CommandState.ERROR,
        start_time=self.START_TIME,
        end_time=self.END_TIME)
    command_error.put()
    request, _ = request_manager.EvaluateState(request.key.id(), force=True)
    self.assertEqual(common.RequestState.ERROR, request.state)
    self.assertEqual(self.START_TIME, request.start_time)
    self.assertEqual(self.END_TIME, request.end_time)
    self._AssertRequestEventMessageIsQueued(
        request_manager.CreateRequestEventMessage(request), mock_add)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testEvaluteState_withCanceledCommand(self, now, mock_add):
    """Tests EvaluateState() when a command is in canceled state."""
    now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        user="user1",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id="1")
    command_complete = datastore_entities.Command(
        parent=request.key,
        request_id=request.key.id(),
        command_hash="command_hash_complete",
        command_line="command_line",
        cluster="cluster",
        run_target="run_target",
        run_count=5,
        state=common.CommandState.COMPLETED,
        start_time=self.START_TIME,
        end_time=self.END_TIME)
    command_complete.put()
    command_canceled = datastore_entities.Command(
        parent=request.key,
        request_id=request.key.id(),
        command_hash="command_hash_canceled",
        command_line="command_line",
        cluster="cluster",
        run_target="run_target",
        run_count=5,
        state=common.CommandState.CANCELED,
        start_time=self.START_TIME,
        end_time=self.END_TIME,
        cancel_reason=common.CancelReason.INVALID_REQUEST)
    command_canceled.put()
    request, _ = request_manager.EvaluateState(request.key.id(), force=True)
    self.assertEqual(common.RequestState.CANCELED, request.state)
    self.assertEqual(self.START_TIME, request.start_time)
    self.assertEqual(self.END_TIME, request.end_time)
    # command's cancel_reason is propagated to request
    self.assertEqual(common.CancelReason.INVALID_REQUEST, request.cancel_reason)
    self._AssertRequestEventMessageIsQueued(
        request_manager.CreateRequestEventMessage(request), mock_add)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testEvaluateState_cancelCompletedCommand(self, now, mock_add):
    """Tests EvaluateState() when cancelling a completed command."""
    now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        user="user1",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id="1")
    command_entity = datastore_entities.Command(
        parent=request.key,
        request_id=request.key.id(),
        command_hash="command_hash_complete",
        command_line="command_line",
        cluster="cluster",
        run_target="run_target",
        run_count=5,
        state=common.CommandState.COMPLETED,
        start_time=self.START_TIME,
        end_time=self.END_TIME)
    command_entity.put()
    request, _ = request_manager.EvaluateState(request.key.id(), force=True)
    self.assertEqual(common.RequestState.COMPLETED, request.state)
    self.assertEqual(self.START_TIME, request.start_time)
    self.assertEqual(self.END_TIME, request.end_time)
    self._AssertRequestEventMessageIsQueued(
        request_manager.CreateRequestEventMessage(request), mock_add)
    mock_add.reset_mock()

    # If a command is COMPLETED, then any attempts to cancel it afterwards
    # should not change its state.
    request_manager.CancelRequest(
        request.key.id(), common.CancelReason.QUEUE_TIMEOUT)
    request = request_manager.GetRequest(request.key.id())
    self.assertEqual(common.RequestState.COMPLETED, request.state)
    self.assertEqual(self.START_TIME, request.start_time)
    self.assertEqual(self.END_TIME, request.end_time)
    self.assertIsNone(request.cancel_reason)
    self.assertFalse(mock_add.called)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testEvaluateState_completeCancelledCommand(self, now, mock_add):
    """Tests EvaluateState() when updating a cancelled command."""
    now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        user="user1",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                cluster="cluster",
                run_target="run_target")
        ],
        request_id="1")
    command_entity = datastore_entities.Command(
        parent=request.key,
        request_id=request.key.id(),
        command_hash="command_hash_complete",
        command_line="command_line",
        cluster="cluster",
        run_target="run_target",
        run_count=5,
        state=common.CommandState.CANCELED,
        start_time=None,
        end_time=None)
    command_entity.put()
    request, _ = request_manager.EvaluateState(request.key.id(), force=True)
    self.assertEqual(common.RequestState.CANCELED, request.state)
    self.assertIsNone(request.start_time)
    self.assertIsNone(request.end_time)
    self._AssertRequestEventMessageIsQueued(
        request_manager.CreateRequestEventMessage(request), mock_add)
    mock_add.reset_mock()

    # If the commands of a request are all COMPLETED while the request is
    # CANCELLED, then the request should be put in the COMPLETED state.
    command_entity.state = common.CommandState.COMPLETED
    command_entity.start_time = self.START_TIME
    command_entity.end_time = self.END_TIME
    command_entity.put()
    request, _ = request_manager.EvaluateState(request.key.id(), force=True)
    self.assertEqual(common.RequestState.COMPLETED, request.state)
    self.assertEqual(request.start_time, self.START_TIME)
    self.assertEqual(request.end_time, self.END_TIME)
    self._AssertRequestEventMessageIsQueued(
        request_manager.CreateRequestEventMessage(request), mock_add)

  def testGetCommandAttempts_byRequestId(self):
    for _ in range(10):
      command = datastore_entities.Command(
          parent=self.request.key,
          command_line="command_line",
          cluster="cluster",
          run_target="run_target",
          run_count=1,
          state=common.CommandState.COMPLETED,
          start_time=self.START_TIME,
          end_time=self.END_TIME)
      command.put()
      datastore_entities.CommandAttempt(
          parent=command.key,
          task_id="task_id",
          attempt_id="attempt_id",
          state=common.CommandState.UNKNOWN,
          hostname="hostname",
          device_serial="device_serial",
          start_time=self.START_TIME,
          end_time=self.END_TIME,
          status="status",
          error="error",
          summary="summary",
          total_test_count=1000,
          failed_test_count=100).put()

    command_attempts = request_manager.GetCommandAttempts(self.request.key.id())

    self.assertEqual(10, len(command_attempts))
    prev = None
    for i in range(10):
      command_attempt = command_attempts[i]
      if prev:
        self.assertLessEqual(prev.create_time, command_attempt.create_time)
      self.assertEqual("task_id", command_attempt.task_id)
      self.assertEqual("attempt_id", command_attempt.attempt_id)
      self.assertEqual(common.CommandState.UNKNOWN, command_attempt.state)
      self.assertEqual("hostname", command_attempt.hostname)
      self.assertEqual("device_serial", command_attempt.device_serial)
      self.assertEqual(self.START_TIME, command_attempt.start_time)
      self.assertEqual(self.END_TIME, command_attempt.end_time)
      self.assertEqual("status", command_attempt.status)
      self.assertEqual("summary", command_attempt.summary)
      self.assertEqual(1000, command_attempt.total_test_count)
      self.assertEqual(100, command_attempt.failed_test_count)
      prev = command_attempt

  def testGetCommandAttempts_byCommandId(self):
    commands = []
    for i in range(3):
      command = datastore_entities.Command(
          parent=self.request.key,
          command_line="command_line",
          cluster="cluster",
          run_target="run_target",
          run_count=1,
          state=common.CommandState.COMPLETED,
          start_time=self.START_TIME,
          end_time=self.END_TIME)
      commands.append(command)
      command.put()
      datastore_entities.CommandAttempt(
          parent=command.key,
          task_id="task_id",
          attempt_id="attempt_id",
          state=common.CommandState.UNKNOWN,
          hostname="hostname",
          device_serial="device_serial",
          start_time=self.START_TIME,
          end_time=self.END_TIME,
          status="status",
          error="error",
          summary="summary",
          total_test_count=i+1,
          failed_test_count=i).put()

    command_attempts = request_manager.GetCommandAttempts(self.request.key.id(),
                                                          commands[0].key.id())

    self.assertEqual(1, len(command_attempts))
    self.assertEqual("task_id", command_attempts[0].task_id)
    self.assertEqual("attempt_id", command_attempts[0].attempt_id)
    self.assertEqual(common.CommandState.UNKNOWN, command_attempts[0].state)
    self.assertEqual("hostname", command_attempts[0].hostname)
    self.assertEqual("device_serial", command_attempts[0].device_serial)
    self.assertEqual(self.START_TIME, command_attempts[0].start_time)
    self.assertEqual(self.END_TIME, command_attempts[0].end_time)
    self.assertEqual("status", command_attempts[0].status)
    self.assertEqual("summary", command_attempts[0].summary)
    self.assertEqual(1, command_attempts[0].total_test_count)
    self.assertEqual(0, command_attempts[0].failed_test_count)

  def testGetCommandAttempt(self):
    command = datastore_entities.Command(
        parent=self.request.key,
        id=COMMAND_ID,
        command_line="command_line",
        cluster="cluster",
        run_target="run_target",
        run_count=1,
        state=common.CommandState.COMPLETED,
        start_time=self.START_TIME,
        end_time=self.END_TIME)
    datastore_entities.CommandAttempt(
        parent=command.key,
        id=ATTEMPT_ID,
        task_id="task_id",
        attempt_id="attempt_id",
        state=common.CommandState.UNKNOWN,
        hostname="hostname",
        device_serial="device_serial",
        start_time=self.START_TIME,
        end_time=self.END_TIME,
        status="status",
        error="error",
        summary="summary",
        total_test_count=1000,
        failed_test_count=100).put()

    command_attempt = request_manager.GetCommandAttempt(
        REQUEST_ID, COMMAND_ID, ATTEMPT_ID)
    self.assertEqual("task_id", command_attempt.task_id)
    self.assertEqual("attempt_id", command_attempt.attempt_id)
    self.assertEqual(common.CommandState.UNKNOWN, command_attempt.state)
    self.assertEqual("hostname", command_attempt.hostname)
    self.assertEqual("device_serial", command_attempt.device_serial)
    self.assertEqual(self.START_TIME, command_attempt.start_time)
    self.assertEqual(self.END_TIME, command_attempt.end_time)
    self.assertEqual("status", command_attempt.status)
    self.assertEqual("summary", command_attempt.summary)
    self.assertEqual(1000, command_attempt.total_test_count)
    self.assertEqual(100, command_attempt.failed_test_count)

  def testCreateRequest(self):
    request_manager.CreateRequest(
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line="command_line",
                run_target="run_target0",
                cluster="cluster0",
                run_count=10,
                shard_count=20),
        ],
        priority=1,
        queue_timeout_seconds=10,
        type_=api_messages.RequestType.MANAGED,
        request_id="1001")
    request = ndb.Key(datastore_entities.Request, "1001",
                      namespace=common.NAMESPACE).get(use_cache=False)
    self.assertEqual("user", request.user)
    self.assertEqual("command_line", request.command_infos[0].command_line)
    self.assertEqual("run_target0", request.command_infos[0].run_target)
    self.assertEqual("cluster0", request.command_infos[0].cluster)
    self.assertEqual(10, request.command_infos[0].run_count)
    self.assertEqual(20, request.command_infos[0].shard_count)
    self.assertEqual(10, request.queue_timeout_seconds)
    self.assertEqual(1, request.priority)
    self.assertEqual(api_messages.RequestType.MANAGED, request.type)

  def testCreateRequest_escapeInCommandLine(self):
    command_line = 'command_line --arg \'option=\'"\'"\'value\'"\'"\'\''
    request_manager.CreateRequest(
        user="user",
        command_infos=[
            datastore_entities.CommandInfo(
                command_line=command_line,
                run_target="run_target0",
                cluster="cluster0",
                run_count=10,
                shard_count=20)
        ],
        priority=1,
        queue_timeout_seconds=10,
        type_=api_messages.RequestType.MANAGED,
        request_id="1001")
    request = ndb.Key(datastore_entities.Request, "1001",
                      namespace=common.NAMESPACE).get(use_cache=False)
    self.assertEqual("user", request.user)
    self.assertEqual(10, request.queue_timeout_seconds)
    self.assertEqual(1, request.priority)
    self.assertEqual(api_messages.RequestType.MANAGED, request.type)
    # CreateRequest doesn't change the command line
    self.assertEqual(command_line, request.command_infos[0].command_line)
    self.assertEqual("run_target0", request.command_infos[0].run_target)
    self.assertEqual("cluster0", request.command_infos[0].cluster)
    self.assertEqual(10, request.command_infos[0].run_count)
    self.assertEqual(20, request.command_infos[0].shard_count)

  def testGetRequest(self):
    request = request_manager.GetRequest("1001")
    self.assertEqual(self.request.key, request.key)
    self.assertEqual(self.request.command_infos, request.command_infos)
    self.assertEqual(self.request.user, request.user)

  def testGetRequest_nonExistent(self):
    """Tests getting a non existing request."""
    request = request_manager.GetRequest("8888")
    self.assertIsNone(request)

  def testGetCommands(self):
    for i in range(10):
      command = datastore_entities.Command(
          parent=self.request.key,
          command_line="command_line",
          cluster="cluster",
          run_target="run_target",
          run_count=1,
          state=common.CommandState.COMPLETED,
          start_time=self.START_TIME,
          end_time=self.END_TIME)
      command.put()

    commands = request_manager.GetCommands(self.request.key.id())

    for i in range(10):
      command = commands[i]
      self.assertEqual("command_line", command.command_line)
      self.assertEqual("cluster", command.cluster)
      self.assertEqual("run_target", command.run_target)
      self.assertEqual(1, command.run_count)
      self.assertEqual(common.CommandState.COMPLETED, command.state)
      self.assertEqual(self.START_TIME, command.start_time)
      self.assertEqual(self.END_TIME, command.end_time)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testNotifyRequestState(self, now, mock_add_task):
    now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        request_id=self._request_id, state=common.RequestState.COMPLETED)
    command = self._CreateTestCommand(request, common.CommandState.COMPLETED)
    self._CreateTestCommandAttempt(
        command,
        common.CommandState.COMPLETED,
        total_test_count=5,
        failed_test_count=3,
        passed_test_count=2,
        failed_test_run_count=1,
        device_lost_detected=2,
        start_time=datetime.datetime(2016, 12, 1, 0, 0, 0),
        end_time=datetime.datetime(2016, 12, 1, 0, 0, 1))
    request_manager.NotifyRequestState(REQUEST_ID, force=True)

    msg = api_messages.RequestEventMessage(
        type=common.ObjectEventType.REQUEST_STATE_CHANGED,
        request_id=REQUEST_ID,
        new_state=common.RequestState.COMPLETED,
        request=datastore_entities.ToMessage(request),
        summary="Attempt attempt_id: summary: %s\n" % self.v1_result_link,
        total_test_count=5,
        failed_test_count=3,
        passed_test_count=2,
        failed_test_run_count=1,
        device_lost_detected=2,
        result_links=[self.v1_result_link],
        total_run_time_sec=1,
        event_time=self.END_TIME)
    self._AssertRequestEventMessageIsQueued(msg, mock_add_task)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testNotifyRequestState_withV2Link(self, now, mock_add_task):
    now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        request_id=self._request_id, state=common.RequestState.COMPLETED)
    command = self._CreateTestCommand(request, common.CommandState.COMPLETED)
    self._CreateTestCommandAttempt(
        command,
        common.CommandState.COMPLETED,
        total_test_count=5,
        failed_test_count=3,
        passed_test_count=2,
        failed_test_run_count=1,
        start_time=datetime.datetime(2016, 12, 1, 0, 0, 0),
        end_time=datetime.datetime(2016, 12, 1, 0, 0, 1),
        result_link=self.v2_result_link)
    request_manager.NotifyRequestState(REQUEST_ID, force=True)

    msg = api_messages.RequestEventMessage(
        type=common.ObjectEventType.REQUEST_STATE_CHANGED,
        request_id=REQUEST_ID,
        new_state=common.RequestState.COMPLETED,
        request=datastore_entities.ToMessage(request),
        summary="Attempt attempt_id: summary: %s\n" % self.v2_result_link,
        total_test_count=5,
        failed_test_count=3,
        passed_test_count=2,
        failed_test_run_count=1,
        device_lost_detected=0,
        result_links=[self.v2_result_link],
        total_run_time_sec=1,
        event_time=self.END_TIME)
    self._AssertRequestEventMessageIsQueued(msg, mock_add_task)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testNotifyRequestState_commandWithMultipleAttempts(
      self, now, mock_add_task):
    now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        request_id=self._request_id, state=common.RequestState.COMPLETED)
    command = self._CreateTestCommand(request, common.CommandState.COMPLETED)
    self._CreateTestCommandAttempt(
        command,
        state=common.CommandState.COMPLETED,
        total_test_count=5,
        failed_test_count=3,
        passed_test_count=2,
        failed_test_run_count=1,
        device_lost_detected=2,
        start_time=datetime.datetime(2016, 12, 1, 0, 0, 0),
        end_time=datetime.datetime(2016, 12, 1, 0, 0, 1))
    command_attempt2 = self._CreateTestCommandAttempt(
        command,
        state=common.CommandState.COMPLETED,
        total_test_count=10,
        failed_test_count=5,
        passed_test_count=5,
        failed_test_run_count=3,
        device_lost_detected=3,
        start_time=datetime.datetime(2016, 12, 1, 0, 0, 0),
        end_time=datetime.datetime(2016, 12, 1, 0, 0, 1))
    request_manager.NotifyRequestState(REQUEST_ID, force=True)

    msg = api_messages.RequestEventMessage(
        type=common.ObjectEventType.REQUEST_STATE_CHANGED,
        request_id=REQUEST_ID,
        new_state=common.RequestState.COMPLETED,
        request=datastore_entities.ToMessage(request),
        summary="Attempt attempt_id: summary: %s\n" % self.v1_result_link,
        total_test_count=command_attempt2.total_test_count,
        failed_test_count=command_attempt2.failed_test_count,
        passed_test_count=command_attempt2.passed_test_count,
        failed_test_run_count=command_attempt2.failed_test_run_count,
        device_lost_detected=5,
        result_links=[self.v1_result_link],
        total_run_time_sec=2,
        event_time=self.END_TIME)
    self._AssertRequestEventMessageIsQueued(msg, mock_add_task)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testNotifyRequestState_commandWithError(self, now, mock_add_task):
    now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        request_id=self._request_id, state=common.RequestState.ERROR)
    command = self._CreateTestCommand(request, common.CommandState.ERROR)
    attempts = []
    for _ in range(3):
      attempt = self._CreateTestCommandAttempt(
          command,
          state=common.CommandState.ERROR,
          device_lost_detected=1,
          start_time=datetime.datetime(2016, 12, 1, 0, 0, 0),
          end_time=datetime.datetime(2016, 12, 1, 0, 0, 1))
      attempts.append(attempt)
    request_manager.NotifyRequestState(REQUEST_ID, force=True)

    msg = api_messages.RequestEventMessage(
        type=common.ObjectEventType.REQUEST_STATE_CHANGED,
        request_id=REQUEST_ID,
        new_state=common.RequestState.ERROR,
        request=datastore_entities.ToMessage(request),
        summary="\n".join([
            "Attempt attempt_id: %s error (ERROR)" % self.v1_result_link] * 3),
        total_test_count=0,
        failed_test_count=0,
        passed_test_count=0,
        failed_test_run_count=0,
        device_lost_detected=3,
        result_links=[self.v1_result_link],
        total_run_time_sec=3,
        error_reason="UnknownErrorReason",
        error_type=common.CommandErrorType.UNKNOWN,
        event_time=self.END_TIME)
    self._AssertRequestEventMessageIsQueued(msg, mock_add_task)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testNotifyRequestState_commandWithFatalError(self, now, mock_add_task):
    now.return_value = self.END_TIME
    error_message = "com.android.tradefed.config.ConfigurationException"
    request = datastore_test_util.CreateRequest(
        request_id=self._request_id, state=common.RequestState.ERROR)
    command = self._CreateTestCommand(request, state=common.CommandState.FATAL)
    attempt = self._CreateTestCommandAttempt(
        command,
        state=common.CommandState.FATAL,
        start_time=datetime.datetime(2016, 12, 1, 0, 0, 0),
        end_time=datetime.datetime(2016, 12, 1, 0, 0, 1))
    attempt.error = error_message
    attempt.put()
    request_manager.NotifyRequestState(REQUEST_ID, force=True)

    msg = api_messages.RequestEventMessage(
        type=common.ObjectEventType.REQUEST_STATE_CHANGED,
        request_id=REQUEST_ID,
        new_state=common.RequestState.ERROR,
        request=datastore_entities.ToMessage(request),
        summary="Attempt attempt_id: %s %s (ERROR)" % (
            self.v1_result_link, error_message),
        total_test_count=0,
        failed_test_count=0,
        passed_test_count=0,
        failed_test_run_count=0,
        device_lost_detected=0,
        result_links=[self.v1_result_link],
        total_run_time_sec=1,
        error_reason="ConfigurationError",
        error_type=common.CommandErrorType.TEST,
        event_time=self.END_TIME)
    self._AssertRequestEventMessageIsQueued(msg, mock_add_task)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testNotifyRequestState_commandWithErrorType(self, now, mock_add_task):
    now.return_value = self.END_TIME
    error_message = "error"
    request = datastore_test_util.CreateRequest(
        request_id=self._request_id, state=common.RequestState.ERROR)
    command = self._CreateTestCommand(request, state=common.CommandState.ERROR)
    attempts = []
    for _ in range(3):
      attempt = self._CreateTestCommandAttempt(
          command,
          state=common.CommandState.ERROR,
          start_time=datetime.datetime(2016, 12, 1, 0, 0, 0),
          end_time=datetime.datetime(2016, 12, 1, 0, 0, 1))
      attempts.append(attempt)
    request_manager.NotifyRequestState(REQUEST_ID, force=True)

    msg = api_messages.RequestEventMessage(
        type=common.ObjectEventType.REQUEST_STATE_CHANGED,
        request_id=REQUEST_ID,
        new_state=common.RequestState.ERROR,
        request=datastore_entities.ToMessage(request),
        summary="\n".join(["Attempt attempt_id: %s %s (ERROR)" % (
            self.v1_result_link, error_message)] * 3),
        total_test_count=0,
        failed_test_count=0,
        passed_test_count=0,
        failed_test_run_count=0,
        device_lost_detected=0,
        result_links=[self.v1_result_link],
        total_run_time_sec=3,
        error_reason="BuildRetrievalError",
        error_type=common.CommandErrorType.INFRA,
        event_time=self.END_TIME)
    self._AssertRequestEventMessageIsQueued(msg, mock_add_task)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testNotifyRequestState_multipleRunCount(self, now, mock_add_task):
    now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        request_id=self._request_id, state=common.RequestState.COMPLETED)
    command = self._CreateTestCommand(request,
                                      state=common.CommandState.COMPLETED,
                                      run_count=2)
    attempts = []
    for i in range(2):
      attempt = self._CreateTestCommandAttempt(
          command,
          state=common.CommandState.COMPLETED,
          total_test_count=5,
          failed_test_count=i,
          passed_test_count=5-i,
          failed_test_run_count=i,
          device_lost_detected=1,
          start_time=datetime.datetime(2016, 12, 1, 0, 0, 0),
          end_time=datetime.datetime(2016, 12, 1, 0, 0, 1))
      attempts.append(attempt)
    request_manager.NotifyRequestState(REQUEST_ID, force=True)

    msg = api_messages.RequestEventMessage(
        type=common.ObjectEventType.REQUEST_STATE_CHANGED,
        request_id=REQUEST_ID,
        new_state=common.RequestState.COMPLETED,
        request=datastore_entities.ToMessage(request),
        summary="\n".join(["Attempt attempt_id: summary: %s\n" %
                           self.v1_result_link] * 2),
        total_test_count=10,
        failed_test_count=1,
        passed_test_count=9,
        failed_test_run_count=1,
        device_lost_detected=2,
        result_links=[self.v1_result_link],
        total_run_time_sec=2,
        event_time=self.END_TIME)
    self._AssertRequestEventMessageIsQueued(msg, mock_add_task)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testNotifyRequestState_multipleCommands(self, now, mock_add_task):
    now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        request_id=self._request_id, state=common.RequestState.COMPLETED)
    commands = [self._CreateTestCommand(
        request,
        state=common.CommandState.COMPLETED) for _ in range(2)]
    attempts = []
    for command in commands:
      attempt = self._CreateTestCommandAttempt(
          command,
          state=common.CommandState.COMPLETED,
          total_test_count=5,
          failed_test_count=1,
          passed_test_count=1,
          failed_test_run_count=1,
          device_lost_detected=1,
          start_time=datetime.datetime(2016, 12, 1, 0, 0, 0),
          end_time=datetime.datetime(2016, 12, 1, 0, 0, 1))
      attempts.append(attempt)
    request_manager.NotifyRequestState(REQUEST_ID, force=True)

    msg = api_messages.RequestEventMessage(
        type=common.ObjectEventType.REQUEST_STATE_CHANGED,
        request_id=REQUEST_ID,
        new_state=common.RequestState.COMPLETED,
        request=datastore_entities.ToMessage(request),
        summary="\n".join(["Attempt attempt_id: summary: %s\n" %
                           self.v1_result_link] * 2),
        total_test_count=10,
        failed_test_count=2,
        passed_test_count=2,
        failed_test_run_count=2,
        device_lost_detected=2,
        result_links=[self.v1_result_link],
        total_run_time_sec=2,
        event_time=self.END_TIME)
    self._AssertRequestEventMessageIsQueued(msg, mock_add_task)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testNotifyRequestState_completedMissingFields(self, now, mock_add_task):
    now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        request_id=self._request_id, state=common.RequestState.COMPLETED)
    command = self._CreateTestCommand(request, common.CommandState.COMPLETED)
    attempt = self._CreateTestCommandAttempt(
        command,
        state=common.CommandState.COMPLETED,
        start_time=datetime.datetime(2016, 12, 1, 0, 0, 0),
        end_time=datetime.datetime(2016, 12, 1, 0, 0, 1))
    attempt.summary = None
    attempt.total_test_count = None
    attempt.failed_test_count = None
    attempt.passed_test_count = None
    attempt.failed_test_run_count = None
    attempt.device_lost_detected = None
    attempt.put()
    request_manager.NotifyRequestState(REQUEST_ID, force=True)

    msg = api_messages.RequestEventMessage(
        type=common.ObjectEventType.REQUEST_STATE_CHANGED,
        request_id=REQUEST_ID,
        new_state=common.RequestState.COMPLETED,
        request=datastore_entities.ToMessage(request),
        summary="Attempt attempt_id: No summary available.",
        total_test_count=0,
        failed_test_count=0,
        passed_test_count=0,
        failed_test_run_count=0,
        device_lost_detected=0,
        total_run_time_sec=1,
        event_time=self.END_TIME)
    self._AssertRequestEventMessageIsQueued(msg, mock_add_task)

  @mock.patch.object(task_scheduler, "AddTask")
  @mock.patch.object(common, "Now")
  def testNotifyRequestStateChange_errorMissingFields(self, now, mock_add_task):
    now.return_value = self.END_TIME
    request = datastore_test_util.CreateRequest(
        request_id=self._request_id, state=common.RequestState.ERROR)
    command = self._CreateTestCommand(request, state=common.CommandState.ERROR)
    attempt = self._CreateTestCommandAttempt(
        command,
        state=common.CommandState.ERROR)
    attempt.error = None
    attempt.put()
    request_manager.NotifyRequestState(REQUEST_ID, force=True)

    msg = api_messages.RequestEventMessage(
        type=common.ObjectEventType.REQUEST_STATE_CHANGED,
        request_id=REQUEST_ID,
        new_state=common.RequestState.ERROR,
        request=datastore_entities.ToMessage(request),
        summary=("Attempt attempt_id: %s No error message available. (ERROR)" %
                 self.v1_result_link),
        total_test_count=0,
        failed_test_count=0,
        passed_test_count=0,
        device_lost_detected=0,
        result_links=[self.v1_result_link],
        total_run_time_sec=0,
        event_time=self.END_TIME,
        failed_test_run_count=0)
    self._AssertRequestEventMessageIsQueued(msg, mock_add_task)

  def testCreateRequestId(self):
    id_ = request_manager._CreateRequestId()
    self.assertGreater(int(id_), 30000000)

  def _CreateTestCommand(self, request, state, run_count=1):
    """Creates a Command associated with a Request."""
    command = datastore_entities.Command(
        parent=request.key,
        id=str(self._command_id),
        command_line="command_line",
        cluster="cluster",
        run_target="run_target",
        run_count=run_count,
        state=state)
    command.put()
    self._command_id += 1
    return command

  def _CreateTestCommandAttempt(self,
                                command,
                                state,
                                total_test_count=1,
                                failed_test_count=1,
                                passed_test_count=0,
                                failed_test_run_count=1,
                                device_lost_detected=0,
                                start_time=None,
                                end_time=None,
                                result_link=None):
    """Creates a CommandAttempt associated with a Command."""
    if not result_link:
      result_link = self.v1_result_link
    command_attempt = datastore_entities.CommandAttempt(
        parent=command.key,
        id=str(self._attempt_id),
        command_id=command.key.id(),
        task_id="task_id",
        attempt_id="attempt_id",
        state=state,
        summary="summary: %s\n" % result_link,
        error="error" if state == common.CommandState.ERROR else None,
        total_test_count=total_test_count,
        failed_test_count=failed_test_count,
        passed_test_count=passed_test_count,
        failed_test_run_count=failed_test_run_count,
        device_lost_detected=device_lost_detected,
        start_time=start_time,
        end_time=end_time)
    command_attempt.put()
    self._attempt_id += 1
    return command_attempt

  def _AssertRequestEventMessageIsQueued(self, message, mock_add_task):
    mock_add_task.assert_called_once_with(
        queue_name=common.OBJECT_EVENT_QUEUE,
        payload=mock.ANY,
        transactional=True)
    payload = zlib.decompress(mock_add_task.call_args[1]["payload"])
    queue_message = protojson.decode_message(api_messages.RequestEventMessage,
                                             payload)

    json_message = protojson.encode_message(message)
    message = protojson.decode_message(
        api_messages.RequestEventMessage, json_message)

    self.assertEqual(queue_message.type, message.type)
    self.assertEqual(queue_message.request_id, message.request_id)
    self.assertEqual(queue_message.new_state, message.new_state)
    # Ignore request update_time
    message.request.update_time = queue_message.request.update_time
    self.assertEqual(queue_message.request, message.request)
    self.assertEqual(queue_message.summary, message.summary)
    self.assertEqual(queue_message.total_test_count, message.total_test_count)
    self.assertEqual(queue_message.failed_test_count, message.failed_test_count)
    self.assertEqual(queue_message.passed_test_count, message.passed_test_count)
    self.assertEqual(queue_message.failed_test_run_count,
                     message.failed_test_run_count)
    self.assertEqual(queue_message.device_lost_detected,
                     message.device_lost_detected)
    self.assertEqual(queue_message.result_links, message.result_links)
    self.assertEqual(queue_message.total_run_time_sec,
                     message.total_run_time_sec)
    self.assertEqual(queue_message.event_time, message.event_time)


if __name__ == "__main__":
  unittest.main()
