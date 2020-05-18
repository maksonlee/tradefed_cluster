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

"""A task scheduler service.

This module is developed to replace the legacy usage of GAE Taskqueue.
"""

from google.appengine.api import taskqueue


class Error(Exception):
  """A task scheduler error."""
  pass


def add_task(queue_name, payload, name=None, eta=None, transactional=False):
  """Add a task.

  This is currently a shim to GAE taskqueue.

  Args:
    queue_name: a queue name.
    payload: a task payload.
    name: a task name (optional).
    eta: a ETA for task execution (optional).
    transactional: a flag to indicate whether this task should be tied to
        datastore transaction.
  Returns:
    a taskqueue.Task object.
  """
  try:
    return taskqueue.add(
        queue_name=queue_name,
        payload=payload,
        name=name,
        eta=eta,
        transactional=transactional)
  except taskqueue.Error as e:
    raise Error(e)


def delete_task(queue_name, task_name):
  """delete a task.

  This is currently a shim to GAE taskqueue.

  Args:
    queue_name: a queue name.
    task_name: a task name.
  """
  try:
    taskqueue.Queue(queue_name).delete_tasks_by_name(task_name=task_name)
  except taskqueue.Error as e:
    raise Error(e)
