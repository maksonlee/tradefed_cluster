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

"""Unit tests for base module."""

import unittest

from tradefed_cluster.plugins import base
from tradefed_cluster.plugins import noop_plugin
from tradefed_cluster.plugins import registry


class BaseTest(unittest.TestCase):

  def testGetPlugin(self):
    plugin = registry.GetNoOpPlugin()
    self.assertEqual(isinstance(plugin, noop_plugin.NoOpPlugin), True)

    plugin = registry.GetPlugin('stub')
    self.assertEqual(isinstance(plugin, StubPlugin), True)


class StubPlugin(base.Plugin):
  """A stub Plugin."""
  name = 'stub'

if __name__ == '__main__':
  unittest.main()
