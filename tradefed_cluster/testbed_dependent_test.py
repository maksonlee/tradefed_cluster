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
import os
import shutil
import stat
import tempfile
import uuid

import mock


from tradefed_cluster import env_config
from tradefed_cluster.plugins import base
from tradefed_cluster.util import ndb_test_lib


class MockFileStorage(base.FileStorage):
  """A mock file storage."""

  def __init__(self):
    super(MockFileStorage, self).__init__()
    self.root_dir = tempfile.mkdtemp()

  def _GetRealPath(self, path):
    return os.path.join(self.root_dir, path.lstrip('/'))

  def Cleanup(self):
    shutil.rmtree(self.root_dir)

  def ListFiles(self, path):
    real_path = self._GetRealPath(path)
    files = []
    for filename in os.listdir(real_path):
      st = os.stat(os.path.join(real_path, filename))
      files.append(
          base.FileInfo(
              filename=os.path.join(path, filename),
              is_dir=stat.S_ISDIR(st.st_mode),
              size=st.st_size,
              content_type=None))
    return files

  def OpenFile(self, path, mode='r', content_type=None, content_encoding=None):
    del content_type
    del content_encoding
    real_path = self._GetRealPath(path)
    parent_path = os.path.dirname(real_path)
    if 'w' == mode and not os.path.exists(parent_path):
      os.makedirs(parent_path)
    return open(real_path, mode + 'b')


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
    # Simulate GAE environment.
    os.environ['GAE_APPLICATION'] = 'testbed-test'
    os.environ['GAE_SERVICE'] = 'default'
    os.environ['GAE_VERSION'] = 'testbed-version'
    self.mock_app_manager = mock.MagicMock(spec=base.AppManager)
    env_config.CONFIG.app_manager = self.mock_app_manager
    self.mock_file_storage = MockFileStorage()
    env_config.CONFIG.file_storage = self.mock_file_storage
    self.addCleanup(self.mock_file_storage.Cleanup)
    self.mock_mailer = mock.MagicMock(spec=base.Mailer)
    env_config.CONFIG.mailer = self.mock_mailer
    self.mock_task_scheduler = MockTaskScheduler()
    env_config.CONFIG.task_scheduler = self.mock_task_scheduler
