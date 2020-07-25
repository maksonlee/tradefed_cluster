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
"""TFC Adaptation for the Cloud Datastore emulator."""
import os
import tempfile

from googledatastore.v1 import datastore_emulator


MISSING_ENVIRONMENT_VARIABLES_MESSAGE = (
    'Please make your your environment variables are correctly set.'
    'https://cloud.google.com/datastore/docs/tools/datastore-emulator')


class DatastoreEmulatorFactory(datastore_emulator.DatastoreEmulatorFactory):
  """Datastore Emulator Factory that fetches ENV variables."""

  def __init__(self):
    """Create a new factory."""
    if not os.getenv('JAVA_HOME'):
      raise RuntimeError(
          'JAVA_HOME environment variable has not being set.',
          MISSING_ENVIRONMENT_VARIABLES_MESSAGE)
    if not os.getenv('DATASTORE_EMULATOR_ZIP_PATH'):
      raise RuntimeError(
          'DATASTORE_EMULATOR_ZIP_PATH variable has not being set.',
          MISSING_ENVIRONMENT_VARIABLES_MESSAGE)

    working_directory = (
        os.getenv('TEST_TMPDIR') if os.environ.get('TEST_TMPDIR')
        else tempfile.mkdtemp())

    # Disable bad lint cause the class name is the same as the parent class
        super(DatastoreEmulatorFactory, self).__init__(
        working_directory,
        os.getenv('DATASTORE_EMULATOR_ZIP_PATH'),
        os.getenv('JAVA_HOME'))

