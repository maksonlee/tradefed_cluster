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

from tradefed_cluster.util import ndb_shim as ndb
from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import device_manager
from tradefed_cluster import note_manager


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
        datastore_entities.DeviceInfo.device_serial == serial).get()
    device.state = state
    device.put()

  def setUp(self):
    api_test.ApiTest.setUp(self)
    self.ndb_host_0 = datastore_test_util.CreateHost('free', 'host_0')
    self.ndb_device_0 = datastore_test_util.CreateDevice(
        'free', 'host_0', 'device_0', 'lab-name-1', timestamp=self.TIMESTAMP)
    self.ndb_device_1 = datastore_test_util.CreateDevice(
        'free', 'host_0', 'device_1', timestamp=self.TIMESTAMP)
    self.ndb_host_1 = datastore_test_util.CreateHost(
        'paid', 'host_1', lab_name='alab')
    self.ndb_device_2 = datastore_test_util.CreateDevice(
        'paid', 'host_1', 'device_2', hidden=True, lab_name='alab')
    self.ndb_device_3 = datastore_test_util.CreateDevice(
        'paid',
        'host_1',
        'device_3',
        lab_name='alab',
        device_type=api_messages.DeviceTypeMessage.NULL)
    self.ndb_host_2 = datastore_test_util.CreateHost(
        'free', 'host_2', hidden=True)
    self.ndb_device_4 = datastore_test_util.CreateDevice(
        'free',
        'host_2',
        'device_4',
        device_type=api_messages.DeviceTypeMessage.NULL)
    self.note = datastore_entities.Note(
        type=common.NoteType.DEVICE_NOTE,
        device_serial='device_0',
        user='user0',
        timestamp=self.TIMESTAMP,
        message='Hello, World')
    self.note.put()

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

  def testListDevices(self):
    """Tests ListDevices returns all devices."""
    api_request = {}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    # ListDevices counts non-hidden devices under hidden host.
    self.assertEqual(4, len(device_collection.device_infos))

  def testListDevices_filterCluster(self):
    """Tests ListDevices returns devices filtered by cluster."""
    api_request = {'cluster_id': 'free'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
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
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    # It will not get the hidden device.
    self.assertEqual(1, len(device_collection.device_infos))
    for device in device_collection.device_infos:
      self.assertEqual('alab', device.lab_name)

  def testListDevices_filterDeviceSerial(self):
    """Tests ListDevices returns device filtered by device serial."""
    api_request = {'device_serial': self.ndb_device_3.device_serial}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(device_collection.device_infos))
    self.assertEqual(self.ndb_device_3.device_serial,
                     device_collection.device_infos[0].device_serial)

  def testListDevices_filterTestHarness(self):
    """Tests ListDevices returns devices filtered by test harness."""
    self.ndb_device_0 = datastore_test_util.CreateDevice(
        'mh_cluster',
        'mh_host',
        'mh_device',
        timestamp=self.TIMESTAMP,
        test_harness='mh')
    api_request = {'test_harness': 'mh'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    # It will not get the hidden device.
    self.assertEqual(1, len(device_collection.device_infos))
    self.assertEqual('mh', device_collection.device_infos[0].test_harness)

  def testListDevices_filterMultiTestHarness(self):
    """Tests ListDevices returns devices filtered by multiple test harness."""
    datastore_test_util.CreateDevice(
        'mh_cluster',
        'mh_host',
        'mh_device',
        test_harness='mh')
    datastore_test_util.CreateDevice(
        'goats_cluster',
        'goats_host',
        'goats_device',
        test_harness='goats')
    api_request = {'test_harness': ['mh', 'goats']}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    # It will not get the hidden device.
    self.assertEqual(2, len(device_collection.device_infos))
    self.assertEqual('goats', device_collection.device_infos[0].test_harness)
    self.assertEqual('mh', device_collection.device_infos[1].test_harness)

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

  def testListDevices_filterHostnames(self):
    """Tests ListDevices returns devices filtered by hostnames."""
    api_request = {'hostnames': ['host_0', 'host_1']}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(3, len(device_collection.device_infos))
    self.assertEqual(self.ndb_device_0.device_serial,
                     device_collection.device_infos[0].device_serial)
    self.assertEqual(self.ndb_device_1.device_serial,
                     device_collection.device_infos[1].device_serial)
    self.assertEqual(self.ndb_device_3.device_serial,
                     device_collection.device_infos[2].device_serial)

  def testListDevices_filterPools(self):
    """Tests ListDevices returns devices filtered by pools."""
    datastore_test_util.CreateDevice('cluster_01', 'host_01', 'device_01',
                                     pools='pools_A')
    datastore_test_util.CreateDevice('cluster_01', 'host_01', 'device_02',
                                     pools='pools_B')
    api_request = {'pools': ['pools_A', 'pools_B']}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(device_collection.device_infos))
    self.assertEqual(['pools_A'], device_collection.device_infos[0].pools)
    self.assertEqual(['pools_B'], device_collection.device_infos[1].pools)

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
      self.assertEqual(api_messages.DeviceTypeMessage.NULL, d.device_type)

  def testListDevices_filterHostGroups(self):
    """Tests ListDevices returns devices filtered by host groups."""
    datastore_test_util.CreateDevice(
        'cluster_01',
        'host_01',
        'device_01',
        host_group='hg_01')
    datastore_test_util.CreateDevice(
        'cluster_01',
        'host_01',
        'device_02',
        host_group='hg_02')
    datastore_test_util.CreateDevice(
        'cluster_01',
        'host_01',
        'device_03',
        host_group='hg_02')
    datastore_test_util.CreateDevice(
        'cluster_01',
        'host_01',
        'device_04',
        host_group='hg_03')
    api_request = {'host_groups': ['hg_01', 'hg_02']}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(3, len(device_collection.device_infos))
    self.assertEqual('hg_01', device_collection.device_infos[0].host_group)
    self.assertEqual('hg_02', device_collection.device_infos[1].host_group)
    self.assertEqual('hg_02', device_collection.device_infos[2].host_group)

  def testListDevices_withOffset(self):
    """Tests ListDevices returns devices applying a count and offset."""
    api_request = {'include_hidden': True, 'count': '2'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
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
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(3, len(device_collection.device_infos))
    api_request = {
        'include_hidden': True,
        'count': '3',
        'cursor': device_collection.next_cursor
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(device_collection.device_infos))
    self.assertFalse(device_collection.more)

  def testListDevices_filterRunTargets(self):
    """Tests ListDevices returns devices filtered by run targets."""
    datastore_test_util.CreateDevice('cluster_01', 'host_01', 'device_01',
                                     run_target='run_target_01')
    datastore_test_util.CreateDevice('cluster_01', 'host_01', 'device_02',
                                     run_target='run_target_02')
    datastore_test_util.CreateDevice('cluster_01', 'host_01', 'device_03',
                                     run_target='run_target_03')
    api_request = {'run_targets': ['run_target_01', 'run_target_02']}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(device_collection.device_infos))
    self.assertEqual('run_target_01',
                     device_collection.device_infos[0].run_target)
    self.assertEqual('run_target_02',
                     device_collection.device_infos[1].run_target)

  def testListDevices_filterState(self):
    """Tests ListDevices returns devices filtered by states."""
    datastore_test_util.CreateDevice(
        'cluster_01',
        'host_01',
        'device_01',
        state=common.DeviceState.ALLOCATED)
    datastore_test_util.CreateDevice(
        'cluster_01', 'host_01', 'device_02', state=common.DeviceState.UNKNOWN)
    api_request = {
        'device_states': [
            common.DeviceState.ALLOCATED, common.DeviceState.UNKNOWN
        ]
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListDevices', api_request)
    device_collection = protojson.decode_message(
        api_messages.DeviceInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(device_collection.device_infos))
    self.assertEqual(common.DeviceState.ALLOCATED,
                     device_collection.device_infos[0].state)
    self.assertEqual(common.DeviceState.UNKNOWN,
                     device_collection.device_infos[1].state)

  def testBatchGetLastestNotesByDevice(self):
    """Tests ListDevices returns all devices."""
    note_entities = [
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            user='user1',
            device_serial=self.ndb_device_2.device_serial,
            timestamp=datetime.datetime(1987, 10, 19),
            message='message_0'),
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            user='user1',
            device_serial=self.ndb_device_2.device_serial,
            timestamp=datetime.datetime(2020, 3, 12),
            message='message_3'),
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            user='user1',
            device_serial=self.ndb_device_4.device_serial,
            timestamp=datetime.datetime(2001, 9, 17),
            message='message_1'),
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            user='user1',
            device_serial=self.ndb_device_4.device_serial,
            timestamp=datetime.datetime(2008, 10, 15),
            message='message_2'),
    ]
    ndb.put_multi(note_entities)
    api_request = {
        'device_serials': [
            self.ndb_device_2.device_serial,
            self.ndb_device_4.device_serial,
        ]
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.BatchGetLastestNotesByDevice', api_request)
    device_note_collection = protojson.decode_message(
        api_messages.NoteCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(device_note_collection.notes))
    self.assertEqual('message_3',
                     device_note_collection.notes[0].message)
    self.assertEqual('message_2',
                     device_note_collection.notes[1].message)

  def testBatchGetLastestNotesByDevice_noNotesFound(self):
    """Tests ListDevices returns all devices."""
    note_entities = [
        datastore_entities.DeviceNote(
            device_serial=self.ndb_device_3.device_serial,
            note=datastore_entities.Note(
                timestamp=datetime.datetime(1929, 10, 28),
                message='message_0')),
        datastore_entities.DeviceNote(
            device_serial=self.ndb_device_3.device_serial,
            note=datastore_entities.Note(
                timestamp=datetime.datetime(2020, 3, 12), message='message_1')),
    ]
    ndb.put_multi(note_entities)
    api_request = {
        'device_serials': [
            self.ndb_device_2.device_serial,
            self.ndb_device_4.device_serial,
        ]
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.BatchGetLastestNotesByDevice', api_request)
    device_note_collection = protojson.decode_message(
        api_messages.NoteCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(0, len(device_note_collection.notes))

  def testGetDevice(self):
    """Tests GetDevice without including notes."""
    api_request = {'device_serial': self.ndb_device_0.device_serial}
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
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
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(self.ndb_device_0.device_serial, device.device_serial)
    self.assertEqual(self.ndb_device_0.hostname, device.hostname)

  def testGetDevice_notFound(self):
    """Tests GetDevice where it does not exist."""
    api_request = {'device_serial': 'fake_device_serial'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.GetDevice', api_request, expect_errors=True)
    self.assertEqual('404 Not Found', api_response.status)

  def testGetDevice_includeNotes(self):
    """Tests GetDevice including notes when they are available."""
    api_request = {
        'device_serial': self.ndb_device_0.device_serial,
        'include_notes': True
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
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
    api_request = {
        'device_serial': self.ndb_device_1.device_serial,
        'include_notes': True
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
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
    api_request = {
        'device_serial': self.ndb_device_0.device_serial,
        'include_utilization': True
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, device.utilization)

  def testGetDevice_includeUtilization_noUtilization(self):
    """Tests GetDevice including utilization."""
    api_request = {
        'device_serial': self.ndb_device_0.device_serial,
        'include_utilization': True
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(0, device.utilization)

  def testNewNote_withNoneExisting(self):
    """Tests adding a note to a device when none exist already."""
    user = 'some_user'
    timestamp = datetime.datetime(2015, 10, 18, 20, 46)
    message = 'The Message'
    offline_reason = 'Battery ran out'
    recovery_action = 'Press a button'
    api_request = {
        'device_serial': self.ndb_device_1.device_serial,
        'user': user,
        'timestamp': timestamp.isoformat(),
        'message': message,
        'offline_reason': offline_reason,
        'recovery_action': recovery_action,
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.NewNote',
                                          api_request)
    self.assertEqual('200 OK', api_response.status)
    api_request = {
        'device_serial': self.ndb_device_1.device_serial,
        'include_notes': True
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
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
        'message': message
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.NewNote',
                                          api_request)
    self.assertEqual('200 OK', api_response.status)
    api_request = {
        'device_serial': self.ndb_device_1.device_serial,
        'include_notes': True
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
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
    api_request = {
        'device_serial': self.ndb_device_0.device_serial,
        'user': user,
        'timestamp': timestamp.isoformat(),
        'message': message
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.NewNote',
                                          api_request)
    self.assertEqual('200 OK', api_response.status)
    # Query the same device again. Notes should be sorted.
    api_request = {
        'device_serial': self.ndb_device_0.device_serial,
        'include_notes': True
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
    self.assertEqual(2, len(device.notes))
    self.assertEqual(user, device.notes[0].user)
    self.assertEqual(timestamp, device.notes[0].timestamp)
    self.assertEqual(message, device.notes[0].message)
    self.assertEqual(self.note.user, device.notes[1].user)
    self.assertEqual(self.note.timestamp, device.notes[1].timestamp)
    self.assertEqual(self.note.message, device.notes[1].message)

  @mock.patch.object(device_manager, 'GetDevice')
  @mock.patch.object(note_manager, 'PublishMessage')
  def testAddOrUpdateDeviceNote_addWithTextOfflineReasonAndRecoveryAction(
      self, mock_publish_device_note_message, mock_get_device):
    """Tests adding a non-existing device note."""
    mock_get_device.return_value = self.ndb_device_0
    api_request = {
        'device_serial': self.ndb_device_0.device_serial,
        'user': 'user-1',
        'message': 'message-1',
        'offline_reason': 'offline-reason-1',
        'recovery_action': 'recovery-action-1',
        'lab_name': self.ndb_device_0.lab_name,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.AddOrUpdateNote', api_request)
    self.assertEqual('200 OK', api_response.status)
    device_note = protojson.decode_message(api_messages.Note,
                                           api_response.body)
    device_note_event_msg = api_messages.NoteEvent(
        note=device_note,
        hostname=self.ndb_device_0.hostname,
        lab_name=self.ndb_device_0.lab_name,
        run_target=self.ndb_device_0.run_target)

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
    # Side Effect: Assert DeviceInfoHistory is written into datastore.
    histories = list(
        datastore_entities.DeviceInfoHistory.query(
            datastore_entities.DeviceInfoHistory.device_serial ==
            self.ndb_device_0.device_serial).fetch())
    self.assertEqual(1, len(histories))
    self.assertEqual(
        int(device_note.id), histories[0].extra_info['device_note_id'])
    mock_publish_device_note_message.assert_called_once_with(
        device_note_event_msg, common.PublishEventType.DEVICE_NOTE_EVENT)

  @mock.patch.object(device_manager, 'GetDevice')
  @mock.patch.object(note_manager, 'PublishMessage')
  def testAddOrUpdateDeviceNote_UpdateWithTextOfflineReasonAndRecoveryAction(
      self, mock_publish_device_note_message, mock_get_device):
    """Tests updating an existing device note."""
    mock_get_device.return_value = self.ndb_device_0
    api_request_1 = {
        'device_serial': self.ndb_device_0.device_serial,
        'user': 'user-1',
        'message': 'message-1',
        'offline_reason': 'offline-reason-1',
        'recovery_action': 'recovery-action-1',
        'lab_name': self.ndb_device_0.lab_name,
    }
    api_response_1 = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.AddOrUpdateNote', api_request_1)
    self.assertEqual('200 OK', api_response_1.status)
    device_note_1 = protojson.decode_message(api_messages.Note,
                                             api_response_1.body)
    new_lab_name = 'lab-name-2'
    mock_get_device.return_value.lab_name = new_lab_name
    api_request_2 = {
        'id': int(device_note_1.id),
        'device_serial': self.ndb_device_0.device_serial,
        'user': 'user-2',
        'message': 'message-2',
        'offline_reason': 'offline-reason-2',
        'recovery_action': 'recovery-action-2',
        'lab_name': new_lab_name,
    }
    api_response_2 = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.AddOrUpdateNote', api_request_2)
    self.assertEqual('200 OK', api_response_1.status)
    device_note_2 = protojson.decode_message(api_messages.Note,
                                             api_response_2.body)
    device_note_event_msg = api_messages.NoteEvent(
        note=device_note_2,
        hostname=self.ndb_device_0.hostname,
        lab_name=new_lab_name,
        run_target=self.ndb_device_0.run_target)

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
    # Side Effect: Assert DeviceInfoHistory is written into datastore.
    histories = list(
        datastore_entities.DeviceInfoHistory.query(
            datastore_entities.DeviceInfoHistory.device_serial ==
            self.ndb_device_0.device_serial).fetch())
    self.assertEqual(1, len(histories))
    self.assertEqual(int(device_note_1.id),
                     histories[0].extra_info['device_note_id'])
    mock_publish_device_note_message.assert_called_with(
        device_note_event_msg, common.PublishEventType.DEVICE_NOTE_EVENT)

  @mock.patch.object(device_manager, 'GetDevice')
  @mock.patch.object(note_manager, 'PublishMessage')
  def testAddOrUpdateDeviceNote_UpdateWithDedupTextPredefinedMessage(
      self, mock_publish_device_note_message, mock_get_device):
    """Tests updating an existing device note."""
    mock_get_device.return_value = self.ndb_device_0
    api_request_1 = {
        'device_serial': self.ndb_device_0.device_serial,
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
        'device_serial': self.ndb_device_0.device_serial,
        'user': 'user-2',
        'message': 'message-2',
        'offline_reason': 'offline-reason-1',
        'recovery_action': 'recovery-action-1',
        'lab_name': 'lab-name-1',
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
    # Side Effect: Assert PredefinedMessage is created only in first call.
    predefine_messages = list(datastore_entities.PredefinedMessage.query(
        datastore_entities.PredefinedMessage.lab_name == 'lab-name-1').fetch())
    self.assertEqual(2, len(predefine_messages))

  @mock.patch.object(device_manager, 'GetDevice')
  @mock.patch.object(note_manager, 'PublishMessage')
  def testAddOrUpdateDeviceNote_addWithIdOfflineReasonAndRecoveryAction(
      self, mock_publish_device_note_message, mock_get_device):
    """Tests adding a device note with existing predefined messages."""
    offline_reason = 'offline-reason'
    recovery_action = 'recovery-action'
    mock_get_device.return_value = self.ndb_device_0
    predefined_message_entities = [
        datastore_entities.PredefinedMessage(
            key=ndb.Key(datastore_entities.PredefinedMessage, 111),
            lab_name=self.ndb_device_0.lab_name,
            type=api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
            content=offline_reason,
            used_count=2),
        datastore_entities.PredefinedMessage(
            key=ndb.Key(datastore_entities.PredefinedMessage, 222),
            lab_name=self.ndb_device_0.lab_name,
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content=recovery_action,
            used_count=5),
    ]
    offline_reason_key, recovery_action_key = ndb.put_multi(
        predefined_message_entities)
    api_request = {
        'device_serial': self.ndb_device_0.device_serial,
        'user': 'user-1',
        'message': 'message-1',
        'offline_reason_id': 111,
        'recovery_action_id': 222,
        'lab_name': self.ndb_device_0.lab_name,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.AddOrUpdateNote', api_request)
    self.assertEqual('200 OK', api_response.status)
    device_note = protojson.decode_message(api_messages.Note,
                                           api_response.body)
    device_note_event_msg = api_messages.NoteEvent(
        note=device_note,
        hostname=self.ndb_device_0.hostname,
        lab_name=self.ndb_device_0.lab_name,
        run_target=self.ndb_device_0.run_target)

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
    # Side Effect: Assert DeviceInfoHistory is written into datastore.
    histories = list(
        datastore_entities.DeviceInfoHistory.query(
            datastore_entities.DeviceInfoHistory.device_serial ==
            self.ndb_device_0.device_serial).fetch())
    self.assertEqual(1, len(histories))
    self.assertEqual(
        int(device_note.id), histories[0].extra_info['device_note_id'])
    mock_publish_device_note_message.assert_called_once_with(
        device_note_event_msg, common.PublishEventType.DEVICE_NOTE_EVENT)

  @mock.patch.object(device_manager, 'GetDevice')
  @mock.patch.object(note_manager, 'PublishMessage')
  def testAddOrUpdateDeviceNote_InvalidIdOfflineReasonAndRecoveryAction(
      self, mock_publish_device_note_message, mock_get_device):
    """Tests adding a device note with existing predefined messages."""
    mock_get_device.return_value = self.ndb_device_0
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
    ndb.put_multi(predefined_message_entities)

    # Invalid recovery action.
    api_request = {
        'device_serial': self.ndb_device_0.device_serial,
        'user': 'user-1',
        'message': 'message-1',
        'recovery_action_id': 111,
        'lab_name': lab_name,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.AddOrUpdateNote',
        api_request,
        expect_errors=True)
    self.assertEqual('400 Bad Request', api_response.status)
    # Non-existing offline reason.
    api_request = {
        'device_serial': self.ndb_device_0.device_serial,
        'user': 'user-1',
        'message': 'message-1',
        'offline_reason_id': 333,
        'lab_name': lab_name,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.AddOrUpdateNote',
        api_request,
        expect_errors=True)
    self.assertEqual('400 Bad Request', api_response.status)

  def testGetDevice_includeHistory(self):
    """Tests GetDevice including history when they are available."""
    api_request = {
        'device_serial': self.ndb_device_0.device_serial,
        'include_history': True
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
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
    api_request = {
        'device_serial': self.ndb_device_1.device_serial,
        'include_history': True
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(self.ndb_device_1.device_serial, device.device_serial)
    self.assertEqual(self.ndb_device_1.hostname, device.hostname)
    self.assertEqual(self.ndb_device_1.battery_level, device.battery_level)
    self.assertEqual(self.ndb_device_1.hidden, device.hidden)
    self.assertEqual(0, len(device.history))

  def testGetDevice_includeNotesAndHistory(self):
    """Tests GetDevice including notes and history."""
    api_request = {
        'device_serial': self.ndb_device_0.device_serial,
        'include_notes': True,
        'include_history': True
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(device.notes))
    self.assertEqual(2, len(device.history))

  def testRemove(self):
    """Tests Remove."""
    # Check that the existing device is not set to hidden
    api_request = {'device_serial': self.ndb_device_0.device_serial}
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
    self.assertFalse(device.hidden)
    # Call Remove
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.Remove',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
    # Verify API response
    self.assertEqual('200 OK', api_response.status)
    self.assertTrue(device.hidden)
    # Verify by retrieving the device
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
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
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
    self.assertFalse(device.hidden)
    # Call Remove
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.Remove',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
    # Verify API response
    self.assertEqual('200 OK', api_response.status)
    self.assertTrue(device.hidden)
    # Verify by retrieving the device
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
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
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
    self.assertTrue(device.hidden)
    # Call Restore
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.Restore',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
    # Verify API response
    self.assertEqual('200 OK', api_response.status)
    self.assertFalse(device.hidden)
    # Verify by retrieving the device
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
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
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
    self.assertTrue(device.hidden)
    # Call Restore
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.Restore',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
    # Verify API response
    self.assertEqual('200 OK', api_response.status)
    self.assertFalse(device.hidden)
    # Verify by retrieving the device
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.GetDevice',
                                          api_request)
    device = protojson.decode_message(api_messages.DeviceInfo,
                                      api_response.body)
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
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            device_serial='device_1',
            user='user1',
            timestamp=datetime.datetime(1928, 1, 1),
            message='message_1',
            offline_reason='offline_reason_1',
            recovery_action='recovery_action_1'),
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            device_serial='device_1',
            user='user2',
            timestamp=datetime.datetime(1918, 1, 1),
            message='message_2',
            offline_reason='offline_reason_2',
            recovery_action='recovery_action_2'),
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            device_serial='device_1',
            user='user3',
            timestamp=datetime.datetime(1988, 1, 1),
            message='message_3',
            offline_reason='offline_reason_3',
            recovery_action='recovery_action_3'),
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            device_serial='device_2',
            user='user4',
            timestamp=datetime.datetime(2008, 1, 1),
            message='message_4',
            offline_reason='offline_reason_4',
            recovery_action='recovery_action_4'),
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
        api_messages.NoteCollection, api_response.body)
    self.assertTrue(device_note_collection_msg.more)
    self.assertIsNotNone(device_note_collection_msg.next_cursor)
    note_msgs = device_note_collection_msg.notes
    self.assertEqual(2, len(note_msgs))
    self.assertEqual(note_msgs[0].device_serial, note_entities[2].device_serial)
    self.assertEqual(note_msgs[0].user, note_entities[2].user)
    self.assertEqual(note_msgs[0].timestamp,
                     note_entities[2].timestamp)
    self.assertEqual(note_msgs[0].message, note_entities[2].message)
    self.assertEqual(note_msgs[0].offline_reason,
                     note_entities[2].offline_reason)
    self.assertEqual(note_msgs[0].recovery_action,
                     note_entities[2].recovery_action)
    self.assertEqual(note_msgs[1].device_serial, note_entities[0].device_serial)
    self.assertEqual(note_msgs[1].user, note_entities[0].user)
    self.assertEqual(note_msgs[1].timestamp,
                     note_entities[0].timestamp)
    self.assertEqual(note_msgs[1].message, note_entities[0].message)
    self.assertEqual(note_msgs[1].offline_reason,
                     note_entities[0].offline_reason)
    self.assertEqual(note_msgs[1].recovery_action,
                     note_entities[0].recovery_action)

  def testListDeviceNotes_withCursorAndOffsetAndBackwards(self):
    note_entities = [
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            device_serial='device_1',
            user='user1',
            timestamp=datetime.datetime(1928, 1, 1),
            message='message_1',
            offline_reason='offline_reason_1',
            recovery_action='recovery_action_1'),
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            device_serial='device_1',
            user='user2',
            timestamp=datetime.datetime(1918, 1, 1),
            message='message_2',
            offline_reason='offline_reason_2',
            recovery_action='recovery_action_2'),
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            device_serial='device_1',
            user='user3',
            timestamp=datetime.datetime(1988, 1, 1),
            message='message_3',
            offline_reason='offline_reason_3',
            recovery_action='recovery_action_3'),
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            device_serial='device_2',
            user='user4',
            timestamp=datetime.datetime(2008, 1, 1),
            message='message_4',
            offline_reason='offline_reason_4',
            recovery_action='recovery_action_4'),
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
        api_messages.NoteCollection, api_response.body)
    self.assertIsNotNone(device_note_collection_msg.next_cursor)
    note_msgs = device_note_collection_msg.notes
    self.assertEqual(2, len(note_msgs))
    self.assertEqual(note_msgs[0].device_serial, note_entities[2].device_serial)
    self.assertEqual(note_msgs[0].user, note_entities[2].user)
    self.assertEqual(note_msgs[0].timestamp, note_entities[2].timestamp)
    self.assertEqual(note_msgs[0].message, note_entities[2].message)
    self.assertEqual(note_msgs[0].offline_reason,
                     note_entities[2].offline_reason)
    self.assertEqual(note_msgs[0].recovery_action,
                     note_entities[2].recovery_action)
    self.assertEqual(note_msgs[1].device_serial, note_entities[0].device_serial)
    self.assertEqual(note_msgs[1].user, note_entities[0].user)
    self.assertEqual(note_msgs[1].timestamp,
                     note_entities[0].timestamp)
    self.assertEqual(note_msgs[1].message, note_entities[0].message)
    self.assertEqual(note_msgs[1].offline_reason,
                     note_entities[0].offline_reason)
    self.assertEqual(note_msgs[1].recovery_action,
                     note_entities[0].recovery_action)

    # fetch next page
    api_request = {
        'device_serial': 'device_1',
        'count': 2,
        'cursor': device_note_collection_msg.next_cursor,
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.ListNotes',
                                          api_request)
    device_note_collection_msg = protojson.decode_message(
        api_messages.NoteCollection, api_response.body)
    self.assertIsNotNone(device_note_collection_msg.prev_cursor)
    note_msgs = device_note_collection_msg.notes
    self.assertEqual(1, len(note_msgs))
    self.assertEqual(note_msgs[0].device_serial, note_entities[1].device_serial)
    self.assertEqual(note_msgs[0].user, note_entities[1].user)
    self.assertEqual(note_msgs[0].timestamp,
                     note_entities[1].timestamp)
    self.assertEqual(note_msgs[0].message, note_entities[1].message)
    self.assertEqual(note_msgs[0].offline_reason,
                     note_entities[1].offline_reason)
    self.assertEqual(note_msgs[0].recovery_action,
                     note_entities[1].recovery_action)

    # fetch previous page (same as first page)
    api_request = {
        'device_serial': 'device_1',
        'count': 2,
        'cursor': device_note_collection_msg.prev_cursor,
        'backwards': True,
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterDeviceApi.ListNotes',
                                          api_request)
    device_note_collection_msg = protojson.decode_message(
        api_messages.NoteCollection, api_response.body)
    note_msgs = device_note_collection_msg.notes
    self.assertEqual(2, len(note_msgs))
    self.assertEqual(note_msgs[0].device_serial, note_entities[2].device_serial)
    self.assertEqual(note_msgs[0].user, note_entities[2].user)
    self.assertEqual(note_msgs[0].timestamp,
                     note_entities[2].timestamp)
    self.assertEqual(note_msgs[0].message, note_entities[2].message)
    self.assertEqual(note_msgs[0].offline_reason,
                     note_entities[2].offline_reason)
    self.assertEqual(note_msgs[0].recovery_action,
                     note_entities[2].recovery_action)
    self.assertEqual(note_msgs[1].device_serial, note_entities[0].device_serial)
    self.assertEqual(note_msgs[1].user, note_entities[0].user)
    self.assertEqual(note_msgs[1].timestamp,
                     note_entities[0].timestamp)
    self.assertEqual(note_msgs[1].message, note_entities[0].message)
    self.assertEqual(note_msgs[1].offline_reason,
                     note_entities[0].offline_reason)
    self.assertEqual(note_msgs[1].recovery_action,
                     note_entities[0].recovery_action)

  def testBatchGetDeviceNotes(self):
    note_entities = [
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            device_serial='device_1',
            user='user1',
            timestamp=datetime.datetime(1928, 1, 1),
            message='message_1',
            offline_reason='offline_reason_1',
            recovery_action='recovery_action_1'),
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            device_serial='device_1',
            user='user2',
            timestamp=datetime.datetime(1918, 1, 1),
            message='message_2',
            offline_reason='offline_reason_2',
            recovery_action='recovery_action_2'),
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            device_serial='device_1',
            user='user3',
            timestamp=datetime.datetime(1988, 1, 1),
            message='message_3',
            offline_reason='offline_reason_3',
            recovery_action='recovery_action_3'),
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            device_serial='device_2',
            user='user4',
            timestamp=datetime.datetime(2008, 1, 1),
            message='message_4',
            offline_reason='offline_reason_4',
            recovery_action='recovery_action_4'),
    ]
    keys = ndb.put_multi(note_entities)

    # note4 will not be included in response because device_serial is unmatched.
    api_request = {
        'device_serial': 'device_1',
        'ids': [keys[0].id(), keys[1].id(), keys[3].id()],
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.BatchGetNotes', api_request)
    device_note_collection_msg = protojson.decode_message(
        api_messages.NoteCollection, api_response.body)
    note_msgs = device_note_collection_msg.notes
    self.assertEqual(2, len(note_msgs))
    self.assertEqual(note_msgs[0].device_serial, note_entities[0].device_serial)
    self.assertEqual(note_msgs[0].user, note_entities[0].user)
    self.assertEqual(note_msgs[0].timestamp,
                     note_entities[0].timestamp)
    self.assertEqual(note_msgs[0].message, note_entities[0].message)
    self.assertEqual(note_msgs[0].offline_reason,
                     note_entities[0].offline_reason)
    self.assertEqual(note_msgs[0].recovery_action,
                     note_entities[0].recovery_action)
    self.assertEqual(note_msgs[1].device_serial, note_entities[1].device_serial)
    self.assertEqual(note_msgs[1].user, note_entities[1].user)
    self.assertEqual(note_msgs[1].timestamp,
                     note_entities[1].timestamp)
    self.assertEqual(note_msgs[1].message, note_entities[1].message)
    self.assertEqual(note_msgs[1].offline_reason,
                     note_entities[1].offline_reason)
    self.assertEqual(note_msgs[1].recovery_action,
                     note_entities[1].recovery_action)

  def testListDeviceHistories(self):
    """Tests ListHistories returns all device histories."""
    device_manager._CreateDeviceInfoHistory(self.ndb_device_0).put()
    self.ndb_device_0.state = common.DeviceState.ALLOCATED
    self.ndb_device_0.timestamp += datetime.timedelta(hours=1)
    device_manager._CreateDeviceInfoHistory(self.ndb_device_0).put()
    self.ndb_device_0.state = common.DeviceState.GONE
    self.ndb_device_0.timestamp += datetime.timedelta(hours=1)
    device_manager._CreateDeviceInfoHistory(self.ndb_device_0).put()
    api_request = {'device_serial': self.ndb_device_0.device_serial}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListHistories', api_request)
    device_history_collection = protojson.decode_message(
        api_messages.DeviceInfoHistoryCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(3, len(device_history_collection.histories))
    self.assertEqual(common.DeviceState.GONE,
                     device_history_collection.histories[0].state)
    self.assertEqual(common.DeviceState.ALLOCATED,
                     device_history_collection.histories[1].state)
    self.assertEqual(common.DeviceState.AVAILABLE,
                     device_history_collection.histories[2].state)

  def testListDeviceHistories_withCursorAndOffsetAndBackwards(self):
    """Tests ListHistories returns histories applying a count and offset."""
    device_manager._CreateDeviceInfoHistory(self.ndb_device_0).put()
    self.ndb_device_0.state = common.DeviceState.ALLOCATED
    self.ndb_device_0.timestamp += datetime.timedelta(hours=1)
    device_manager._CreateDeviceInfoHistory(self.ndb_device_0).put()
    self.ndb_device_0.state = common.DeviceState.GONE
    self.ndb_device_0.timestamp += datetime.timedelta(hours=1)
    device_manager._CreateDeviceInfoHistory(self.ndb_device_0).put()
    # fetch first page
    api_request = {'device_serial': self.ndb_device_0.device_serial, 'count': 2}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListHistories', api_request)
    device_history_collection = protojson.decode_message(
        api_messages.DeviceInfoHistoryCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(device_history_collection.histories))
    self.assertEqual(common.DeviceState.GONE,
                     device_history_collection.histories[0].state)
    self.assertEqual(common.DeviceState.ALLOCATED,
                     device_history_collection.histories[1].state)
    self.assertIsNotNone(device_history_collection.next_cursor)  # has next

    # fetch next page
    api_request = {
        'device_serial': self.ndb_device_0.device_serial,
        'count': 2,
        'cursor': device_history_collection.next_cursor
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListHistories', api_request)
    device_history_collection = protojson.decode_message(
        api_messages.DeviceInfoHistoryCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(device_history_collection.histories))
    self.assertIsNone(device_history_collection.next_cursor)
    self.assertIsNotNone(device_history_collection.prev_cursor)  # has previous

    # fetch previous page (same as first page)
    api_request = {
        'device_serial': self.ndb_device_0.device_serial,
        'count': 2,
        'cursor': device_history_collection.prev_cursor,
        'backwards': True
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterDeviceApi.ListHistories', api_request)
    device_history_collection = protojson.decode_message(
        api_messages.DeviceInfoHistoryCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(device_history_collection.histories))
    self.assertEqual(common.DeviceState.GONE,
                     device_history_collection.histories[0].state)
    self.assertEqual(common.DeviceState.ALLOCATED,
                     device_history_collection.histories[1].state)
    self.assertIsNotNone(device_history_collection.next_cursor)


if __name__ == '__main__':
  unittest.main()
