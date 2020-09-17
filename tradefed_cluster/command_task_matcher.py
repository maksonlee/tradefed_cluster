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

"""Command task matcher is used to matcher tasks against a host."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from collections import defaultdict, namedtuple  import itertools
import logging

import six
from tradefed_cluster import common


Device = namedtuple('Device', ['device_serial', 'run_target'])


RunTarget = namedtuple('RunTarget', ['name', 'group', 'devices'])


Group = namedtuple('Group', ['name', 'run_targets'])


class CommandTaskMatcher(object):
  """CommandTaskMatcher is used to matcher tasks against a host.

  go/atp-multiple-device-match-design-doc has more details
  about matching algorithm.
  """

  def __init__(self, host_info):
    """Create a new CommandTaskMatcher.

    Args:
      host_info: a HostInfo message.
    """
    # A group name to group map. It represents the device tree.
    self._groups = self._BuildGroupTrees(host_info.device_infos)
    # A run target to {device serial: device} map. It's an index for run target.
    self._run_target_index = self._BuildRunTargetIndex(self._groups)

  def _BuildGroupTrees(self, devices):
    """Build device trees for groups.

    Create a map from group name to group tree and
    only contains groups not in use and have available devices.

    Args:
      devices: a list of DeviceInfo.
    Returns:
      a group name to group map.
    """
    allocated_group = set([])
    for d in devices:
      if not d.group_name:
        # if a device doesn't belong to any group,
        # then its serial will be its group name.
        d.group_name = d.device_serial
      if d.state == common.DeviceState.ALLOCATED:
        logging.debug('Group %s is in use.', d.group_name)
        allocated_group.add(d.group_name)

    group_devices = defaultdict(list)
    for d in devices:
      if d.group_name in allocated_group:
        continue
      if d.state != common.DeviceState.AVAILABLE:
        continue
      group_devices[d.group_name].append(d)

    group_map = {}
    for group_name, devices in six.iteritems(group_devices):
      group = self._BuildGroupSubtree(group_name, devices)
      group_map[group_name] = group
    return group_map

  def _BuildGroupSubtree(self, group_name, devices):
    """Build a group subtree.

    The created group tree only includes available devices.
    If there is no device availabe under the group,
    return None.

    Args:
      group_name: group name
      devices: devices iter under the group
    Returns:
      a group if the group has available devices, otherwise None
    """
    group = Group(name=group_name, run_targets={})
    for d in devices:
      run_target = group.run_targets.setdefault(
          d.run_target,
          RunTarget(name=d.run_target, group=group, devices={}))
      run_target.devices[d.device_serial] = Device(
          device_serial=d.device_serial,
          run_target=run_target)
    if group.run_targets:
      return group
    return None

  def _BuildRunTargetIndex(self, groups):
    """Build run target to devices map.

    It's like an index from run target to devices.

    Args:
      groups: a map from group name to Group objects
    Returns:
      run target to device list
    """
    run_target_to_devices = {}
    for group in six.itervalues(groups):
      for d in self._ListGroupDevices(group):
        run_target_to_devices.setdefault(
            d.run_target.name, {})[d.device_serial] = d
    return run_target_to_devices

  def _ListGroupDevices(self, group):
    """Get all devices under a group.

    Args:
      group: a Group object
    Yields:
      devices under a group
    """
    for run_target in six.itervalues(group.run_targets):
      for d in six.itervalues(run_target.devices):
        yield d

  def Match(self, command_task):
    """Match a command task against.

    Args:
      command_task: a CommandTask object
    Returns:
      a list of matched devices
    """
    if len(command_task.test_bench.host.groups) == 1:
      if len(command_task.test_bench.host.groups[0].run_targets) == 1:
        # type1 test
        return self._MatchType1(command_task)
      else:
        # type2 test
        return self._MatchType2(command_task)
    else:
      # type3 test
      return self._MatchType3(command_task)

  def _MatchType1(self, command_task):
    """Match type1 test.

    Type1 tests have only one run target.

    Args:
      command_task: a CommandTask object
    Returns:
      a list of matched devices
    """
    run_target = command_task.run_targets[0]
    devices = self._run_target_index.get(run_target)
    if devices:
      return [next(six.itervalues(devices))]
    return None

  def _MatchType2(self, command_task):
    """Match type2 test.

    type2 tests require multiple devices and
    all devices should be under one group.

    Args:
      command_task: a CommandTask object
    Returns:
      a list of matched devices
    """
    for group in six.itervalues(self._groups):
      matched_devices = self._MatchGroup(
          group, command_task.test_bench.host.groups[0])
      if matched_devices:
        return matched_devices
    return None

  def _MatchGroup(self, device_group, group_requirements):
    """Match a device group against a group requirements.

    Args:
      device_group: the device group
      group_requirements: the expect group
    Returns:
      a list of matched devices
    """
    logging.debug('Try to match %s against %s',
                  group_requirements, device_group.name)
    matched_devices = []
    expect_run_target_count = defaultdict(int)
    # Count the number of devices required for each run target.
    for r in group_requirements.run_targets:
      expect_run_target_count[r.name] += 1
    # Check if every run target can be fullfilled.
    for r, count in six.iteritems(expect_run_target_count):
      run_target = device_group.run_targets.get(r, None)
      if not run_target or len(run_target.devices) < count:
        # There is no or not enough needed run target devices in current group.
        logging.debug('Need %d %s, but not enough in %s.',
                      count, r, device_group.name)
        return None
      # Get the first count devices in the run_target.
      matched_devices.extend(
          itertools.islice(six.itervalues(run_target.devices), count))
    logging.debug('%s matches requirement %s with %s.',
                  device_group.name,
                  [r.name for r in group_requirements.run_targets],
                  [d.device_serial for d in matched_devices])
    return matched_devices

  def _MatchType3(self, command_task):
    """Match type3 test.

    type3 tests require multiple devices and
    those devices can be under different groups.
    Groups are not reentrant.

    Args:
      command_task: a CommandTask object
    Returns:
      a list of matched devices
    """
    # TODO: Current impl is not smart enough. First, groups are not
    # reentrant, when a group is matched by some group requirement, other group
    # requirement can not grab this group again.
    # Second, assume the task has two group requirements: gr1, gr2, and the host
    # has two device groups: dg1, dg2. Assume dg1 and dg2 both fullfill gr1, but
    # only dg1 fullfill gr2. There is a possibility that gr1 grabs dg1, gr2
    # can not be matched and the whole matching failed. But in fact there is a
    # matching dg2->gr1, dg1->gr2.
    # This implementation basically only support task that has multiple groups
    # but each group has only one run target.
    matched_devices = []
    allocated_groups = set()
    for group_requirement in command_task.test_bench.host.groups:
      logging.debug('Matching group %s', group_requirement)
      group_matched_devices = None
      group = None
      for group in six.itervalues(self._groups):
        if group.name in allocated_groups:
          continue
        group_matched_devices = self._MatchGroup(group, group_requirement)
        if group_matched_devices:
          break
      if group_matched_devices and group:
        matched_devices.extend(group_matched_devices)
        allocated_groups.add(group.name)
      else:
        # for some group requirement there is no matching in this host.
        logging.debug('Failed to match')
        return None
    return matched_devices

  def RemoveDeviceGroups(self, devices):
    """Remove the devices' groups in the host.

    The devices must exist in the device tree.
    And this method will remove those devices and their groups' devices
    from the device tree, since the group is in use.

    Args:
      devices: a list of devices
    """
    for d in devices:
      # delete the group from the device tree
      group = self._groups.pop(d.run_target.group.name, None)
      if not group:
        continue
      # delete all devices under the group from the _run_target_index
      for d in self._ListGroupDevices(group):
        self._run_target_index[d.run_target.name].pop(d.device_serial)

  def GetRunTargets(self):
    """Get all run targets in this host.

    Returns:
      a list of run target names
    """
    return list(self._run_target_index.keys())

  def IsEmpty(self):
    """The host has usable devices or not.

    Returns:
      true if the host has no usable devices, otherwise false
    """
    return not self._groups
