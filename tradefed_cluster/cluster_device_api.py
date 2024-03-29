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
"""API module to serve cluster device service calls."""

import datetime
import json
import logging
import time

import endpoints
from protorpc import message_types
from protorpc import messages
from protorpc import remote

from tradefed_cluster.util import elasticsearch_client
from tradefed_cluster.util import ndb_shim as ndb


from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_util
from tradefed_cluster import device_manager
from tradefed_cluster import env_config
from tradefed_cluster import note_manager


_DEFAULT_LIST_NOTES_COUNT = 10
_DEFAULT_LIST_DEVICE_COUNT = 100
_DEFAULT_LIST_HISTORIES_COUNT = 100


@api_common.tradefed_cluster_api.api_class(
    resource_name="devices", path="devices")
class ClusterDeviceApi(remote.Service):
  """A class for cluster device API service."""

  DEVICE_LIST_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      lab_name=messages.StringField(1),
      hostname=messages.StringField(2),
      cluster_id=messages.StringField(3),
      device_types=messages.EnumField(
          api_messages.DeviceTypeMessage, 4, repeated=True),
      include_hidden=messages.BooleanField(5, default=False),
      include_offline_devices=messages.BooleanField(6, default=True),
      cursor=messages.StringField(7),
      count=messages.IntegerField(
          8, variant=messages.Variant.INT32,
          default=_DEFAULT_LIST_DEVICE_COUNT),
      product=messages.StringField(9),
      test_harnesses=messages.StringField(10, repeated=True),
      run_targets=messages.StringField(11, repeated=True),
      hostnames=messages.StringField(12, repeated=True),
      pools=messages.StringField(13, repeated=True),
      device_states=messages.StringField(14, repeated=True),
      host_groups=messages.StringField(15, repeated=True),
      device_serial=messages.StringField(16, repeated=True),
      flated_extra_info=messages.StringField(17),
      # TODO: Please use test_harnesses, this field is deprecated.
      test_harness=messages.StringField(18, repeated=True),
      elastic_query=messages.StringField(19),
  )

  def _GetValueFromExtraInfo(self, extra_info, key):
    """Fetches a value from extra info by the given key.

    Args:
      extra_info: a key value pair list.
      key: the key name in the extra info.

    Returns:
      a string value of the key.
    """
    for item in extra_info:
      if item.get("key") == key:
        return item.get("value")
    return None

  def FromElasticDocument(self, document):
    """Fetches a value from extra info by the given key.

    Args:
      document: a item of source from elastic.

    Returns:
      a DeviceInfo object
    """
    extra_info = document.get("extra_info")
    sim_state = self._GetValueFromExtraInfo(extra_info, "sim_state")
    sim_operator = self._GetValueFromExtraInfo(extra_info, "sim_operator")
    last_recovery_time = document.get("last_recovery_time")
    if last_recovery_time is not None:
      last_recovery_time = datetime.datetime.fromisoformat(last_recovery_time)
    return api_messages.DeviceInfo(
        device_serial=document.get("device_serial"),
        lab_name=document.get("lab_name"),
        cluster=document.get("cluster"),
        host_group=document.get("host_group"),
        hostname=document.get("hostname"),
        run_target=document.get("run_target"),
        pools=document.get("pools"),
        build_id=document.get("build_id"),
        product=document.get("product"),
        product_variant=document.get("product_variant"),
        sdk_version=document.get("sdk_version"),
        state=document.get("state"),
        timestamp=datetime.datetime.fromisoformat(document.get("timestamp")),
        hidden=document.get("hidden"),
        battery_level=document.get("battery_level"),
        mac_address=document.get("mac_address"),
        sim_state=sim_state,
        sim_operator=sim_operator,
        device_type=api_messages.DeviceTypeMessage(document.get("device_type")),
        extra_info=extra_info,
        test_harness=document.get("test_harness"),
        recovery_state=document.get("recovery_state"),
        flated_extra_info=document.get("flated_extra_info"),
        last_recovery_time=last_recovery_time)

  @api_common.method(
      DEVICE_LIST_RESOURCE,
      api_messages.DeviceInfoCollection,
      path="/devices",
      http_method="GET",
      name="list")
  def ListDevices(self, request):
    """Fetches a list of devices from NDB.

    Args:
      request: an API request.

    Returns:
      a DeviceInfoCollection object.
    """
    logging.debug("ClusterDeviceApi.NDBListDevices request: %s", request)
    if (request.elastic_query is not None and
        env_config.CONFIG.use_elasticsearch):  # pytype: disable=attribute-error
      elastic_query = json.loads(request.elastic_query)
      client = elasticsearch_client.ElasticsearchClient()
      result, prev_cursor, next_cursor = client.Search(
          common.ELASTIC_INDEX_DEVICES, elastic_query)
      device_infos = [self.FromElasticDocument(d) for d in result]
      return api_messages.DeviceInfoCollection(
          device_infos=device_infos,
          next_cursor=next_cursor,
          prev_cursor=prev_cursor,
          more=bool(next_cursor))

    query = datastore_entities.DeviceInfo.query().order(
                datastore_entities.DeviceInfo.key)
    if request.lab_name:
      query = query.filter(
          datastore_entities.DeviceInfo.lab_name == request.lab_name)
    if request.cluster_id:
      query = query.filter(
          datastore_entities.DeviceInfo.clusters == request.cluster_id)
    if request.hostname:
      query = query.filter(
          datastore_entities.DeviceInfo.hostname == request.hostname)

    # We only consider device hidden here, since there is no simple way to do
    # join like operation in datastore. We tried fetching host and use
    # in(hostnames), but it was not scalable at all.
    if not request.include_hidden:
      query = query.filter(datastore_entities.DeviceInfo.hidden == False)  

    if request.product:
      query = query.filter(
          datastore_entities.DeviceInfo.product == request.product)

    if request.flated_extra_info:
      query = query.filter(datastore_entities.DeviceInfo.flated_extra_info ==
                           request.flated_extra_info)

    start_time = time.time()

    if len(request.pools) == 1:
      query = query.filter(
          datastore_entities.DeviceInfo.pools == request.pools[0])
    if len(request.device_states) == 1:
      query = query.filter(
          datastore_entities.DeviceInfo.state == request.device_states[0])
    if len(request.host_groups) == 1:
      query = query.filter(
          datastore_entities.DeviceInfo.host_group == request.host_groups[0])
    if len(request.device_types) == 1:
      query = query.filter(
          datastore_entities.DeviceInfo.device_type == request.device_types[0])
    test_harnesses = request.test_harness + request.test_harnesses
    if len(test_harnesses) == 1:
      query = query.filter(
          datastore_entities.DeviceInfo.test_harness == test_harnesses[0])
    if len(request.hostnames) == 1:
      query = query.filter(
          datastore_entities.DeviceInfo.hostname == request.hostnames[0])
    if len(request.run_targets) == 1:
      query = query.filter(
          datastore_entities.DeviceInfo.run_target == request.run_targets[0])
    if len(request.device_serial) == 1:
      query = query.filter(datastore_entities.DeviceInfo.device_serial ==
                           request.device_serial[0])

    def _PostFilter(device):
      if (request.pools and
          not set(device.pools).intersection(set(request.pools))):
        return
      if request.device_states and device.state not in request.device_states:
        return
      if request.host_groups and device.host_group not in request.host_groups:
        return
      if (not request.include_offline_devices and
          device.state not in common.DEVICE_ONLINE_STATES):
        return
      if (request.device_types and
          device.device_type not in request.device_types):
        return
      if test_harnesses and device.test_harness not in test_harnesses:
        return
      if request.hostnames and device.hostname not in request.hostnames:
        return
      if request.run_targets and device.run_target not in request.run_targets:
        return
      if (request.device_serial and
          device.device_serial not in request.device_serial):
        return
      return True

    devices, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, request.count, request.cursor, result_filter=_PostFilter)

    logging.debug("Fetched %d devices in %r seconds.", len(devices),
                  time.time() - start_time)
    start_time = time.time()
    device_infos = [datastore_entities.ToMessage(d) for d in devices]
    logging.debug("Tranformed devices to messages in %r seconds.",
                  time.time() - start_time)
    return api_messages.DeviceInfoCollection(
        device_infos=device_infos,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
        more=bool(next_cursor))

  DEVICE_GET_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      device_serial=messages.StringField(1, required=True),
      include_notes=messages.BooleanField(2, default=False),
      include_history=messages.BooleanField(3, default=False),
      include_utilization=messages.BooleanField(4, default=False),
      hostname=messages.StringField(5),
  )

  @api_common.method(
      DEVICE_GET_RESOURCE,
      api_messages.DeviceInfo,
      path="{device_serial}",
      http_method="GET",
      name="get")
  def GetDevice(self, request):
    """Fetches the information and notes of a given device.

    Args:
      request: an API request.

    Returns:
      a DeviceInfo object.
    Raises:
      endpoints.NotFoundException: If the given device does not exist.
    """
    device_serial = request.device_serial
    device = device_manager.GetDevice(
        hostname=request.hostname, device_serial=device_serial)
    if not device:
      raise endpoints.NotFoundException(
          "Device {0} does not exist.".format(device_serial))

    device_info = datastore_entities.ToMessage(device)

    # TODO: deprecate "include_notes".
    if request.include_notes:
      device_notes = (
          datastore_entities.Note.query().filter(
              datastore_entities.Note.type == common.NoteType.DEVICE_NOTE)
          .filter(datastore_entities.Note.device_serial == device_serial).order(
              -datastore_entities.Note.timestamp))
      device_info.notes = [
          datastore_entities.ToMessage(note) for note in device_notes
      ]
    if request.include_history:
      histories = device_manager.GetDeviceStateHistory(device.hostname,
                                                       device_serial)
      device_info.history = [datastore_entities.ToMessage(h) for h in histories]
    if request.include_utilization:
      utilization = device_manager.CalculateDeviceUtilization(device_serial)
      device_info.utilization = utilization
    return device_info

  # TODO: deprecate "NewNote" endpoint.
  NEW_NOTE_RESOURCE = endpoints.ResourceContainer(
      device_serial=messages.StringField(1, required=True),
      user=messages.StringField(2, required=True),
      message=messages.StringField(3),
      offline_reason=messages.StringField(4),
      recovery_action=messages.StringField(5),
      offline_reason_id=messages.IntegerField(6),
      recovery_action_id=messages.IntegerField(7),
      lab_name=messages.StringField(8),
      timestamp=message_types.DateTimeField(9, required=True),
      hostname=messages.StringField(10),
  )

  @api_common.method(
      NEW_NOTE_RESOURCE,
      api_messages.Note,
      path="{device_serial}/note",
      http_method="POST",
      name="newNote")
  def NewNote(self, request):
    """Submits a note for this device.

    Args:
      request: an API request.

    Returns:
      an api_messages.Note object.
    """
    timestamp = request.timestamp
    # Datastore only accepts UTC times. Doing a conversion if necessary.
    if timestamp.utcoffset() is not None:
      timestamp = timestamp.replace(tzinfo=None) - timestamp.utcoffset()
    note = datastore_entities.Note(
        type=common.NoteType.DEVICE_NOTE,
        hostname=request.hostname,
        device_serial=request.device_serial,
        user=request.user,
        timestamp=timestamp,
        message=request.message,
        offline_reason=request.offline_reason,
        recovery_action=request.recovery_action)

    note.put()
    return datastore_entities.ToMessage(note)

  NOTE_ADD_OR_UPDATE_RESOURCE = endpoints.ResourceContainer(
      device_serial=messages.StringField(1, required=True),
      id=messages.IntegerField(2),
      user=messages.StringField(3, required=True),
      message=messages.StringField(4),
      offline_reason=messages.StringField(5),
      recovery_action=messages.StringField(6),
      offline_reason_id=messages.IntegerField(7),
      recovery_action_id=messages.IntegerField(8),
      lab_name=messages.StringField(9),
      hostname=messages.StringField(10),
      event_time=message_types.DateTimeField(11),
  )

  @api_common.method(
      NOTE_ADD_OR_UPDATE_RESOURCE,
      api_messages.Note,
      path="{device_serial}/notes",
      http_method="POST",
      name="addOrUpdateNote")
  def AddOrUpdateNote(self, request):
    """Add or update a device note.

    Args:
      request: an API request.

    Returns:
      an api_messages.Note.
    """
    time_now = datetime.datetime.utcnow()

    device_note_entity = datastore_util.GetOrCreateEntity(
        datastore_entities.Note,
        entity_id=request.id,
        device_serial=request.device_serial,
        hostname=request.hostname,
        type=common.NoteType.DEVICE_NOTE)
    device_note_entity.populate(
        user=request.user,
        message=request.message,
        timestamp=time_now,
        event_time=request.event_time)
    entities_to_update = [device_note_entity]

    try:
      offline_reason_entity = note_manager.PreparePredefinedMessageForNote(
          common.PredefinedMessageType.DEVICE_OFFLINE_REASON,
          message_id=request.offline_reason_id,
          lab_name=request.lab_name,
          content=request.offline_reason)
    except note_manager.InvalidParameterError as err:
      raise endpoints.BadRequestException("Invalid offline reason: [%s]" % err)
    if offline_reason_entity:
      device_note_entity.offline_reason = offline_reason_entity.content
      entities_to_update.append(offline_reason_entity)

    try:
      recovery_action_entity = note_manager.PreparePredefinedMessageForNote(
          common.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
          message_id=request.recovery_action_id,
          lab_name=request.lab_name,
          content=request.recovery_action)
    except note_manager.InvalidParameterError as err:
      raise endpoints.BadRequestException("Invalid recovery action: [%s]" % err)
    if recovery_action_entity:
      device_note_entity.recovery_action = recovery_action_entity.content
      entities_to_update.append(recovery_action_entity)

    keys = ndb.put_multi(entities_to_update)
    device_note_msg = datastore_entities.ToMessage(device_note_entity)

    device = device_manager.GetDevice(
        device_serial=device_note_entity.device_serial)
    device_note_event_msg = api_messages.NoteEvent(
        note=device_note_msg,
        hostname=device.hostname,
        lab_name=device.lab_name,
        run_target=device.run_target)
    note_manager.PublishMessage(device_note_event_msg,
                                common.PublishEventType.DEVICE_NOTE_EVENT)

    note_key = keys[0]
    if request.id != note_key.id():
      # If ids are different, then a new note is created, we should create
      # a history snapshot.
      device_manager.CreateAndSaveDeviceInfoHistoryFromDeviceNote(
          request.device_serial, note_key.id())

    return device_note_msg

  @api_common.method(
      api_messages.BatchUpdateNotesWithPredefinedMessageRequest,
      api_messages.NoteCollection,
      path="notes:batchUpdateNotesWithPredefinedMessage",
      http_method="POST",
      name="batchUpdateNotesWithPredefinedMessage")
  def BatchUpdateNotesWithPredefinedMessage(self, request):
    """Batch update notes with the same predefined message.

    Args:
      request: an API request.

    Returns:
      an api_messages.NoteCollection object.
    """
    time_now = datetime.datetime.utcnow()

    device_note_entities = []
    for note in request.notes:
      note_id = int(note.id) if note.id is not None else None
      device_note_entity = datastore_util.GetOrCreateEntity(
          datastore_entities.Note,
          entity_id=note_id,
          device_serial=note.device_serial,
          hostname=note.hostname,
          type=common.NoteType.DEVICE_NOTE)
      device_note_entity.populate(
          user=request.user,
          message=request.message,
          timestamp=time_now,
          event_time=request.event_time)
      device_note_entities.append(device_note_entity)

    try:
      offline_reason_entity = note_manager.PreparePredefinedMessageForNote(
          common.PredefinedMessageType.DEVICE_OFFLINE_REASON,
          message_id=request.offline_reason_id,
          lab_name=request.lab_name,
          content=request.offline_reason,
          delta_count=len(device_note_entities))
    except note_manager.InvalidParameterError as err:
      raise endpoints.BadRequestException("Invalid offline reason: [%s]" % err)
    if offline_reason_entity:
      for device_note_entity in device_note_entities:
        device_note_entity.offline_reason = offline_reason_entity.content
      offline_reason_entity.put()

    try:
      recovery_action_entity = note_manager.PreparePredefinedMessageForNote(
          common.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
          message_id=request.recovery_action_id,
          lab_name=request.lab_name,
          content=request.recovery_action,
          delta_count=len(device_note_entities))
    except note_manager.InvalidParameterError as err:
      raise endpoints.BadRequestException("Invalid recovery action: [%s]" % err)
    if recovery_action_entity:
      for device_note_entity in device_note_entities:
        device_note_entity.recovery_action = recovery_action_entity.content
      recovery_action_entity.put()

    note_keys = ndb.put_multi(device_note_entities)
    device_note_entities = ndb.get_multi(note_keys)
    note_msgs = []
    for device_note_entity in device_note_entities:
      device_note_msg = datastore_entities.ToMessage(device_note_entity)
      note_msgs.append(device_note_msg)

      device = device_manager.GetDevice(
          device_serial=device_note_entity.device_serial)
      device_note_event_msg = api_messages.NoteEvent(
          note=device_note_msg,
          hostname=device.hostname,
          lab_name=device.lab_name,
          run_target=device.run_target)
      note_manager.PublishMessage(
          device_note_event_msg, common.PublishEventType.DEVICE_NOTE_EVENT)

    for request_note, updated_note_key in zip(request.notes, note_keys):
      if not request_note.id:
        # If ids are not provided, then a new note is created, we should create
        # a history snapshot.
        device_manager.CreateAndSaveDeviceInfoHistoryFromDeviceNote(
            request_note.device_serial, updated_note_key.id())

    return api_messages.NoteCollection(
        notes=note_msgs, more=False, next_cursor=None, prev_cursor=None)

  NOTES_BATCH_GET_RESOURCE = endpoints.ResourceContainer(
      device_serial=messages.StringField(1, required=True),
      ids=messages.IntegerField(2, repeated=True),
  )

  @api_common.method(
      NOTES_BATCH_GET_RESOURCE,
      api_messages.NoteCollection,
      path="{device_serial}/notes:batchGet",
      http_method="GET",
      name="batchGetNotes")
  def BatchGetNotes(self, request):
    """Batch get notes of a device.

    Args:
      request: an API request.
    Request Params:
      device_serial: string, the serial of a lab device.
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
        if entity and entity.device_serial == request.device_serial
    ]
    return api_messages.NoteCollection(
        notes=note_msgs, more=False, next_cursor=None, prev_cursor=None)

  NOTES_DELETE_RESOURCE = endpoints.ResourceContainer(
      device_serial=messages.StringField(1, required=True),
      ids=messages.IntegerField(2, repeated=True),
  )

  @api_common.method(
      NOTES_DELETE_RESOURCE,
      message_types.VoidMessage,
      path="{device_serial}/notes",
      http_method="DELETE",
      name="batchDeleteNotes")
  def BatchDeleteNotes(self, request):
    """Delete notes of a device.

    Args:
      request: an API request.
    Request Params:
      device_serial: string, the serial of a lab device.
      ids: a list of strings, the ids of notes to delete.

    Returns:
      a message_types.VoidMessage object.

    Raises:
      endpoints.BadRequestException, when request does not match existing notes.
    """
    keys = [
        ndb.Key(datastore_entities.Note, entity_id)
        for entity_id in request.ids
    ]
    note_entities = ndb.get_multi(keys)
    for key, note_entity in zip(keys, note_entities):
      if not note_entity:
        logging.warning("Note does not exist for key %s", key)
        continue
      if note_entity.device_serial != request.device_serial:
        raise endpoints.BadRequestException(
            "Note<id:{0}> does not exist under device<serial:{1}>.".format(
                key.id(), note_entity.device_serial))
    for key in keys:
      key.delete()
    return message_types.VoidMessage()

  NOTES_LIST_RESOURCE = endpoints.ResourceContainer(
      device_serial=messages.StringField(1, required=True),
      count=messages.IntegerField(2, default=_DEFAULT_LIST_NOTES_COUNT),
      cursor=messages.StringField(3),
      backwards=messages.BooleanField(4, default=False),
  )

  @api_common.method(
      NOTES_LIST_RESOURCE,
      api_messages.NoteCollection,
      path="{device_serial}/notes",
      http_method="GET",
      name="listNotes")
  def ListNotes(self, request):
    """List notes of a device.

    Args:
      request: an API request.

    Returns:
      an api_messages.NoteCollection object.
    """
    query = (
        datastore_entities.Note.query()
        .filter(datastore_entities.Note.type == common.NoteType.DEVICE_NOTE)
        .filter(datastore_entities.Note.device_serial == request.device_serial)
        .order(-datastore_entities.Note.timestamp))

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

  LATEST_NOTES_BATCH_GET_BY_DEVICE_RESOURCE = endpoints.ResourceContainer(
      device_serials=messages.StringField(1, repeated=True),)

  @api_common.method(
      LATEST_NOTES_BATCH_GET_BY_DEVICE_RESOURCE,
      api_messages.NoteCollection,
      path="latest_notes:batchGet",
      http_method="GET",
      name="batchGetLatestNotesByDevice")
  def BatchGetLatestNotesByDevice(self, request):
    """Batch get notes of a device.

    Args:
      request: an API request.
    Request Params:
      device_serial: string, the serial of a lab device.
      ids: a list of strings, the ids of notes to batch get.

    Returns:
      an api_messages.NoteCollection object.
    """
    note_entities = []
    for device_serial in request.device_serials:
      query = (
          datastore_entities.Note.query()
          .filter(datastore_entities.Note.type == common.NoteType.DEVICE_NOTE)
          .filter(datastore_entities.Note.device_serial == device_serial)
          .order(-datastore_entities.Note.timestamp))
      note_entities += list(query.fetch(1))
    note_msgs = [
        datastore_entities.ToMessage(entity) for entity in note_entities
    ]
    return api_messages.NoteCollection(
        notes=note_msgs, more=False, next_cursor=None, prev_cursor=None)

  DEVICE_SERIAL_RESOURCE = endpoints.ResourceContainer(
      device_serial=messages.StringField(1, required=True),
      hostname=messages.StringField(2),
  )

  @api_common.method(
      DEVICE_SERIAL_RESOURCE,
      api_messages.DeviceInfo,
      path="{device_serial}/remove",
      http_method="POST",
      name="remove")
  def Remove(self, request):
    """Remove this device .

    Args:
      request: an API request.

    Returns:
      an updated DeviceInfo
    Raises:
      endpoints.NotFoundException: If the given device does not exist.
    """
    device = device_manager.GetDevice(
        device_serial=request.device_serial, hostname=request.hostname)
    if not device:
      raise endpoints.NotFoundException("Device {0} {1} does not exist.".format(
          request.hostname, request.device_serial))
    device = device_manager.HideDevice(
        device_serial=device.device_serial, hostname=device.hostname)
    return datastore_entities.ToMessage(device)

  @api_common.method(
      DEVICE_SERIAL_RESOURCE,
      api_messages.DeviceInfo,
      path="{device_serial}/restore",
      http_method="POST",
      name="restore")
  def Restore(self, request):
    """Restore this device .

    Args:
      request: an API request.

    Returns:
      an updated DeviceInfo
    Raises:
      endpoints.NotFoundException: If the given device does not exist.
    """
    device = device_manager.GetDevice(
        device_serial=request.device_serial, hostname=request.hostname)
    if not device:
      raise endpoints.NotFoundException("Device {0} {1} does not exist.".format(
          request.hostname, request.device_serial))
    device = device_manager.RestoreDevice(
        device_serial=device.device_serial, hostname=device.hostname)
    return datastore_entities.ToMessage(device)

  HISTORIES_LIST_RESOURCE = endpoints.ResourceContainer(
      device_serial=messages.StringField(1, required=True),
      count=messages.IntegerField(2, default=_DEFAULT_LIST_HISTORIES_COUNT),
      cursor=messages.StringField(3),
      backwards=messages.BooleanField(4, default=False),
  )

  @api_common.method(
      HISTORIES_LIST_RESOURCE,
      api_messages.DeviceInfoHistoryCollection,
      path="{device_serial}/histories",
      http_method="GET",
      name="listHistories")
  def ListHistories(self, request):
    """List histories of a device.

    Args:
      request: an API request.

    Returns:
      an api_messages.DeviceInfoHistoryCollection object.
    """
    device = device_manager.GetDevice(device_serial=request.device_serial)
    if not device:
      raise endpoints.NotFoundException(
          f"Device {request.device_serial} does not exist.")

    query = (
        datastore_entities.DeviceInfoHistory.query(ancestor=device.key).order(
            -datastore_entities.DeviceInfoHistory.timestamp))
    histories, prev_cursor, next_cursor = datastore_util.FetchPage(
        query, request.count, request.cursor, backwards=request.backwards)
    history_msgs = [
        datastore_entities.ToMessage(entity) for entity in histories
    ]
    return api_messages.DeviceInfoHistoryCollection(
        histories=history_msgs,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor)

  @api_common.method(
      api_messages.DeviceRecoveryStateRequests,
      message_types.VoidMessage,
      path="batchSetRecoveryState",
      http_method="POST",
      name="batchSetRecoveryState")
  def BatchSetRecoveryState(self, request):
    """Batch set recovery state for devices.

    Args:
      request: a DeviceRecoveryStateRequests.
    Returns:
      message_types.VoidMessage
    """
    device_manager.SetDevicesRecoveryState(
        request.device_recovery_state_requests)
    return message_types.VoidMessage()
