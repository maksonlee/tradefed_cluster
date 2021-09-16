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
import logging

import endpoints
from endpoints import api_request
from endpoints import endpoints_dispatcher
from tradefed_cluster import datastore_entities
from tradefed_cluster import device_manager
from tradefed_cluster import env_config


_AUTHENTICATE_HEADER = 'AUTHENTICATED-USER'
_DEVICE_KEY = 'device_serial'
_HOST_KEY = 'hostname'


class Permission(enum.Enum):
  owner = 'owner'
  reader = 'reader'


def _GetPlugin():
  if not env_config.CONFIG.acl_plugin:
    logging.info('No acl plugin installed.')
  return env_config.CONFIG.acl_plugin


def CheckMembership(user, group):
  """Checks if user is the group member or not.

  Args:
    user: the user name.
    group: the group name.
  Returns:
    a boolean value to indicate the user membership.
  """
  plugin = _GetPlugin()
  if plugin:
    return _GetPlugin().CheckMembership(user, group)


def CheckPermission(object_id, permission, user_name):
  """Checks user permission.

  Args:
    object_id: the target object id.
    permission: the Permission value.
    user_name: the user name.
  """
  plugin = _GetPlugin()
  if plugin:
    plugin.CheckPermission(object_id, permission, user_name)


def CheckResourcePermission(
    user_name, permission, device_serial=None, hostname=None):
  """The wrapper method to check device/host access permission.

  Args:
    user_name: the user name
    permission: the access permission type
    device_serial: the device serial if provided check device access permission
    hostname: the hostname if provided check host access permission
  """
  if device_serial:
    _CheckDevicePermission(device_serial, permission, user_name)
  if hostname:
    _CheckHostPermission(hostname, permission, user_name)


def _CheckDevicePermission(obj_id, permission, user_name):
  """Checks device access permission.

  The device access permission is associated with HostConfig.

  Args:
    obj_id: the DeviceInfo id string
    permission: the access permission type
    user_name: the user name
  Raises:
    ResourceNotFoundError: if the DeviceInfo doesn't exist
  """
  device = device_manager.GetDevice(device_serial=obj_id)
  if not device:
    raise endpoints.NotFoundException(f'Device({obj_id}) not found')
  # skip checking if the device lost hostname information.
  if not device.hostname:
    return
  _CheckHostPermission(device.hostname, permission, user_name)


def _CheckHostPermission(obj_id, permission, user_name):
  """Checks host access permission.

  The host access permission is associated with HostGroupConfig. If the users
  have permissions to access any HostGroupConfig in inventory_groups then they
  have permissions to access the host.

  Args:
    obj_id: the HostConfig id string
    permission: the access permission type
    user_name: the user name
  Raises:
    ResourceNotFoundError: if the HostConfig doesn't exist
    ForbiddenError: if the user has no permissions
  Returns:
    Nothing
  """
  host_config = datastore_entities.HostConfig.get_by_id(obj_id)
  if not host_config:
    raise endpoints.NotFoundException(f'HostConfig({obj_id}) not found')
  # skip checking if the host doesn't belong to any lab.
  if not host_config.lab_name:
    logging.warning('Failed to get lab_name from HostConfig(%s)',
                    host_config.hostname)
    return
  # Checks if the user has permissions to access the inventory_groups.
  # A host might belong to multiple groups and these groups might belong to
  # different DAC graphs, thus, it requires to check all the groups. However,
  # the method could return earlier if the leaf groups could be checked earlier.
  for group in host_config.inventory_groups:
    try:
      return CheckPermission(
          datastore_entities.HostGroupConfig.CreateId(
              host_config.lab_name, group),
          permission,
          user_name)
    except endpoints.ForbiddenException:
      pass
  # checks if the user is a lab owner.
  lab_config = datastore_entities.LabConfig.get_by_id(host_config.lab_name)
  if lab_config.owners:
    for user_group in lab_config.owners:
      if CheckMembership(user_name, user_group):
        return
  raise endpoints.ForbiddenException(
      f'Failed to authorize {user_name} for accessing {obj_id} resources' +
      f' with {permission.value} permission')


class PermissionMiddleware:
  """The wsgi middleware for checking resource access permission."""

  def __init__(self, app: endpoints_dispatcher.EndpointsDispatcherMiddleware):
    self._app = app

  def __call__(self, environ, start_response):
    # skip acl checking if no acl plugin installed.
    if not _GetPlugin():
      logging.info('No acl plugin installed, skip permission check.')
      return self._app(environ, start_response)
    original = api_request.ApiRequest(
        environ, base_paths=self._backend.base_paths)
    method_config, params = self.lookup_rest_method(original)
    if not method_config:
      return self._HandleAclError(
          endpoints.NotFoundException('Not Found'), original, start_response)
    request = self.transform_request(original, params, method_config)
    authentication = request.headers.get(_AUTHENTICATE_HEADER)
    if authentication:
      device_serial = request.body_json.get(_DEVICE_KEY)
      hostname = request.body_json.get(_HOST_KEY)
      try:
        CheckResourcePermission(
            authentication, Permission.reader if request.http_method == 'GET'
            else Permission.owner, device_serial, hostname)
      except endpoints.ServiceException as err:
        return self._HandleAclError(err, original, start_response)
    return self._app(environ, start_response)

  def _HandleAclError(self, err, orig_request, start_response):
    cors_handler = self._create_cors_handler(orig_request)
    headers = [('Content-Type', 'text/plain'), ('Content-Length', '0')]
    if cors_handler:
      cors_handler.update_headers(headers)
    start_response(f'{err.http_status} {str(err)}', headers)
    return []

  def __getattr__(self, name):
    return getattr(self._app, name)
