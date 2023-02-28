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

"""API module to serve cluster service calls."""
import endpoints
from protorpc import message_types
from protorpc import messages
from protorpc import remote


from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import datastore_entities
from tradefed_cluster import device_manager


class ClusterInfoCollection(messages.Message):
  """A class representing a collection of cluster infos."""
  cluster_infos = messages.MessageField(
      api_messages.ClusterInfo, 1, repeated=True)


@api_common.tradefed_cluster_api.api_class(
    resource_name="clusters", path="clusters")
class ClusterApi(remote.Service):
  """A class for cluster API service."""

  CLUSTER_LIST_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      include_hosts=messages.BooleanField(1, default=False))

  @api_common.method(CLUSTER_LIST_RESOURCE, ClusterInfoCollection,
                     path="/clusters", http_method="GET", name="list")
  def ListClusters(self, request):
    """Fetches a list of clusters that are available.

    Args:
      request: an API request.
    Returns:
      a ClusterInfoCollection object.
    """
    cluster_infos = []
    clusters = datastore_entities.ClusterInfo.query().fetch()
    for cluster in clusters:
      host_msgs = []
      # TODO: deprecate option include_hosts.
      if request.include_hosts:
        host_msgs = self._GetHostsForCluster(cluster.cluster)
      cluster_infos.append(self._BuildClusterInfo(cluster, host_msgs))
    return ClusterInfoCollection(cluster_infos=cluster_infos)

  CLUSTER_GET_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      cluster_id=messages.StringField(1, variant=messages.Variant.STRING,
                                      required=True),
      include_hosts=messages.BooleanField(2, default=False),
      include_notes=messages.BooleanField(3, default=False),
  )

  @api_common.method(
      CLUSTER_GET_RESOURCE,
      api_messages.ClusterInfo,
      path="{cluster_id}",
      http_method="GET", name="get")
  def GetCluster(self, request):
    """Fetches the information/status for a given cluster id.

    Args:
      request: an API request.
    Returns:
      a ClusterInfo message.
    Raises:
      endpoints.BadRequestException: If the given cluster ID is invalid.
    """
    cluster_id = request.cluster_id
    cluster = device_manager.GetCluster(cluster_id)
    if not cluster:
      raise endpoints.NotFoundException(
          "Cluster [%s] does not exist." % cluster_id)
    host_msgs = []
    if request.include_hosts:
      host_msgs = self._GetHostsForCluster(cluster_id)
    cluster_info = self._BuildClusterInfo(cluster, host_msgs)

    if request.include_notes:
      cluster_notes = datastore_entities.ClusterNote.query()
      cluster_notes = cluster_notes.filter(
          datastore_entities.ClusterNote.cluster == cluster_id)
      notes = [datastore_entities.ToMessage(n.note)
               for n in cluster_notes.iter()]
      cluster_info.notes = sorted(
          notes, key=lambda x: x.timestamp, reverse=True)
    return cluster_info

  def _GetHostsForCluster(self, cluster_id):
    """Get hosts and their devices for a cluster.

    Args:
      cluster_id: cluster id
    Returns:
      a list of HostInfoMessages include devices.
    """
    hosts = (datastore_entities.HostInfo.query()
             .filter(datastore_entities.HostInfo.clusters == cluster_id)
             .filter(datastore_entities.HostInfo.hidden == False)  
             .fetch())
    host_msgs = []
    for host in hosts:
      devices = (datastore_entities.DeviceInfo.query(ancestor=host.key)
                 .filter(datastore_entities.DeviceInfo.hidden == False)  
                 .fetch())
      host_msgs.append(datastore_entities.ToMessage(host, devices))
    return host_msgs

  CLUSTER_NOTE_RESOURCE = endpoints.ResourceContainer(
      cluster_id=messages.StringField(1, required=True),
      user=messages.StringField(2, required=True),
      message=messages.StringField(3),
      offline_reason=messages.StringField(4),
      recovery_action=messages.StringField(5),
      offline_reason_id=messages.IntegerField(6),
      recovery_action_id=messages.IntegerField(7),
      lab_name=messages.StringField(8),
      timestamp=message_types.DateTimeField(9, required=True),
  )

  @api_common.method(CLUSTER_NOTE_RESOURCE, api_messages.Note,
                     path="{cluster_id}/note", http_method="POST",
                     name="newNote")
  def NewNote(self, request):
    """Submits a note for this host.

    Args:
      request: an API request.
    Returns:
      a VoidMessage
    """
    cluster = request.cluster_id
    timestamp = request.timestamp
    # Datastore only accepts UTC times. Doing a conversion if necessary.
    if timestamp.utcoffset() is not None:
      timestamp = timestamp.replace(tzinfo=None) - timestamp.utcoffset()
    note = datastore_entities.Note(user=request.user, timestamp=timestamp,
                                   message=request.message)
    cluster_note = datastore_entities.ClusterNote(cluster=cluster)
    cluster_note.note = note
    cluster_note.put()
    return datastore_entities.ToMessage(note)

  def _BuildClusterInfo(self, cluster, host_infos):
    """Helper to build a ClusterInfo object from host messages.

    Args:
      cluster: a cluster entity
      host_infos: a list of HostInfo messages.
    Returns:
      a ClusterInfo object.
    """
    run_targets = set()
    for host in host_infos:
      run_targets.update([d.run_target
                          for d in host.device_infos if d.run_target])
    run_target_messages = [api_messages.RunTarget(name=r) for r in run_targets]
    return api_messages.ClusterInfo(
        cluster_id=cluster.cluster,
        total_devices=cluster.total_devices,
        offline_devices=cluster.offline_devices,
        available_devices=cluster.available_devices,
        allocated_devices=cluster.allocated_devices,
        device_count_timestamp=cluster.device_count_timestamp,
        host_infos=host_infos,
        run_targets=run_target_messages,
        host_update_state_summary=datastore_entities.ToMessage(
            cluster.host_update_state_summary),
        host_count_by_harness_version=api_messages.MapToKeyValuePairMessages(
            cluster.host_count_by_harness_version),
        host_update_state_summaries_by_version=[
            datastore_entities.ToMessage(summary) for summary
            in cluster.host_update_state_summaries_by_version
        ])
