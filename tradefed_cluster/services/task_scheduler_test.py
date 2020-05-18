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

from absl.testing import absltest
import mock

from google.appengine.api import taskqueue

from tradefed_cluster.services import task_scheduler


class TaskSchedulerTest(absltest.TestCase):

  @mock.patch.object(taskqueue, 'add')
  def testAddTask(self, mock_add):
    mock_task = mock.MagicMock()
    mock_add.return_value = mock_task
    kwargs = {
        'queue_name': 'queue_name',
        'payload': 'payload',
        'name': 'name',
        'eta': None,
        'transactional': False
    }

    task = task_scheduler.add_task(**kwargs)

    mock_add.assert_called_once_with(**kwargs)
    self.assertEqual(mock_task, task)

  @mock.patch.object(taskqueue, 'Queue')
  def testDeleteTask(self, mock_queue_ctor):
    queue_name = 'queue_name'
    task_name = 'task_name'
    mock_queue = mock.MagicMock()
    mock_queue_ctor.return_value = mock_queue

    task_scheduler.delete_task(queue_name=queue_name, task_name=task_name)

    mock_queue_ctor.assert_called_once_with(queue_name)
    mock_queue.delete_tasks_by_name.assert_called_once_with(task_name=task_name)

if __name__ == '__main__':
  absltest.main()
