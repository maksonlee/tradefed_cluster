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

"""Tests for device_monitor."""
import base64
import datetime
import json
import unittest

import mock
from protorpc import protojson
import webtest

from google.appengine.ext import ndb

from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import device_manager
from tradefed_cluster import device_monitor
from tradefed_cluster import metric
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.util import metric_util


class DeviceMonitorTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    testbed_dependent_test.TestbedDependentTest.setUp(self)
    self.host1 = datastore_test_util.CreateHost(
        'free', 'atl-01.mtv', lab_name='alab')
    self.device_1 = datastore_test_util.CreateDevice(
        'free', 'atl-01.mtv', 'serial_1', run_target='shamu',
        state='Allocated')
    self.device_2 = datastore_test_util.CreateDevice(
        'free', 'atl-01.mtv', 'serial_2', run_target='shamu',
        state='Allocated')
    self.device_3 = datastore_test_util.CreateDevice(
        'free', 'atl-01.mtv', 'serial_3', run_target='shamu',
        state='Available')
    self.device_4 = datastore_test_util.CreateDevice(
        'free', 'atl-01.mtv', 'serial_4', run_target='hammerhead',
        state='Available')
    self.device_5 = datastore_test_util.CreateDevice(
        'free', 'atl-01.mtv', 'serial_5', run_target='hammerhead',
        state='Ignored')
    self.host1_devices = [
        self.device_1, self.device_2, self.device_3, self.device_4,
        self.device_5]
    device_manager._CountDeviceForHost('atl-01.mtv')
    datastore_test_util.CreateHost(
        'presubmit', 'atl-02.mtv', lab_name='alab')
    self.device_6 = datastore_test_util.CreateDevice(
        'presubmit', 'atl-02.mtv', 'serial_6', run_target='hammerhead',
        state='Allocated')
    self.device_7 = datastore_test_util.CreateDevice(
        'presubmit', 'atl-02.mtv', 'serial_7', run_target='hammerhead',
        state='Unavailable')
    self.device_8 = datastore_test_util.CreateDevice(
        'presubmit', 'atl-02.mtv', 'serial_8', run_target='bullhead',
        state='Gone')
    self.device_9 = datastore_test_util.CreateDevice(
        'presubmit', 'atl-02.mtv', 'serial_9', run_target='angler',
        state='Allocated', hidden=True)
    device_manager._CountDeviceForHost('atl-02.mtv')
    self.cloud_host = datastore_test_util.CreateHost(
        'dockerized-tf-gke', 'cloud-tf-1234', lab_name='cloud_tf')
    self.device_10 = datastore_test_util.CreateDevice(
        'dockerized-tf-gke', 'cloud-tf-1234', 'null-device-0',
        run_target='NullDevice')
    device_manager._CountDeviceForHost('cloud-tf-1234')

    self.testapp = webtest.TestApp(device_monitor.APP)
    # Clear Datastore cache
    ndb.get_context().clear_cache()

  def testBuildMetricFields(self):
    expected = {
        metric.METRIC_FIELD_CLUSTER: 'presubmit',
        metric.METRIC_FIELD_HOSTNAME: 'atl-02.mtv',
        metric.METRIC_FIELD_RUN_TARGET: 'angler',
        metric.METRIC_FIELD_SERIAL: 'serial_9'
    }
    self.assertEqual(expected, device_monitor._BuildMetricFields(self.device_9))

  @mock.patch.object(metric_util, 'MetricBatch')
  @mock.patch.object(metric, 'GetDeviceStateMetric')
  def testScanDevices_stateMetrics(
      self, mock_get_device_state_metric, mock_new_metric_batch):
    """Test metrics are reported for all devices on all states."""
    mock_metric_batch = mock.MagicMock()
    mock_new_metric_batch.return_value = mock_metric_batch
    device_state_metrics = {}
    def metric_side_effect(state):
      if state not in device_state_metrics:
        device_state_metrics[state] = mock.MagicMock()
      return device_state_metrics[state]
    mock_get_device_state_metric.side_effect = metric_side_effect
    device_monitor._ScanDevices()

    # 4 allocated, 2 available, and 1 of each of the rest
    get_metric_calls = [mock.call('Allocated')
                       ] * 4 + [mock.call('Available')] * 2 + [
                           mock.call('Gone')
                       ]
    mock_get_device_state_metric.assert_has_calls(get_metric_calls,
                                                  any_order=True)

    allocated = [
        mock.call.Set(
            1, device_monitor._BuildMetricFields(self.device_1),
            batch=mock_metric_batch),
        mock.call.Set(
            1, device_monitor._BuildMetricFields(self.device_2),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_3),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_4),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_5),
            batch=mock_metric_batch),
        mock.call.Set(
            1, device_monitor._BuildMetricFields(self.device_6),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_7),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_8),
            batch=mock_metric_batch),
    ]

    available = [
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_1),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_2),
            batch=mock_metric_batch),
        mock.call.Set(
            1, device_monitor._BuildMetricFields(self.device_3),
            batch=mock_metric_batch),
        mock.call.Set(
            1, device_monitor._BuildMetricFields(self.device_4),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_5),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_6),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_7),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_8),
            batch=mock_metric_batch),
    ]
    gone = [
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_1),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_2),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_3),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_4),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_5),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_6),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_7),
            batch=mock_metric_batch),
        mock.call.Set(
            1, device_monitor._BuildMetricFields(self.device_8),
            batch=mock_metric_batch),
    ]
    device_state_metrics['Allocated'].assert_has_calls(allocated,
                                                       any_order=True)
    device_state_metrics['Available'].assert_has_calls(available,
                                                       any_order=True)
    device_state_metrics['Gone'].assert_has_calls(gone,
                                                  any_order=True)
    mock_metric_batch.Emit.assert_called_once()

  @mock.patch.object(metric_util, 'MetricBatch')
  @mock.patch.object(metric, 'devices_visible')
  @mock.patch.object(metric, 'GetDeviceStateMetric')
  def testScanDevices_visibleMetrics(
      self, mock_get, mock_visible, mock_new_metric_batch):
    """Test metrics for visible and hidden devices."""
    mock_metric_batch = mock.MagicMock()
    mock_new_metric_batch.return_value = mock_metric_batch
    device_state_metrics = {}
    def metric_side_effect(state):
      if state not in device_state_metrics:
        device_state_metrics[state] = mock.MagicMock()
      return device_state_metrics[state]
    mock_get.side_effect = metric_side_effect
    device_monitor._ScanDevices()
    # Hidden devices should not be reported
    mock_visible.assert_has_calls(
        [
            mock.call.Set(
                1,
                device_monitor._BuildMetricFields(self.device_1),
                batch=mock_metric_batch),
            mock.call.Set(
                1,
                device_monitor._BuildMetricFields(self.device_2),
                batch=mock_metric_batch),
            mock.call.Set(
                1,
                device_monitor._BuildMetricFields(self.device_3),
                batch=mock_metric_batch),
            mock.call.Set(
                1,
                device_monitor._BuildMetricFields(self.device_4),
                batch=mock_metric_batch),
            mock.call.Set(
                1,
                device_monitor._BuildMetricFields(self.device_5),
                batch=mock_metric_batch),
            mock.call.Set(
                1,
                device_monitor._BuildMetricFields(self.device_6),
                batch=mock_metric_batch),
            mock.call.Set(
                1,
                device_monitor._BuildMetricFields(self.device_7),
                batch=mock_metric_batch),
            mock.call.Set(
                1,
                device_monitor._BuildMetricFields(self.device_8),
                batch=mock_metric_batch),
        ])
    device_state_metrics['Allocated'].assert_has_calls(
        [
            mock.call.Set(
                1,
                device_monitor._BuildMetricFields(self.device_1),
                batch=mock_metric_batch),
            mock.call.Set(
                1,
                device_monitor._BuildMetricFields(self.device_2),
                batch=mock_metric_batch),
            mock.call.Set(
                0,
                device_monitor._BuildMetricFields(self.device_3),
                batch=mock_metric_batch),
            mock.call.Set(
                0,
                device_monitor._BuildMetricFields(self.device_4),
                batch=mock_metric_batch),
            mock.call.Set(
                0,
                device_monitor._BuildMetricFields(self.device_5),
                batch=mock_metric_batch),
            mock.call.Set(
                1,
                device_monitor._BuildMetricFields(self.device_6),
                batch=mock_metric_batch),
            mock.call.Set(
                0,
                device_monitor._BuildMetricFields(self.device_7),
                batch=mock_metric_batch),
            mock.call.Set(
                0,
                device_monitor._BuildMetricFields(self.device_8),
                batch=mock_metric_batch),
        ])
    mock_metric_batch.Emit.assert_called_once()

  @mock.patch.object(metric_util, 'MetricBatch')
  @mock.patch.object(metric, 'devices_offline')
  @mock.patch.object(metric, 'GetDeviceStateMetric')
  def testScanDevices_offlineMetrics(
      self, mock_get, mock_offline, mock_new_metric_batch):
    """Test metrics for offline devices."""
    mock_metric_batch = mock.MagicMock()
    mock_new_metric_batch.return_value = mock_metric_batch
    device_state_metrics = {}
    def metric_side_effect(state):
      if state not in device_state_metrics:
        device_state_metrics[state] = mock.MagicMock()
      return device_state_metrics[state]
    mock_get.side_effect = metric_side_effect
    device_monitor._ScanDevices()
    offline = [
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_1),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_2),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_3),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_4),
            batch=mock_metric_batch),
        mock.call.Set(
            1, device_monitor._BuildMetricFields(self.device_5),
            batch=mock_metric_batch),
        mock.call.Set(
            0, device_monitor._BuildMetricFields(self.device_6),
            batch=mock_metric_batch),
        mock.call.Set(
            1, device_monitor._BuildMetricFields(self.device_7),
            batch=mock_metric_batch),
        mock.call.Set(
            1, device_monitor._BuildMetricFields(self.device_8),
            batch=mock_metric_batch),
    ]
    mock_offline.assert_has_calls(offline, any_order=True)
    mock_metric_batch.Emit.assert_called_once()

  def testUpdateClusters(self):
    # Test counting devices for a cluster
    device_monitor._UpdateClusters()
    cluster = datastore_entities.ClusterInfo.get_by_id('free')
    self.assertEqual(5, cluster.total_devices)
    self.assertEqual(2, cluster.available_devices)
    self.assertEqual(2, cluster.allocated_devices)
    self.assertEqual(1, cluster.offline_devices)
    cluster = datastore_entities.ClusterInfo.get_by_id('presubmit')
    self.assertEqual(3, cluster.total_devices)
    self.assertEqual(0, cluster.available_devices)
    self.assertEqual(1, cluster.allocated_devices)
    self.assertEqual(2, cluster.offline_devices)
    cluster = datastore_entities.ClusterInfo.get_by_id('dockerized-tf-gke')
    self.assertEqual(1, cluster.total_devices)
    self.assertEqual(1, cluster.available_devices)
    self.assertEqual(0, cluster.allocated_devices)
    self.assertEqual(0, cluster.offline_devices)

  def testUpdateClusters_deleteCluster(self):
    # Test counting devices for a cluster without host
    # Cluster previously had devices
    cluster = datastore_entities.ClusterInfo(
        id='cluster_to_delete',
        cluster='cluster_to_delete',
        total_devices=5,
        available_devices=1,
        allocated_devices=1,
        offline_devices=3)
    cluster.put()
    device_monitor._UpdateClusters()
    self.assertIsNone(
        datastore_entities.ClusterInfo.get_by_id('cluster_to_delete'))

  def testUpdateLabs(self):
    device_monitor._UpdateLabs()
    labs = datastore_entities.LabInfo.query()
    lab_names = {lab.lab_name for lab in labs}
    self.assertEqual({'alab', 'cloud_tf'}, lab_names)

  @mock.patch.object(device_manager, 'StartHostSync')
  def testScanHosts(self, mock_start_sync):
    device_monitor._ScanHosts()
    mock_start_sync.assert_has_calls(
        [mock.call('atl-01.mtv'),
         mock.call('atl-02.mtv'),
         mock.call('cloud-tf-1234')],
        any_order=True)

  @mock.patch.object(device_monitor, '_Now')
  @mock.patch.object(device_manager, 'HideHost')
  @mock.patch.object(device_manager, 'UpdateGoneHost')
  def testSyncHost(self, mock_gone, mock_hide, mock_now):
    """Normal sync will just add the task back."""
    now = datetime.datetime(2019, 11, 14, 10, 10)
    before = now - datetime.timedelta(minutes=2)
    mock_now.return_value = now
    self.host1.timestamp = before
    self.host1.put()

    should_sync = device_monitor._SyncHost(self.host1.hostname)

    self.assertTrue(should_sync)
    self.assertFalse(mock_gone.called)
    self.assertFalse(mock_hide.called)

  @mock.patch.object(device_monitor, '_Now')
  @mock.patch.object(device_manager, 'UpdateGoneHost')
  def testSyncHost_hideHost(self, mock_gone, mock_now):
    """Test _SyncHost will hide host and it devices."""
    now = datetime.datetime(2019, 11, 14, 10, 10)
    before = now - datetime.timedelta(days=35)
    mock_now.return_value = now
    self.host1.timestamp = before
    self.host1.put()

    should_sync = device_monitor._SyncHost(self.host1.hostname)

    self.assertFalse(should_sync)
    self.host1 = self.host1.key.get()
    self.assertTrue(self.host1.hidden)
    for d in self.host1_devices:
      self.assertTrue(d.key.get().hidden)
    self.assertFalse(mock_gone.called)

  @mock.patch.object(device_monitor, '_Now')
  @mock.patch.object(device_manager, 'UpdateGoneHost')
  def testSyncHost_hideCloudTfHost(self, mock_gone, mock_now):
    """Test _SyncHost will hide cloud tf host and it devices."""
    now = datetime.datetime(2019, 11, 14, 10, 10)
    before = now - datetime.timedelta(minutes=65)
    mock_now.return_value = now
    self.cloud_host.timestamp = before
    self.cloud_host.put()

    should_sync = device_monitor._SyncHost(self.cloud_host.hostname)

    self.assertFalse(should_sync)
    self.assertTrue(self.cloud_host.key.get().hidden)
    self.assertTrue(self.device_10.key.get().hidden)
    self.assertFalse(mock_gone.called)

  @mock.patch.object(device_monitor, '_Now')
  @mock.patch.object(device_manager, 'HideHost')
  def testSyncHost_hostGone(self, mock_hide, mock_now):
    """Test _SyncHost will set host and its devices to GONE."""
    now = datetime.datetime(2019, 11, 14, 10, 10)
    before = now - datetime.timedelta(hours=2)
    mock_now.return_value = now
    self.host1.timestamp = before
    self.host1.put()

    should_sync = device_monitor._SyncHost(self.host1.hostname)

    self.assertTrue(should_sync)
    self.host1 = self.host1.key.get()
    self.assertEqual(api_messages.HostState.GONE, self.host1.host_state)
    for d in self.host1_devices:
      self.assertEqual(common.DeviceState.GONE, d.key.get().state)
    self.assertFalse(mock_hide.called)
    host_histories = device_manager.GetHostStateHistory(self.host1.hostname)
    self.assertEqual(1, len(host_histories))
    self.assertEqual(api_messages.HostState.GONE, host_histories[0].state)
    for d in self.host1_devices:
      device_histories = device_manager.GetDeviceHistory(
          self.host1.hostname, d.device_serial)
      self.assertEqual(1, len(device_histories))
      self.assertEqual(common.DeviceState.GONE, device_histories[0].state)

  @mock.patch.object(device_monitor, '_Now')
  @mock.patch.object(device_monitor, '_PubsubClient')
  def testPublishHostMessage(self, mock_pubsub_client, mock_now):
    now = datetime.datetime(2019, 11, 14, 10, 10)
    mock_now.return_value = now
    device_monitor._PublishHostMessage(self.host1.hostname)

    topic, messages = mock_pubsub_client.PublishMessages.call_args[0]
    self.assertEqual(device_monitor.HOST_AND_DEVICE_PUBSUB_TOPIC, topic)
    message = messages[0]
    self.assertEqual('host', message['attributes']['type'])
    data = message['data']
    data = base64.urlsafe_b64decode(data)
    msg_dict = json.loads(data)
    self.assertEqual('2019-11-14T10:10:00', msg_dict['publish_timestamp'])
    host_msg = protojson.decode_message(api_messages.HostInfo, data)
    self.assertEqual(self.host1.hostname, host_msg.hostname)
    self.assertEqual(str(self.host1.host_state), host_msg.host_state)
    self.assertEqual(5, len(host_msg.device_infos))
    for msg, d in zip(host_msg.device_infos, self.host1_devices):
      self.assertEqual(d.device_serial, msg.device_serial)
      self.assertEqual(d.state, msg.state)


if __name__ == '__main__':
  unittest.main()
