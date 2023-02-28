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

"""Unit tests for file_storage module."""

from absl.testing import absltest
import mock


from tradefed_cluster import env_config
from tradefed_cluster.plugins import base as plugins_base
from tradefed_cluster.services import file_storage


class FileStorageTest(absltest.TestCase):

  def setUp(self):
    super(FileStorageTest, self).setUp()
    self.mock_file_storage = mock.MagicMock(spec=plugins_base.FileStorage)
    env_config.CONFIG.file_storage = self.mock_file_storage

  def testListFiles(self):
    mock_iterator = mock.Mock()
    self.mock_file_storage.ListFiles.return_value = mock_iterator

    it = file_storage.ListFiles(path='path')

    self.assertEqual(it, mock_iterator)
    self.mock_file_storage.ListFiles.assert_called_once_with('path')

  def testOpenFile(self):
    mock_file_object = mock.Mock()
    self.mock_file_storage.OpenFile.return_value = mock_file_object

    f = file_storage.OpenFile(path='path')

    self.assertEqual(f, mock_file_object)
    self.mock_file_storage.OpenFile.assert_called_once_with(
        path='path', mode='r', content_type=None, content_encoding=None)

  def testOpenFile_withAllParameters(self):
    mock_file_object = mock.Mock()
    self.mock_file_storage.OpenFile.return_value = mock_file_object

    f = file_storage.OpenFile(
        path='path',
        mode='w',
        content_type='content_type',
        content_encoding='content_encoding')

    self.assertEqual(f, mock_file_object)
    self.mock_file_storage.OpenFile.assert_called_once_with(
        path='path',
        mode='w',
        content_type='content_type',
        content_encoding='content_encoding')

if __name__ == '__main__':
  absltest.main()
