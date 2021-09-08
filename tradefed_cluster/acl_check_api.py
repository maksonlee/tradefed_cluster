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
"""API module to serve ACL calls."""

import logging

import endpoints
from protorpc import messages
from protorpc import remote
from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import datastore_entities
from tradefed_cluster.services import acl_service
from tradefed_cluster.util import ndb_shim as ndb


_JUMP_GROUP_NAME = "jump"
_JUMP_HOST_ACCOUNT = "android-test"
_PRINCIPALS_KEY = "principals"


@api_common.tradefed_cluster_api.api_class(resource_name="acl", path="acl")
class AclApi(remote.Service):
  """The APIs for checking ACL."""

  CHECK_HOST_PRINCIPALS = endpoints.ResourceContainer(
      hostname=messages.StringField(1, required=True),
      host_account=messages.StringField(2, required=True),
      user_name=messages.StringField(3, required=True),
  )

  @endpoints.method(
      CHECK_HOST_PRINCIPALS,
      api_messages.AclCheckResult,
      path="ssh_access/check",
      http_method="GET",
      name="checkSshAccessible")
  @api_common.with_ndb_context
  def CheckSshAccessible(self, request):
    """Authenticates host account principals."""
    host_config = datastore_entities.HostConfig.get_by_id(request.hostname)
    if not host_config:
      logging.debug("no host config found for hostname: %s", request.hostname)
      raise endpoints.NotFoundException(
          f"{request.hostname} host config not found")
    try:
      if (request.host_account == _JUMP_HOST_ACCOUNT and
          _JUMP_GROUP_NAME in host_config.inventory_groups):
        return self._CheckAccessibilityForJump(request.user_name, host_config)
      return self._CheckAccessibilityForHost(request.user_name, host_config,
                                             request.host_account)
    except acl_service.UserNotFoundError as e:
      raise endpoints.NotFoundException(str(e))

  def _CheckAccessibilityForJump(self, user_name, host_config):
    """Checks if the user can pass through ssh jump hosts.

    If the user has access to any host in the lab, then they should be able
    to access "android-test" in jump hosts.

    Args:
      user_name: the user name.
      host_config: the HostConfig entity for the jump host that user requested
        to access.

    Returns:
      the AclCheckResult api message.
    """
    groups = datastore_entities.HostGroupConfig.query(
        datastore_entities.HostGroupConfig.lab_name ==
        host_config.lab_name).fetch()
    for group in groups:
      if self._CheckAccessibilityForHostGroup(user_name, group):
        return api_messages.AclCheckResult(has_access=True)
    return api_messages.AclCheckResult(has_access=False)

  def _CheckAccessibilityForHost(self, user_name, host_config, host_account):
    """Checks if the user can access the given host account on the given host.

    Args:
      user_name: the user name.
      host_config: the HostConfig entity for the host that user requested to
        access.
      host_account: the host account that the user want to login.

    Returns:
      the AclCheckResult api message.
    """
    # every host belong to the "all" group in ansible, thus we should also
    # check accessibility for the "all" group.
    # https://docs.ansible.com/ansible/latest/user_guide/intro_inventory.html#default-groups
    keys = []
    for group_name in ["all"] + host_config.inventory_groups:
      keys.append(
          ndb.Key(
              datastore_entities.HostGroupConfig,
              datastore_entities.HostGroupConfig.CreateId(
                  host_config.lab_name, group_name)))
    groups = ndb.get_multi(keys)
    for group in groups:
      if not group:
        continue
      if self._CheckAccessibilityForHostAccountInHostGroup(
          user_name, host_account, group):
        return api_messages.AclCheckResult(has_access=True)
    return api_messages.AclCheckResult(has_access=False)

  def _CheckAccessibilityForHostAccountInHostGroup(self, user_name,
                                                   host_account, host_group):
    """Checks if the user can access the given host account in the host_group.

    Args:
      user_name: the user name.
      host_account: the host account that the user want to login.
      host_group: the HostGroupConfig entity.

    Returns:
      a boolean indicates whether the user can access the host account or not.
    """
    if not host_group.account_principals:
      return False
    for principal in host_group.account_principals.get(host_account, {}).get(
        _PRINCIPALS_KEY, []):
      if acl_service.CheckMembership(user_name, principal):
        return True
    return False

  def _CheckAccessibilityForHostGroup(self, user_name, host_group):
    """Checks if the user can access the given host_group.

    Args:
      user_name: the user name.
      host_group: the HostGroupConfig entity.

    Returns:
      a boolean indicates whether the user can access the host group or not.
    """
    if (not host_group.account_principals or
        not host_group.account_principals.values()):
      return False
    for account_info in host_group.account_principals.values():
      for principal in account_info.get(_PRINCIPALS_KEY, []):
        if acl_service.CheckMembership(user_name, principal):
          return True
    return False
