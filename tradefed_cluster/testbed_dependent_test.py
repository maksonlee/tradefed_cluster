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

"""Module for testbed dependencies base class."""

import collections
import uuid

import mock
from google.appengine.ext import testbed

from tradefed_cluster import api_common
from tradefed_cluster import env_config
from tradefed_cluster.plugins import base
from tradefed_cluster.util import ndb_test_lib


class MockTaskScheduler(base.TaskScheduler):
  """A mock task scheduler."""

  def __init__(self):
    super(MockTaskScheduler, self).__init__()
    self.queues = collections.defaultdict(list)

  def AddTask(self, queue_name, payload, target, task_name, eta):
    task = base.Task(
        name=task_name or str(uuid.uuid4()), payload=payload, eta=eta)
    self.queues[queue_name].append(task)
    return task

  def DeleteTask(self, queue_name, task_name):
    queue = self.queues[queue_name]
    for i, task in enumerate(queue):
      if task.name == task_name:
        del queue[i]
        break

  def GetTasks(self, queue_names=None):
    tasks = []
    for name, queue in self.queues.items():
      if queue_names and name not in queue_names:
        continue
      tasks.extend(queue)
    return tasks


class TestbedDependentTest(ndb_test_lib.NdbWithContextTest):
  """Base class for tests with testbed dependencies."""

  def setUp(self):
    """Create database and tables."""
    super(TestbedDependentTest, self).setUp()
    self.testbed = testbed.Testbed()
    self.testbed.setup_env(
        user_email='user@example.com',
        user_id=api_common.ANONYMOUS,
        user_is_admin='1',
        endpoints_auth_email='user@example.com',
        endpoints_auth_domain='example.com',
        overwrite=True)
    self.testbed.activate()
    self.testbed.init_all_stubs()
    self.addCleanup(self.testbed.deactivate)

    self.mock_mailer = mock.MagicMock(spec=base.Mailer)
    env_config.CONFIG.mailer = self.mock_mailer
    self.mock_task_scheduler = MockTaskScheduler()
    env_config.CONFIG.task_scheduler = self.mock_task_scheduler
