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

"""Tests host_event_api module."""

import datetime
import unittest

import mock

from google.appengine.ext import deferred

from tradefed_cluster import api_test
from tradefed_cluster import datastore_entities
from tradefed_cluster import device_manager
from tradefed_cluster import host_event
from tradefed_cluster import host_event_api


device_info_emulator = {
    'product': 'unknown',
    'state': 'Available',
    'device_serial': 'emulator-5554',
    'sdk_version': 'unknown',
    'build_id': 'unknown',
    'run_target': 'unknown',
    'product_variant': 'unknown'
}
device_info_hammerhead = {
    'product': 'hammerhead',
    'state': 'Available',
    'device_serial': '021f34c1d01e5a59',
    'sdk_version': '23',
    'build_id': 'MASTER',
    'run_target': 'hammerhead',
    'product_variant': 'hammerhead'
}
snapshot_event = {
    'time': 1234567890,
    'data': {},
    'cluster': 'example-cluster',
    'hostname': 'example0.mtv.corp.example.com',
    'lab_name': 'alab',
    'event_type': 'DEVICE_SNAPSHOT',
    'device_infos': [device_info_emulator, device_info_hammerhead]
}
host_state_event = {
    'time': 1234567890,
    'cluster': 'example-cluster',
    'hostname': 'example0.mtv.corp.example.com',
    'event_type': 'HOST_STATE_CHANGED',
    'host_state': 'KILLING',
}


class MockDefer(object):
  """Mock methods to replace host_event_api deferred methods.

  We cannot use the mock library to do this as deferred will error out with an
  error related to module name changes (some black magic that the mock library
  uses when replacing method implementations).
  """

  deferred_ran = None
  events = None

  @classmethod
  def ProcessHostEventA(cls, events):
    assert events is not None
    cls.deferred_ran = 'A'
    cls.events = events

  @classmethod
  def ProcessHostEventB(cls, events):
    assert events is not None
    cls.deferred_ran = 'B'
    cls.events = events


class HostEventApiTest(api_test.ApiTest):

  def testSubmitHostEvents(self):
    request = {'host_events': [snapshot_event]}
    # Verify that there aren't any entities persisted before the API call
    hosts = datastore_entities.HostInfo.query().fetch()
    self.assertEqual(0, len(hosts))
    devices = datastore_entities.DeviceInfo.query().fetch()
    self.assertEqual(0, len(devices))
    self.testapp.post_json('/_ah/api/HostEventApi.SubmitHostEvents', request)

    tasks = self.taskqueue_stub.get_filtered_tasks(
        queue_names=host_event.HOST_EVENT_QUEUE_NDB)
    self.assertEqual(len(tasks), 1)
    deferred.run(tasks[0].payload)
    # Verify host info in datastore.
    hosts = datastore_entities.HostInfo.query().fetch()
    timestamp = datetime.datetime.utcfromtimestamp(int(snapshot_event['time']))
    self.assertEqual(1, len(hosts))
    self.assertEqual(snapshot_event['hostname'], hosts[0].hostname)
    self.assertEqual(snapshot_event['lab_name'], hosts[0].lab_name)
    self.assertEqual(snapshot_event['cluster'], hosts[0].physical_cluster)
    self.assertEqual(timestamp, hosts[0].timestamp)
    devices = datastore_entities.DeviceInfo.query().fetch()
    self.assertEqual(2, len(devices))

  def testSubmitHostEvents_hostStateChangedEvent(self):
    request = {'host_events': [host_state_event]}
    self.testapp.post_json('/_ah/api/HostEventApi.SubmitHostEvents', request)
    tasks = self.taskqueue_stub.get_filtered_tasks(
        queue_names=host_event.HOST_EVENT_QUEUE_NDB)
    self.assertEqual(len(tasks), 1)
    host_event_api.HostEventApi._ProcessHostEventWithNDB = (
        MockDefer.ProcessHostEventA)
    deferred.run(tasks[0].payload)
    event = host_event.HostEvent(**MockDefer.events[0])
    self.assertEqual('HOST_STATE_CHANGED', event.type)
    self.assertEqual('KILLING', event.host_state)

  def testSubmitHostEvents_changeDeferredFunction(self):
    """Tests that tasks execute the latest deferred function implementation."""
    MockDefer.deferred_ran = None
    request = {'host_events': [snapshot_event]}
    # Sending 3 requests and run each with a different version
    self.testapp.post_json('/_ah/api/HostEventApi.SubmitHostEvents', request)
    self.testapp.post_json('/_ah/api/HostEventApi.SubmitHostEvents', request)
    self.testapp.post_json('/_ah/api/HostEventApi.SubmitHostEvents', request)
    tasks = self.taskqueue_stub.get_filtered_tasks(
        queue_names=host_event.HOST_EVENT_QUEUE_NDB)
    self.assertEqual(len(tasks), 3)
    deferred.run(tasks[0].payload)
    self.assertIsNone(MockDefer.deferred_ran)
    host_event_api.HostEventApi._ProcessHostEventWithNDB = (
        MockDefer.ProcessHostEventA)
    deferred.run(tasks[1].payload)
    self.assertEqual('A', MockDefer.deferred_ran)
    host_event_api.HostEventApi._ProcessHostEventWithNDB = (
        MockDefer.ProcessHostEventB)
    deferred.run(tasks[2].payload)
    self.assertEqual('B', MockDefer.deferred_ran)

  @mock.patch.object(deferred, 'defer')
  def testSubmitHostEvents_multipleChunks(self, mock_defer):
    """Tests a request with more vents than the chunk size."""
    host_event_api.CHUNK_SIZE = 5
    request = {'host_events': [snapshot_event] * 50}
    self.testapp.post_json('/_ah/api/HostEventApi.SubmitHostEvents', request)
    # Should be called 10 times with 5 chunks each
    mock_defer.assert_has_calls([
        mock.call(mock.ANY, [snapshot_event] * 5,
                  _queue=host_event.HOST_EVENT_QUEUE_NDB)] * 10)

  @mock.patch.object(device_manager, 'HandleDeviceSnapshotWithNDB')
  @mock.patch.object(device_manager, 'IsHostEventValid', return_value=False)
  def testProcessHostEvent_invalidEvent(self, mock_valid, mock_handle):
    """Tests _ProcessHostEvent with an invalid event."""
    host_event_api.HostEventApi()._ProcessHostEventWithNDB([snapshot_event])
    mock_valid.assert_called_once_with(snapshot_event)
    self.assertFalse(mock_handle.called)

  def testChunks(self):
    """Test host_event_api.chunks()."""
    l = [1, 2, 3, 4, 5]
    result = [c for c in host_event_api.chunks(l, 2)]
    self.assertEqual(3, len(result))
    self.assertEqual([1, 2], result[0])
    self.assertEqual([3, 4], result[1])
    self.assertEqual([5], result[2])

  def testChunks_emptyList(self):
    """Test host_event_api.chunks() given an empty list."""
    result = [c for c in host_event_api.chunks([], 2)]
    self.assertEqual(0, len(result))


if __name__ == '__main__':
  unittest.main()
