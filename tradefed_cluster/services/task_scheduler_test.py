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
import json
import pickle
import threading
import unittest

import mock

from tradefed_cluster import env_config
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.plugins import base as plugins_base
from tradefed_cluster.services import task_scheduler
from tradefed_cluster.util import ndb_shim as ndb

from google3.pyglib import stringutil



_object = threading.local()


def Callable(*args, **kwargs):
  """A stub function for callable task testing."""
  _object.last_callable_call = mock.call(*args, **kwargs)


class TaskSchedulerTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super(TaskSchedulerTest, self).setUp()
    self.mock_task_scheduler = mock.MagicMock(spec=plugins_base.TaskScheduler)
    self.mock_add = self.mock_task_scheduler.AddTask
    env_config.CONFIG.task_scheduler = self.mock_task_scheduler
    _object.last_callable_call = None

  def testAddTask(self):
    mock_task = mock.MagicMock()
    self.mock_add.return_value = mock_task

    task = task_scheduler.AddTask(queue_name='queue_name', payload='payload')

    self.mock_add.assert_called_once_with(
        queue_name='queue_name',
        payload='payload',
        task_name=None,
        eta=None,
        target=None)
    self.assertEqual(mock_task, task)

  def testAddTask_taskTooLargeButNotStoreInNDB(self):
    large_payload = 'payload' + 'x' * task_scheduler.MAX_TASK_SIZE_BYTES

    with self.assertRaises(task_scheduler.TaskTooLargeError):
      task_scheduler.AddTask(
          queue_name='queue_name', payload=large_payload,
          ndb_store_oversized_task=False)

  def testAddTask_taskTooLargeAndStoreInNDB(self):
    large_payload = 'payload' + 'x' * task_scheduler.MAX_TASK_SIZE_BYTES
    large_payload = stringutil.ensure_binary(large_payload)
    task_key = task_scheduler._TaskEntity(data=large_payload).put()

    with mock.patch('__main__.task_scheduler._TaskEntity.put',
                    return_value=task_key):
      mock_task = mock.MagicMock()
      self.mock_add.return_value = mock_task

      task = task_scheduler.AddTask(
          queue_name='queue_name', payload=large_payload,
          ndb_store_oversized_task=True)

      expected_new_payload_dict = {
          task_scheduler.TASK_ENTITY_ID_KEY: task_key.id(),
      }
      expected_new_payload_binary = stringutil.ensure_binary(
          json.dumps(expected_new_payload_dict))

      self.mock_add.assert_called_once_with(
          queue_name='queue_name',
          payload=expected_new_payload_binary,
          task_name=None,
          eta=None,
          target=None)
      self.assertEqual(task_key.get().data, large_payload)
      self.assertEqual(mock_task, task)

  def testAddTask_withTransaction(self):
    self.mock_add.return_value = mock.MagicMock()
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

    self.mock_add.assert_called_once_with(
        queue_name='queue_name',
        payload='payload',
        task_name='name',
        target='target',
        eta=eta)
    self.assertEqual('name', task.name)

  def testAddTask_withTransactionFailure(self):
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

    self.mock_add.assert_not_called()

  def testDeleteTask(self):
    queue_name = 'queue_name'
    task_name = 'task_name'

    task_scheduler.DeleteTask(queue_name=queue_name, task_name=task_name)

    self.mock_task_scheduler.DeleteTask.assert_called_once_with(
        queue_name=queue_name, task_name=task_name)

  def testAddCallableTask(self):
    task_scheduler.AddCallableTask(Callable, 123, foo=bytearray(100))

    self.mock_add.assert_called_once_with(
        queue_name=task_scheduler.DEFAULT_CALLABLE_TASK_QUEUE,
        payload=mock.ANY,
        target=None,
        task_name=None,
        eta=None)
    payload = self.mock_add.call_args[1]['payload']
    # Small payload is executed directly
    self.assertEqual(Callable, pickle.loads(payload)[0])

    task_scheduler.RunCallableTask(payload)
    self.assertEqual(
        mock.call(123, foo=bytearray(100)), _object.last_callable_call)

  def testAddCallableTask_withLargePayload(self):
    task_scheduler.AddCallableTask(Callable, 123, foo=bytearray(100 * 1024))

    self.mock_add.assert_called_once_with(
        queue_name=task_scheduler.DEFAULT_CALLABLE_TASK_QUEUE,
        payload=mock.ANY,
        target=None,
        task_name=None,
        eta=None)
    payload = self.mock_add.call_args[1]['payload']
    # Large payload is stored in datastore
    self.assertEqual(task_scheduler._RunCallableTaskFromDatastore,
                     pickle.loads(payload)[0])

    task_scheduler.RunCallableTask(payload)
    self.assertEqual(
        mock.call(123, foo=bytearray(100 * 1024)), _object.last_callable_call)

  def testAddCallableTask_withLargePayloadAndTransaction(self):
    @ndb.transactional()
    def Func():
      task_scheduler.AddCallableTask(Callable, 123, foo=bytearray(100 * 1024))
    Func()

    self.mock_add.assert_called_once_with(
        queue_name=task_scheduler.DEFAULT_CALLABLE_TASK_QUEUE,
        payload=mock.ANY,
        target=None,
        task_name=mock.ANY,  # Handled transactionally and given a name
        eta=None)
    payload = self.mock_add.call_args[1]['payload']
    task_scheduler.RunCallableTask(payload)
    self.assertEqual(
        mock.call(123, foo=bytearray(100 * 1024)), _object.last_callable_call)

  def testAddCallableTask_withLargePayloadAndTransactionFailure(self):
    @ndb.transactional()
    def Func():
      task_scheduler.AddCallableTask(Callable, 123, foo=bytearray(100 * 1024))
      raise ValueError()
    with self.assertRaises(ValueError):
      Func()

    # Large payload is handled transactionally and not added on failure
    self.mock_add.assert_not_called()

  def testFetchPayloadFromTaskEntity(self):
    large_payload = 'payload' + 'x' * task_scheduler.MAX_TASK_SIZE_BYTES
    large_payload = stringutil.ensure_binary(large_payload)
    task_key = task_scheduler._TaskEntity(data=large_payload).put()

    task_key_id = task_key.id()
    self.assertEqual(
        large_payload,
        task_scheduler.FetchPayloadFromTaskEntity(task_key_id))

  def testDeleteTaskEntity(self):
    large_payload = 'payload' + 'x' * task_scheduler.MAX_TASK_SIZE_BYTES
    large_payload = stringutil.ensure_binary(large_payload)
    task_key = task_scheduler._TaskEntity(data=large_payload).put()
    task_key_id = task_key.id()

    self.assertIsNotNone(task_key.get())
    # Test delete a task that exist
    task_scheduler.DeleteTaskEntity(task_key_id)
    self.assertIsNone(task_key.get())
    # Ensure no error when deleting a task doesn't exist.
    task_scheduler.DeleteTaskEntity(task_entity_id='non-existent')
    # Ensure no error when deleting a task without providing an ID.
    task_scheduler.DeleteTaskEntity(task_entity_id=None)


if __name__ == '__main__':
  unittest.main()
