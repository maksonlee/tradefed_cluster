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
from tradefed_cluster import device_manager


@api_common.tradefed_cluster_api.api_class(
    resource_name="filterHints", path="filterHints")
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
  @api_common.with_ndb_context
  def ListFilterHints(self, request):
    """Fetches a list of filter hint by type.

    Args:
      request: an API request.
    Returns:
      a FilterHintCollection object.
    """

    if request.type == common.FilterHintType.POOL:
      return self._ListPools()
    elif request.type == common.FilterHintType.LAB:
      return self._ListLabs()
    elif request.type == common.FilterHintType.RUN_TARGET:
      return self._ListRunTargets()
    elif request.type == common.FilterHintType.HOST:
      return self._ListHosts()
    elif request.type == common.FilterHintType.TEST_HARNESS:
      return self._ListTestHarness()
    elif request.type == common.FilterHintType.TEST_HARNESS_VERSION:
      return self._ListTestHarnessVersion()
    elif request.type == common.FilterHintType.HOST_STATE:
      return self._ListHostStates()
    elif request.type == common.FilterHintType.DEVICE_STATE:
      return self._ListDeviceStates()
    elif request.type == common.FilterHintType.HOST_GROUP:
      return self._ListHostGroup()
    elif request.type == common.FilterHintType.UPDATE_STATE:
      return self._ListHostUpdateStates()
    else:
      raise endpoints.BadRequestException("Invalid type: %s" % request.type)

  def _ListPools(self):
    """Fetches a list of pool."""
    entities = datastore_entities.HostInfo.query(
        projection=[datastore_entities.HostInfo.pools], distinct=True).filter(
            datastore_entities.HostInfo.hidden == False).fetch(                  projection=[datastore_entities.HostInfo.pools])
    mergedlist = []
    for item in entities:
      mergedlist += item.pools
    mergedlist = list(set(mergedlist))
    mergedlist.sort()
    infos = [
        api_messages.FilterHintMessage(value=item) for item in mergedlist
    ]
    return api_messages.FilterHintCollection(filter_hints=infos)

  def _ListLabs(self):
    """Fetches a list of labs."""
    entities = datastore_entities.LabInfo.query().fetch(keys_only=True)
    infos = [
        api_messages.FilterHintMessage(value=str(item.id()))
        for item in entities
    ]
    return api_messages.FilterHintCollection(filter_hints=infos)

  def _ListRunTargets(self):
    """Fetches a list of run targets."""
    entities = device_manager.GetRunTargetsFromNDB()
    infos = [api_messages.FilterHintMessage(value=item) for item in entities]
    return api_messages.FilterHintCollection(filter_hints=infos)

  def _ListHosts(self):
    """Fetches a list of hostnames."""
    entities = datastore_entities.HostInfo.query().filter(
        datastore_entities.HostInfo.hidden == False).fetch(keys_only=True)      infos = [
        api_messages.FilterHintMessage(value=str(item.id()))
        for item in entities
    ]
    return api_messages.FilterHintCollection(filter_hints=infos)

  def _ListTestHarness(self):
    """Fetches a list of test harness."""
    entities = datastore_entities.HostInfo.query(
        projection=[datastore_entities.HostInfo.test_harness],
        distinct=True).filter(
            datastore_entities.HostInfo.hidden == False).fetch(                  projection=[datastore_entities.HostInfo.test_harness])
    infos = [
        api_messages.FilterHintMessage(value=item.test_harness)
        for item in entities
    ]
    return api_messages.FilterHintCollection(filter_hints=infos)

  def _ListTestHarnessVersion(self):
    """Fetches a list of test harness version."""
    entities = datastore_entities.HostInfo.query(
        projection=[datastore_entities.HostInfo.test_harness_version],
        distinct=True).filter(
            datastore_entities.HostInfo.hidden == False).fetch(                  projection=[datastore_entities.HostInfo.test_harness_version])
    infos = [
        api_messages.FilterHintMessage(value=item.test_harness_version)
        for item in entities
    ]
    return api_messages.FilterHintCollection(filter_hints=infos)

  def _ListHostStates(self):
    """Fetches a list of host state."""
    infos = [
        api_messages.FilterHintMessage(value=state.name)
        for state in api_messages.HostState
    ]
    return api_messages.FilterHintCollection(filter_hints=infos)

  def _ListDeviceStates(self):
    """Fetches a list of device state."""
    entities = list(common.DEVICE_ALL_STATES)
    infos = [api_messages.FilterHintMessage(value=state) for state in entities]
    return api_messages.FilterHintCollection(filter_hints=infos)

  def _ListHostGroup(self):
    """Fetches a list of host group."""
    entities = datastore_entities.HostInfo.query(
        projection=[datastore_entities.HostInfo.host_group],
        distinct=True).filter(
            datastore_entities.HostInfo.hidden == False).fetch(                  projection=[datastore_entities.HostInfo.host_group])
    infos = [
        api_messages.FilterHintMessage(value=item.host_group)
        for item in entities
    ]
    return api_messages.FilterHintCollection(filter_hints=infos)

  def _ListHostUpdateStates(self):
    """Fetches a list of host update states."""
    infos = [
        api_messages.FilterHintMessage(value=state.name)
        for state in api_messages.HostUpdateState
    ]
    return api_messages.FilterHintCollection(filter_hints=infos)
