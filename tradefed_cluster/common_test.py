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

"""Tests for google3.wireless.android.test_tools.tradefed_cluster.common."""

import unittest

from tradefed_cluster import common


# GPyLint does not recognize the ClassProperty in the common module.
class TestIntState(int):

  def __new__(cls, value):
    return int.__new__(cls, int(value))

  @common.ClassProperty
  def StateZero(cls):
    return cls(0)

  @common.ClassProperty
  def StateOne(cls):
    return cls(1)


class CommonTest(unittest.TestCase):

  def testClassProperty(self):
    """Tests that class properties can be accessed."""
    self.assertEqual(0, TestIntState.StateZero)
    self.assertEqual(1, TestIntState.StateOne)


if __name__ == "__main__":
  unittest.main()
