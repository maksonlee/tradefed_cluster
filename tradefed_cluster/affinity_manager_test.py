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

"""Unit tests for affinity_manager."""

import unittest

from tradefed_cluster import affinity_manager
from tradefed_cluster import testbed_dependent_test


class AffinityManagerTest(testbed_dependent_test.TestbedDependentTest):

  def testSetDeviceAffinity(self):
    serial = 'serial'
    affinity_tag = 'affinity_tag'

    affinity_manager.SetDeviceAffinity(serial, affinity_tag)

    infos = affinity_manager.GetDeviceAffinityInfos([serial])
    self.assertEqual(infos[0].device_serial, serial)
    self.assertEqual(infos[0].affinity_tag, affinity_tag)
    status = affinity_manager.GetAffinityStatus(affinity_tag)
    self.assertEqual(status.affinity_tag, affinity_tag)
    self.assertEqual(status.device_count, 1)
    self.assertEqual(status.task_count, 0)
    self.assertEqual(status.needed_device_count, 0)

  def testResetDeviceAffinities(self):
    serial = 'serial'
    affinity_tag = 'affinity_tag'
    affinity_manager.SetDeviceAffinity(serial, affinity_tag)

    affinity_manager.ResetDeviceAffinity(serial)

    infos = affinity_manager.GetDeviceAffinityInfos([serial])
    self.assertIsNone(infos[0])
    status = affinity_manager.GetAffinityStatus(affinity_tag)
    self.assertEqual(status.affinity_tag, affinity_tag)
    self.assertEqual(status.device_count, 0)
    self.assertEqual(status.task_count, 0)
    self.assertEqual(status.needed_device_count, 0)

  def testSetTaskAffinity(self):
    task_id = 'task_id'
    affinity_tag = 'affinity_tag'

    affinity_manager.SetTaskAffinity(task_id, affinity_tag, 2)

    infos = affinity_manager.GetTaskAffinityInfos([task_id])
    self.assertEqual(infos[0].task_id, task_id)
    self.assertEqual(infos[0].affinity_tag, affinity_tag)
    self.assertEqual(infos[0].needed_device_count, 2)
    status = affinity_manager.GetAffinityStatus(affinity_tag)
    self.assertEqual(status.affinity_tag, affinity_tag)
    self.assertEqual(status.device_count, 0)
    self.assertEqual(status.task_count, 1)
    self.assertEqual(status.needed_device_count, 2)

  def testSetTaskAffinity_multipleTasks(self):
    task_ids = ['task_id 1', 'task_id 2', 'task_id 3']
    affinity_tag = 'affinity_tag'

    for task_id in task_ids:
      affinity_manager.SetTaskAffinity(task_id, affinity_tag, 1)

    status = affinity_manager.GetAffinityStatus(affinity_tag)
    self.assertEqual(status.affinity_tag, affinity_tag)
    self.assertEqual(status.device_count, 0)
    self.assertEqual(status.task_count, 3)
    self.assertEqual(status.needed_device_count, 3)

  def testResetTaskAffinity(self):
    task_id = 'task_id'
    affinity_tag = 'affinity_tag'
    affinity_manager.SetTaskAffinity(task_id, affinity_tag, 2)

    affinity_manager.ResetTaskAffinity(task_id)

    infos = affinity_manager.GetTaskAffinityInfos([task_id])
    self.assertIsNone(infos[0])
    status = affinity_manager.GetAffinityStatus(affinity_tag)
    self.assertEqual(status.affinity_tag, affinity_tag)
    self.assertEqual(status.device_count, 0)
    self.assertEqual(status.task_count, 0)
    self.assertEqual(status.needed_device_count, 0)

  def testResetTaskAffinity_multipleTasks(self):
    task_ids = ['task_id 1', 'task_id 2', 'task_id 3']
    affinity_tag = 'affinity_tag'
    for task_id in task_ids:
      affinity_manager.SetTaskAffinity(task_id, affinity_tag, 1)

    affinity_manager.ResetTaskAffinity(task_ids[0])
    affinity_manager.ResetTaskAffinity(task_ids[1])

    status = affinity_manager.GetAffinityStatus(affinity_tag)
    self.assertEqual(status.affinity_tag, affinity_tag)
    self.assertEqual(status.device_count, 0)
    self.assertEqual(status.task_count, 1)
    self.assertEqual(status.needed_device_count, 1)

if __name__ == '__main__':
  unittest.main()
