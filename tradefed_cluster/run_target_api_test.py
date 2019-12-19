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

"""Tests for Run Target API."""

import unittest

from protorpc import protojson

from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import datastore_test_util
from tradefed_cluster import run_target_api


class RunTargetApiTest(api_test.ApiTest):

  SHAMU_RUN_TARGET = api_messages.RunTarget(name='shamu')
  HAMMERHEAD_RUN_TARGET = api_messages.RunTarget(name='hammerhead')

  def AssertRunTargetsEqual(self, expected, actual):
    """Helper to assert run targets."""
    self.assertEqual(expected.name, actual.name)

  def AssertRunTargetsListEqual(self, expected, actual):
    """Helper to assert lists of run targets."""
    self.assertItemsEqual([rt.name for rt in expected],
                          [rt.name for rt in actual])

  def setUp(self):
    api_test.ApiTest.setUp(self)
    self.host_0 = datastore_test_util.CreateHost(
        cluster='free', hostname='host_0')
    self.device_0 = datastore_test_util.CreateDevice(
        cluster='free',
        hostname=self.host_0.hostname,
        device_serial='device_0',
        run_target='shamu')
    self.device_1 = datastore_test_util.CreateDevice(
        cluster='free',
        hostname=self.host_0.hostname,
        device_serial='device_1',
        run_target='shamu')

    self.host_1 = datastore_test_util.CreateHost(
        cluster='free', hostname='host_1')
    self.device_2 = datastore_test_util.CreateDevice(
        cluster='free',
        hostname=self.host_1.hostname,
        device_serial='device_2',
        run_target='hammerhead')
    self.host_2 = datastore_test_util.CreateHost(
        cluster='presubmit', hostname='host_2')
    self.device_3 = datastore_test_util.CreateDevice(
        cluster='presubmit',
        hostname=self.host_2.hostname,
        device_serial='device_3',
        run_target='hammerhead')

  def testListRunTargets(self):
    """Tests ListRunTargets returns all run targets in all clusters."""
    api_request = {}
    api_response = self.testapp.post_json(
        '/_ah/api/RunTargetApi.ListRunTargets',
        api_request)
    run_target_collection = protojson.decode_message(
        run_target_api.RunTargetCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(run_target_collection.run_targets))
    expected = [self.SHAMU_RUN_TARGET, self.HAMMERHEAD_RUN_TARGET]
    self.AssertRunTargetsListEqual(expected, run_target_collection.run_targets)

  def testListRunTargets_hiddenDevice(self):
    """Tests ListRunTargets ignores run targets from hidden devices."""
    datastore_test_util.CreateDevice(
        cluster='free',
        hostname=self.host_2.hostname,
        device_serial='device_4',
        run_target='hammerhead',
        hidden=True)
    datastore_test_util.CreateDevice(
        cluster='free',
        hostname=self.host_2.hostname,
        device_serial='device_5',
        run_target='mako',
        hidden=True)
    api_request = {}
    api_response = self.testapp.post_json(
        '/_ah/api/RunTargetApi.ListRunTargets',
        api_request)
    run_target_collection = protojson.decode_message(
        run_target_api.RunTargetCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(run_target_collection.run_targets))
    # there are other hammerhead devices, so it should still be present
    # however, mako shouldn't be there.
    expected = [self.SHAMU_RUN_TARGET, self.HAMMERHEAD_RUN_TARGET]
    self.AssertRunTargetsListEqual(expected, run_target_collection.run_targets)

  def testListRunTargets_withCluster_multipleRunTargets(self):
    """Tests ListRunTargets returns multiple run targets in a cluster."""
    api_request = {'cluster': 'free'}
    api_response = self.testapp.post_json(
        '/_ah/api/RunTargetApi.ListRunTargets',
        api_request)
    run_target_collection = protojson.decode_message(
        run_target_api.RunTargetCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(run_target_collection.run_targets))
    expected = [self.SHAMU_RUN_TARGET, self.HAMMERHEAD_RUN_TARGET]
    self.AssertRunTargetsListEqual(expected, run_target_collection.run_targets)

  def testListRunTargets_withCluster_singleRunTarget(self):
    """Tests ListRunTargets returns a single run target in a cluster."""
    api_request = {'cluster': 'presubmit'}
    api_response = self.testapp.post_json(
        '/_ah/api/RunTargetApi.ListRunTargets',
        api_request)
    run_target_collection = protojson.decode_message(
        run_target_api.RunTargetCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(run_target_collection.run_targets))
    self.AssertRunTargetsEqual(self.HAMMERHEAD_RUN_TARGET,
                               run_target_collection.run_targets[0])

  def testListRunTargets_withCluster_noRunTargets(self):
    """Tests ListRunTargets with no run targets for a cluster."""
    api_request = {'cluster': 'fake'}
    api_response = self.testapp.post_json(
        '/_ah/api/RunTargetApi.ListRunTargets',
        api_request)
    run_target_collection = protojson.decode_message(
        run_target_api.RunTargetCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(0, len(run_target_collection.run_targets))

  def testListRunTargets_noneRunTargets(self):
    """Tests ListRunTargets with 'None' run target for all clusters."""
    host_3 = datastore_test_util.CreateHost(
        cluster='unbundled', hostname='host_3')
    # Device 4 does not have a run target defined
    datastore_test_util.CreateDevice(
        cluster='unbundled',
        hostname=host_3.hostname,
        device_serial='device_4',
        run_target=None)
    api_request = {}
    api_response = self.testapp.post_json(
        '/_ah/api/RunTargetApi.ListRunTargets',
        api_request)
    run_target_collection = protojson.decode_message(
        run_target_api.RunTargetCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(run_target_collection.run_targets))
    expected = [self.SHAMU_RUN_TARGET, self.HAMMERHEAD_RUN_TARGET]
    self.AssertRunTargetsListEqual(expected, run_target_collection.run_targets)

  def testListRunTargets_withCluster_noneRunTargets(self):
    """Tests ListRunTargets with 'None' run target for a cluster."""
    host_3 = datastore_test_util.CreateHost(
        cluster='unbundled', hostname='host_3')
    # Device 4 does not have a run target defined
    datastore_test_util.CreateDevice(
        cluster='unbundled',
        hostname=host_3.hostname,
        device_serial='device_4',
        run_target=None)
    api_request = {'cluster': host_3.physical_cluster}
    api_response = self.testapp.post_json(
        '/_ah/api/RunTargetApi.ListRunTargets',
        api_request)
    run_target_collection = protojson.decode_message(
        run_target_api.RunTargetCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(0, len(run_target_collection.run_targets))


if __name__ == '__main__':
  unittest.main()
