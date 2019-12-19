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

"""Tests cluster_device_api."""

import datetime
import unittest

import mock
from protorpc import protojson
import pytz

from google.appengine.ext import ndb
from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import device_manager


class ClusterDeviceApiTest(api_test.ApiTest):

  TIMESTAMP = datetime.datetime(2015, 10, 9)
  TIMESTAMP_0 = datetime.datetime(2015, 10, 5)
  TIMESTAMP_1 = datetime.datetime(2015, 10, 6)

  def _assertDeviceCount(self, request, count):
    """Helper function for checking device list count given a request."""
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(count, len(device_collection.device_infos))

  def _setDeviceState(self, serial, state):
    """Helper function to set a device's state."""
    device = datastore_entities.DeviceInfo.query().filter(
        datastore_entities.DeviceInfo.device_serial ==
        serial).get()
    device.state = state
    device.put()

  def setUp(self):
    api_test.ApiTest.setUp(self)
    self.ndb_host_0 = datastore_test_util.CreateHost(
        'free', 'host_0')
    self.ndb_device_0 = datastore_test_util.CreateDevice(
        'free', 'host_0', 'device_0')
    self.ndb_device_1 = datastore_test_util.CreateDevice(
        'free', 'host_0', 'device_1', timestamp=self.TIMESTAMP)
    self.ndb_host_1 = datastore_test_util.CreateHost(
        'paid', 'host_1', lab_name='alab')
    self.ndb_device_2 = datastore_test_util.CreateDevice(
        'paid', 'host_1', 'device_2', hidden=True,
        lab_name='alab')
    self.ndb_device_3 = datastore_test_util.CreateDevice(
        'paid', 'host_1', 'device_3',
        lab_name='alab',
        device_type=api_messages.DeviceTypeMessage.NULL)
    self.ndb_host_2 = datastore_test_util.CreateHost(
        'free', 'host_2', hidden=True)
    self.ndb_device_4 = datastore_test_util.CreateDevice(
        'free', 'host_2', 'device_4',
        device_type=api_messages.DeviceTypeMessage.NULL)
    self.note = datastore_entities.Note(
        user='user0', timestamp=self.TIMESTAMP, message='Hello, World')

    self.device_history_0 = datastore_entities.DeviceStateHistory(
        device_serial='device_0',
        parent=self.ndb_device_0.key,
        timestamp=self.TIMESTAMP_0,
        state='Available')
    device_history_0_key = self.device_history_0.put()
    self.device_history_1 = datastore_entities.DeviceStateHistory(
        device_serial='device_0',
        parent=self.ndb_device_0.key,
        timestamp=self.TIMESTAMP_1,
        state='Allocated')
    device_history_1_key = self.device_history_1.put()
    self.history = [device_history_0_key, device_history_1_key]
    device_note = datastore_entities.DeviceNote(device_serial='device_0')
    device_note.note = self.note
    device_note.put()

  def testListDevices(self):
    """Tests ListDevices returns all devices."""
    api_request = {}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices',
        api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    # ListDevices counts non-hidden devices under hidden host.
    self.assertEqual(4, len(device_collection.device_infos))

  def testListDevices_filterCluster(self):
    """Tests ListDevices returns devices filtered by cluster."""
    api_request = {'cluster_id': 'free'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices',
        api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    # ListDevices counts non-hidden devices under hidden host.
    self.assertEqual(3, len(device_collection.device_infos))
    for device in device_collection.device_infos:
      self.assertEqual('free', device.cluster)

  def testListDevices_filterLabName(self):
    """Tests ListDevices returns devices filtered by lab_name."""
    api_request = {'lab_name': 'alab'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices',
        api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    # It will not get the hidden device.
    self.assertEqual(1, len(device_collection.device_infos))
    for device in device_collection.device_infos:
      self.assertEqual('alab', device.lab_name)

  def testListDevices_filterHostname(self):
    """Tests ListDevices returns devices filtered by hostname."""
    api_request = {'hostname': 'host_1'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    # It will not get the hidden device.
    self.assertEqual(1, len(device_collection.device_infos))
    for device in device_collection.device_infos:
      self.assertEqual('host_1', device.hostname)

  def testListDevices_includeHidden(self):
    """Tests ListDevices returns both hidden and non-hidden devices."""
    api_request = {'include_hidden': True}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(5, len(device_collection.device_infos))

  def testListDevices_deviceTypePhysicalAndNull(self):
    """Tests ListDevices returns physical and null devices."""
    api_request = {'device_types': ['PHYSICAL', 'NULL']}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    # ListDevices counts non-hidden devices under hidden host.
    self.assertEqual(4, len(device_collection.device_infos))

  def testListDevices_deviceTypeNull(self):
    """Tests ListDevices returns null devices."""
    api_request = {'device_types': ['NULL']}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    # ListDevices counts non-hidden devices under hidden host.
    self.assertEqual(2, len(device_collection.device_infos))
    for d in device_collection.device_infos:
      self.assertEqual(api_messages.DeviceTypeMessage.NULL,
                       d.device_type)

  def testListDevices_withOffset(self):
    """Tests ListDevices returns devices applying a count and offset."""
    api_request = {'include_hidden': True, 'count': '2'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices',
        api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(device_collection.device_infos))
    self.assertTrue(device_collection.more)
    self.assertIsNotNone(device_collection.next_cursor)

  def testListDevices_withCursorAndOffsetAndLastPage(self):
    """Tests ListDevices returns devices applying a count and offset.

    This test retrieves the last page which should have less devices than the
    specified count.
    """
    # 4 devices. Offset of 3 means it should return only 1 when count >= 1
    api_request = {'include_hidden': True, 'count': '3'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices',
        api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(3, len(device_collection.device_infos))
    api_request = {'include_hidden': True, 'count': '3',
                   'cursor': device_collection.next_cursor}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices',
        api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(device_collection.device_infos))
    self.assertFalse(device_collection.more)

  def testGetDevice(self):
    """Tests GetDevice without including notes."""
    api_request = {'device_serial': self.ndb_device_0.device_serial}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.GetDevice', api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(self.ndb_device_0.device_serial, device.device_serial)
    self.assertEqual(self.ndb_device_0.hostname, device.hostname)
    self.assertEqual(self.ndb_device_0.physical_cluster, device.cluster)
    self.assertEqual(self.ndb_device_0.battery_level, device.battery_level)
    self.assertEqual(self.ndb_device_0.hidden, device.hidden)
    self.assertEqual(0, len(device.notes))

  def testGetDevice_withHostname(self):
    """Tests GetDevice without including notes."""
    api_request = {
        'device_serial': self.ndb_device_0.device_serial,
        'hostname': self.ndb_device_0.hostname
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.GetDevice', api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(self.ndb_device_0.device_serial, device.device_serial)
    self.assertEqual(self.ndb_device_0.hostname, device.hostname)

  def testGetDevice_notFound(self):
    """Tests GetDevice where it does not exist."""
    api_request = {'device_serial': 'fake_device_serial'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.GetDevice', api_request,
        expect_errors=True)
    self.assertEqual('404 Not Found', api_response.status)

  def testGetDevice_includeNotes(self):
    """Tests GetDevice including notes when they are available."""
    api_request = {'device_serial': self.ndb_device_0.device_serial,
                   'include_notes': True}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.GetDevice',
        api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(self.ndb_device_0.device_serial, device.device_serial)
    self.assertEqual(self.ndb_device_0.hostname, device.hostname)
    self.assertEqual(self.ndb_device_0.physical_cluster, device.cluster)
    self.assertEqual(self.ndb_device_0.battery_level, device.battery_level)
    self.assertEqual(self.ndb_device_0.hidden, device.hidden)
    self.assertEqual(1, len(device.notes))
    self.assertEqual(self.note.user, device.notes[0].user)
    self.assertEqual(self.note.timestamp, device.notes[0].timestamp)
    self.assertEqual(self.note.message, device.notes[0].message)

  def testGetDevice_includeNotesNoneAvailable(self):
    """Tests GetDevice including notes when they are available."""
    api_request = {'device_serial': self.ndb_device_1.device_serial,
                   'include_notes': True}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.GetDevice',
        api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(self.ndb_device_1.device_serial, device.device_serial)
    self.assertEqual(self.ndb_device_1.hostname, device.hostname)
    self.assertEqual(self.ndb_device_1.battery_level, device.battery_level)
    self.assertEqual(self.ndb_device_1.hidden, device.hidden)
    self.assertEqual(0, len(device.notes))

  @mock.patch.object(device_manager, '_Now')
  def testGetDevice_includeUtilization(self, mock_now):
    """Tests GetDevice including utilization."""
    mock_now.return_value = datetime.datetime(2015, 11, 20)
    device_snapshot = datastore_entities.DeviceStateHistory(
        timestamp=datetime.datetime(2015, 11, 13),
        device_serial=self.ndb_device_0.device_serial,
        state='Allocated')
    device_snapshot.put()
    api_request = {'device_serial': self.ndb_device_0.device_serial,
                   'include_utilization': True}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.GetDevice',
        api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, device.utilization)

  def testGetDevice_includeUtilization_noUtilization(self):
    """Tests GetDevice including utilization."""
    api_request = {'device_serial': self.ndb_device_0.device_serial,
                   'include_utilization': True}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.GetDevice',
        api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(0, device.utilization)

  def testNewNote_withNoneExisting(self):
    """Tests adding a note to a device when none exist already."""
    user = 'some_user'
    timestamp = datetime.datetime(2015, 10, 18, 20, 46)
    message = 'The Message'
    offline_reason = 'Battery ran out'
    recovery_action = 'Press a button'
    api_request = {'device_serial': self.ndb_device_1.device_serial,
                   'user': user,
                   'timestamp': timestamp.isoformat(),
                   'message': message,
                   'offline_reason': offline_reason,
                   'recovery_action': recovery_action,
                  }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.NewNote',
                                          api_request)
    self.assertEqual('200 OK', api_response.status)
    api_request = {'device_serial': self.ndb_device_1.device_serial,
                   'include_notes': True}
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertEqual(1, len(device.notes))
    self.assertEqual(user, device.notes[0].user)
    self.assertEqual(timestamp, device.notes[0].timestamp)
    self.assertEqual(message, device.notes[0].message)
    self.assertEqual(offline_reason, device.notes[0].offline_reason)
    self.assertEqual(recovery_action, device.notes[0].recovery_action)

  def testNewNote_withTimezoneOffset(self):
    """Tests adding a note to a device with a timestamp with offset."""
    user = 'some_user'
    timestamp = pytz.utc.localize(datetime.datetime(2015, 10, 18, 20))
    message = 'The Message'
    api_request = {
        'device_serial': self.ndb_device_1.device_serial,
        'user': user,
        'timestamp': timestamp.isoformat(),
        'message': message}
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.NewNote',
                                          api_request)
    self.assertEqual('200 OK', api_response.status)
    api_request = {
        'device_serial': self.ndb_device_1.device_serial,
        'include_notes': True}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.GetDevice', api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertEqual(1, len(device.notes))
    self.assertEqual(user, device.notes[0].user)
    expected_timestamp = datetime.datetime(2015, 10, 18, 20)
    self.assertEqual(expected_timestamp, device.notes[0].timestamp)
    self.assertEqual(message, device.notes[0].message)

  def testNewNote_withExisting(self):
    """Tests adding a note to a device when one already exists."""
    user = 'some_user'
    timestamp = datetime.datetime(2015, 10, 18, 20, 46)
    message = 'The Message'
    api_request = {'device_serial': self.ndb_device_0.device_serial,
                   'user': user,
                   'timestamp': timestamp.isoformat(),
                   'message': message
                  }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.NewNote',
                                          api_request)
    self.assertEqual('200 OK', api_response.status)
    # Query the same device again. Notes should be sorted.
    api_request = {'device_serial': self.ndb_device_0.device_serial,
                   'include_notes': True}
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertEqual(2, len(device.notes))
    self.assertEqual(user, device.notes[0].user)
    self.assertEqual(timestamp, device.notes[0].timestamp)
    self.assertEqual(message, device.notes[0].message)
    self.assertEqual(self.note.user, device.notes[1].user)
    self.assertEqual(self.note.timestamp, device.notes[1].timestamp)
    self.assertEqual(self.note.message, device.notes[1].message)

  def testAddOrUpdateDeviceNote_addWithTextOfflineReasonAndRecoveryAction(self):
    """Tests adding a non-existing device note."""
    api_request = {
        'device_serial': 'device-serial-1',
        'user': 'user-1',
        'message': 'message-1',
        'offline_reason': 'offline-reason-1',
        'recovery_action': 'recovery-action-1',
        'lab_name': 'lab-name-1',
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.AddOrUpdateNote', api_request)
    self.assertEqual('200 OK', api_response.status)
    device_note = protojson.decode_message(api_messages.DeviceNote,
                                           api_response.body)
    # Assert datastore id is generated.
    self.assertIsNotNone(device_note.id)
    # Assert fields equal.
    self.assertEqual(api_request['device_serial'], device_note.device_serial)
    self.assertEqual(api_request['user'], device_note.user)
    self.assertEqual(api_request['message'], device_note.message)
    self.assertEqual(api_request['offline_reason'], device_note.offline_reason)
    self.assertEqual(api_request['recovery_action'],
                     device_note.recovery_action)
    # Assert PredefinedMessage entities are written into datastore.
    self.assertIsNotNone(datastore_entities.PredefinedMessage.query().filter(
        datastore_entities.PredefinedMessage.content ==
        api_request['offline_reason']).get())
    self.assertIsNotNone(datastore_entities.PredefinedMessage.query().filter(
        datastore_entities.PredefinedMessage.content ==
        api_request['recovery_action']).get())

  def testAddOrUpdateDeviceNote_UpdateWithTextOfflineReasonAndRecoveryAction(
      self):
    """Tests updating an existing device note."""
    api_request_1 = {
        'device_serial': 'device-serial',
        'user': 'user-1',
        'message': 'message-1',
        'offline_reason': 'offline-reason-1',
        'recovery_action': 'recovery-action-1',
        'lab_name': 'lab-name-1',
    }
    api_response_1 = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.AddOrUpdateNote', api_request_1)
    self.assertEqual('200 OK', api_response_1.status)
    device_note_1 = protojson.decode_message(api_messages.DeviceNote,
                                             api_response_1.body)
    api_request_2 = {
        'id': int(device_note_1.id),
        'device_serial': 'device-serial',
        'user': 'user-2',
        'message': 'message-2',
        'offline_reason': 'offline-reason-2',
        'recovery_action': 'recovery-action-2',
        'lab_name': 'lab-name-2',
    }
    api_response_2 = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.AddOrUpdateNote', api_request_2)
    self.assertEqual('200 OK', api_response_1.status)
    device_note_2 = protojson.decode_message(api_messages.DeviceNote,
                                             api_response_2.body)
    # Assert two requests modified the same datastore entity.
    self.assertEqual(device_note_1.id, device_note_2.id)
    # Assert the fields finally equal to the ones in the 2nd request.
    self.assertEqual(api_request_2['device_serial'],
                     device_note_2.device_serial)
    self.assertEqual(api_request_2['user'], device_note_2.user)
    self.assertEqual(api_request_2['message'], device_note_2.message)
    self.assertEqual(api_request_2['offline_reason'],
                     device_note_2.offline_reason)
    self.assertEqual(api_request_2['recovery_action'],
                     device_note_2.recovery_action)

  def testAddOrUpdateDeviceNote_addWithIdOfflineReasonAndRecoveryAction(self):
    """Tests adding a device note with existing predefined messages."""
    offline_reason = 'offline-reason'
    recovery_action = 'recovery-action'
    lab_name = 'lab-name'
    predefined_message_entities = [
        datastore_entities.PredefinedMessage(
            key=ndb.Key(datastore_entities.PredefinedMessage, 111),
            lab_name=lab_name,
            type=api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
            content=offline_reason,
            used_count=2),
        datastore_entities.PredefinedMessage(
            key=ndb.Key(datastore_entities.PredefinedMessage, 222),
            lab_name=lab_name,
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content=recovery_action,
            used_count=5),
    ]
    offline_reason_key, recovery_action_key = ndb.put_multi(
        predefined_message_entities)
    api_request = {
        'device_serial': 'device-serial-1',
        'user': 'user-1',
        'message': 'message-1',
        'offline_reason_id': 111,
        'recovery_action_id': 222,
        'lab_name': lab_name,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.AddOrUpdateNote', api_request)
    self.assertEqual('200 OK', api_response.status)
    device_note = protojson.decode_message(api_messages.DeviceNote,
                                           api_response.body)
    # Assert datastore id is generated.
    self.assertIsNotNone(device_note.id)
    # Assert fields equal.
    self.assertEqual(api_request['device_serial'], device_note.device_serial)
    self.assertEqual(api_request['user'], device_note.user)
    self.assertEqual(api_request['message'], device_note.message)
    self.assertEqual(offline_reason, device_note.offline_reason)
    self.assertEqual(recovery_action, device_note.recovery_action)
    # Assert PredefinedMessage used_count fields are updated.
    self.assertEqual(3, offline_reason_key.get().used_count)
    self.assertEqual(6, recovery_action_key.get().used_count)

  def testGetDevice_includeHistory(self):
    """Tests GetDevice including history when they are available."""
    api_request = {'device_serial': self.ndb_device_0.device_serial,
                   'include_history': True}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.GetDevice',
        api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(self.ndb_device_0.device_serial, device.device_serial)
    self.assertEqual(self.ndb_device_0.hostname, device.hostname)
    self.assertEqual(self.ndb_device_0.battery_level, device.battery_level)
    self.assertEqual(self.ndb_device_0.hidden, device.hidden)
    self.assertEqual(2, len(device.history))
    # history will be sorted with newest first
    self.assertEqual(self.device_history_1.timestamp,
                     device.history[0].timestamp)
    self.assertEqual(self.device_history_1.state, device.history[0].state)
    self.assertEqual(self.device_history_0.timestamp,
                     device.history[1].timestamp)
    self.assertEqual(self.device_history_0.state, device.history[1].state)

  def testGetDevice_includeHistoryNoneAvailable(self):
    """Tests GetDevice including history when none available."""
    api_request = {'device_serial': self.ndb_device_1.device_serial,
                   'include_history': True}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.GetDevice',
        api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(self.ndb_device_1.device_serial, device.device_serial)
    self.assertEqual(self.ndb_device_1.hostname, device.hostname)
    self.assertEqual(self.ndb_device_1.battery_level, device.battery_level)
    self.assertEqual(self.ndb_device_1.hidden, device.hidden)
    self.assertEqual(0, len(device.history))

  def testGetDevice_includeNotesAndHistory(self):
    """Tests GetDevice including notes and history."""
    api_request = {'device_serial': self.ndb_device_0.device_serial,
                   'include_notes': True,
                   'include_history': True}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.GetDevice',
        api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(device.notes))
    self.assertEqual(2, len(device.history))

  def testRemove(self):
    """Tests Remove."""
    # Check that the existing device is not set to hidden
    api_request = {'device_serial': self.ndb_device_0.device_serial}
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertFalse(device.hidden)
    # Call Remove
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.Remove', api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    # Verify API response
    self.assertEqual('200 OK', api_response.status)
    self.assertTrue(device.hidden)
    # Verify by retrieving the device
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertTrue(device.hidden)

  def testRemove_withHostname(self):
    """Tests Remove."""
    # Check that the existing device is not set to hidden
    api_request = {
        'device_serial': self.ndb_device_0.device_serial,
        'hostname': self.ndb_device_0.hostname
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertFalse(device.hidden)
    # Call Remove
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.Remove', api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    # Verify API response
    self.assertEqual('200 OK', api_response.status)
    self.assertTrue(device.hidden)
    # Verify by retrieving the device
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertTrue(device.hidden)

  def testRemove_missingDevice(self):
    """Test Remove with an invalid device."""
    api_request = {'device_serial': 'some-fake-serial'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.Remove', api_request, expect_errors=True)
    self.assertEqual('404 Not Found', api_response.status)

  def testRestore(self):
    """Tests Restore."""
    # Check that the existing device is set to hidden
    api_request = {'device_serial': self.ndb_device_2.device_serial}
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertTrue(device.hidden)
    # Call Restore
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.Restore', api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    # Verify API response
    self.assertEqual('200 OK', api_response.status)
    self.assertFalse(device.hidden)
    # Verify by retrieving the device
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertFalse(device.hidden)

  def testRestore_withHostname(self):
    """Tests Restore."""
    # Check that the existing device is set to hidden
    api_request = {
        'device_serial': self.ndb_device_2.device_serial,
        'hostname': self.ndb_device_2.hostname,
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertTrue(device.hidden)
    # Call Restore
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.Restore', api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    # Verify API response
    self.assertEqual('200 OK', api_response.status)
    self.assertFalse(device.hidden)
    # Verify by retrieving the device
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(
        api_messages.DeviceInfo, api_response.body)
    self.assertFalse(device.hidden)

  def testRestore_missingDevice(self):
    """Test Remove with an invalid device."""
    api_request = {'device_serial': 'some-fake-serial'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.Restore', api_request, expect_errors=True)
    self.assertEqual('404 Not Found', api_response.status)

  def testListDevices_ignoreOfflineDevices(self):
    """Test list ignoring offline devices."""
    # Should list all 4 devices when excluding unavailable devices
    api_request = {'include_offline_devices': False}
    self._assertDeviceCount(api_request, 4)
    # Set Device 4 state to Gone
    self._setDeviceState(self.ndb_device_4.device_serial,
                         common.DeviceState.GONE)
    # Should only list 3 devices when excluding unavailable devices
    api_request = {'include_offline_devices': False}
    self._assertDeviceCount(api_request, 3)
    # Set Device 3 state to Fastboot
    self._setDeviceState(self.ndb_device_3.device_serial,
                         common.DeviceState.FASTBOOT)
    # Should list 2 devices when excluding unavailable devices
    api_request = {'include_offline_devices': False}
    self._assertDeviceCount(api_request, 2)
    # Should list 4 devices when including unavailable devices
    api_request = {'include_offline_devices': True}
    self._assertDeviceCount(api_request, 4)

  def testListDeviceNotes(self):
    note_entities = [
        datastore_entities.DeviceNote(
            device_serial='device_1',
            note=datastore_entities.Note(
                user='user1',
                timestamp=datetime.datetime(1928, 1, 1),
                message='message_1',
                offline_reason='offline_reason_1',
                recovery_action='recovery_action_1')),
        datastore_entities.DeviceNote(
            device_serial='device_1',
            note=datastore_entities.Note(
                user='user2',
                timestamp=datetime.datetime(1918, 1, 1),
                message='message_2',
                offline_reason='offline_reason_2',
                recovery_action='recovery_action_2')),
        datastore_entities.DeviceNote(
            device_serial='device_1',
            note=datastore_entities.Note(
                user='user3',
                timestamp=datetime.datetime(1988, 1, 1),
                message='message_3',
                offline_reason='offline_reason_3',
                recovery_action='recovery_action_3')),
        datastore_entities.DeviceNote(
            device_serial='device_2',
            note=datastore_entities.Note(
                user='user4',
                timestamp=datetime.datetime(2008, 1, 1),
                message='message_4',
                offline_reason='offline_reason_4',
                recovery_action='recovery_action_4')),
    ]
    ndb.put_multi(note_entities)

    # The result will be sorted by timestamp in descending order.  `
    api_request = {
        'device_serial': 'device_1',
        'count': 2,
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.ListNotes',
                                          api_request)
    device_note_collection_msg = protojson.decode_message(
        api_messages.DeviceNoteCollection, api_response.body)
    self.assertTrue(device_note_collection_msg.more)
    self.assertIsNotNone(device_note_collection_msg.next_cursor)
    note_msgs = device_note_collection_msg.device_notes
    self.assertEqual(2, len(note_msgs))
    self.assertEqual(note_msgs[0].device_serial, note_entities[2].device_serial)
    self.assertEqual(note_msgs[0].user, note_entities[2].note.user)
    self.assertEqual(note_msgs[0].update_timestamp,
                     note_entities[2].note.timestamp)
    self.assertEqual(note_msgs[0].message, note_entities[2].note.message)
    self.assertEqual(note_msgs[0].offline_reason,
                     note_entities[2].note.offline_reason)
    self.assertEqual(note_msgs[0].recovery_action,
                     note_entities[2].note.recovery_action)
    self.assertEqual(note_msgs[1].device_serial, note_entities[0].device_serial)
    self.assertEqual(note_msgs[1].user, note_entities[0].note.user)
    self.assertEqual(note_msgs[1].update_timestamp,
                     note_entities[0].note.timestamp)
    self.assertEqual(note_msgs[1].message, note_entities[0].note.message)
    self.assertEqual(note_msgs[1].offline_reason,
                     note_entities[0].note.offline_reason)
    self.assertEqual(note_msgs[1].recovery_action,
                     note_entities[0].note.recovery_action)


if __name__ == '__main__':
  unittest.main()
