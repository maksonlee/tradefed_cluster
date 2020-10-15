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

"""Unit tests for appengine module."""

from absl.testing import absltest
import cloudstorage

from google.appengine.ext import testbed

from tradefed_cluster.plugins import appengine


class FileStorageTest(absltest.TestCase):
  """Unit tests for Appengine file storage."""

  def setUp(self):
    super(FileStorageTest, self).setUp()
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_all_stubs()
    self.addCleanup(self.testbed.deactivate)

    self.file_storage = appengine.FileStorage()

  def testOpenFile(self):
    with cloudstorage.open('/path/to/file', mode='w') as f:
      f.write(b'hello')

    with self.file_storage.OpenFile(
        '/path/to/file',
        mode='r',
        content_type=None,
        content_encoding=None) as f:
      self.assertEqual(b'hello', f.read())

if __name__ == '__main__':
  absltest.main()
