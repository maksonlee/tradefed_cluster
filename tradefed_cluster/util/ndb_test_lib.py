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
"""Test classes to make ndb context available for tests."""
from __future__ import absolute_import
from __future__ import division
from __future__ import google_type_annotations
from __future__ import print_function

import os

from absl.testing import absltest

from tradefed_cluster.util import datastore_emulator
from tradefed_cluster.util import ndb_shim as ndb

from google.auth import credentials

# Use a single datastore emulator instance per module, as its creation
# is expensive.
datastore = None


def NdbContextManager():
  """Will start a ndb.Client.context with default credentials.

  Returns:
    An instance of ndb.Context provided by the ndb.Client
  """
  return ndb.Client(
      project='testbed-test',
      credentials=credentials.AnonymousCredentials()).context(
          cache_policy=False, global_cache_policy=False,
          legacy_data=False)


class NdbTest(absltest.TestCase):
  """Makes ndb context manager available for tests."""

  @classmethod
  def setUpClass(cls):
    super(NdbTest, cls).setUpClass()
    global datastore
    if datastore:
      return

    datastore_factory = datastore_emulator.DatastoreEmulatorFactory()
    # The timeout for large tests is 900 seconds
    datastore = datastore_factory.Create('foo', deadline=800)

    # The host doesn't get used since we override the stub, however the
    # existence of this environment variable can break if we try to get
    # credentials.
    os.environ['DATASTORE_EMULATOR_HOST'] = datastore.GetHostPort().replace(
        'http://', '')

  def setUp(self):
    super(NdbTest, self).setUp()
    self.context_manager = NdbContextManager()
    datastore.Clear()


class NdbWithContextTest(NdbTest):
  """Wrapps test cases by a ndb context block."""

  def setUp(self):
    super(NdbWithContextTest, self).setUp()
    try:
      self.context_manager.__enter__()
    except RuntimeError:
      pass

  def tearDown(self):
    try:
      self.context_manager.__exit__(None, None, None)
    except RuntimeError:
      pass
    super(NdbWithContextTest, self).tearDown()
