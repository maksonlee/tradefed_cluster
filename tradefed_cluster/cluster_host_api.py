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

"""API module to serve cluster host service calls."""

import datetime

from protorpc import message_types
from protorpc import messages
from protorpc import remote

from google.appengine.ext import ndb
from google3.third_party.apphosting.python.endpoints.v1_1 import endpoints

from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_util
from tradefed_cluster import device_manager


_DEFAULT_LIST_NOTES_COUNT = 10
_DEFAULT_LIST_HOST_COUNT = 100


@api_common.tradefed_cluster_api.api_class(resource_name="hosts",
                                           path="hosts")
class ClusterHostApi(remote.Service):
  """A class for cluster host API service."""

  HOST_LIST_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      lab_name=messages.StringField(1),
      include_hidden=messages.BooleanField(2, default=False),
      include_devices=messages.BooleanField(3, default=False),
      assignee=messages.StringField(4),
      is_bad=messages.BooleanField(5),
      host_groups=messages.StringField(6, repeated=True),
      cursor=messages.StringField(7),
      count=messages.IntegerField(8, variant=messages.Variant.INT32,
                                  default=_DEFAULT_LIST_HOST_COUNT)
  )

  @endpoints.method(
      HOST_LIST_RESOURCE,
      api_messages.HostInfoCollection,
      path="/hosts",
      http_method="GET",
      name="list"
  )
  def ListHosts(self, request):
    """Fetches a list of hosts.

    Args:
      request: an API request.
    Returns:
      a HostInfoCollection object.
    """
    query = datastore_entities.HostInfo.query()
    if request.lab_name:
      query = query.filter(
          datastore_entities.HostInfo.lab_name == request.lab_name)

    if request.assignee:
      query = query.filter(
          datastore_entities.HostInfo.assignee == request.assignee)

    if request.is_bad is not None:
      query = query.filter(datastore_entities.HostInfo.is_bad == request.is_bad)

    if not request.include_hidden:
      query = query.filter(datastore_entities.HostInfo.hidden == False)  
    if request.host_groups:
      query = query.filter(datastore_entities.HostInfo.host_group.IN(
          request.host_groups))

    hosts, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, request.count, page_cursor=request.cursor)

    host_infos = []
    for host in hosts:
      devices = []
      if request.include_devices:
        device_query = datastore_entities.DeviceInfo.query(
            ancestor=host.key)
        if not request.include_hidden:
          device_query = device_query.filter(
              datastore_entities.DeviceInfo.hidden == False)          devices = device_query.fetch()
      host_infos.append(datastore_entities.ToMessage(host, devices=devices))
    return api_messages.HostInfoCollection(
        host_infos=host_infos,
        more=bool(next_cursor),
        next_cursor=next_cursor,
        prev_cursor=prev_cursor)

  HOST_GET_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      hostname=messages.StringField(1, required=True),
      include_notes=messages.BooleanField(2, default=False),
      include_hidden=messages.BooleanField(3, default=False),
      include_host_state_history=messages.BooleanField(4, default=False),
      host_state_history_limit=messages.IntegerField(
          5, default=device_manager.DEFAULT_HOST_HISTORY_SIZE),
  )

  @endpoints.method(
      HOST_GET_RESOURCE,
      api_messages.HostInfo,
      path="{hostname}",
      http_method="GET",
      name="get"
  )
  def GetHost(self, request):
    """Fetches the information and notes of a given hostname.

    Args:
      request: an API request.
    Returns:
      a HostInfo object.
    Raises:
      endpoints.NotFoundException: If the given host does not exist.
      endpoint.BadRequestException: If request includes history info with
      negative limit.
    """
    hostname = request.hostname
    host = device_manager.GetHost(hostname)
    if not host:
      raise endpoints.NotFoundException("Host %s does not exist." % hostname)

    device_query = datastore_entities.DeviceInfo.query(ancestor=host.key)
    if not request.include_hidden:
      device_query = device_query.filter(
          datastore_entities.DeviceInfo.hidden == False)      devices = device_query.fetch()

    host_info = datastore_entities.ToMessage(host, devices=devices)
    # TODO: deprecate "include_notes".
    if request.include_notes:
      host_notes = datastore_entities.HostNote.query()
      host_notes = host_notes.filter(
          datastore_entities.HostNote.hostname == hostname)
      notes = [datastore_entities.ToMessage(n.note)
               for n in host_notes.iter()]
      host_info.notes = sorted(notes, key=lambda x: x.timestamp, reverse=True)
    if request.include_host_state_history:
      history_states = None
      limit = request.host_state_history_limit
      try:
        history_states = device_manager.GetHostStateHistory(hostname,
                                                            limit=limit)
      except ValueError as err:
        raise endpoints.BadRequestException(err)

      host_state_history = [datastore_entities.ToMessage(state)
                            for state in history_states]
      host_info.state_history = host_state_history
    return host_info

  # TODO: deprecate "NewNote" endpoint.
  NEW_NOTE_RESOURCE = endpoints.ResourceContainer(
      api_messages.Note,
      hostname=messages.StringField(2, required=True),
  )

  @endpoints.method(
      NEW_NOTE_RESOURCE,
      api_messages.Note,
      path="{hostname}/note",
      http_method="POST",
      name="newNote")
  def NewNote(self, request):
    """Submits a note for this host.

    Args:
      request: an API request.
    Returns:
      a VoidMessage
    """
    hostname = request.hostname
    timestamp = request.timestamp
    # Datastore only accepts UTC times. Doing a conversion if necessary.
    if timestamp.utcoffset() is not None:
      timestamp = timestamp.replace(tzinfo=None) - timestamp.utcoffset()
    note = datastore_entities.Note(user=request.user,
                                   timestamp=timestamp,
                                   message=request.message,
                                   offline_reason=request.offline_reason,
                                   recovery_action=request.recovery_action)
    host_note = datastore_entities.HostNote(hostname=hostname)
    host_note.note = note
    host_note.put()
    return datastore_entities.ToMessage(note)

  NOTE_ADD_OR_UPDATE_RESOURCE = endpoints.ResourceContainer(
      hostname=messages.StringField(1, required=True),
      id=messages.IntegerField(2),
      user=messages.StringField(3, required=True),
      message=messages.StringField(4),
      offline_reason=messages.StringField(5),
      recovery_action=messages.StringField(6),
      offline_reason_id=messages.IntegerField(7),
      recovery_action_id=messages.IntegerField(8),
      lab_name=messages.StringField(9),
  )

  @endpoints.method(
      NOTE_ADD_OR_UPDATE_RESOURCE,
      api_messages.HostNote,
      path="{hostname}/notes",
      http_method="POST",
      name="addOrUpdateNote")
  def AddOrUpdateNote(self, request):
    """Add or update a host note.

    Args:
      request: an API request.

    Returns:
      an api_messages.HostNote.
    """
    time_now = datetime.datetime.utcnow()

    host_note_entity = datastore_util.GetOrCreateEntity(
        datastore_entities.HostNote,
        entity_id=request.id,
        hostname=request.hostname,
        note=datastore_entities.Note())
    host_note_entity.note.populate(
        user=request.user, message=request.message, timestamp=time_now)
    entities_to_update = [host_note_entity]

    if request.offline_reason_id or request.offline_reason:
      offline_reason_entity = datastore_util.GetOrCreateEntity(
          datastore_entities.PredefinedMessage,
          entity_id=request.offline_reason_id,
          type=common.PredefinedMessageType.HOST_OFFLINE_REASON,
          content=request.offline_reason,
          lab_name=request.lab_name,
          create_timestamp=time_now)
      offline_reason_entity.used_count += 1
      host_note_entity.note.offline_reason = offline_reason_entity.content
      entities_to_update.append(offline_reason_entity)

    if request.recovery_action_id or request.recovery_action:
      recovery_action_entity = datastore_util.GetOrCreateEntity(
          datastore_entities.PredefinedMessage,
          entity_id=request.recovery_action_id,
          type=common.PredefinedMessageType.HOST_RECOVERY_ACTION,
          content=request.recovery_action,
          lab_name=request.lab_name,
          create_timestamp=time_now)
      recovery_action_entity.used_count += 1
      host_note_entity.note.recovery_action = recovery_action_entity.content
      entities_to_update.append(recovery_action_entity)

    ndb.put_multi(entities_to_update)
    host_note_msg = datastore_entities.ToMessage(host_note_entity)

    return host_note_msg

  NOTES_LIST_RESOURCE = endpoints.ResourceContainer(
      hostname=messages.StringField(1, required=True),
      count=messages.IntegerField(2, default=_DEFAULT_LIST_NOTES_COUNT),
      cursor=messages.StringField(3),
  )

  @endpoints.method(
      NOTES_LIST_RESOURCE,
      api_messages.HostNoteCollection,
      path="{hostname}/notes",
      http_method="GET",
      name="listNotes")
  def ListNotes(self, request):
    """List notes of a host.

    Args:
      request: an API request.

    Returns:
      an api_messages.HostNoteCollection object.
    """
    query = (
        datastore_entities.HostNote.query().filter(
            datastore_entities.HostNote.hostname == request.hostname).order(
                -datastore_entities.HostNote.note.timestamp))

    note_entities, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, request.count, request.cursor)
    note_msgs = [
        datastore_entities.ToMessage(entity) for entity in note_entities
    ]
    return api_messages.HostNoteCollection(
        host_notes=note_msgs,
        more=bool(next_cursor),
        next_cursor=next_cursor,
        prev_cursor=prev_cursor)

  ASSIGN_HOSTS_RESOURCE = endpoints.ResourceContainer(
      hostnames=messages.StringField(1, repeated=True),
      assignee=messages.StringField(2, required=True))

  @endpoints.method(
      ASSIGN_HOSTS_RESOURCE,
      message_types.VoidMessage,
      path="assign",
      http_method="POST",
      name="assign"
      )
  def Assign(self, request):
    """Mark the hosts as recover.

    Args:
      request: request with a list of hostnames and an assignee.
    Returns:
      message_types.VoidMessage
    """
    device_manager.AssignHosts(request.hostnames, request.assignee)
    return message_types.VoidMessage()

  UNASSIGN_HOSTS_RESOURCE = endpoints.ResourceContainer(
      hostnames=messages.StringField(1, repeated=True))

  @endpoints.method(
      UNASSIGN_HOSTS_RESOURCE,
      message_types.VoidMessage,
      path="unassign",
      http_method="POST",
      name="unassign"
      )
  def Unassign(self, request):
    """Mark the hosts as recover.

    Args:
      request: request with a list of hostnames.
    Returns:
      message_types.VoidMessage
    """
    device_manager.AssignHosts(request.hostnames, None)
    return message_types.VoidMessage()

  HOSTNAME_RESOURCE = endpoints.ResourceContainer(
      hostname=messages.StringField(1, required=True),
  )

  @endpoints.method(
      HOSTNAME_RESOURCE,
      api_messages.HostInfo,
      path="{hostname}/remove",
      http_method="POST",
      name="remove"
      )
  def Remove(self, request):
    """Remove this host.

    Args:
      request: an API request.
    Returns:
      an updated HostInfo
    Raises:
      endpoints.NotFoundException: If the given device does not exist.
    """
    return self._SetHidden(request.hostname, True)

  @endpoints.method(
      HOSTNAME_RESOURCE,
      api_messages.HostInfo,
      path="{hostname}/restore",
      http_method="POST",
      name="restore"
      )
  def Restore(self, request):
    """Restore this host.

    Args:
      request: an API request.
    Returns:
      an updated HostInfo
    Raises:
      endpoints.NotFoundException: If the given device does not exist.
    """
    return self._SetHidden(request.hostname, False)

  def _SetHidden(self, hostname, hidden):
    """Helper to set the hidden flag of a host."""
    entities_to_update = []
    host = device_manager.GetHost(hostname)
    if not host:
      raise endpoints.NotFoundException("Host %s does not exist." % hostname)
    host.hidden = hidden
    entities_to_update.append(host)
    if hidden:
      # Hide a host should also hide devices under the host.
      device_query = (datastore_entities.DeviceInfo.query(ancestor=host.key)
                      .filter(datastore_entities.DeviceInfo.hidden == False))        for device in device_query.fetch():
        device.hidden = hidden
        entities_to_update.append(device)
    ndb.put_multi(entities_to_update)
    host_info = datastore_entities.ToMessage(host)
    return host_info
