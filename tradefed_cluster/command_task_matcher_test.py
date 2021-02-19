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

"""Tests for command_task_matcher."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import unittest

import six
from tradefed_cluster import api_messages
from tradefed_cluster import command_task_matcher
from tradefed_cluster import common
from tradefed_cluster import datastore_entities

CLUSTER = 'cluster'
HOSTNAME = 'hostname'


class CommandTaskMatcherTest(unittest.TestCase):

  def _CreateDeviceInfo(self, serial, run_target, group_name,
                        state=common.DeviceState.AVAILABLE,
                        sim_state=None):
    return api_messages.DeviceInfo(
        device_serial=serial,
        hostname=HOSTNAME,
        run_target=run_target,
        state=state,
        group_name=group_name,
        cluster=CLUSTER,
        sim_state=sim_state)

  def _CreateHostInfo(self, device_infos):
    return api_messages.HostInfo(
        hostname=HOSTNAME,
        cluster=CLUSTER,
        device_infos=device_infos)

  def _CreateCommandTask(self, task_id, groups):
    """Create CommandTask.

    Args:
      task_id: task id
      groups: a list of lists of datastore_entities.RunTarget objects
    Returns:
      CommandTask
    """
    test_bench = datastore_entities.TestBench(
        cluster=CLUSTER,
        host=datastore_entities.Host(groups=[]))
    for run_targets in groups:
      group = datastore_entities.Group(run_targets=run_targets)
      test_bench.host.groups.append(group)
    return datastore_entities.CommandTask(
        task_id=task_id,
        test_bench=test_bench)

  def testBuildGroupTrees(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1'),
         self._CreateDeviceInfo('d2', 'run_target2', 'g1')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    # group g1
    group = matcher._groups['g1']
    self.assertEqual('g1', group.name)
    r1 = group.run_targets['run_target1']
    r2 = group.run_targets['run_target2']
    self.assertIs(group, r1.group)
    self.assertIs(group, r2.group)
    d1 = r1.devices['d1']
    d2 = r2.devices['d2']
    self.assertIs(r1, d1.run_target)
    self.assertIs(r2, d2.run_target)

  def testBuildGroupTrees_allocatedGroup(self):
    """Test group with allocate device will not be used to match."""
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1',
                                common.DeviceState.ALLOCATED),
         self._CreateDeviceInfo('d2', 'run_target2', 'g1')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    self.assertIsNone(matcher._groups.get('g1'))

  def testBuildGroupTrees_notAvailableDevices(self):
    """Test devices not available will not be used to match."""
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1',
                                common.DeviceState.GONE),
         self._CreateDeviceInfo('d2', 'run_target2', 'g1')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    group = matcher._groups['g1']
    self.assertEqual(1, len(group.run_targets))
    self.assertEqual(1, len(group.run_targets['run_target2'].devices))

  def testBuildRunTargetToDevices(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1'),
         self._CreateDeviceInfo('d2', 'run_target2', 'g1'),
         self._CreateDeviceInfo('d3', 'run_target1', 'g2')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    r1_devices = matcher._run_target_index['run_target1']
    self.assertSetEqual(
        set(['d1', 'd3']), set((s for s, _ in six.iteritems(r1_devices))))
    r2_devices = matcher._run_target_index['run_target2']
    self.assertSetEqual(
        set(['d2']), set((s for s, _ in six.iteritems(r2_devices))))

  def testMatchType1Test(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1'),
         self._CreateDeviceInfo('d2', 'run_target2', 'g1'),
         self._CreateDeviceInfo('d3', 'run_target1', 'g2')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    task = self._CreateCommandTask(
        '1', [[datastore_entities.RunTarget(name='run_target2')]])
    matched_devices = matcher.Match(task)
    self.assertEqual(1, len(matched_devices))
    d = matched_devices[0]
    self.assertEqual('d2', d.device_serial)

  def testMatchType1Test_withAttribute(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1'),
         self._CreateDeviceInfo('d2', 'run_target2', 'g1'),
         self._CreateDeviceInfo('d3', 'run_target1', 'g2', sim_state='READY')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    task = self._CreateCommandTask(
        '1',
        [[
            datastore_entities.RunTarget(
                name='run_target1',
                device_attributes=[
                    datastore_entities.Attribute(
                        name='sim_state', value='READY')]
                )
        ]])
    matched_devices = matcher.Match(task)
    self.assertEqual(1, len(matched_devices))
    d = matched_devices[0]
    self.assertEqual('d3', d.device_serial)
    self.assertEqual('READY', d.attributes['sim_state'])

  def testMatchType1Test_withDeviceSerial(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1'),
         self._CreateDeviceInfo('d2', 'run_target2', 'g1'),
         self._CreateDeviceInfo('d3', 'run_target1', 'g2')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    task = self._CreateCommandTask(
        '1',
        [[
            datastore_entities.RunTarget(
                name='run_target1',
                device_attributes=[
                    datastore_entities.Attribute(
                        name='device_serial', value='d3')]
                )
        ]])
    matched_devices = matcher.Match(task)
    self.assertEqual(1, len(matched_devices))
    d = matched_devices[0]
    self.assertEqual('d3', d.device_serial)

  def testMatchType2Test(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1'),
         self._CreateDeviceInfo('d2', 'run_target2', 'g1'),
         self._CreateDeviceInfo('d3', 'run_target1', 'g2')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    task = self._CreateCommandTask(
        '1',
        [[datastore_entities.RunTarget(name='run_target1'),
          datastore_entities.RunTarget(name='run_target2')]])
    matched_devices = matcher.Match(task)
    self.assertEqual(2, len(matched_devices))
    d1 = matched_devices[0]
    d2 = matched_devices[1]
    self.assertEqual(
        set(['d1', 'd2']),
        set([d1.device_serial, d2.device_serial]))

  def testMatchType2Test_noMatch(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1'),
         self._CreateDeviceInfo('d2', 'run_target2', 'g2')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    task = self._CreateCommandTask(
        '1',
        [[datastore_entities.RunTarget(name='run_target1'),
          datastore_entities.RunTarget(name='run_target2')]])
    matched_devices = matcher.Match(task)
    self.assertIsNone(matched_devices)

  def _CreateRunTargetRequirement(self, name, attributes=()):
    run_target_requirement = datastore_entities.RunTarget(
        name=name, device_attributes=[])
    for attribute in attributes or []:
      run_target_requirement.device_attributes.append(
          datastore_entities.Attribute(
              name=attribute[0], value=attribute[1]))
    return run_target_requirement

  def testMatchType2Test_withDeviceAttribute(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'rt1', 'g1', sim_state='READY'),
         self._CreateDeviceInfo('d2', 'rt1', 'g1', sim_state='NONE'),
         self._CreateDeviceInfo('d3', 'rt1', 'g2', sim_state='READY'),
         self._CreateDeviceInfo('d4', 'rt1', 'g2', sim_state='READY'),
        ])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    task = self._CreateCommandTask(
        '1',
        [[self._CreateRunTargetRequirement('rt1', [('sim_state', 'READY')]),
          self._CreateRunTargetRequirement('rt1', [('sim_state', 'READY')])]])
    matched_devices = matcher.Match(task)
    self.assertEqual(2, len(matched_devices))
    d1 = matched_devices[0]
    d2 = matched_devices[1]
    self.assertEqual(
        set(['d3', 'd4']),
        set([d1.device_serial, d2.device_serial]))

  def testMatchType2Test_withDeviceAttribute_noMatch(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'rt1', 'g1', sim_state='READY'),
         self._CreateDeviceInfo('d2', 'rt1', 'g1', sim_state='NONE'),
         self._CreateDeviceInfo('d3', 'rt1', 'g2', sim_state='READY'),
         self._CreateDeviceInfo('d4', 'rt1', 'g2', sim_state='NONE'),
        ])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    task = self._CreateCommandTask(
        '1',
        [[self._CreateRunTargetRequirement('rt1', [('sim_state', 'READY')]),
          self._CreateRunTargetRequirement('rt1', [('sim_state', 'READY')])]])
    matched_devices = matcher.Match(task)
    self.assertIsNone(matched_devices)

  def testMatchType3Test(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1'),
         self._CreateDeviceInfo('d2', 'run_target2', 'g1'),
         self._CreateDeviceInfo('d3', 'run_target3', 'g2'),
         self._CreateDeviceInfo('d4', 'run_target4', 'g2')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    task = self._CreateCommandTask(
        '1',
        [[datastore_entities.RunTarget(name='run_target1')],
         [datastore_entities.RunTarget(name='run_target3')]])
    matched_devices = matcher.Match(task)
    self.assertEqual(2, len(matched_devices))
    d1 = matched_devices[0]
    d2 = matched_devices[1]
    self.assertEqual(
        set(['d1', 'd3']),
        set([d1.device_serial, d2.device_serial]))

  def testMatchType3Test_exclusive(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1'),
         self._CreateDeviceInfo('d2', 'run_target2', 'g1'),
         self._CreateDeviceInfo('d3', 'run_target3', 'g2'),
         self._CreateDeviceInfo('d4', 'run_target4', 'g2')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    task = self._CreateCommandTask(
        '1',
        [[datastore_entities.RunTarget(name='run_target1')],
         [datastore_entities.RunTarget(name='run_target3')]])
    matched_devices = matcher.Match(task)
    matcher.RemoveDeviceGroups(matched_devices)
    self.assertEqual(2, len(matched_devices))
    d1 = matched_devices[0]
    d2 = matched_devices[1]
    self.assertEqual(
        set(['d1', 'd3']),
        set([d1.device_serial, d2.device_serial]))
    # task2 can not be matched because g1 is already in use.
    task2 = self._CreateCommandTask(
        '1', [[datastore_entities.RunTarget(name='run_target2')]])
    matched_devices = matcher.Match(task2)
    self.assertIsNone(matched_devices)

  def testMatchType3Test_noMatch(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1'),
         self._CreateDeviceInfo('d2', 'run_target2', 'g1'),
         self._CreateDeviceInfo('d3', 'run_target3', 'g2'),
         self._CreateDeviceInfo('d4', 'run_target4', 'g2')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    task = self._CreateCommandTask(
        '1',
        [[datastore_entities.RunTarget(name='run_target1')],
         [datastore_entities.RunTarget(name='run_target2')]])

    matched_devices = matcher.Match(task)
    self.assertIsNone(matched_devices)

  def testMatchType3Test_withDeviceAttribute(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'rt1', 'g1', sim_state='NONE'),
         self._CreateDeviceInfo('d2', 'rt1', 'g1', sim_state='READY'),
         self._CreateDeviceInfo('d3', 'rt1', 'g2', sim_state='NONE'),
         self._CreateDeviceInfo('d4', 'rt1', 'g2', sim_state='READY')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    task = self._CreateCommandTask(
        '1',
        [[self._CreateRunTargetRequirement('rt1', [('sim_state', 'READY')])],
         [self._CreateRunTargetRequirement('rt1', [('sim_state', 'READY')])]])
    matched_devices = matcher.Match(task)
    self.assertEqual(2, len(matched_devices))
    d1 = matched_devices[0]
    d2 = matched_devices[1]
    self.assertEqual(
        set(['d2', 'd4']),
        set([d1.device_serial, d2.device_serial]))

  def testMatchType3Test_withDeviceAttribute_noMatch(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'rt1', 'g1', sim_state='NONE'),
         self._CreateDeviceInfo('d2', 'rt1', 'g1', sim_state='NONE'),
         self._CreateDeviceInfo('d3', 'rt1', 'g2', sim_state='NONE'),
         self._CreateDeviceInfo('d4', 'rt1', 'g2', sim_state='READY')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    task = self._CreateCommandTask(
        '1',
        [[self._CreateRunTargetRequirement('rt1', [('sim_state', 'READY')])],
         [self._CreateRunTargetRequirement('rt1', [('sim_state', 'READY')])]])
    matched_devices = matcher.Match(task)
    self.assertIsNone(matched_devices)

  def testRemoveDeviceGroups(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1'),
         self._CreateDeviceInfo('d2', 'run_target2', 'g1'),
         self._CreateDeviceInfo('d3', 'run_target1', 'g2')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    task = self._CreateCommandTask(
        '2', [[datastore_entities.RunTarget(name='run_target2')]])
    matched_devices = matcher.Match(task)
    self.assertEqual(1, len(matched_devices))
    d = matched_devices[0]
    matcher.RemoveDeviceGroups([d])
    self.assertIsNone(matcher._groups.get('g1', None))
    self.assertIsNone(
        matcher._run_target_index['run_target2'].get('d2', None))
    # d1 is in the same group as d2, will be removed as well
    r1_devices = matcher._run_target_index['run_target1']
    self.assertSetEqual(
        set(['d3']), set((s for s, _ in six.iteritems(r1_devices))))

  def testRemoveDeviceGroups_multipleDevices(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1'),
         self._CreateDeviceInfo('d2', 'run_target2', 'g1'),
         self._CreateDeviceInfo('d3', 'run_target3', 'g1'),
         self._CreateDeviceInfo('d4', 'run_target1', 'g2')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    task = self._CreateCommandTask(
        '1',
        [[datastore_entities.RunTarget(name='run_target1'),
          datastore_entities.RunTarget(name='run_target2')]])
    matched_devices = matcher.Match(task)
    self.assertEqual(2, len(matched_devices))

    matcher.RemoveDeviceGroups(matched_devices)

    self.assertIsNone(matcher._groups.get('g1', None))
    self.assertIsNone(
        matcher._run_target_index['run_target3'].get('d3', None))
    r1_devices = matcher._run_target_index['run_target1']
    self.assertSetEqual(
        set(['d4']), set((s for s, _ in six.iteritems(r1_devices))))

  def testRemoveDeviceGroups_multipleGroups(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1'),
         self._CreateDeviceInfo('d2', 'run_target2', 'g1'),
         self._CreateDeviceInfo('d3', 'run_target3', 'g2'),
         self._CreateDeviceInfo('d4', 'run_target4', 'g2')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    task = self._CreateCommandTask(
        '1',
        [[datastore_entities.RunTarget(name='run_target1')],
         [datastore_entities.RunTarget(name='run_target3')]])
    matched_devices = matcher.Match(task)
    self.assertEqual(2, len(matched_devices))

    matcher.RemoveDeviceGroups(matched_devices)

    self.assertIsNone(matcher._groups.get('g1', None))
    self.assertIsNone(matcher._groups.get('g2', None))
    for devices in six.itervalues(matcher._run_target_index):
      self.assertEqual(0, len(devices))

  def testGetRunTargets(self):
    host = self._CreateHostInfo(
        [self._CreateDeviceInfo('d1', 'run_target1', 'g1'),
         self._CreateDeviceInfo('d2', 'run_target2', 'g1'),
         self._CreateDeviceInfo('d3', 'run_target1', 'g2')])
    matcher = command_task_matcher.CommandTaskMatcher(host)
    run_targets = matcher.GetRunTargets()
    self.assertSetEqual(
        set(['run_target1', 'run_target2']),
        set(run_targets))


if __name__ == '__main__':
  unittest.main()
