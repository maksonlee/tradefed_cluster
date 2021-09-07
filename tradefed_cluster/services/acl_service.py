# Lint as: python2, python3
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
"""A host account validator service."""
import enum
from tradefed_cluster import env_config


class UserNotFoundError(Exception):
  """The error indicating the user doesn't exist."""


class AuthenticationError(Exception):
  """Raises when failed to find user authentication."""


class ForbiddenError(Exception):
  """Raised when user has no permission to access resources."""


class Permission(enum.Enum):
  owner = 'owner'
  reader = 'reader'


def _GetPlugin():
  if not env_config.CONFIG.acl_plugin:
    raise ValueError('No acl_plugin is configured')
  return env_config.CONFIG.acl_plugin


def CheckMembership(user, group):
  """Checks if user is the group member or not.

  Args:
    user: the user name.
    group: the group name.
  Returns:
    a boolean value to indicate the user membership.
  """
  return _GetPlugin().CheckMembership(user, group)
