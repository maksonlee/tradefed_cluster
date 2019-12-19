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

"""Unit Tests for command_error_type_config module."""

import unittest

from tradefed_cluster import command_error_type_config
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import testbed_dependent_test


class CommandCommandErrorTypeConfigTest(
    testbed_dependent_test.TestbedDependentTest):

  def testGetConfig_fromDatastore(self):
    """Tests get error reason and type from datastore correctly."""
    self.assertIsNone(command_error_type_config.TYPE_DICT.get('error1'))

    config = datastore_entities.CommandErrorConfigMapping(
        error_message='error1',
        reason='reason1',
        type_code=common.CommandErrorType.INFRA
    )
    config.put()
    # Test existing mapping config in datastore but not in default
    self.assertEqual(
        ('reason1', common.CommandErrorType.INFRA),
        command_error_type_config.GetConfig('error1'))
    self.assertErrorConfigInDatastore(
        'error1', 'reason1', common.CommandErrorType.INFRA)

  def testGetConfig_default(self):
    """Tests get reason and type from default configs correctly."""
    error_message = 'com.android.tradefed.build.BuildRetrievalError: Failed'
    self.assertEqual(
        (command_error_type_config.ErrorReason.BUILD_RETRIEVAL_ERROR,
         common.CommandErrorType.INFRA),
        command_error_type_config.TYPE_DICT.get(
            'com.android.tradefed.build.BuildRetrievalError'))

    self.assertEqual(
        (command_error_type_config.ErrorReason.BUILD_RETRIEVAL_ERROR,
         common.CommandErrorType.INFRA),
        command_error_type_config.GetConfig(error_message))

    # Default config is added into datastore after getConfig is called.
    self.assertErrorConfigInDatastore(
        'com.android.tradefed.build.BuildRetrievalError',
        command_error_type_config.ErrorReason.BUILD_RETRIEVAL_ERROR,
        common.CommandErrorType.INFRA)

  def testGetConfig_override(self):
    """Tests datastore error mapping could override default configs."""
    self.assertEqual(
        (command_error_type_config.ErrorReason.QUEUE_TIMEOUT,
         common.CommandErrorType.INFRA),
        command_error_type_config.TYPE_DICT.get(
            'A task reset by command attempt monitor.'))

    config = datastore_entities.CommandErrorConfigMapping(
        error_message='A task reset by command attempt monitor.',
        reason='reason2',
        type_code=common.CommandErrorType.TEST
    )
    config.put()
    self.assertEqual(
        ('reason2', common.CommandErrorType.TEST),
        command_error_type_config.GetConfig(
            'A task reset by command attempt monitor.'))
    self.assertErrorConfigInDatastore(
        'A task reset by command attempt monitor.', 'reason2',
        common.CommandErrorType.TEST)

  def assertErrorConfigInDatastore(self, error_message, reason, type_code):
    query = datastore_entities.CommandErrorConfigMapping.query(
        (datastore_entities.CommandErrorConfigMapping.error_message ==
         error_message))
    config = query.get()
    self.assertEqual(error_message, config.error_message)
    self.assertEqual(reason, config.reason)
    self.assertEqual(type_code, config.type_code)


if __name__ == '__main__':
  unittest.main()
