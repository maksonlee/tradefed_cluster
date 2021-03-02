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

"""A module for command error type map config."""

from tradefed_cluster import common
from tradefed_cluster import datastore_entities


class ErrorReason(object):
  """Error reason constants."""
  ASSERTION_FAILED_ERROR = 'AssertionFailedError'
  BUILD_NOT_FOUND = 'BuildNotFound'
  BUILD_RETRIEVAL_ERROR = 'BuildRetrievalError'
  CONFIGURATION_ERROR = 'ConfigurationError'
  DEVICE_DISCONNECTED_ERROR = 'DeviceDisconnectedError'
  DEVICE_NOT_AVAILABLE_ERROR = 'DeviceNotAvailableError'
  DEVICE_UNRESPONSIVE_ERROR = 'DeviceUnresponsiveError'
  ILLEGAL_ARGUMENT_ERROR = 'IllegalArgumentError'
  NULL_POINTER_ERROR = 'NullPointerError'
  QUEUE_TIMEOUT = 'QueueTimeout'
  RUNTIME_ERROR = 'RuntimeError'
  TARGET_SETUP_ERROR = 'TargetSetupError'
  UNKNOWN_ERROR_REASON = 'UnknownErrorReason'


# Default error message to error reason and type dictionary.
TYPE_DICT = {
    'A task reset by command attempt monitor.':
        (ErrorReason.QUEUE_TIMEOUT, common.CommandErrorType.INFRA),
    'build not found':
        (ErrorReason.BUILD_NOT_FOUND, common.CommandErrorType.INFRA),
    'com.android.tradefed.build.BuildRetrievalError':
        (ErrorReason.BUILD_RETRIEVAL_ERROR, common.CommandErrorType.INFRA),
    'com.android.tradefed.config.ConfigurationException':
        (ErrorReason.CONFIGURATION_ERROR, common.CommandErrorType.TEST),
    'com.android.tradefed.device.DeviceDisconnectedException':
        (ErrorReason.DEVICE_DISCONNECTED_ERROR, common.CommandErrorType.TEST),
    'com.android.tradefed.device.DeviceNotAvailableException':
        (ErrorReason.DEVICE_NOT_AVAILABLE_ERROR, common.CommandErrorType.INFRA),
    'com.android.tradefed.device.DeviceUnresponsiveException':
        (ErrorReason.DEVICE_UNRESPONSIVE_ERROR, common.CommandErrorType.INFRA),
    'com.android.tradefed.targetprep.TargetSetupError':
        (ErrorReason.TARGET_SETUP_ERROR, common.CommandErrorType.TEST),
    'java.lang.RuntimeException':
        (ErrorReason.RUNTIME_ERROR, common.CommandErrorType.TEST),
    'java.lang.IllegalArgumentException':
        (ErrorReason.ILLEGAL_ARGUMENT_ERROR, common.CommandErrorType.TEST),
    'java.lang.NullPointerException':
        (ErrorReason.NULL_POINTER_ERROR, common.CommandErrorType.INFRA),
    'junit.framework.AssertionFailedError':
        (ErrorReason.ASSERTION_FAILED_ERROR, common.CommandErrorType.TEST),
}


def GetConfig(error):
  """Get error reason and type tuple from error map.

  If config is already in datastore, return tuple directly, if config is
  not in datastore but in predefined default dict, insert dict value to
  datastore and return.

  Args:
    error: error message
  Returns:
    (reason, type_code) tuple
  """
  if error:
    separator_index = min([len(error)] + [
        error.find(separator)
        for separator in ('[', ':')
        if error.find(separator) != -1
    ])
    error = error[:separator_index]

  query = datastore_entities.CommandErrorConfigMapping.query(
      datastore_entities.CommandErrorConfigMapping.error_message == error)
  config = query.get()

  # Insert error config maps into datastore to auto-populate new error messages.
  if not config:
    reason, type_code = TYPE_DICT.get(error, (
        ErrorReason.UNKNOWN_ERROR_REASON, common.CommandErrorType.UNKNOWN))
    config = datastore_entities.CommandErrorConfigMapping(
        error_message=error, reason=reason, type_code=type_code)
    config.put()

  return config.reason, config.type_code
