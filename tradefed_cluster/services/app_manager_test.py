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

"""Unit tests for app_manager module."""

from absl.testing import absltest
import mock


from tradefed_cluster import env_config
from tradefed_cluster.plugins import base as plugins_base
from tradefed_cluster.services import app_manager


class AppManagerTest(absltest.TestCase):
  """Unit tests for AppManager class."""

  def setUp(self):
    super(AppManagerTest, self).setUp()
    self.mock_app_manager = mock.MagicMock(spec=plugins_base.AppManager)
    env_config.CONFIG.app_manager = self.mock_app_manager

  def testGetInfo(self):
    mock_info = plugins_base.AppInfo(name='name', hostname='hostname')
    self.mock_app_manager.GetInfo.return_value = mock_info

    info = app_manager.GetInfo('default')
    self.assertEqual(mock_info, info)

    self.mock_app_manager.GetInfo.assert_called_once_with('default')

if __name__ == '__main__':
  absltest.main()
