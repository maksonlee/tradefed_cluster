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

import endpoints
from protorpc import message_types
from protorpc import messages
from protorpc import remote

from tradefed_cluster.util import ndb_shim as ndb

from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_util
from tradefed_cluster import device_manager
from tradefed_cluster import note_manager


_DEFAULT_LIST_NOTES_COUNT = 10
_DEFAULT_LIST_HOST_COUNT = 100
_DEFAULT_LIST_HISTORIES_COUNT = 100


def _CheckTimestamp(t1, operator, t2):
  """Compare 2 timestamps."""
  if operator == common.Operator.EQUAL:
    return t1 == t2
  if operator == common.Operator.LESS_THAN:
    return t1 < t2
  if operator == common.Operator.LESS_THAN_OR_EQUAL:
    return t1 <= t2
  if operator == common.Operator.GREATER_THAN:
    return t1 > t2
  if operator == common.Operator.GREATER_THAN_OR_EQUAL:
    return t1 >= t2
  raise ValueError('Operator "%s" is not supported.' % operator)


@api_common.tradefed_cluster_api.api_class(resource_name="hosts", path="hosts")
class ClusterHostApi(remote.Service):
  """A class for cluster host API service."""

  HOST_LIST_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      lab_name=messages.StringField(1),
      include_hidden=messages.BooleanField(2, default=False),
      include_devices=messages.BooleanField(3, default=False),
      assignee=messages.StringField(4),
      is_bad=messages.BooleanField(5),
      hostnames=messages.StringField(6, repeated=True),
      host_groups=messages.StringField(7, repeated=True),
      test_harness=messages.StringField(8, repeated=True),
      test_harness_versions=messages.StringField(9, repeated=True),
      pools=messages.StringField(10, repeated=True),
      host_states=messages.EnumField(api_messages.HostState, 11, repeated=True),
      flated_extra_info=messages.StringField(12),
      cursor=messages.StringField(13),
      count=messages.IntegerField(
          14, variant=messages.Variant.INT32, default=_DEFAULT_LIST_HOST_COUNT),
      timestamp_operator=messages.EnumField(common.Operator, 15),
      timestamp=message_types.DateTimeField(16))

  @endpoints.method(
      HOST_LIST_RESOURCE,
      api_messages.HostInfoCollection,
      path="/hosts",
      http_method="GET",
      name="list")
  @api_common.with_ndb_context
  def ListHosts(self, request):
    """Fetches a list of hosts.

    Args:
      request: an API request.

    Returns:
      a HostInfoCollection object.
    """
    if ((request.timestamp and not request.timestamp_operator) or
        (not request.timestamp and request.timestamp_operator)):
      raise endpoints.BadRequestException(
          '"timestamp" and "timestamp_operator" must be set at the same time.')
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
    if request.flated_extra_info:
      query = query.filter(datastore_entities.HostInfo.flated_extra_info ==
                           request.flated_extra_info)

    if request.timestamp:
      query = query.order(
          datastore_entities.HostInfo.timestamp,
          datastore_entities.HostInfo.key)
    else:
      query = query.order(datastore_entities.HostInfo.key)

    def _PostFilter(host):
      if request.host_groups and host.host_group not in request.host_groups:
        return
      if request.hostnames and host.hostname not in request.hostnames:
        return
      # TODO: Change test_runner to test_harness.
      if request.test_harness and host.test_runner not in request.test_harness:
        return
      if request.test_harness_versions and \
          host.test_runner_version not in request.test_harness_versions:
        return
      if request.pools and not set(host.pools).issubset(set(request.pools)):
        return
      if request.host_states and host.host_state not in request.host_states:
        return
      if request.timestamp:
        if not host.timestamp:
          return
        return _CheckTimestamp(
            host.timestamp, request.timestamp_operator, request.timestamp)
      return True

    hosts, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, request.count, request.cursor, result_filter=_PostFilter)

    host_infos = []
    for host in hosts:
      devices = []
      if request.include_devices:
        device_query = datastore_entities.DeviceInfo.query(ancestor=host.key)
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
      name="get")
  @api_common.with_ndb_context
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
      host_notes = (
          datastore_entities.Note.query().filter(
              datastore_entities.Note.type == common.NoteType.HOST_NOTE).filter(
                  datastore_entities.Note.hostname == hostname).order(
                      -datastore_entities.Note.timestamp))
      host_info.notes = [
          datastore_entities.ToMessage(note) for note in host_notes
      ]
    if request.include_host_state_history:
      history_states = None
      limit = request.host_state_history_limit
      try:
        history_states = device_manager.GetHostStateHistory(
            hostname, limit=limit)
      except ValueError as err:
        raise endpoints.BadRequestException(err)

      host_state_history = [
          datastore_entities.ToMessage(state) for state in history_states
      ]
      host_info.state_history = host_state_history
    return host_info

  # TODO: deprecate "NewNote" endpoint.
  NEW_NOTE_RESOURCE = endpoints.ResourceContainer(
      hostname=messages.StringField(1, required=True),
      user=messages.StringField(2, required=True),
      message=messages.StringField(3),
      offline_reason=messages.StringField(4),
      recovery_action=messages.StringField(5),
      offline_reason_id=messages.IntegerField(6),
      recovery_action_id=messages.IntegerField(7),
      lab_name=messages.StringField(8),
      timestamp=message_types.DateTimeField(9, required=True),
  )

  @endpoints.method(
      NEW_NOTE_RESOURCE,
      api_messages.Note,
      path="{hostname}/note",
      http_method="POST",
      name="newNote")
  @api_common.with_ndb_context
  def NewNote(self, request):
    """Submits a note for this host.

    Args:
      request: an API request.

    Returns:
      a VoidMessage
    """
    timestamp = request.timestamp
    # Datastore only accepts UTC times. Doing a conversion if necessary.
    if timestamp.utcoffset() is not None:
      timestamp = timestamp.replace(tzinfo=None) - timestamp.utcoffset()
    note = datastore_entities.Note(
        type=common.NoteType.HOST_NOTE,
        hostname=request.hostname,
        user=request.user,
        timestamp=timestamp,
        message=request.message,
        offline_reason=request.offline_reason,
        recovery_action=request.recovery_action)
    note.put()
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
      api_messages.Note,
      path="{hostname}/notes",
      http_method="POST",
      name="addOrUpdateNote")
  @api_common.with_ndb_context
  def AddOrUpdateNote(self, request):
    """Add or update a host note.

    Args:
      request: an API request.

    Returns:
      an api_messages.Note.
    """
    time_now = datetime.datetime.utcnow()

    host_note_entity = datastore_util.GetOrCreateEntity(
        datastore_entities.Note,
        entity_id=request.id,
        hostname=request.hostname,
        type=common.NoteType.HOST_NOTE)
    host_note_entity.populate(
        user=request.user, message=request.message, timestamp=time_now)
    entities_to_update = [host_note_entity]

    try:
      offline_reason_entity = note_manager.PreparePredefinedMessageForNote(
          common.PredefinedMessageType.HOST_OFFLINE_REASON,
          message_id=request.offline_reason_id,
          lab_name=request.lab_name,
          content=request.offline_reason)
    except note_manager.InvalidParameterError:
      raise endpoints.BadRequestException(
          "Invalid offline_reason_id: %s" % request.offline_reason_id)
    if offline_reason_entity:
      host_note_entity.offline_reason = offline_reason_entity.content
      entities_to_update.append(offline_reason_entity)

    try:
      recovery_action_entity = note_manager.PreparePredefinedMessageForNote(
          common.PredefinedMessageType.HOST_RECOVERY_ACTION,
          message_id=request.recovery_action_id,
          lab_name=request.lab_name,
          content=request.recovery_action)
    except note_manager.InvalidParameterError:
      raise endpoints.BadRequestException(
          "Invalid recovery_action_id: %s" % request.recovery_action_id)
    if recovery_action_entity:
      host_note_entity.recovery_action = recovery_action_entity.content
      entities_to_update.append(recovery_action_entity)

    keys = ndb.put_multi(entities_to_update)
    host_note_msg = datastore_entities.ToMessage(host_note_entity)

    host_note_event_msg = api_messages.NoteEvent(
        note=host_note_msg, lab_name=request.lab_name)
    note_manager.PublishMessage(host_note_event_msg,
                                common.PublishEventType.HOST_NOTE_EVENT)

    note_key = keys[0]
    if request.id != note_key.id():
      # If ids are different, then a new note is created, we should create
      # a history snapshot.
      device_manager.CreateAndSaveHostInfoHistoryFromHostNote(
          request.hostname, note_key.id())

    return host_note_msg

  NOTES_BATCH_GET_RESOURCE = endpoints.ResourceContainer(
      hostname=messages.StringField(1, required=True),
      ids=messages.IntegerField(2, repeated=True),
  )

  @endpoints.method(
      NOTES_BATCH_GET_RESOURCE,
      api_messages.NoteCollection,
      path="{hostname}/notes:batchGet",
      http_method="GET",
      name="batchGetNotes")
  @api_common.with_ndb_context
  def BatchGetNotes(self, request):
    """Batch get notes of a host.

    Args:
      request: an API request.
    Request Params:
      hostname: string, the name of a lab host.
      ids: a list of strings, the ids of notes to batch get.

    Returns:
      an api_messages.NoteCollection object.
    """
    keys = [
        ndb.Key(datastore_entities.Note, entity_id)
        for entity_id in request.ids
    ]
    note_entities = ndb.get_multi(keys)
    note_msgs = [
        datastore_entities.ToMessage(entity)
        for entity in note_entities
        if entity and entity.hostname == request.hostname
    ]
    return api_messages.NoteCollection(
        notes=note_msgs, more=False, next_cursor=None, prev_cursor=None)

  NOTES_LIST_RESOURCE = endpoints.ResourceContainer(
      hostname=messages.StringField(1, required=True),
      count=messages.IntegerField(2, default=_DEFAULT_LIST_NOTES_COUNT),
      cursor=messages.StringField(3),
      backwards=messages.BooleanField(4, default=False),
      include_device_notes=messages.BooleanField(5, default=False),
  )

  @endpoints.method(
      NOTES_LIST_RESOURCE,
      api_messages.NoteCollection,
      path="{hostname}/notes",
      http_method="GET",
      name="listNotes")
  @api_common.with_ndb_context
  def ListNotes(self, request):
    """List notes of a host.

    Args:
      request: an API request.

    Returns:
      an api_messages.NoteCollection object.
    """
    query = (
        datastore_entities.Note.query()
        .filter(datastore_entities.Note.hostname == request.hostname)
        .order(-datastore_entities.Note.timestamp))
    if not request.include_device_notes:
      query = query.filter(
          datastore_entities.Note.type == common.NoteType.HOST_NOTE)

    note_entities, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, request.count, request.cursor, backwards=request.backwards)
    note_msgs = [
        datastore_entities.ToMessage(entity) for entity in note_entities
    ]
    return api_messages.NoteCollection(
        notes=note_msgs,
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
      name="assign")
  @api_common.with_ndb_context
  def Assign(self, request):
    """Mark the hosts as recover.

    TODO: deprecated, use set_recovery_state

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
      name="unassign")
  @api_common.with_ndb_context
  def Unassign(self, request):
    """Mark the hosts as recover.

    TODO: deprecated, use set_recovery_state

    Args:
      request: request with a list of hostnames.

    Returns:
      message_types.VoidMessage
    """
    device_manager.AssignHosts(request.hostnames, None)
    return message_types.VoidMessage()

  @endpoints.method(
      api_messages.HostRecoveryStateRequests,
      message_types.VoidMessage,
      path="batchSetRecoveryState",
      http_method="POST",
      name="batchSetRecoveryState")
  @api_common.with_ndb_context
  def BatchSetRecoveryState(self, request):
    """Batch set recovery state for hosts.

    Args:
      request: a HostRecoveryStateRequests.
    Returns:
      message_types.VoidMessage
    """
    device_manager.SetHostsRecoveryState(request.host_recovery_state_requests)
    return message_types.VoidMessage()

  HOSTNAME_RESOURCE = endpoints.ResourceContainer(
      hostname=messages.StringField(1, required=True),)

  @endpoints.method(
      HOSTNAME_RESOURCE,
      api_messages.HostInfo,
      path="{hostname}/remove",
      http_method="POST",
      name="remove")
  @api_common.with_ndb_context
  def Remove(self, request):
    """Remove this host.

    Args:
      request: an API request.

    Returns:
      an updated HostInfo
    Raises:
      endpoints.NotFoundException: If the given device does not exist.
    """
    host = device_manager.HideHost(request.hostname)
    if not host:
      raise endpoints.NotFoundException("Host %s does not exist." %
                                        request.hostname)
    return datastore_entities.ToMessage(host)

  @endpoints.method(
      HOSTNAME_RESOURCE,
      api_messages.HostInfo,
      path="{hostname}/restore",
      http_method="POST",
      name="restore")
  @api_common.with_ndb_context
  def Restore(self, request):
    """Restore this host.

    Args:
      request: an API request.

    Returns:
      an updated HostInfo
    Raises:
      endpoints.NotFoundException: If the given device does not exist.
    """
    host = device_manager.RestoreHost(request.hostname)
    if not host:
      raise endpoints.NotFoundException("Host %s does not exist." %
                                        request.hostname)
    return datastore_entities.ToMessage(host)

  HISTORIES_LIST_RESOURCE = endpoints.ResourceContainer(
      hostname=messages.StringField(1, required=True),
      count=messages.IntegerField(2, default=_DEFAULT_LIST_HISTORIES_COUNT),
      cursor=messages.StringField(3),
      backwards=messages.BooleanField(4, default=False),
  )

  @endpoints.method(
      HISTORIES_LIST_RESOURCE,
      api_messages.HostInfoHistoryCollection,
      path="{hostname}/histories",
      http_method="GET",
      name="listHistories")
  @api_common.with_ndb_context
  def ListHistories(self, request):
    """List histories of a host.

    Args:
      request: an API request.

    Returns:
      an api_messages.HostInfoHistoryCollection object.
    """
    query = (
        datastore_entities.HostInfoHistory.query(
            ancestor=ndb.Key(datastore_entities.HostInfo, request.hostname))
        .order(-datastore_entities.HostInfoHistory.timestamp))
    histories, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, request.count, request.cursor, backwards=request.backwards)
    history_msgs = [
        datastore_entities.ToMessage(entity) for entity in histories
    ]
    return api_messages.HostInfoHistoryCollection(
        histories=history_msgs,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor)
