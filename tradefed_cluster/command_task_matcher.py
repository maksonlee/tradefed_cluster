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

from collections import defaultdict, namedtuple
import logging

import six
from tradefed_cluster import common

_OPERATOR_TO_PREDICTOR = {
    '=': lambda a, b: a == b,
    '>': lambda a, b: a > b,
    '>=': lambda a, b: a >= b,
    '<': lambda a, b: a < b,
    '<=': lambda a, b: a <= b,
}


Device = namedtuple('Device', ['device_serial', 'run_target', 'attributes'])


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
          run_target=run_target,
          attributes=self._GetDeviceAttributes(d))
    if group.run_targets:
      return group
    return None

  def _GetDeviceAttributes(self, device):
    """Get device's attributes.

    Args:
      device: a message.DeviceInfo.
    Returns:
      device's attributes that can be used to schedule tests.
    """
    # TODO: To start with we only allow limit device attributes
    # for scheduling tests, we will make it more flexible later.
    attributes = {}
    attributes['build_id'] = device.build_id
    attributes['device_serial'] = device.device_serial
    attributes['hostname'] = device.hostname
    attributes['product'] = device.product
    attributes['product_variant'] = device.product_variant
    attributes['sim_state'] = device.sim_state
    attributes['battery_level'] = device.battery_level
    return attributes

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
    for device in six.itervalues(devices):
      if self._MatchDeviceAttributes(
          (command_task.test_bench.host.groups[0].run_targets[0]
           .device_attributes),
          device.attributes):
        return [device]
    return None

  def _MatchDeviceAttributes(self, required_attributes, device_attributes):
    """Check if a device's attributes match the task's requirements.

    Args:
      required_attributes: a list of datastore_entities.Attribute.
      device_attributes: a map of device's attribute name to its value.
    Returns:
      True if the device meet the requirements, otherwise False.
    """
    if not required_attributes:
      return True
    for required_attribute in required_attributes:
      if not _MatchDeviceAttribute(required_attribute, device_attributes):
        return False
    return True

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
    matched_device_serials = set()
    for run_target_requirement in group_requirements.run_targets:
      matched = False
      run_target_candidate = device_group.run_targets.get(
          run_target_requirement.name)
      if not run_target_candidate:
        logging.debug('No run target %s.', run_target_requirement.name)
        return None
      for device_candidate in run_target_candidate.devices.values():
        if device_candidate.device_serial in matched_device_serials:
          continue
        if self._MatchDeviceAttributes(
            run_target_requirement.device_attributes,
            device_candidate.attributes):
          matched_devices.append(device_candidate)
          matched_device_serials.add(device_candidate.device_serial)
          matched = True
          break
      if not matched:
        logging.debug('There is no match for %s.', run_target_requirement)
        return None
    logging.debug('%s matches requirement %s with %s.',
                  device_group.name,
                  group_requirements,
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
      for d_in_group in self._ListGroupDevices(group):
        self._run_target_index[d_in_group.run_target.name].pop(
            d_in_group.device_serial)

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


def _MatchDeviceAttribute(required_attr, device_attrs):
  """Check if a device's attributes match the task's requirements."""
  if required_attr.name not in device_attrs:
    logging.debug(
        'No %s in %s.',
        required_attr.name, device_attrs.get('device_serial'))
    return False
  operator = required_attr.operator or '='
  if operator not in _OPERATOR_TO_PREDICTOR:
    # This should never happen, since we check the expression in
    # request_api._ParseAttributeRequirement.
    raise ValueError('Operator "%s" is not supported.' % operator)

  device_attr_value = device_attrs[required_attr.name]
  required_value = required_attr.value
  required_attribute_value = required_value.split('|')

  if len(required_attribute_value) > 1:
    if operator == '=' and required_attr.name not in common.NUMBER_DEVICE_ATTRIBUTES:
      return device_attr_value in required_attribute_value
    else:
      raise ValueError('Operator "|" is not supported.')

  if required_attr.name in common.NUMBER_DEVICE_ATTRIBUTES:
    required_value = common.ParseFloat(required_value)
    if required_value is None:
      # This should never happen, since we check the expression in
      # request_api._ParseAttributeRequirement.
      raise ValueError(
          "%s can not compare to a non-number value '%s'" %
          (required_attr.name, required_attr.value))
    device_attr_value = common.ParseFloat(device_attr_value)
    if device_attr_value is None:
      logging.debug(
          'Device attr %s is a non-number "%s".',
          required_attr.name, device_attrs[required_attr.name])
      return False
  return _OPERATOR_TO_PREDICTOR[operator](device_attr_value, required_value)
