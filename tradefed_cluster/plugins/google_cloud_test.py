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

"""Unit tests for google_cloud module."""

import datetime
import unittest
import zlib

import mock

from google.cloud import tasks_v2
from google3.google.protobuf import timestamp_pb2


from tradefed_cluster.plugins import google_cloud


class TaskSchedulerTest(unittest.TestCase):
  """Unit tests for Google Cloud task scheduler."""

  def setUp(self):
    super(TaskSchedulerTest, self).setUp()
    self.mock_client = mock.MagicMock(spec=tasks_v2.CloudTasksClient)
    self.target = google_cloud.TaskScheduler(
        'project', 'location')
    self.target._GetClient = mock.MagicMock(return_value=self.mock_client)

  def testAddTask(self):
    self.mock_client.queue_path.return_value = 'queue_path'
    self.mock_client.task_path.return_value = 'task_path'
    mock_task = mock.MagicMock()
    mock_task.name = (
        'projects/project/locations/location/queues/queue/tasks/task_name')
    self.mock_client.create_task.return_value = mock_task
    payload = 'payload'
    eta = datetime.datetime.utcnow()
    timestamp = timestamp_pb2.Timestamp()
    timestamp.FromDatetime(eta)

    task = self.target.AddTask(
        queue_name='queue_name',
        payload=payload,
        target='target',
        task_name='task_name',
        eta=eta)

    self.mock_client.queue_path.assert_called_once_with(
        'project', 'location', 'queue_name')
    self.mock_client.task_path.assert_called_once_with(
        'project', 'location', 'queue_name', 'task_name')
    self.mock_client.create_task.assert_called_once_with(
        'queue_path',
        {
            'name': 'task_path',
            'schedule_time': timestamp,
            'app_engine_http_request': {
                'http_method': 'POST',
                'app_engine_routing': {
                    'service': 'target',
                },
                'relative_uri': '/_ah/queue/queue_name',
                'body': payload.encode()
            }
        },
        retry=google_cloud.DEFAULT_RETRY_OPTION)
    self.assertIsNotNone(task)
    self.assertEqual('task_name', task.name)

  def testAddTask_withCompressedPayload(self):
    self.mock_client.queue_path.return_value = 'queue_path'
    mock_task = mock.MagicMock()
    mock_task.name = (
        'projects/project/locations/location/queues/queue/tasks/task_name')
    self.mock_client.create_task.return_value = mock_task
    payload = zlib.compress(b'payload')

    task = self.target.AddTask(
        queue_name='queue_name',
        payload=payload,
        target=None,
        task_name=None,
        eta=None)

    self.mock_client.queue_path.assert_called_once_with(
        'project', 'location', 'queue_name')
    self.mock_client.create_task.assert_called_once_with(
        'queue_path',
        {
            'app_engine_http_request': {
                'http_method': 'POST',
                'app_engine_routing': {},
                'relative_uri': '/_ah/queue/queue_name',
                'body': payload
            }
        },
        retry=google_cloud.DEFAULT_RETRY_OPTION)
    self.assertIsNotNone(task)
    self.assertEqual('task_name', task.name)


if __name__ == '__main__':
  unittest.main()
