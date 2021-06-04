# Copyright 2021 Google LLC
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
"""NDB utility classes."""

from tradefed_cluster.util import ndb_shim as ndb


class UpgradeError(Exception):
  """Raised when something goes wrong when upgrading NDB objects."""
  pass


class UpgradableModel(ndb.Model):
  """Represents a NDB model whose schema can change."""

  schema_version = ndb.IntegerProperty()

  @property
  def _upgrade_steps(self):
    """A list of functions that actually perform the upgrades.

    Classes which extend UpgradableModel should override this.
    """
    raise NotImplementedError(
        'Upgradable models must specify _upgrade_steps')

  def _pre_put_hook(self):
    if self.schema_version is None:
      self.schema_version = len(self._upgrade_steps)

  @classmethod
  def _post_get_hook(cls, key, future):
    result = future.get_result()
    if result:
      result.Upgrade()

  def Upgrade(self):
    """Updates the object to the latest version if necessary.

    Raises:
      UpgradeError: If an upgrade step raises an exception.
      ValueError: If the object has a newer version than we know about.
    """
    if self.schema_version is None:
      self.schema_version = 0
    if self.schema_version > len(self._upgrade_steps):
      raise ValueError(
          'The schema version of the object is newer than the model.')
    if self.schema_version == len(self._upgrade_steps):
      return
    for step in self._upgrade_steps[self.schema_version:]:
      try:
        step(self)
      except Exception as e:
        raise UpgradeError(
            'Something went wrong while performing {} on {}: {}'.format(
                step.__name__,
                self.key.urlsafe().decode(), e))
      self.schema_version += 1
    self.put()
