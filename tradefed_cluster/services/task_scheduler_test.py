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

"""Unit tests for task_scheduler module."""

import datetime
import threading
import unittest

import mock

from tradefed_cluster import env_config
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.plugins import base as plugins_base
from tradefed_cluster.services import task_scheduler
from tradefed_cluster.util import ndb_shim as ndb

_object = threading.local()


def Callable(*args, **kwargs):
  """A stub function for callable task testing."""
  _object.last_callable_call = mock.call(*args, **kwargs)


class TaskSchedulerTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super(TaskSchedulerTest, self).setUp()
    self.mock_task_scheduler = mock.MagicMock(spec=plugins_base.TaskScheduler)
    env_config.CONFIG.task_scheduler = self.mock_task_scheduler

  def testAddTask(self):
    mock_add = self.mock_task_scheduler.AddTask
    mock_task = mock.MagicMock()
    mock_add.return_value = mock_task

    task = task_scheduler.AddTask(queue_name='queue_name', payload='payload')

    mock_add.assert_called_once_with(
        queue_name='queue_name',
        payload='payload',
        task_name=None,
        eta=None,
        target=None)
    self.assertEqual(mock_task, task)

  def testAddTask_withTransaction(self):
    mock_add = self.mock_task_scheduler.AddTask
    mock_task = mock.MagicMock()
    mock_add.return_value = mock_task
    eta = datetime.datetime.utcnow() + datetime.timedelta(days=1)

    @ndb.transactional()
    def Func():
      return task_scheduler.AddTask(
          queue_name='queue_name',
          payload='payload',
          name='name',
          target='target',
          eta=eta,
          transactional=True)
    task = Func()

    mock_add.assert_called_once_with(
        queue_name='queue_name',
        payload='payload',
        task_name='name',
        target='target',
        eta=eta)
    self.assertEqual('name', task.name)

  def testAddTask_withTransactionFailure(self):
    mock_add = self.mock_task_scheduler.AddTask
    eta = datetime.datetime.utcnow() + datetime.timedelta(days=1)

    @ndb.transactional()
    def Func():
      task_scheduler.AddTask(
          queue_name='queue_name',
          payload='payload',
          name='name',
          target='target',
          eta=eta,
          transactional=True)
      raise ValueError()
    with self.assertRaises(ValueError):
      Func()

    mock_add.assert_not_called()

  def testDeleteTask(self):
    queue_name = 'queue_name'
    task_name = 'task_name'

    task_scheduler.DeleteTask(queue_name=queue_name, task_name=task_name)

    self.mock_task_scheduler.DeleteTask.assert_called_once_with(
        queue_name=queue_name, task_name=task_name)

  def testAddCallableTask(self):
    mock_add = self.mock_task_scheduler.AddTask
    _object.last_callable_call = None

    task_scheduler.AddCallableTask(Callable, 1, foo=10, bar=100, zzz=1000)

    mock_add.assert_called_once_with(
        queue_name=task_scheduler.DEFAULT_CALLABLE_TASK_QUEUE,
        payload=mock.ANY,
        target=None,
        task_name=None,
        eta=None)
    task_scheduler.RunCallableTask(mock_add.call_args[1]['payload'])
    self.assertEqual(
        mock.call(1, foo=10, bar=100, zzz=1000), _object.last_callable_call)

  def testAddCallableTask_withLargePayload(self):
    mock_add = self.mock_task_scheduler.AddTask
    _object.last_callable_call = None
    mock_add.return_value = None

    task_scheduler.AddCallableTask(Callable, 1, foo=10, bar=100, zzz=1000)

    mock_add.assert_called_once_with(
        queue_name=task_scheduler.DEFAULT_CALLABLE_TASK_QUEUE,
        payload=mock.ANY,
        target=None,
        task_name=None,
        eta=None)
    task_scheduler.RunCallableTask(mock_add.call_args[1]['payload'])
    self.assertEqual(
        mock.call(1, foo=10, bar=100, zzz=1000), _object.last_callable_call)

  def testAddCallableTask_withLargePayloadAndTransaction(self):
    mock_add = self.mock_task_scheduler.AddTask
    _object.last_callable_call = None
    mock_add.return_value = None

    @ndb.transactional()
    def Func():
      task_scheduler.AddCallableTask(Callable, 1, foo=10, bar=100, zzz=1000)
    Func()

    mock_add.assert_called_once_with(
        queue_name=task_scheduler.DEFAULT_CALLABLE_TASK_QUEUE,
        payload=mock.ANY,
        target=None,
        task_name=None,
        eta=None)
    task_scheduler.RunCallableTask(mock_add.call_args[1]['payload'])
    self.assertEqual(
        mock.call(1, foo=10, bar=100, zzz=1000), _object.last_callable_call)

  def testAddCallableTask_withLargePayloadAndTransactionFailure(self):
    mock_add = self.mock_task_scheduler.AddTask
    _object.last_callable_call = None
    mock_add.return_value = None

    @ndb.transactional()
    def Func():
      task_scheduler.AddCallableTask(Callable, 1, foo=10, bar=100, zzz=1000)
      raise ValueError()
    with self.assertRaises(ValueError):
      Func()

    mock_add.assert_called_once_with(
        queue_name=task_scheduler.DEFAULT_CALLABLE_TASK_QUEUE,
        payload=mock.ANY,
        target=None,
        task_name=None,
        eta=None)
    task_scheduler.RunCallableTask(mock_add.call_args[1]['payload'])
    self.assertEqual(
        mock.call(1, foo=10, bar=100, zzz=1000), _object.last_callable_call)


if __name__ == '__main__':
  unittest.main()
