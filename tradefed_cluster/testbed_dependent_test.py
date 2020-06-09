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
import os

import unittest

from google.appengine.datastore import datastore_stub_util
from google.appengine.ext import testbed

from tradefed_cluster import api_common
from tradefed_cluster.util import ndb_shim as ndb


class TestbedDependentTest(unittest.TestCase):
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
    policy = datastore_stub_util.PseudoRandomHRConsistencyPolicy(1.0)
    self.testbed.init_datastore_v3_stub(consistency_policy=policy)
    self.testbed.init_taskqueue_stub(
        root_path=os.path.join(os.path.dirname(__file__), 'test_yaml'))
    self.taskqueue_stub = self.testbed.get_stub(testbed.TASKQUEUE_SERVICE_NAME)
    self.addCleanup(self.testbed.deactivate)
    # Clear Datastore cache
    ndb.get_context().clear_cache()
