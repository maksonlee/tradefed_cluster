# Copyright 202 Google LLC
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
"""Tests for ndb_util."""

import unittest

from google.cloud import ndb

from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.util import ndb_util


def _MockModelRenameFooToBar(obj):
  obj.bar = obj.foo


def _MockModelRenameBarToZzz(obj):
  obj.zzz = obj.bar


class MockModel(ndb_util.UpgradableModel):
  foo = ndb.StringProperty()
  bar = ndb.StringProperty()
  zzz = ndb.StringProperty()

  _upgrade_steps = [
      _MockModelRenameFooToBar,
      _MockModelRenameBarToZzz,
  ]


class UpgradableModelTest(testbed_dependent_test.TestbedDependentTest):

  def testUpgrade(self):
    obj = MockModel(foo='foo')
    obj.schema_version = 0
    obj.Upgrade()
    self.assertEqual(obj.zzz, 'foo')

  def testUpgrade_oneVersion(self):
    obj = MockModel(bar='foo')
    obj.schema_version = 1
    obj.Upgrade()
    self.assertEqual(obj.zzz, 'foo')

  def testUpgrade_latestVersion(self):
    obj = MockModel(zzz='zzz')
    obj.put()
    obj.Upgrade()
    self.assertEqual(obj.zzz, 'zzz')

  def testPostGetHook(self):
    obj = MockModel(foo='foo')
    obj.schema_version = 0
    obj.put()

    obj = obj.key.get()
    self.assertEqual(obj.zzz, 'foo')


if __name__ == '__main__':
  unittest.main()
