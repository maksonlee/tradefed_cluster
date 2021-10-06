# Copyright 2021 Google LLC
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
"""Tests for harness_update_scheduler."""
import datetime
import unittest

from absl.testing import parameterized

import mock

from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import harness_update_scheduler
from tradefed_cluster import testbed_dependent_test


class HarnessUpdateSchedulerTest(
    parameterized.TestCase, testbed_dependent_test.TestbedDependentTest):
  """Tests for HarnessUpdateScheduler."""

  @parameterized.named_parameters(
      ('Allow first 2 hosts', 40, [common.HostUpdateState.PENDING] * 5,
       [False] * 5, [True, True, False, False, False]),
      ('Percentage results in non-integer number of hosts', 62,
       [common.HostUpdateState.PENDING] * 5,
       [False] * 5, [True, True, True, False, False]),
      ('Percentage results in 0 hosts, but correct to 1 host', 1,
       [common.HostUpdateState.PENDING] * 5,
       [False] * 5, [True, False, False, False, False]),
      ('2 hosts not final yet', 40, [common.HostUpdateState.PENDING] * 5,
       [True, True, False, False, False], [True, True, False, False, False]),
      ('2 allowed 1 hosts not final yet', 40,
       [common.HostUpdateState.SUCCEEDED, common.HostUpdateState.SYNCING] + [
           common.HostUpdateState.PENDING] * 3,
       [True, True, False, False, False], [True, True, True, False, False]),
      ('2 allowed and final', 40,
       [common.HostUpdateState.SUCCEEDED, common.HostUpdateState.ERRORED] + [
           common.HostUpdateState.PENDING] * 3,
       [True, True, False, False, False], [True, True, True, True, False]),
      ('All scheduled', 40,
       [common.HostUpdateState.SUCCEEDED] * 5, [True] * 5, [True] * 5),
      )
  def testManageHarnessUpdateSchedules_SingleCluster(
      self, percentage, states, initial_flags, expected_flags):
    datastore_test_util.CreateClusterConfig(
        'c1', max_concurrent_update_percentage=percentage)
    datastore_test_util.CreateHostConfig('h0', 'alab', cluster_name='c1')
    datastore_test_util.CreateHostConfig('h1', 'alab', cluster_name='c1')
    datastore_test_util.CreateHostConfig('h2', 'alab', cluster_name='c1')
    datastore_test_util.CreateHostConfig('h3', 'alab', cluster_name='c1')
    datastore_test_util.CreateHostConfig('h4', 'alab', cluster_name='c1')
    datastore_test_util.CreateHostUpdateState(
        hostname='h0', state=states[0])
    datastore_test_util.CreateHostUpdateState(
        hostname='h1', state=states[1])
    datastore_test_util.CreateHostUpdateState(
        hostname='h2', state=states[2])
    datastore_test_util.CreateHostUpdateState(
        hostname='h3', state=states[3])
    datastore_test_util.CreateHostUpdateState(
        hostname='h4', state=states[4])
    datastore_test_util.CreateHostMetadata(
        hostname='h0', allow_to_update=initial_flags[0])
    datastore_test_util.CreateHostMetadata(
        hostname='h1', allow_to_update=initial_flags[1])
    datastore_test_util.CreateHostMetadata(
        hostname='h2', allow_to_update=initial_flags[2])
    datastore_test_util.CreateHostMetadata(
        hostname='h3', allow_to_update=initial_flags[3])
    datastore_test_util.CreateHostMetadata(
        hostname='h4', allow_to_update=initial_flags[4])

    harness_update_scheduler.ManageHarnessUpdateSchedules()

    metadata = datastore_entities.HostMetadata.get_by_id('h0')
    self.assertEqual(expected_flags[0], metadata.allow_to_update)
    metadata = datastore_entities.HostMetadata.get_by_id('h1')
    self.assertEqual(expected_flags[1], metadata.allow_to_update)
    metadata = datastore_entities.HostMetadata.get_by_id('h2')
    self.assertEqual(expected_flags[2], metadata.allow_to_update)
    metadata = datastore_entities.HostMetadata.get_by_id('h3')
    self.assertEqual(expected_flags[3], metadata.allow_to_update)
    metadata = datastore_entities.HostMetadata.get_by_id('h4')
    self.assertEqual(expected_flags[4], metadata.allow_to_update)

  def testManageHarnessUpdateSchedules_MultipleClusters(self):
    datastore_test_util.CreateClusterConfig(
        'c1', max_concurrent_update_percentage=50)
    datastore_test_util.CreateClusterConfig(
        'c2', max_concurrent_update_percentage=10)
    datastore_test_util.CreateClusterConfig(
        'c3', max_concurrent_update_percentage=996)  # value out of range
    datastore_test_util.CreateClusterConfig(
        'c4', max_concurrent_update_percentage=0)    # value out of range
    datastore_test_util.CreateHostConfig('h0', 'alab', cluster_name='c1')
    datastore_test_util.CreateHostConfig('h1', 'alab', cluster_name='c1')
    datastore_test_util.CreateHostConfig('h2', 'alab', cluster_name='c2')
    datastore_test_util.CreateHostConfig('h3', 'alab', cluster_name='c2')
    datastore_test_util.CreateHostConfig('h4', 'alab', cluster_name='c3')
    datastore_test_util.CreateHostConfig('h5', 'alab', cluster_name='c4')

    datastore_test_util.CreateHostUpdateState(
        hostname='h0', state=common.HostUpdateState.PENDING)
    datastore_test_util.CreateHostUpdateState(
        hostname='h1', state=common.HostUpdateState.PENDING)
    datastore_test_util.CreateHostUpdateState(
        hostname='h2', state=common.HostUpdateState.PENDING)
    datastore_test_util.CreateHostUpdateState(
        hostname='h3', state=common.HostUpdateState.PENDING)
    datastore_test_util.CreateHostUpdateState(
        hostname='h4', state=common.HostUpdateState.PENDING)
    datastore_test_util.CreateHostUpdateState(
        hostname='h5', state=common.HostUpdateState.PENDING)
    datastore_test_util.CreateHostMetadata(
        hostname='h0', allow_to_update=False)
    datastore_test_util.CreateHostMetadata(
        hostname='h1', allow_to_update=False)
    datastore_test_util.CreateHostMetadata(
        hostname='h2', allow_to_update=False)
    datastore_test_util.CreateHostMetadata(
        hostname='h3', allow_to_update=False)
    datastore_test_util.CreateHostMetadata(
        hostname='h4', allow_to_update=False)
    datastore_test_util.CreateHostMetadata(
        hostname='h5', allow_to_update=False)

    harness_update_scheduler.ManageHarnessUpdateSchedules()

    # cluster c1 hosts have 1 host scheduled
    metadata = datastore_entities.HostMetadata.get_by_id('h0')
    self.assertTrue(metadata.allow_to_update)
    metadata = datastore_entities.HostMetadata.get_by_id('h1')
    self.assertFalse(metadata.allow_to_update)
    # cluster c2 hosts have 1 host scheduled
    metadata = datastore_entities.HostMetadata.get_by_id('h2')
    self.assertTrue(metadata.allow_to_update)
    metadata = datastore_entities.HostMetadata.get_by_id('h3')
    self.assertFalse(metadata.allow_to_update)
    # cluster c3 hosts does not need schedules
    metadata = datastore_entities.HostMetadata.get_by_id('h4')
    self.assertFalse(metadata.allow_to_update)
    # cluster c4 hosts does not need schedules
    metadata = datastore_entities.HostMetadata.get_by_id('h5')
    self.assertFalse(metadata.allow_to_update)

  @mock.patch('tradefed_cluster.harness_update_scheduler.datetime')
  def testManageHarnessUpdateSchedules_TouchUnscheduledHostsTimeStamp(
      self, mock_dt):
    datastore_test_util.CreateClusterConfig(
        'c1', max_concurrent_update_percentage=50)
    datastore_test_util.CreateHostConfig('h0', 'alab', cluster_name='c1')
    datastore_test_util.CreateHostConfig('h1', 'alab', cluster_name='c1')
    datastore_test_util.CreateHostConfig('h2', 'alab', cluster_name='c1')
    datastore_test_util.CreateHostConfig('h3', 'alab', cluster_name='c1')
    # A redundant host config without host update state for testing
    # when update_state datastore entity is not found.
    datastore_test_util.CreateHostConfig('h4', 'alab', cluster_name='c1')

    time_1 = datetime.datetime(2020, 12, 24)
    time_2 = datetime.datetime(2021, 9, 9, 5, 20)
    time_3 = datetime.datetime(2021, 9, 9, 5, 30)

    mock_dt.datetime.utcnow.return_value = time_3

    datastore_test_util.CreateHostUpdateState(
        hostname='h0', state=common.HostUpdateState.PENDING,
        update_timestamp=time_1)
    datastore_test_util.CreateHostUpdateState(
        hostname='h1', state=common.HostUpdateState.PENDING,
        update_timestamp=time_1)
    datastore_test_util.CreateHostUpdateState(
        hostname='h2', state=common.HostUpdateState.PENDING,
        update_timestamp=time_1)
    datastore_test_util.CreateHostUpdateState(
        hostname='h3', state=common.HostUpdateState.PENDING,
        update_timestamp=time_2)
    datastore_test_util.CreateHostMetadata(
        hostname='h0', allow_to_update=False)
    datastore_test_util.CreateHostMetadata(
        hostname='h1', allow_to_update=False)
    datastore_test_util.CreateHostMetadata(
        hostname='h2', allow_to_update=False)
    datastore_test_util.CreateHostMetadata(
        hostname='h3', allow_to_update=False)

    harness_update_scheduler.ManageHarnessUpdateSchedules()

    metadata = datastore_entities.HostMetadata.get_by_id('h0')
    self.assertTrue(metadata.allow_to_update)
    metadata = datastore_entities.HostMetadata.get_by_id('h1')
    self.assertTrue(metadata.allow_to_update)

    # Host h2 not scheduled in this iteration get a refresh for PENDING update
    # state timestamps.
    metadata = datastore_entities.HostMetadata.get_by_id('h2')
    self.assertFalse(metadata.allow_to_update)
    update_state = datastore_entities.HostUpdateState.get_by_id('h2')
    self.assertEqual(common.HostUpdateState.PENDING, update_state.state)
    self.assertEqual(time_3, update_state.update_timestamp)
    # Host h3 did not refresh timestamp because its timestamp is still new.
    metadata = datastore_entities.HostMetadata.get_by_id('h3')
    self.assertFalse(metadata.allow_to_update)
    update_state = datastore_entities.HostUpdateState.get_by_id('h3')
    self.assertEqual(time_2, update_state.update_timestamp)
    self.assertEqual(common.HostUpdateState.PENDING, update_state.state)


if __name__ == '__main__':
  unittest.main()
