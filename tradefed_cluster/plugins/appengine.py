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

"""Plugins for Python 2 GAE."""

from google.appengine.api import taskqueue

from tradefed_cluster.plugins import base


class TaskScheduler(base.TaskScheduler):
  """A Python 2 GAE task scheduler.

  TODO: remove this scheduler once MTT migrates to a new scheduler.
  """

  def AddTask(self, queue_name, payload, target, task_name, eta):
    return taskqueue.add(
        queue_name=queue_name,
        payload=payload,
        target=target,
        name=task_name,
        eta=eta)

  def DeleteTask(self, queue_name, task_name):
    taskqueue.Queue(queue_name).delete_tasks_by_name(task_name=task_name)
