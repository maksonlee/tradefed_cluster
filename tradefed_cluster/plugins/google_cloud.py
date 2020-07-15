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

"""Plugins for Google Cloud Platform."""

from google.api_core import retry
from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2

from tradefed_cluster.plugins import base

DEFAULT_RETRY_OPTION = retry.Retry(deadline=60)


class TaskScheduler(base.TaskScheduler):
  """A task scheduler for Cloud Tasks."""

  def __init__(self, project, location, client=None):
    """Constructor.

    Args:
      project: a project name.
      location: a project location.
      client: a tasks_v2.CloudTasksClient object (for testing).
    """
    self._project = project
    self._location = location
    self._client = client or tasks_v2.CloudTasksClient()

  def AddTask(self, queue_name, payload, target, task_name, eta):
    parent = self._client.queue_path(self._project, self._location, queue_name)
    if not isinstance(payload, bytes):
      payload = payload.encode()
    task = {
        'app_engine_http_request': {
            'http_method': 'POST',
            'app_engine_routing': {},
            'relative_uri': '/_ah/queue/%s' % queue_name,
            'body': payload
        }
    }
    if task_name:
      task['name'] = self._client.task_path(
          self._project, self._location, queue_name, task_name)
    if eta:
      timestamp = timestamp_pb2.Timestamp()
      timestamp.FromDatetime(eta)
      task['schedule_time'] = timestamp
    if target:
      task['app_engine_http_request']['app_engine_routing']['service'] = target
    task = self._client.create_task(parent, task, retry=DEFAULT_RETRY_OPTION)
    return base.Task(name=task.name)

  def DeleteTask(self, queue_name, task_name):
    task_path = self._client.task_path(
        self._project, self._location, queue_name, task_name)
    self._client.delete_task(task_path, retry=DEFAULT_RETRY_OPTION)
