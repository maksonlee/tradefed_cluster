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

"""API module to serve dimension calls."""

import endpoints
from protorpc import message_types
from protorpc import messages
from protorpc import remote


from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities


@api_common.tradefed_cluster_api.api_class(resource_name="filterHints",
                                           path="filterHints")
class FilterHintApi(remote.Service):
  """A class for filter hint API service."""

  FILTER_HINT_LIST_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      type=messages.EnumField(common.FilterHintType, 1))

  @endpoints.method(
      FILTER_HINT_LIST_RESOURCE,
      api_messages.FilterHintCollection,
      path="/filterHints",
      http_method="GET",
      name="list")
  def ListFilterHints(self, request):
    """Fetches a list of filter hint by type.

    Args:
      request: an API request.
    Returns:
      a FilterHintCollection object.
    """

    if request.type == common.FilterHintType.POOL:
      return self._ListPools()
    else:
      raise endpoints.BadRequestException("Invalid type: %s" % request.type)

  def _ListPools(self):
    """Fetches a list of pools."""
    entities = datastore_entities.ClusterInfo.query().fetch(keys_only=True)
    infos = [
        api_messages.FilterHintMessage(value=item.id()) for item in entities
    ]
    return api_messages.FilterHintCollection(filter_hints=infos)

