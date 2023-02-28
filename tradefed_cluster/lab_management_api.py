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
from tradefed_cluster.util import ndb_shim as ndb


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

  @api_common.method(LAB_LIST_RESOURCE, api_messages.LabInfoCollection,
                     path="/labs", http_method="GET", name="list")
  def ListLabs(self, request):
    """Fetches a list of labs that are available.

    Args:
      request: API request that includes lab related filters.
    Returns:
      a LabInfoCollection object.
    """
    if request.owner:
      return self._ListLabsByOwner(request)
    return self._ListLabs(request)

  def _ListLabsByOwner(self, request):
    """Lab owners are in LabConfig, so need to query by LabConfig."""
    query = datastore_entities.LabConfig.query()
    query = query.order(datastore_entities.LabConfig.key)
    query = query.filter(
        datastore_entities.LabConfig.owners == request.owner)
    lab_configs, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, request.count, page_cursor=request.cursor)
    lab_info_msgs = []
    for lab_config in lab_configs:
      lab_info_msgs.append(
          api_messages.LabInfo(
              lab_name=lab_config.lab_name,
              owners=(lab_config.owners or [])))

    return api_messages.LabInfoCollection(
        lab_infos=lab_info_msgs,
        more=bool(next_cursor),
        next_cursor=next_cursor,
        prev_cursor=prev_cursor)

  def _ListLabs(self, request):
    """ListLabs without owner filter. Some labs don't have config."""
    query = datastore_entities.LabInfo.query()
    query = query.order(datastore_entities.LabInfo.key)
    labs, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, request.count, page_cursor=request.cursor)
    lab_config_keys = [
        ndb.Key(datastore_entities.LabConfig, lab.lab_name) for lab in labs]
    lab_configs = ndb.get_multi(lab_config_keys)
    lab_infos = [datastore_entities.ToMessage(lab, lab_config)
                 for lab, lab_config in zip(labs, lab_configs)]
    return api_messages.LabInfoCollection(
        lab_infos=lab_infos,
        more=bool(next_cursor),
        next_cursor=next_cursor,
        prev_cursor=prev_cursor)

  LAB_GET_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      lab_name=messages.StringField(1, required=True),
  )

  @api_common.method(
      LAB_GET_RESOURCE,
      api_messages.LabInfo,
      path="{lab_name}",
      http_method="GET", name="get")
  def GetLab(self, request):
    lab_info = datastore_entities.LabInfo.get_by_id(request.lab_name)
    lab_config = datastore_entities.LabConfig.get_by_id(request.lab_name)
    return datastore_entities.ToMessage(lab_info, lab_config)
