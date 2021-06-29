"""Tests for tradefed_cluster.request_sync_monitor."""

import datetime
import json
import unittest

import mock

from tradefed_cluster import command_event_test_util
from tradefed_cluster import commander
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import request_sync_monitor
from tradefed_cluster import testbed_dependent_test

REQUEST_ID = 'req_id'
TIMESTAP_INT = 1000


class RequestMonitorTest(testbed_dependent_test.TestbedDependentTest):

  def testMonitor(self):
    request_sync_monitor.Monitor(REQUEST_ID)

    tasks = self.mock_task_scheduler.GetTasks(
        queue_names=(request_sync_monitor.REQUEST_SYNC_QUEUE,))
    self.assertLen(tasks, 1)
    task = json.loads(tasks[0].payload)
    self.assertEqual(REQUEST_ID, task[request_sync_monitor.REQUEST_ID_KEY])

    sync_key = request_sync_monitor.GetRequestSyncStatusKey(REQUEST_ID)
    sync_status = sync_key.get()
    self.assertEqual(REQUEST_ID, sync_status.request_id)

  @mock.patch.object(common, 'Now')
  def testUpdateSyncStatus(self, mock_now):
    now = datetime.datetime.utcnow()
    mock_now.return_value = now

    request_sync_monitor.Monitor(REQUEST_ID)
    sync_key = request_sync_monitor.GetRequestSyncStatusKey(REQUEST_ID)
    sync_status = sync_key.get()
    sync_status.has_new_command_events = True
    sync_status.put()

    self.assertTrue(request_sync_monitor._UpdateSyncStatus(REQUEST_ID))
    sync_status = sync_key.get()
    self.assertFalse(sync_status.has_new_command_events)
    self.assertEqual(now, sync_status.last_sync_time)

  @mock.patch.object(common, 'Now')
  def testUpdateSyncStatus_noSyncTime(self, mock_now):
    now = datetime.datetime.utcnow()
    mock_now.return_value = now

    request_sync_monitor.Monitor(REQUEST_ID)
    sync_key = request_sync_monitor.GetRequestSyncStatusKey(REQUEST_ID)
    sync_status = sync_key.get()
    sync_status.has_new_command_events = False
    sync_status.put()

    self.assertTrue(request_sync_monitor._UpdateSyncStatus(REQUEST_ID))
    sync_status = sync_key.get()
    self.assertFalse(sync_status.has_new_command_events)
    self.assertEqual(now, sync_status.last_sync_time)

  @mock.patch.object(common, 'Now')
  def testUpdateSyncStatus_noEvents(self, mock_now):
    last_sync = datetime.datetime(2021, 1, 1)  # last synced 1 second ago
    now = datetime.datetime(2021, 1, 1, 0, 0, 1)
    mock_now.return_value = now

    request_sync_monitor.Monitor(REQUEST_ID)
    sync_key = request_sync_monitor.GetRequestSyncStatusKey(REQUEST_ID)
    sync_status = sync_key.get()
    sync_status.has_new_command_events = False
    sync_status.last_sync_time = last_sync
    sync_status.put()

    self.assertFalse(request_sync_monitor._UpdateSyncStatus(REQUEST_ID))
    sync_status = sync_key.get()
    self.assertEqual(last_sync, sync_status.last_sync_time)

  @mock.patch.object(common, 'Now')
  def testUpdateSyncStatus_force(self, mock_now):
    now = datetime.datetime.utcnow()
    mock_now.return_value = now

    request_sync_monitor.Monitor(REQUEST_ID)
    sync_key = request_sync_monitor.GetRequestSyncStatusKey(REQUEST_ID)
    sync_status = sync_key.get()
    sync_status.last_sync_time = now - datetime.timedelta(minutes=2)
    sync_status.put()

    self.assertTrue(request_sync_monitor._UpdateSyncStatus(REQUEST_ID))
    sync_status = sync_key.get()
    self.assertEqual(now, sync_status.last_sync_time)

  def testUpdateSyncStatus_noSyncStatus(self):
    with self.assertRaises(request_sync_monitor.RequestSyncStatusNotFoundError):
      request_sync_monitor._UpdateSyncStatus(REQUEST_ID)

  @mock.patch.object(request_sync_monitor, '_ProcessCommandEvents')
  @mock.patch.object(request_sync_monitor, '_AddRequestToQueue')
  @mock.patch.object(request_sync_monitor, '_UpdateSyncStatus')
  def testSyncRequest(self, mock_update, mock_queue, mock_process):
    mock_update.return_value = True
    datastore_test_util.CreateRequest(
        request_id=REQUEST_ID,
        user='user2',
        command_infos=[
            datastore_entities.CommandInfo(
                command_line='command_line2',
                cluster='cluster',
                run_target='run_target')
        ])

    request_sync_monitor.SyncRequest(REQUEST_ID)

    mock_process.assert_called_once_with(REQUEST_ID)
    mock_queue.assert_called_once_with(
        REQUEST_ID,
        countdown_secs=request_sync_monitor.SHORT_SYNC_COUNTDOWN_SECS)

  @mock.patch.object(request_sync_monitor, '_ProcessCommandEvents')
  @mock.patch.object(request_sync_monitor, '_UpdateSyncStatus')
  def testSyncRequest_shouldNotSyncYet(self, mock_update, mock_process):
    mock_update.return_value = False

    request_sync_monitor.SyncRequest(REQUEST_ID)

    tasks = self.mock_task_scheduler.GetTasks(
        queue_names=(request_sync_monitor.REQUEST_SYNC_QUEUE,))
    self.assertLen(tasks, 1)
    task = json.loads(tasks[0].payload)
    self.assertEqual(REQUEST_ID, task[request_sync_monitor.REQUEST_ID_KEY])
    mock_update.assert_called_once_with(REQUEST_ID)
    mock_process.assert_not_called()

  @mock.patch.object(request_sync_monitor, '_ProcessCommandEvents')
  @mock.patch.object(request_sync_monitor, '_AddRequestToQueue')
  @mock.patch.object(request_sync_monitor, '_UpdateSyncStatus')
  def testSyncRequest_noRequest(self, mock_update, mock_queue, mock_process):
    mock_update.return_value = True

    request_sync_monitor.SyncRequest(REQUEST_ID)

    sync_key = request_sync_monitor.GetRequestSyncStatusKey(REQUEST_ID)
    self.assertIsNone(sync_key.get())
    mock_queue.assert_not_called()
    mock_process.assert_not_called()

  @mock.patch.object(request_sync_monitor, '_ProcessCommandEvents')
  @mock.patch.object(request_sync_monitor, '_AddRequestToQueue')
  @mock.patch.object(request_sync_monitor, '_UpdateSyncStatus')
  def testSyncRequest_finalRequest(self, mock_update, mock_queue, mock_process):
    mock_update.return_value = True
    request = datastore_test_util.CreateRequest(
        request_id=REQUEST_ID,
        user='user2',
        command_infos=[
            datastore_entities.CommandInfo(
                command_line='command_line2',
                cluster='cluster',
                run_target='run_target')
        ])
    request.state = common.RequestState.COMPLETED
    request.put()

    request_sync_monitor.SyncRequest(REQUEST_ID)

    sync_key = request_sync_monitor.GetRequestSyncStatusKey(REQUEST_ID)
    self.assertIsNone(sync_key.get())
    mock_process.assert_called_once_with(REQUEST_ID)
    mock_queue.assert_not_called()

  @mock.patch.object(request_sync_monitor, '_ProcessCommandEvents')
  @mock.patch.object(request_sync_monitor, '_AddRequestToQueue')
  def testSyncRequest_processError(self, mock_queue, mock_process):
    request_sync_monitor.Monitor(REQUEST_ID)
    sync_key = request_sync_monitor.GetRequestSyncStatusKey(REQUEST_ID)
    sync_status = sync_key.get()
    sync_status.has_new_command_events = True
    sync_status.put()

    mock_process.side_effect = RuntimeError
    datastore_test_util.CreateRequest(
        request_id=REQUEST_ID,
        user='user2',
        command_infos=[
            datastore_entities.CommandInfo(
                command_line='command_line2',
                cluster='cluster',
                run_target='run_target')
        ])

    with self.assertRaises(RuntimeError):
      request_sync_monitor.SyncRequest(REQUEST_ID)

    mock_process.assert_called_once_with(REQUEST_ID)
    mock_queue.assert_called_once_with(REQUEST_ID)  # Call from Monitor()

    sync_status = sync_key.get()
    self.assertTrue(sync_status.has_new_command_events)

  def testStoreCommandEvent(self):
    request_sync_monitor.Monitor(REQUEST_ID)
    event = _AddCommandEvent()

    raw_events = datastore_entities.RawCommandEvent.query(
        datastore_entities.RawCommandEvent.request_id == REQUEST_ID,
        namespace=common.NAMESPACE).fetch()
    self.assertLen(raw_events, 1)
    self.assertEqual(event.event_dict, raw_events[0].payload)

    sync_key = request_sync_monitor.GetRequestSyncStatusKey(REQUEST_ID)
    self.assertTrue(sync_key.get().has_new_command_events)

  @mock.patch.object(commander, 'ProcessCommandEvent')
  def testProcessCommandEvents_singleEvent(self, mock_process):
    request_sync_monitor.Monitor(REQUEST_ID)
    event = _AddCommandEvent()
    _AddCommandEvent(request_id='another_request')

    request_sync_monitor._ProcessCommandEvents(REQUEST_ID)

    raw_events = datastore_entities.RawCommandEvent.query(
        namespace=common.NAMESPACE).fetch()
    self.assertLen(raw_events, 1)  # only another_request event should remain
    mock_process.assert_called_once_with(event)

  @mock.patch.object(commander, 'ProcessCommandEvent')
  def testProcessCommandEvents_multipleEvents(self, mock_process):
    event_1 = _AddCommandEvent(time=1)
    event_3 = _AddCommandEvent(time=3)
    event_2 = _AddCommandEvent(time=2)

    request_sync_monitor._ProcessCommandEvents(REQUEST_ID)

    raw_events = datastore_entities.RawCommandEvent.query(
        namespace=common.NAMESPACE).fetch()
    self.assertEmpty(raw_events)

    mock_process.assert_has_calls(
        [mock.call(event_1),
         mock.call(event_2),
         mock.call(event_3)],
        any_order=False)

  @mock.patch.object(commander, 'ProcessCommandEvent')
  def testProcessCommandEvents_noEvents(self, mock_process):
    request_sync_monitor._ProcessCommandEvents(REQUEST_ID)
    mock_process.assert_not_called()

  @mock.patch.object(commander, 'ProcessCommandEvent')
  def testProcessCommandEvents_withErrors(self, mock_process):
    mock_process.side_effect = [None, RuntimeError, None]

    event_1 = _AddCommandEvent(time=1)
    event_3 = _AddCommandEvent(time=3)
    event_2 = _AddCommandEvent(time=2)

    with self.assertRaises(RuntimeError):
      request_sync_monitor._ProcessCommandEvents(REQUEST_ID)

    mock_process.assert_has_calls(
        [mock.call(event_1), mock.call(event_2)], any_order=False)

    raw_events = datastore_entities.RawCommandEvent.query(
        namespace=common.NAMESPACE).fetch()
    payloads = [raw_event.payload for raw_event in raw_events]
    self.assertCountEqual([event_2.event_dict, event_3.event_dict], payloads)


def _AddCommandEvent(request_id=REQUEST_ID, time=TIMESTAP_INT):
  """Helper to add a command event."""
  event = command_event_test_util.CreateTestCommandEvent(
      request_id,
      123,
      'attempt0',
      common.InvocationEventType.INVOCATION_COMPLETED,
      time=time)

  request_sync_monitor.StoreCommandEvent(event)

  return event


if __name__ == '__main__':
  unittest.main()
