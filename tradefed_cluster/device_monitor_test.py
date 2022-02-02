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

"""Tests for device_monitor."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import datetime
import json
import unittest

import mock
from protorpc import protojson
from six.moves import zip
import webtest

from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import device_manager
from tradefed_cluster import device_monitor
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.util import ndb_shim as ndb


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
        'dockerized-tf-gke', 'cloud-tf-1234', lab_name='cloud-tf')
    self.device_10 = datastore_test_util.CreateDevice(
        'dockerized-tf-gke', 'cloud-tf-1234', 'null-device-0',
        run_target='NullDevice')
    device_manager._CountDeviceForHost('cloud-tf-1234')
    datastore_test_util.CreateHost('', 'mh.host', lab_name='mh')

    self.testapp = webtest.TestApp(device_monitor.APP)
    # Clear Datastore cache
    ndb.get_context().clear_cache()

  @mock.patch.object(device_manager, 'StartHostSync')
  def testUpdateClusters(self, _):
    # Test counting devices for a cluster
    hosts = device_monitor._ScanHosts()
    device_monitor._UpdateClusters(hosts)
    cluster = datastore_entities.ClusterInfo.get_by_id('free')
    self.assertEqual('alab', cluster.lab_name)
    self.assertEqual(5, cluster.total_devices)
    self.assertEqual(2, cluster.available_devices)
    self.assertEqual(2, cluster.allocated_devices)
    self.assertEqual(1, cluster.offline_devices)
    cluster = datastore_entities.ClusterInfo.get_by_id('presubmit')
    self.assertEqual('alab', cluster.lab_name)
    self.assertEqual(3, cluster.total_devices)
    self.assertEqual(0, cluster.available_devices)
    self.assertEqual(1, cluster.allocated_devices)
    self.assertEqual(2, cluster.offline_devices)
    cluster = datastore_entities.ClusterInfo.get_by_id('dockerized-tf-gke')
    self.assertEqual('cloud-tf', cluster.lab_name)
    self.assertEqual(1, cluster.total_devices)
    self.assertEqual(1, cluster.available_devices)
    self.assertEqual(0, cluster.allocated_devices)
    self.assertEqual(0, cluster.offline_devices)
    cluster = datastore_entities.ClusterInfo.get_by_id(
        common.UNKNOWN_CLUSTER_NAME)
    self.assertEqual('mh', cluster.lab_name)
    self.assertEqual(0, cluster.total_devices)
    self.assertEqual(0, cluster.available_devices)
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
    device_monitor._UpdateClusters([])
    self.assertIsNone(
        datastore_entities.ClusterInfo.get_by_id('cluster_to_delete'))

  def testUpdateClusters_calculateHostUpdateStateSummary(self):
    cluster_name = 'cluster1'
    host1 = datastore_test_util.CreateHost(
        cluster_name, 'host1.mtv', lab_name='alab')
    host2 = datastore_test_util.CreateHost(
        cluster_name, 'host2.mtv', lab_name='alab')
    host3 = datastore_test_util.CreateHost(
        cluster_name, 'host3.mtv', lab_name='alab')
    host4 = datastore_test_util.CreateHost(
        cluster_name, 'host4.mtv', lab_name='alab')
    host5 = datastore_test_util.CreateHost(
        cluster_name, 'host5.mtv', lab_name='alab')
    host6 = datastore_test_util.CreateHost(
        cluster_name, 'host6.mtv', lab_name='alab')
    host7 = datastore_test_util.CreateHost(
        cluster_name, 'host7.mtv', lab_name='alab')
    host8 = datastore_test_util.CreateHost(
        cluster_name, 'host8.mtv', lab_name='alab')
    host9 = datastore_test_util.CreateHost(
        cluster_name, 'host9.mtv', lab_name='alab')
    datastore_test_util.CreateHostUpdateState(
        host1.hostname, state=api_messages.HostUpdateState.SYNCING)
    datastore_test_util.CreateHostUpdateState(
        host2.hostname, state=api_messages.HostUpdateState.SYNCING)
    datastore_test_util.CreateHostUpdateState(
        host3.hostname, state=api_messages.HostUpdateState.RESTARTING)
    datastore_test_util.CreateHostUpdateState(
        host4.hostname, state=api_messages.HostUpdateState.ERRORED)
    datastore_test_util.CreateHostUpdateState(
        host5.hostname, state=api_messages.HostUpdateState.PENDING)
    datastore_test_util.CreateHostUpdateState(
        host6.hostname, state=api_messages.HostUpdateState.TIMED_OUT)
    datastore_test_util.CreateHostUpdateState(
        host7.hostname, state=api_messages.HostUpdateState.SUCCEEDED)
    datastore_test_util.CreateHostUpdateState(
        host8.hostname, state=api_messages.HostUpdateState.SHUTTING_DOWN)
    datastore_test_util.CreateHostUpdateState(
        host9.hostname, state=api_messages.HostUpdateState.UNKNOWN)
    device_monitor._UpdateClusters(
        [host1, host2, host3, host4, host5, host6, host7, host8, host9])
    cluster = datastore_entities.ClusterInfo.get_by_id(cluster_name)
    self.assertEqual(9, cluster.host_update_state_summary.total)
    self.assertEqual(1, cluster.host_update_state_summary.pending)
    self.assertEqual(2, cluster.host_update_state_summary.syncing)
    self.assertEqual(1, cluster.host_update_state_summary.shutting_down)
    self.assertEqual(1, cluster.host_update_state_summary.restarting)
    self.assertEqual(1, cluster.host_update_state_summary.errored)
    self.assertEqual(1, cluster.host_update_state_summary.timed_out)
    self.assertEqual(1, cluster.host_update_state_summary.succeeded)
    self.assertEqual(1, cluster.host_update_state_summary.unknown)

  def testUpdateClusters_calculateHostUpdateStateSummaryPerVersion(self):
    cluster_name = 'cluster1'
    host1 = datastore_test_util.CreateHost(
        cluster_name, 'host1.mtv', lab_name='alab')
    host2 = datastore_test_util.CreateHost(
        cluster_name, 'host2.mtv', lab_name='alab')
    host3 = datastore_test_util.CreateHost(
        cluster_name, 'host3.mtv', lab_name='alab')
    host4 = datastore_test_util.CreateHost(
        cluster_name, 'host4.mtv', lab_name='alab')
    host5 = datastore_test_util.CreateHost(
        cluster_name, 'host5.mtv', lab_name='alab')
    host6 = datastore_test_util.CreateHost(
        cluster_name, 'host6.mtv', lab_name='alab')
    host7 = datastore_test_util.CreateHost(
        cluster_name, 'host7.mtv', lab_name='alab')
    host8 = datastore_test_util.CreateHost(
        cluster_name, 'host8.mtv', lab_name='alab')
    host9 = datastore_test_util.CreateHost(
        cluster_name, 'host9.mtv', lab_name='alab')
    datastore_test_util.CreateHostUpdateState(
        host1.hostname,
        state=api_messages.HostUpdateState.SYNCING,
        target_version='v2')
    datastore_test_util.CreateHostUpdateState(
        host2.hostname,
        state=api_messages.HostUpdateState.SYNCING,
        target_version='v2')
    datastore_test_util.CreateHostUpdateState(
        host3.hostname,
        state=api_messages.HostUpdateState.RESTARTING,
        target_version='v2')
    datastore_test_util.CreateHostUpdateState(
        host4.hostname,
        state=api_messages.HostUpdateState.ERRORED,
        target_version='v2')
    datastore_test_util.CreateHostUpdateState(
        host5.hostname,
        state=api_messages.HostUpdateState.PENDING,
        target_version='v2')
    datastore_test_util.CreateHostUpdateState(
        host6.hostname,
        state=api_messages.HostUpdateState.TIMED_OUT,
        target_version='v2')
    datastore_test_util.CreateHostUpdateState(
        host7.hostname,
        state=api_messages.HostUpdateState.SUCCEEDED,
        target_version='v1')
    datastore_test_util.CreateHostUpdateState(
        host8.hostname,
        state=api_messages.HostUpdateState.SHUTTING_DOWN,
        target_version='v2')
    datastore_test_util.CreateHostUpdateState(
        host9.hostname,
        state=api_messages.HostUpdateState.UNKNOWN,
        target_version='v2')

    device_monitor._UpdateClusters(
        [host1, host2, host3, host4, host5, host6, host7, host8, host9])

    cluster = datastore_entities.ClusterInfo.get_by_id(cluster_name)
    version_to_summaries = {
        summary.target_version: summary
        for summary in cluster.host_update_state_summaries_by_version
    }
    self.assertEqual(1, version_to_summaries['v1'].total)
    self.assertEqual(0, version_to_summaries['v1'].pending)
    self.assertEqual(0, version_to_summaries['v1'].syncing)
    self.assertEqual(0, version_to_summaries['v1'].shutting_down)
    self.assertEqual(0, version_to_summaries['v1'].restarting)
    self.assertEqual(0, version_to_summaries['v1'].errored)
    self.assertEqual(0, version_to_summaries['v1'].timed_out)
    self.assertEqual(1, version_to_summaries['v1'].succeeded)
    self.assertEqual(0, version_to_summaries['v1'].unknown)

    self.assertEqual(8, version_to_summaries['v2'].total)
    self.assertEqual(1, version_to_summaries['v2'].pending)
    self.assertEqual(2, version_to_summaries['v2'].syncing)
    self.assertEqual(1, version_to_summaries['v2'].shutting_down)
    self.assertEqual(1, version_to_summaries['v2'].restarting)
    self.assertEqual(1, version_to_summaries['v2'].errored)
    self.assertEqual(1, version_to_summaries['v2'].timed_out)
    self.assertEqual(0, version_to_summaries['v2'].succeeded)
    self.assertEqual(1, version_to_summaries['v2'].unknown)

  def testUpdateClusters_calculateHostCountByHarnessVersion(self):
    cluster_name = 'cluster1'
    host1 = datastore_test_util.CreateHost(
        cluster_name, 'host1.mtv', lab_name='alab', test_harness_version='v1')
    host2 = datastore_test_util.CreateHost(
        cluster_name, 'host2.mtv', lab_name='alab', test_harness_version='v1')
    host3 = datastore_test_util.CreateHost(
        cluster_name, 'host3.mtv', lab_name='alab', test_harness_version='v1')
    host4 = datastore_test_util.CreateHost(
        cluster_name, 'host4.mtv', lab_name='alab', test_harness_version='v2')
    host5 = datastore_test_util.CreateHost(
        cluster_name, 'host5.mtv', lab_name='alab', test_harness_version='v3a')
    host6 = datastore_test_util.CreateHost(
        cluster_name, 'host6.mtv', lab_name='alab', test_harness_version='v3a')
    host7 = datastore_test_util.CreateHost(
        cluster_name, 'host7.mtv', lab_name='alab', test_harness_version='v3a')
    host8 = datastore_test_util.CreateHost(
        cluster_name, 'host8.mtv', lab_name='alab', test_harness_version='v3a')
    host9 = datastore_test_util.CreateHost(
        cluster_name, 'host9.mtv', lab_name='alab', test_harness_version=None)

    device_monitor._UpdateClusters(
        [host1, host2, host3, host4, host5, host6, host7, host8, host9])
    cluster = datastore_entities.ClusterInfo.get_by_id(cluster_name)

    expected_harness_version_counts = {
        'v1': 3,
        'v2': 1,
        'v3a': 4,
        'UNKNOWN': 1,
    }
    self.assertDictEqual(
        expected_harness_version_counts, cluster.host_count_by_harness_version)

  def testUpdateClusters_skipEmptyLabName(self):
    cluster_name = 'cluster1'
    hosts = [
        datastore_test_util.CreateHost(
            cluster_name, 'atl-07.mtv', lab_name=None),
        datastore_test_util.CreateHost(
            cluster_name, 'atl-08.mtv', lab_name='lab1'),
        datastore_test_util.CreateHost(
            cluster_name, 'atl-09.mtv', lab_name=None),
        datastore_test_util.CreateHost(
            cluster_name, 'atl-10.mtv', lab_name=None),
    ]
    device_monitor._UpdateClusters(hosts)
    cluster = datastore_entities.ClusterInfo.get_by_id(cluster_name)
    self.assertEqual('lab1', cluster.lab_name)

  def testUpdateClusters_noLabNameFound(self):
    cluster_name = 'cluster1'
    hosts = [
        datastore_test_util.CreateHost(
            cluster_name, 'atl-08.mtv', lab_name=None),
        datastore_test_util.CreateHost(
            cluster_name, 'atl-09.mtv', lab_name=None),
        datastore_test_util.CreateHost(
            cluster_name, 'atl-10.mtv', lab_name=None),
    ]
    device_monitor._UpdateClusters(hosts)
    cluster = datastore_entities.ClusterInfo.get_by_id(cluster_name)
    self.assertEqual('UNKNOWN', cluster.lab_name)

  def testUpdateLabs(self):
    clusters = device_monitor._UpdateClusters([self.host1, self.cloud_host])
    device_monitor._UpdateLabs(clusters)
    labs = datastore_entities.LabInfo.query()
    lab_names = {lab.lab_name for lab in labs}
    self.assertCountEqual({'alab', 'cloud-tf'}, lab_names)

  def testUpdateLabs_withUnknownLabFromClusterInfo(self):
    cluster1 = datastore_test_util.CreateCluster(
        'cluster_nolabname',
        lab_name=None)
    device_monitor._UpdateLabs([cluster1])
    labs = datastore_entities.LabInfo.query()
    lab_names = {lab.lab_name for lab in labs}
    self.assertCountEqual(['UNKNOWN'], lab_names)

  def testUpdateLabs_calculateHostUpdateStateSummaryFromClusterInfos(self):
    datastore_test_util.CreateLabInfo('alab', owners=['user1'])
    cluster1 = datastore_test_util.CreateCluster(
        'cluster1',
        lab_name='alab',
        host_update_state_summary=datastore_entities.HostUpdateStateSummary(
            total=13,
            pending=1,
            syncing=2,
            shutting_down=3,
            restarting=4,
            errored=3))
    cluster2 = datastore_test_util.CreateCluster(
        'cluster2',
        lab_name='alab',
        host_update_state_summary=datastore_entities.HostUpdateStateSummary(
            total=14,
            shutting_down=3,
            restarting=4,
            errored=2,
            timed_out=2,
            succeeded=1,
            unknown=2))
    device_monitor._UpdateLabs([cluster1, cluster2])
    lab_info = datastore_entities.LabInfo.get_by_id('alab')
    self.assertCountEqual(['user1'], lab_info.owners)
    self.assertEqual(27, lab_info.host_update_state_summary.total)
    self.assertEqual(1, lab_info.host_update_state_summary.pending)
    self.assertEqual(2, lab_info.host_update_state_summary.syncing)
    self.assertEqual(6, lab_info.host_update_state_summary.shutting_down)
    self.assertEqual(8, lab_info.host_update_state_summary.restarting)
    self.assertEqual(5, lab_info.host_update_state_summary.errored)
    self.assertEqual(2, lab_info.host_update_state_summary.timed_out)
    self.assertEqual(1, lab_info.host_update_state_summary.succeeded)
    self.assertEqual(2, lab_info.host_update_state_summary.unknown)

  def testUpdateLabs_calculateHostUpdateStateSummaryWithExistingLab(self):
    cluster1 = datastore_test_util.CreateCluster(
        'cluster1',
        lab_name='alab',
        host_update_state_summary=datastore_entities.HostUpdateStateSummary(
            total=13,
            pending=1,
            syncing=2,
            shutting_down=3,
            restarting=4,
            errored=3))
    cluster2 = datastore_test_util.CreateCluster(
        'cluster2',
        lab_name='alab',
        host_update_state_summary=datastore_entities.HostUpdateStateSummary(
            total=14,
            shutting_down=3,
            restarting=4,
            errored=2,
            timed_out=2,
            succeeded=1,
            unknown=2))
    device_monitor._UpdateLabs([cluster1, cluster2])
    lab_info = datastore_entities.LabInfo.get_by_id('alab')
    self.assertEqual(27, lab_info.host_update_state_summary.total)
    self.assertEqual(1, lab_info.host_update_state_summary.pending)
    self.assertEqual(2, lab_info.host_update_state_summary.syncing)
    self.assertEqual(6, lab_info.host_update_state_summary.shutting_down)
    self.assertEqual(8, lab_info.host_update_state_summary.restarting)
    self.assertEqual(5, lab_info.host_update_state_summary.errored)
    self.assertEqual(2, lab_info.host_update_state_summary.timed_out)
    self.assertEqual(1, lab_info.host_update_state_summary.succeeded)
    self.assertEqual(2, lab_info.host_update_state_summary.unknown)

  def testUpdateLabs_calculateUpdateStateSummaryPerVersionFromClusters(self):
    cluster1 = datastore_test_util.CreateCluster(
        'cluster1',
        lab_name='alab',
        host_update_state_summaries_by_version=[
            datastore_entities.HostUpdateStateSummary(
                total=17,
                pending=1,
                syncing=2,
                shutting_down=3,
                restarting=4,
                errored=3,
                timed_out=1,
                succeeded=3,
                target_version='v1'),
            datastore_entities.HostUpdateStateSummary(
                total=6,
                pending=1,
                syncing=1,
                shutting_down=1,
                restarting=1,
                errored=2,
                target_version='v2'),
        ])
    cluster2 = datastore_test_util.CreateCluster(
        'cluster2',
        lab_name='alab',
        host_update_state_summaries_by_version=[
            datastore_entities.HostUpdateStateSummary(
                total=11,
                pending=2,
                syncing=2,
                shutting_down=2,
                restarting=2,
                errored=0,
                timed_out=2,
                succeeded=1,
                target_version='v1'),
            datastore_entities.HostUpdateStateSummary(
                total=7,
                pending=2,
                syncing=0,
                shutting_down=2,
                restarting=1,
                errored=2,
                target_version='v3'),
        ])

    device_monitor._UpdateLabs([cluster1, cluster2])

    lab_info = datastore_entities.LabInfo.get_by_id('alab')
    version_to_summaries = {
        summary.target_version: summary
        for summary in lab_info.host_update_state_summaries_by_version
    }

    self.assertEqual(28, version_to_summaries['v1'].total)
    self.assertEqual(3, version_to_summaries['v1'].pending)
    self.assertEqual(4, version_to_summaries['v1'].syncing)
    self.assertEqual(5, version_to_summaries['v1'].shutting_down)
    self.assertEqual(6, version_to_summaries['v1'].restarting)
    self.assertEqual(3, version_to_summaries['v1'].errored)
    self.assertEqual(3, version_to_summaries['v1'].timed_out)
    self.assertEqual(4, version_to_summaries['v1'].succeeded)
    self.assertEqual(0, version_to_summaries['v1'].unknown)

    self.assertEqual(6, version_to_summaries['v2'].total)
    self.assertEqual(1, version_to_summaries['v2'].pending)
    self.assertEqual(1, version_to_summaries['v2'].syncing)
    self.assertEqual(1, version_to_summaries['v2'].shutting_down)
    self.assertEqual(1, version_to_summaries['v2'].restarting)
    self.assertEqual(2, version_to_summaries['v2'].errored)
    self.assertEqual(0, version_to_summaries['v2'].timed_out)
    self.assertEqual(0, version_to_summaries['v2'].succeeded)
    self.assertEqual(0, version_to_summaries['v2'].unknown)

    self.assertEqual(7, version_to_summaries['v3'].total)
    self.assertEqual(2, version_to_summaries['v3'].pending)
    self.assertEqual(0, version_to_summaries['v3'].syncing)
    self.assertEqual(2, version_to_summaries['v3'].shutting_down)
    self.assertEqual(1, version_to_summaries['v3'].restarting)
    self.assertEqual(2, version_to_summaries['v3'].errored)
    self.assertEqual(0, version_to_summaries['v3'].timed_out)
    self.assertEqual(0, version_to_summaries['v3'].succeeded)
    self.assertEqual(0, version_to_summaries['v3'].unknown)

  def testUpdateLabs_calculateHostCountByHarnessVersion(self):
    host_count_by_harness_version_1 = {
        'v1': 5,
        'v2': 3,
    }
    cluster1 = datastore_test_util.CreateCluster(
        'cluster1',
        lab_name='alab',
        host_count_by_harness_version=host_count_by_harness_version_1)
    host_count_by_harness_version_2 = {
        'v1': 5,
        'v3': 7,
    }
    cluster2 = datastore_test_util.CreateCluster(
        'cluster2',
        lab_name='alab',
        host_count_by_harness_version=host_count_by_harness_version_2)

    device_monitor._UpdateLabs([cluster1, cluster2])
    lab_info = datastore_entities.LabInfo.get_by_id('alab')

    expected_host_count_by_harness_version = {
        'v1': 10,
        'v2': 3,
        'v3': 7,
    }
    self.assertDictEqual(
        expected_host_count_by_harness_version,
        lab_info.host_count_by_harness_version)

  @mock.patch.object(device_manager, 'StartHostSync')
  def testScanHosts(self, mock_start_sync):
    device_monitor._ScanHosts()
    mock_start_sync.assert_has_calls(
        [mock.call('atl-01.mtv'),
         mock.call('atl-02.mtv'),
         mock.call('cloud-tf-1234')],
        any_order=True)

  @mock.patch.object(common, 'Now')
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

  @mock.patch.object(common, 'Now')
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

  @mock.patch.object(common, 'Now')
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

  @mock.patch.object(common, 'Now')
  def testSyncHost_hideCloudTfHostWithoutLabName(self, mock_now):
    """Test _SyncHost will hide cloud tf host without lab name."""
    now = datetime.datetime(2019, 11, 14, 10, 10)
    before = now - datetime.timedelta(minutes=65)
    mock_now.return_value = now
    cloud_host = datastore_test_util.CreateHost(
        'dockerized-tf-gke', 'cloud-tf-2345', lab_name=None)
    cloud_host.timestamp = before
    cloud_host.put()
    gke_host = datastore_test_util.CreateHost(
        'dockerized-tf-gke', 'dockerized-tf-gke-2345', lab_name=None)
    gke_host.timestamp = before
    gke_host.put()

    should_sync = device_monitor._SyncHost(cloud_host.hostname)
    self.assertFalse(should_sync)
    should_sync = device_monitor._SyncHost(gke_host.hostname)
    self.assertFalse(should_sync)
    self.assertTrue(cloud_host.key.get().hidden)
    self.assertTrue(gke_host.key.get().hidden)

  @mock.patch.object(common, 'Now')
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
      device_histories = device_manager.GetDeviceStateHistory(
          self.host1.hostname, d.device_serial)
      self.assertEqual(1, len(device_histories))
      self.assertEqual(common.DeviceState.GONE, device_histories[0].state)

  @mock.patch.object(common, 'Now')
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
    data = common.UrlSafeB64Decode(data)
    msg_dict = json.loads(data)
    self.assertEqual('2019-11-14T10:10:00', msg_dict['publish_timestamp'])
    host_msg = protojson.decode_message(api_messages.HostInfo, data)
    self.assertEqual(self.host1.hostname, host_msg.hostname)
    self.assertEqual(str(self.host1.host_state), host_msg.host_state)
    self.assertEqual(5, len(host_msg.device_infos))
    for msg, d in zip(host_msg.device_infos, self.host1_devices):
      self.assertEqual(d.device_serial, msg.device_serial)
      self.assertEqual(d.state, msg.state)

  @mock.patch.object(common, 'Now')
  def testMarkHostUpdateStateIfTimedOut_NonFinalStateUpdateIsNotTimedOut(
      self, mock_now):
    now = datetime.datetime(2021, 1, 15, 10, 10)
    mock_now.return_value = now
    state_updated_time = (
        now - device_monitor._DEFAULT_HOST_UPDATE_STATE_TIMEOUT +
        datetime.timedelta(minutes=5))
    datastore_test_util.CreateHostUpdateState(
        self.host1.hostname, state=api_messages.HostUpdateState.PENDING,
        update_timestamp=state_updated_time)

    host_update_state = device_monitor._MarkHostUpdateStateIfTimedOut(
        self.host1.hostname)

    self.assertEqual(self.host1.hostname, host_update_state.hostname)
    self.assertEqual(api_messages.HostUpdateState.PENDING,
                     host_update_state.state)
    self.assertEqual(state_updated_time, host_update_state.update_timestamp)

    new_state_histories = device_manager.GetHostUpdateStateHistories(
        self.host1.hostname)
    self.assertEmpty(new_state_histories)

  @mock.patch.object(common, 'Now')
  def testMarkHostUpdateStateIfTimedOut_CustomizedTimedOutMarked(
      self, mock_now):
    customized_timeout_sec = 60
    now = datetime.datetime(2021, 1, 15, 10, 10)
    mock_now.return_value = now
    state_updated_time = (
        now - 5 * datetime.timedelta(seconds=customized_timeout_sec))
    datastore_test_util.CreateHostUpdateState(
        self.host1.hostname, state=api_messages.HostUpdateState.PENDING,
        update_timestamp=state_updated_time)
    datastore_test_util.CreateHostConfig(
        self.host1.hostname, self.host1.lab_name,
        shutdown_timeout_sec=customized_timeout_sec)

    host_update_state = device_monitor._MarkHostUpdateStateIfTimedOut(
        self.host1.hostname)

    default_timeout_limit = (
        now - device_monitor._DEFAULT_HOST_UPDATE_STATE_TIMEOUT)
    # Assert that the last updated time did not reach default timeout limit yet.
    self.assertLess(default_timeout_limit, state_updated_time)

    self.assertEqual(self.host1.hostname, host_update_state.hostname)
    self.assertEqual(api_messages.HostUpdateState.TIMED_OUT,
                     host_update_state.state)
    self.assertEqual(now, host_update_state.update_timestamp)
    expected_display_message = (
        'Host <atl-01.mtv> has HostUpdateState<PENDING> changed on '
        '2021-01-15 10:05:00, which is 300 sec ago, '
        'exceeding timeouts 90 sec. ')
    self.assertEqual(expected_display_message,
                     host_update_state.display_message)

    new_state_histories = device_manager.GetHostUpdateStateHistories(
        self.host1.hostname)
    self.assertLen(new_state_histories, 1)
    self.assertEqual(api_messages.HostUpdateState.TIMED_OUT,
                     new_state_histories[0].state)
    self.assertEqual(now, new_state_histories[0].update_timestamp)

  @mock.patch.object(common, 'Now')
  def testMarkHostUpdateStateIfTimedOut_NonFinalStateUpdateIsTimedOut(
      self, mock_now):
    now = datetime.datetime(2021, 1, 15, 10, 10)
    mock_now.return_value = now
    state_updated_time = (
        now - device_monitor._DEFAULT_HOST_UPDATE_STATE_TIMEOUT -
        datetime.timedelta(minutes=5))
    datastore_test_util.CreateHostUpdateState(
        self.host1.hostname, state=api_messages.HostUpdateState.PENDING,
        update_timestamp=state_updated_time)

    host_update_state = device_monitor._MarkHostUpdateStateIfTimedOut(
        self.host1.hostname)

    self.assertEqual(self.host1.hostname, host_update_state.hostname)
    self.assertEqual(api_messages.HostUpdateState.TIMED_OUT,
                     host_update_state.state)
    self.assertEqual(now, host_update_state.update_timestamp)
    expected_display_message = (
        'Host <atl-01.mtv> has HostUpdateState<PENDING> changed on '
        '2021-01-15 08:05:00, which is 7500 sec ago, '
        'exceeding timeouts 7200 sec. ')
    self.assertEqual(expected_display_message,
                     host_update_state.display_message)

    new_state_histories = device_manager.GetHostUpdateStateHistories(
        self.host1.hostname)
    self.assertLen(new_state_histories, 1)
    self.assertEqual(api_messages.HostUpdateState.TIMED_OUT,
                     new_state_histories[0].state)
    self.assertEqual(now, new_state_histories[0].update_timestamp)

  @mock.patch.object(common, 'Now')
  def testMarkHostUpdateStateIfTimedOut_FinalStateUpdateNotBeingChecked(
      self, mock_now):
    now = datetime.datetime(2021, 1, 15, 10, 10)
    mock_now.return_value = now
    state_updated_time = (
        now - device_monitor._DEFAULT_HOST_UPDATE_STATE_TIMEOUT -
        datetime.timedelta(minutes=5))
    datastore_test_util.CreateHostUpdateState(
        self.host1.hostname, state=api_messages.HostUpdateState.SUCCEEDED,
        update_timestamp=state_updated_time)

    host_update_state = device_monitor._MarkHostUpdateStateIfTimedOut(
        self.host1.hostname)

    self.assertEqual(self.host1.hostname, host_update_state.hostname)
    self.assertEqual(api_messages.HostUpdateState.SUCCEEDED,
                     host_update_state.state)
    self.assertEqual(state_updated_time, host_update_state.update_timestamp)

    new_state_histories = device_manager.GetHostUpdateStateHistories(
        self.host1.hostname)
    self.assertEmpty(new_state_histories)

  @mock.patch.object(common, 'Now')
  def testMarkHostUpdateStateIfTimedOut_AddMissingTimestamp(
      self, mock_now):
    now = datetime.datetime(2021, 1, 15, 10, 10)
    mock_now.return_value = now
    datastore_test_util.CreateHostUpdateState(
        self.host1.hostname, state=api_messages.HostUpdateState.SYNCING,
        update_timestamp=None)

    host_update_state = device_monitor._MarkHostUpdateStateIfTimedOut(
        self.host1.hostname)

    self.assertEqual(self.host1.hostname, host_update_state.hostname)
    self.assertEqual(api_messages.HostUpdateState.SYNCING,
                     host_update_state.state)
    self.assertEqual(now, host_update_state.update_timestamp)

    new_state_histories = device_manager.GetHostUpdateStateHistories(
        self.host1.hostname)
    self.assertLen(new_state_histories, 1)
    self.assertEqual(api_messages.HostUpdateState.SYNCING,
                     new_state_histories[0].state)
    self.assertEqual(now, new_state_histories[0].update_timestamp)

  @mock.patch.object(common, 'Now')
  def testCheckServiceAccountKeyExpiration(self, mock_now):
    now_seconds = 1632707046
    now = datetime.datetime.fromtimestamp(now_seconds)
    mock_now.return_value = now
    expire_timestamp1 = now_seconds + 14 * 24 * 3600
    expire_timestamp2 = now_seconds + 32 * 24 * 3600
    resources = [
        datastore_test_util.CreateHostResourceInstance(
            'service_account_key', 'sa1', [('expire', expire_timestamp1)]),
        datastore_test_util.CreateHostResourceInstance(
            'service_account_key', 'sa2', [('expire', expire_timestamp2)])
    ]
    datastore_test_util.CreateHostResource('ahost', resources=resources)
    sa_keys = device_monitor._CheckServiceAccountKeyExpiration('ahost')
    self.assertEqual(['sa1'], sa_keys)

  @mock.patch.object(common, 'Now')
  def testCheckServiceAccountKeyExpiration_noHostResource(self, mock_now):
    sa_keys = device_monitor._CheckServiceAccountKeyExpiration('ahost')
    self.assertIsNone(sa_keys)

  @mock.patch.object(common, 'Now')
  def testCheckServiceAccountKeyExpiration_noServiceAccountKey(self, mock_now):
    datastore_test_util.CreateHostResource('ahost')
    sa_keys = device_monitor._CheckServiceAccountKeyExpiration('ahost')
    self.assertEmpty(sa_keys)

  @mock.patch.object(common, 'Now')
  def testUpdateHostBadness(self, mock_now):
    now_seconds = 1632707046
    now = datetime.datetime.fromtimestamp(now_seconds)
    mock_now.return_value = now
    host = datastore_test_util.CreateHost(
        'acluster', 'ahost',
        host_state=api_messages.HostState.GONE,
        device_count_summaries=[
            datastore_entities.DeviceCountSummary(
                run_target='r1', total=1, offline=1)],
    )
    expire_timestamp1 = now_seconds + 14 * 24 * 3600
    expire_timestamp2 = now_seconds + 32 * 24 * 3600
    resources = [
        datastore_test_util.CreateHostResourceInstance(
            'service_account_key', 'sa1', [('expire', expire_timestamp1)]),
        datastore_test_util.CreateHostResourceInstance(
            'service_account_key', 'sa2', [('expire', expire_timestamp2)])
    ]
    datastore_test_util.CreateHostResource('ahost', resources=resources)
    device_monitor._UpdateHostBadness('ahost')
    ndb.get_context().clear_cache()
    host = host.key.get()
    self.assertTrue(host.is_bad)
    self.assertEqual(
        ("Host is gone. "
         "Some devices are offline. "
         "['sa1'] are going to expire."),
        host.bad_reason)

  def testUpdateHostBadness_doesntExist(self):
    device_monitor._UpdateHostBadness('fakeHost')

  @mock.patch.object(common, 'Now')
  def testUpdateHostBadness_becomeGood(self, mock_now):
    now_seconds = 1632707046
    now = datetime.datetime.fromtimestamp(now_seconds)
    mock_now.return_value = now
    host = datastore_test_util.CreateHost(
        'acluster', 'ahost',
        host_state=api_messages.HostState.RUNNING,
        device_count_summaries=[
            datastore_entities.DeviceCountSummary(
                run_target='r1', total=1, available=1)],
        is_bad=True,
        bad_reason='Host is gone',
    )
    expire_timestamp1 = now_seconds + 32 * 24 * 3600
    resources = [
        datastore_test_util.CreateHostResourceInstance(
            'service_account_key', 'sa1', [('expire', expire_timestamp1)]),
    ]
    datastore_test_util.CreateHostResource('ahost', resources=resources)
    device_monitor._UpdateHostBadness('ahost')
    ndb.get_context().clear_cache()
    host = host.key.get()
    self.assertFalse(host.is_bad)
    self.assertEqual('', host.bad_reason)

  @mock.patch.object(common, 'Now')
  def testUpdateHostBadness_unchanged(self, mock_now):
    now_seconds = 1632707046
    now = datetime.datetime.fromtimestamp(now_seconds)
    mock_now.return_value = now
    host = datastore_test_util.CreateHost(
        'acluster', 'ahost',
        host_state=api_messages.HostState.GONE,
        device_count_summaries=[
            datastore_entities.DeviceCountSummary(
                run_target='r1', total=1, offline=1)],
    )
    expire_timestamp1 = now_seconds + 14 * 24 * 3600
    expire_timestamp2 = now_seconds + 32 * 24 * 3600
    resources = [
        datastore_test_util.CreateHostResourceInstance(
            'service_account_key', 'sa1', [('expire', expire_timestamp1)]),
        datastore_test_util.CreateHostResourceInstance(
            'service_account_key', 'sa2', [('expire', expire_timestamp2)])
    ]
    datastore_test_util.CreateHostResource('ahost', resources=resources)
    device_monitor._UpdateHostBadness('ahost')
    ndb.get_context().clear_cache()
    host = host.key.get()
    self.assertTrue(host.is_bad)
    self.assertEqual(
        ("Host is gone. "
         "Some devices are offline. "
         "['sa1'] are going to expire."),
        host.bad_reason)
    update_timestamp1 = host.update_timestamp

    now = datetime.datetime.fromtimestamp(now_seconds + 3600)
    mock_now.return_value = now
    device_monitor._UpdateHostBadness('ahost')
    ndb.get_context().clear_cache()
    host = host.key.get()
    self.assertEqual(update_timestamp1, host.update_timestamp)
    self.assertTrue(host.is_bad)
    self.assertEqual(
        ("Host is gone. "
         "Some devices are offline. "
         "['sa1'] are going to expire."),
        host.bad_reason)


if __name__ == '__main__':
  unittest.main()
