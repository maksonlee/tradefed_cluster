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

"""API module to serve lab calls."""

import endpoints
from protorpc import message_types
from protorpc import messages
from protorpc import remote

from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_util


_DEFAULT_COUNT = 1000


@api_common.tradefed_cluster_api.api_class(resource_name="labs", path="labs")
class LabManagementApi(remote.Service):
  """A class for lab API service."""

  LAB_LIST_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      owner=messages.StringField(1),
      cursor=messages.StringField(2),
      count=messages.IntegerField(3,
                                  variant=messages.Variant.INT32,
                                  default=_DEFAULT_COUNT))

  @endpoints.method(LAB_LIST_RESOURCE, api_messages.LabInfoCollection,
                    path="/labs", http_method="GET", name="list")
  @api_common.with_ndb_context
  def ListLabs(self, request):
    """Fetches a list of labs that are available.

    Args:
      request: API request that includes lab related filters.
    Returns:
      a LabInfoCollection object.
    """
    query = datastore_entities.LabInfo.query()
    query = query.order(datastore_entities.LabInfo.key)
    if request.owner:
      query = query.filter(
          datastore_entities.LabInfo.owners == request.owner)

    labs, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, request.count, page_cursor=request.cursor)

    return api_messages.LabInfoCollection(
        lab_infos=[datastore_entities.ToMessage(lab) for lab in labs],
        more=bool(next_cursor),
        next_cursor=next_cursor,
        prev_cursor=prev_cursor)
