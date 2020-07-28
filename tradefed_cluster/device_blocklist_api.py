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

"""API module to block devices from running tests."""

import endpoints
from protorpc import message_types
from protorpc import messages
from protorpc import remote

from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_util

_DEFAULT_COUNT = 100


@api_common.tradefed_cluster_api.api_class(
    resource_name="deviceBlocklists", path="deviceBlocklists")
class DeviceBlocklistApi(remote.Service):
  """A class for device blocklist API service."""

  NEW_DEVICE_BLOCKLIST_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      lab_name=messages.StringField(1),
      note=messages.StringField(2),
      user=messages.StringField(3),)

  @endpoints.method(
      NEW_DEVICE_BLOCKLIST_RESOURCE,
      api_messages.DeviceBlocklistMessage,
      path="/deviceBlocklists", http_method="POST", name="new")
  @api_common.with_ndb_context
  def NewDeviceBlocklist(self, request):
    """Create a new device blocklist.

    Args:
      request: API request that includes device blocklist information.
    Returns:
      a DeviceBlocklistMessage object.
    """
    blocklist = datastore_entities.DeviceBlocklist(
        lab_name=request.lab_name,
        note=request.note,
        user=request.user)
    blocklist.put()
    return datastore_entities.ToMessage(blocklist)

  GET_DEVICE_BLOCKLIST_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      key_id=messages.IntegerField(1, required=True),
  )

  @endpoints.method(
      GET_DEVICE_BLOCKLIST_RESOURCE,
      api_messages.DeviceBlocklistMessage,
      path="{key_id}", http_method="GET", name="get")
  @api_common.with_ndb_context
  def GetDeviceBlocklist(self, request):
    """Get a device blocklist.

    Args:
      request: API request with key id.
    Returns:
      a DeviceBlocklistMessage object.
    """
    blocklist = datastore_entities.DeviceBlocklist.get_by_id(request.key_id)
    return datastore_entities.ToMessage(blocklist)

  LIST_DEVICE_BLOCKLIST_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      count=messages.IntegerField(1, default=_DEFAULT_COUNT),
      cursor=messages.StringField(2),
      backwards=messages.BooleanField(3, default=False),
  )

  @endpoints.method(
      LIST_DEVICE_BLOCKLIST_RESOURCE,
      api_messages.DeviceBlocklistCollection,
      path="/deviceBlocklists", http_method="GET", name="list")
  @api_common.with_ndb_context
  def ListDeviceBlocklist(self, request):
    """List device blocklists.

    Args:
      request: API request with key id.
    Returns:
      a list of DeviceBlocklistMessage objects.
    """
    query = (
        datastore_entities.DeviceBlocklist.query()
        .order(-datastore_entities.DeviceBlocklist.create_timestamp))

    device_blocklists, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, request.count, request.cursor, backwards=request.backwards)

    msgs = [
        datastore_entities.ToMessage(blocklist)
        for blocklist in device_blocklists
    ]
    return api_messages.DeviceBlocklistCollection(
        device_blocklists=msgs,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor)
