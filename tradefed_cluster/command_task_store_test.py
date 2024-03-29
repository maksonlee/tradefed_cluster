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

"""Tests for command_task_store."""

import unittest

from tradefed_cluster import command_task_store
from tradefed_cluster import datastore_entities
from tradefed_cluster import testbed_dependent_test


class TaskStoreTest(testbed_dependent_test.TestbedDependentTest):
  """Test cases for task store."""

  def setUp(self):
    super(TaskStoreTest, self).setUp()
    self.test_bench1 = datastore_entities.TestBench(
        cluster='cluster',
        host=datastore_entities.Host(
            groups=[
                datastore_entities.Group(
                    run_targets=[
                        datastore_entities.RunTarget(
                            name='run_target1'),
                        datastore_entities.RunTarget(
                            name='run_target2')]),
                datastore_entities.Group(
                    run_targets=[
                        datastore_entities.RunTarget(
                            name='run_target3'),
                        datastore_entities.RunTarget(
                            name='run_target4')])]))
    self.command_task_args1 = command_task_store.CommandTaskArgs(
        request_id='request_id1',
        command_id='command_id1',
        task_id='task_id1',
        command_line='command_line1',
        run_count=1,
        run_index=0,
        attempt_index=0,
        shard_count=None,
        shard_index=None,
        cluster='cluster',
        run_target='run_target1,run_target2;run_target3,run_target4',
        priority=1,
        request_type=None,
        plugin_data={'ants_invocation_id': 'i123', 'ants_work_unit_id': 'w123'},
        allow_partial_device_match=False)
    self.command_task_args2 = command_task_store.CommandTaskArgs(
        request_id='request_id2',
        command_id='command_id2',
        task_id='task_id2',
        command_line='command_line2',
        run_count=1,
        run_index=0,
        attempt_index=0,
        shard_count=None,
        shard_index=None,
        cluster='cluster',
        run_target='run_target5',
        priority=None,
        request_type=None,
        plugin_data={'ants_invocation_id': 'i123', 'ants_work_unit_id': 'w123'},
        allow_partial_device_match=False)
    command_task_store.CreateTask(self.command_task_args1)
    command_task_store.CreateTask(self.command_task_args2)

    # Avoid randomness in tests.
    def MockRandom():
      return 0
    command_task_store.Random = MockRandom

  def testGetTask(self):
    task = command_task_store.GetTask('task_id1')
    self.assertEqual('task_id1', task.key.id())

  def testGetTask_notExist(self):
    task = command_task_store.GetTask('not_exist_task')
    self.assertIsNone(task)

  def testGetTasks(self):
    tasks = command_task_store.GetTasks(['task_id1', 'task_id2'])
    self.assertEqual(2, len(tasks))
    self.assertEqual('task_id1', tasks[0].key.id())
    self.assertEqual('task_id2', tasks[1].key.id())

  def testCreateTask(self):
    task = command_task_store._Key('task_id1').get()
    self.assertIsNotNone(task)
    self.assertEqual('task_id1', task.task_id)
    self.assertEqual(
        ['run_target1', 'run_target2', 'run_target3', 'run_target4'],
        task.run_targets)
    self.assertTrue(task.leasable)
    self.assertEqual(0, task.lease_count)
    self.assertEqual(1, task.priority)
    self.assertIsNotNone(task.schedule_timestamp)

  def testCreateTask_withTestBench(self):
    command_task_args = command_task_store.CommandTaskArgs(
        request_id='request_id3',
        command_id='command_id3',
        task_id='task_id3',
        command_line='command_line',
        cluster='cluster',
        run_target='run_target5',
        test_bench=self.test_bench1)
    command_task_store.CreateTask(command_task_args)
    task = command_task_store._Key('task_id3').get()
    self.assertTrue(task.leasable)
    self.assertEqual('task_id3', task.task_id)
    self.assertEqual('command_line', task.command_line)
    self.assertIsNotNone(task.schedule_timestamp)
    self.assertEqual(self.test_bench1, task.test_bench)

  def testCreateTask_largeTextCommandLine(self):
    command_line = 'command_line ' + 'arg ' * 10000
    command_task_args = command_task_store.CommandTaskArgs(
        request_id='request_id3',
        command_id='command_id3',
        task_id='task_id3',
        command_line=command_line,
        run_count=1,
        run_index=0,
        attempt_index=0,
        shard_count=None,
        shard_index=None,
        cluster='cluster',
        run_target='run_target5',
        priority=1,
        request_type=None,
        plugin_data={'ants_invocation_id': 'i123', 'ants_work_unit_id': 'w123'},
        allow_partial_device_match=True)
    command_task_store.CreateTask(command_task_args)
    task = command_task_store._Key('task_id3').get()
    self.assertTrue(task.leasable)
    self.assertEqual('task_id3', task.task_id)
    self.assertEqual(command_line, task.command_line)
    self.assertIsNotNone(task.schedule_timestamp)
    self.assertTrue(task.allow_partial_device_match)

  def testGetLeasableTasks(self):
    tasks = list(command_task_store.GetLeasableTasks(
        'cluster', ['run_target5']))
    self.assertEqual(1, len(tasks))
    task = tasks[0]
    self.assertEqual('task_id2', task.task_id)

  def testGetLeasableTasks_multipleRunTargets(self):
    tasks = list(command_task_store.GetLeasableTasks(
        'cluster', ['run_target1', 'run_target2',
                    'run_target3', 'run_target4']))
    self.assertEqual(1, len(tasks))
    task = tasks[0]
    self.assertEqual('task_id1', task.task_id)

  def testGetLeasableTasks_priority(self):
    tasks = list(command_task_store.GetLeasableTasks(
        'cluster', ['run_target1', 'run_target2',
                    'run_target3', 'run_target4',
                    'run_target5']))
    self.assertEqual(2, len(tasks))
    self.assertEqual('task_id1', tasks[0].task_id)
    self.assertEqual('task_id2', tasks[1].task_id)

  def testGetLeasableTasks_noLeasableTasks(self):
    command_task_store.LeaseTask('task_id1')
    command_task_store.LeaseTask('task_id2')
    tasks = list(command_task_store.GetLeasableTasks(
        'cluster', ['run_target1']))
    self.assertEqual(0, len(tasks))

  def testLeaseTask(self):
    # lease works for the first time
    self.assertTrue(command_task_store.LeaseTask('task_id1'))
    # lease fails for the second time
    self.assertFalse(command_task_store.LeaseTask('task_id1'))
    task = command_task_store._Key('task_id1').get()
    self.assertFalse(task.leasable)
    self.assertIsNotNone(task.lease_timestamp)

  def testLeaseTask_notExistTask(self):
    # lease works for the first time
    self.assertFalse(command_task_store.LeaseTask('task_id_not_exist'))

  def testDeleteTask(self):
    task = command_task_store._Key('task_id1').get()
    self.assertIsNotNone(task)
    command_task_store.DeleteTask('task_id1')
    task1 = command_task_store._Key('task_id1').get()
    self.assertIsNone(task1)

  def testDeleteTasks(self):
    self.assertIsNotNone(command_task_store._Key('task_id1').get())
    self.assertIsNotNone(command_task_store._Key('task_id2').get())
    command_task_store.DeleteTasks(['task_id1', 'task_id2'])
    self.assertIsNone(command_task_store._Key('task_id1').get())
    self.assertIsNone(command_task_store._Key('task_id2').get())

  def testRescheduleTask(self):
    self.assertTrue(command_task_store.LeaseTask('task_id1'))
    task = command_task_store._Key('task_id1').get()
    old_schedule_timestamp = task.schedule_timestamp
    self.assertFalse(task.leasable)
    command_task_store.RescheduleTask('task_id1', 1, 2)
    task = command_task_store._Key('task_id1').get()
    self.assertTrue(task.leasable)
    self.assertEqual(1, task.run_index)
    self.assertEqual(2, task.attempt_index)
    self.assertIsNotNone(task.schedule_timestamp)
    self.assertNotEqual(old_schedule_timestamp, task.schedule_timestamp)

  def testGetActiveTaskCount(self):
    count = command_task_store.GetActiveTaskCount([
        'task_id1', 'task_id3'])
    self.assertEqual(1, count)


if __name__ == '__main__':
  unittest.main()
