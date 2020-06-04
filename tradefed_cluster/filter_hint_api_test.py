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
        test_runner='mobile harness',
        test_runner_version='3.0.1',
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
    self.assertEqual(harness[0].value, 'mobile harness')
    self.assertEqual(harness[1].value, 'tradefed')

if __name__ == '__main__':
  unittest.main()
