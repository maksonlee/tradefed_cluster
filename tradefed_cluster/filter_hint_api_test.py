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
"""Tests for Dimension API."""

import datetime
import unittest

from protorpc import protojson

from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import common
from tradefed_cluster import datastore_test_util


class FilterHintApiTest(api_test.ApiTest):
  """Unit test for FilterHintApi."""

  TIMESTAMP = datetime.datetime.utcfromtimestamp(1431712965)

  def setUp(self):
    api_test.ApiTest.setUp(self)

  def testListClusters_keys(self):
    """Tests ListClusters' keys."""
    cluster_list = [
        datastore_test_util.CreateCluster(cluster='free'),
        datastore_test_util.CreateCluster(cluster='paid')
    ]
    api_request = {'type': 'POOL'}
    api_response = self.testapp.post_json(
        '/_ah/api/FilterHintApi.ListFilterHints', api_request)
    cluster_collection = protojson.decode_message(
        api_messages.FilterHintCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    clusters = list(cluster_collection.filter_hints)
    self.assertEqual(clusters[0].value, cluster_list[0].cluster)
    self.assertEqual(clusters[1].value, cluster_list[1].cluster)

  def testListLabs_keys(self):
    """Tests ListLabs's key."""
    lab_list = [
        datastore_test_util.CreateLabInfo('lab1'),
        datastore_test_util.CreateLabInfo('lab2'),
        datastore_test_util.CreateLabInfo('lab3')
    ]
    api_request = {'type': 'LAB'}
    api_response = self.testapp.post_json(
        '/_ah/api/FilterHintApi.ListFilterHints', api_request)
    lab_collection = protojson.decode_message(api_messages.FilterHintCollection,
                                              api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(3, len(lab_collection.filter_hints))
    labs = list(lab_collection.filter_hints)
    self.assertEqual(labs[0].value, lab_list[0].lab_name)
    self.assertEqual(labs[1].value, lab_list[1].lab_name)
    self.assertEqual(labs[2].value, lab_list[2].lab_name)

  def testListRunTarget_keys(self):
    """Tests ListRunTargets."""
    self._setUpRunTarget()
    api_request = {'type': 'RUN_TARGET'}
    api_response = self.testapp.post_json(
        '/_ah/api/FilterHintApi.ListFilterHints', api_request)
    run_target_collection = protojson.decode_message(
        api_messages.FilterHintCollection, api_response.body)
    self.assertEqual(2, len(run_target_collection.filter_hints))
    self.assertEqual('200 OK', api_response.status)
    run_targets = list(run_target_collection.filter_hints)
    self.assertEqual(run_targets[0].value, 'hammerhead')
    self.assertEqual(run_targets[1].value, 'shamu')

  def _setUpRunTarget(self):
    datastore_test_util.CreateHost(cluster='free', hostname='host_0')
    datastore_test_util.CreateDevice(
        cluster='free',
        hostname='host_0',
        device_serial='device_0',
        run_target='shamu')
    datastore_test_util.CreateDevice(
        cluster='free',
        hostname='host_0',
        device_serial='device_1',
        run_target='shamu')

    datastore_test_util.CreateHost(cluster='free', hostname='host_1')
    datastore_test_util.CreateDevice(
        cluster='free',
        hostname='host_1',
        device_serial='device_2',
        run_target='hammerhead')
    datastore_test_util.CreateHost(cluster='presubmit', hostname='host_2')
    datastore_test_util.CreateDevice(
        cluster='presubmit',
        hostname='host_2',
        device_serial='device_3',
        run_target='hammerhead')

  def testListHostnames(self):
    """Tests ListHosts returns all visible hostnames."""
    host_list = [
        datastore_test_util.CreateHost(cluster='paid', hostname='host_0'),
        datastore_test_util.CreateHost(cluster='free', hostname='host_1')
    ]
    api_request = {'type': 'HOST'}
    api_response = self.testapp.post_json(
        '/_ah/api/FilterHintApi.ListFilterHints', api_request)
    host_collection = protojson.decode_message(
        api_messages.FilterHintCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(host_collection.filter_hints))
    hosts = list(host_collection.filter_hints)
    self.assertEqual(hosts[0].value, host_list[0].hostname)
    self.assertEqual(hosts[1].value, host_list[1].hostname)

  def testListTestHarness(self):
    """Tests ListTestHarness."""
    datastore_test_util.CreateHost(
        cluster='free',
        hostname='host_0',
        timestamp=self.TIMESTAMP,
    )
    datastore_test_util.CreateHost(
        cluster='paid',
        hostname='host_1',
        timestamp=self.TIMESTAMP,
        test_harness='MOBILE_HARNESS',
        test_harness_version='3.0.1',
    )
    datastore_test_util.CreateHost(
        cluster='free',
        hostname='host_2',
        lab_name='alab',
        assignee='auser',
        hidden=True,
    )
    api_request = {'type': 'TEST_HARNESS'}
    api_response = self.testapp.post_json(
        '/_ah/api/FilterHintApi.ListFilterHints', api_request)
    test_harness_collection = protojson.decode_message(
        api_messages.FilterHintCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(test_harness_collection.filter_hints))
    harness = list(test_harness_collection.filter_hints)
    self.assertEqual(harness[0].value, 'MOBILE_HARNESS')
    self.assertEqual(harness[1].value, 'TRADEFED')

  def testListTestHarnessVersion(self):
    """Tests ListTestHarnessVersion."""
    datastore_test_util.CreateHost(
        cluster='free',
        hostname='host_0',
        timestamp=self.TIMESTAMP,
    )
    datastore_test_util.CreateHost(
        cluster='paid',
        hostname='host_1',
        timestamp=self.TIMESTAMP,
        test_harness='MOBILE_HARNESS',
        test_harness_version='3.0.1',
    )
    datastore_test_util.CreateHost(
        cluster='free',
        hostname='host_2',
        lab_name='alab',
        assignee='auser',
        hidden=True,
    )
    api_request = {'type': 'TEST_HARNESS_VERSION'}
    api_response = self.testapp.post_json(
        '/_ah/api/FilterHintApi.ListFilterHints', api_request)
    test_harness_version_collection = protojson.decode_message(
        api_messages.FilterHintCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(test_harness_version_collection.filter_hints))
    test_harness_versions = list(test_harness_version_collection.filter_hints)
    self.assertEqual(test_harness_versions[0].value, '1234')
    self.assertEqual(test_harness_versions[1].value, '3.0.1')

  def testListHostStates(self):
    """Tests ListHostStates."""
    api_request = {'type': 'HOST_STATE'}
    api_response = self.testapp.post_json(
        '/_ah/api/FilterHintApi.ListFilterHints', api_request)
    host_state_collection = protojson.decode_message(
        api_messages.FilterHintCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(5, len(host_state_collection.filter_hints))
    states = list(host_state_collection.filter_hints)
    self.assertEqual(states[0].value, api_messages.HostState.UNKNOWN.name)
    self.assertEqual(states[1].value, api_messages.HostState.GONE.name)
    self.assertEqual(states[2].value, api_messages.HostState.RUNNING.name)
    self.assertEqual(states[3].value, api_messages.HostState.QUITTING.name)
    self.assertEqual(states[4].value, api_messages.HostState.KILLING.name)

  def testListDeviceStates(self):
    """Tests ListDeviceStates."""
    api_request = {'type': 'DEVICE_STATE'}
    api_response = self.testapp.post_json(
        '/_ah/api/FilterHintApi.ListFilterHints', api_request)
    device_state_collection = protojson.decode_message(
        api_messages.FilterHintCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(14, len(device_state_collection.filter_hints))
    states = list(device_state_collection.filter_hints)
    self.assertEqual(
        [s.value for s in states],
        [common.DeviceState.ALLOCATED,
         common.DeviceState.AVAILABLE,
         common.DeviceState.CHECKING,
         common.DeviceState.FASTBOOT,
         common.DeviceState.GONE,
         common.DeviceState.IGNORED,
         common.DeviceState.UNAVAILABLE,
         common.DeviceState.UNKNOWN,
         common.DeviceState.INIT,
         common.DeviceState.DYING,
         common.DeviceState.MISSING,
         common.DeviceState.PREPPING,
         common.DeviceState.DIRTY,
         common.DeviceState.LAMEDUCK])

  def testListHostGroup(self):
    """Tests ListHostGroup."""
    datastore_test_util.CreateHost(
        cluster='free',
        hostname='host_0',
        timestamp=self.TIMESTAMP,
    )
    datastore_test_util.CreateHost(
        cluster='paid',
        hostname='host_1',
        timestamp=self.TIMESTAMP,

    )
    datastore_test_util.CreateHost(
        cluster='free',
        hostname='host_2',
        hidden=True,
    )
    api_request = {'type': 'HOST_GROUP'}
    api_response = self.testapp.post_json(
        '/_ah/api/FilterHintApi.ListFilterHints', api_request)
    host_group_collection = protojson.decode_message(
        api_messages.FilterHintCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(host_group_collection.filter_hints))
    host_groups = list(host_group_collection.filter_hints)
    self.assertEqual(host_groups[0].value, 'free')
    self.assertEqual(host_groups[1].value, 'paid')

if __name__ == '__main__':
  unittest.main()
