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
"""Tests for cluster_host_api."""

import datetime
import unittest

import mock
from protorpc import protojson

from tradefed_cluster.util import ndb_shim as ndb

from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import device_manager
from tradefed_cluster import note_manager


class ClusterHostApiTest(api_test.ApiTest):

  TIMESTAMP = datetime.datetime(2015, 10, 9)

  def setUp(self):
    api_test.ApiTest.setUp(self)
    self.ndb_host_0 = datastore_test_util.CreateHost(
        cluster='free',
        hostname='host_0',
        timestamp=self.TIMESTAMP,
        host_state=api_messages.HostState.RUNNING,
        device_count_timestamp=self.TIMESTAMP,
        device_count_summaries=[
            datastore_test_util.CreateDeviceCountSummary(
                run_target='run_target1', available=3, allocated=7)
        ])
    self.ndb_device_0 = datastore_test_util.CreateDevice(
        cluster='free',
        hostname='host_0',
        device_serial='device_0',
        device_type=api_messages.DeviceTypeMessage.EMULATOR,
        battery_level='100',
        hidden=True)
    self.ndb_device_1 = datastore_test_util.CreateDevice(
        cluster='free',
        hostname='host_0',
        device_serial='device_1',
        device_type=api_messages.DeviceTypeMessage.EMULATOR,
        timestamp=self.TIMESTAMP)

    self.ndb_host_1 = datastore_test_util.CreateHost(
        cluster='paid',
        hostname='host_1',
        device_count_timestamp=self.TIMESTAMP,
        hidden=True,
        device_count_summaries=[
            datastore_test_util.CreateDeviceCountSummary(
                run_target='run_target1', available=1, allocated=1)
        ])
    self.ndb_device_2 = datastore_test_util.CreateDevice(
        cluster='paid',
        hostname='host_1',
        device_serial='device_2',
        device_type=api_messages.DeviceTypeMessage.EMULATOR,
        hidden=True)
    self.ndb_device_3 = datastore_test_util.CreateDevice(
        cluster='paid',
        hostname='host_1',
        device_serial='device_3',
        device_type=api_messages.DeviceTypeMessage.EMULATOR,
        hidden=True)

    self.ndb_host_2 = datastore_test_util.CreateHost(
        cluster='free',
        hostname='host_2',
        lab_name='alab',
        assignee='auser',
        device_count_timestamp=self.TIMESTAMP,
        device_count_summaries=[
            datastore_test_util.CreateDeviceCountSummary(
                run_target='run_target1', offline=4, available=0, allocated=1)
        ])
    self.ndb_host_3 = datastore_test_util.CreateHost(
        cluster='paid', hostname='host_3', lab_name='alab')
    self.note = datastore_entities.Note(
        type=common.NoteType.HOST_NOTE,
        hostname='host_0',
        user='user0',
        timestamp=self.TIMESTAMP,
        message='Hello, World')
    self.note.put()

  def AssertEqualHostInfo(self, host_entity, host_message):
    # Helper to compare host entities and messages
    self.assertEqual(host_entity.hostname, host_message.hostname)
    self.assertEqual(host_entity.total_devices, host_message.total_devices)
    self.assertEqual(host_entity.offline_devices, host_message.offline_devices)
    self.assertEqual(host_entity.available_devices,
                     host_message.available_devices)
    self.assertEqual(host_entity.allocated_devices,
                     host_message.allocated_devices)
    self.assertEqual(host_entity.device_count_timestamp,
                     host_message.device_count_timestamp)
    self.assertEqual(host_entity.physical_cluster, host_message.cluster)
    self.assertEqual(host_entity.hidden, host_message.hidden)
    self.assertEqual(host_entity.test_runner_version,
                     host_message.test_runner_version)
    self.assertEqual(host_entity.test_runner, host_message.test_runner)
    self.assertEqual(host_entity.test_runner_version,
                     host_message.test_harness_version)
    self.assertEqual(host_entity.test_runner, host_message.test_harness)

  def testListHosts(self):
    """Tests ListHosts returns all visible hosts."""
    api_request = {}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(3, len(host_collection.host_infos))
    for host in host_collection.host_infos:
      self.assertEqual(0, len(host.device_infos))
      if host.hostname == 'host_0':
        self.AssertEqualHostInfo(self.ndb_host_0, host)
      elif host.hostname == 'host_2':
        self.AssertEqualHostInfo(self.ndb_host_2, host)
      elif host.hostname == 'host_3':
        self.AssertEqualHostInfo(self.ndb_host_3, host)
      else:
        # host_1 is hidden and should not be reported
        self.fail()

  def testListHosts_shouldContainDevices(self):
    """Tests ListHosts returns hosts and include visible devices."""
    api_request = {'include_devices': True}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    for host in host_collection.host_infos:
      if host.hostname == 'host_0':
        self.AssertEqualHostInfo(self.ndb_host_0, host)
        self.assertEqual(1, len(host.device_infos))
      elif host.hostname == 'host_2':
        self.AssertEqualHostInfo(self.ndb_host_2, host)
        self.assertEqual(0, len(host.device_infos))
      elif host.hostname == 'host_3':
        self.AssertEqualHostInfo(self.ndb_host_3, host)
        self.assertEqual(0, len(host.device_infos))
      else:
        # host_1 is hidden and should not be reported
        self.fail()

  def testListHosts_includeHidden(self):
    """Tests ListHosts returns all hosts includding hidden and devices."""
    api_request = {'include_hidden': True, 'include_devices': True}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(4, len(host_collection.host_infos))
    for host in host_collection.host_infos:
      if host.hostname == 'host_0':
        self.AssertEqualHostInfo(self.ndb_host_0, host)
        self.assertEqual(2, len(host.device_infos))
      elif host.hostname == 'host_1':
        self.AssertEqualHostInfo(self.ndb_host_1, host)
        self.assertEqual(2, len(host.device_infos))
      elif host.hostname == 'host_2':
        self.AssertEqualHostInfo(self.ndb_host_2, host)
        self.assertEqual(0, len(host.device_infos))
      elif host.hostname == 'host_3':
        self.AssertEqualHostInfo(self.ndb_host_3, host)
      else:
        self.fail()

  def testListHosts_withOffset(self):
    """Tests ListHosts returns hosts for a count and offset."""
    api_request = {'count': '1'}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(host_collection.host_infos))
    self.assertEqual(0, len(host_collection.host_infos[0].device_infos))

  def testListHosts_withCursorAndOffset(self):
    """Tests ListHosts returns hosts for a count and offset."""
    api_request = {'count': '2'}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertTrue(host_collection.more)
    cursor = host_collection.next_cursor
    self.assertIsNotNone(cursor)
    self.assertEqual(2, len(host_collection.host_infos))
    self.assertEqual('host_0', host_collection.host_infos[0].hostname)
    self.assertEqual('host_2', host_collection.host_infos[1].hostname)
    self.assertEqual(0, len(host_collection.host_infos[0].device_infos))

    api_request = {'count': '2', 'cursor': cursor}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertFalse(host_collection.more)
    self.assertIsNone(host_collection.next_cursor)
    self.assertEqual(1, len(host_collection.host_infos))
    self.assertEqual('host_3', host_collection.host_infos[0].hostname)

  def testListHosts_withDevicesOffset(self):
    """Tests ListHosts returns hosts with devices for a count and offset."""
    api_request = {'include_devices': True, 'count': '1'}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(host_collection.host_infos))
    self.assertEqual(1, len(host_collection.host_infos[0].device_infos))

  def testListHosts_includeHiddenWithCount(self):
    """Tests ListHosts includes hidden applying a count and offset."""
    api_request = {'include_hidden': True, 'count': '1'}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(host_collection.host_infos))
    self.assertEqual(0, len(host_collection.host_infos[0].device_infos))

  def testListHosts_includeHiddenWithDevicesCount(self):
    """Tests ListHosts includes hidden applying a count and offset."""
    api_request = {
        'include_devices': True,
        'include_hidden': True,
        'count': '1'
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(host_collection.host_infos))
    self.assertEqual(2, len(host_collection.host_infos[0].device_infos))

  def testListHosts_filterByLab(self):
    """Tests ListHosts returns hosts the under a lab."""
    api_request = {'lab_name': 'alab'}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(host_collection.host_infos))
    for host in host_collection.host_infos:
      self.assertEqual('alab', host.lab_name)

  def testListHosts_filterByAssignee(self):
    """Tests ListHosts returns hosts that assign to certain user."""
    api_request = {'assignee': 'auser'}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(host_collection.host_infos))
    for host in host_collection.host_infos:
      self.assertEqual('auser', host.assignee)

  def testListHosts_filterByIsBad(self):
    """Tests ListHosts returns hosts that is bad."""
    api_request = {'is_bad': True}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(host_collection.host_infos))
    for host in host_collection.host_infos:
      self.assertTrue(host.is_bad)

  def testListHosts_filterByHostGroups(self):
    """Tests ListHosts returns hosts the under host groups."""
    api_request = {'host_groups': ['paid']}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(host_collection.host_infos))
    for host in host_collection.host_infos:
      self.assertEqual('paid', host.host_group)

  def testListHosts_filterByHostnames(self):
    """Tests ListHosts returns hosts the under hostnames."""
    api_request = {'hostnames': ['host_2']}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(host_collection.host_infos))
    for host in host_collection.host_infos:
      self.assertEqual('host_2', host.hostname)

  def testListHosts_filterByTestHarness(self):
    """Tests ListHosts returns hosts the under a test harness."""
    mh_host = datastore_test_util.CreateHost(
        cluster='mh_cluster',
        hostname='mh_host',
        lab_name='mh_lab',
        test_runner='MH',
        test_runner_version='v1')
    mh_host.put()
    api_request = {'test_harness': 'MH'}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(host_collection.host_infos))
    self.AssertEqualHostInfo(mh_host, host_collection.host_infos[0])

  def testListHosts_filterByMultiTestHarness(self):
    """Tests ListHosts returns hosts the under multi test harness."""
    mh_host = datastore_test_util.CreateHost(
        cluster='mh_cluster',
        hostname='mh_host',
        lab_name='mh_lab',
        test_runner='MH',
        test_runner_version='v1')
    mh_host.put()
    goats_host = datastore_test_util.CreateHost(
        cluster='goats_cluster',
        hostname='goats_host',
        lab_name='goats_lab',
        test_runner='GOATS',
        test_runner_version='v3.2')
    goats_host.put()
    api_request = {'test_harness': ['MH', 'tradefed']}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(4, len(host_collection.host_infos))

  def testListHosts_filterByMultiTestHarnessVersions(self):
    """Tests ListHosts returns hosts the under multi test harness versions."""
    mh_host = datastore_test_util.CreateHost(
        cluster='mh_cluster',
        hostname='mh_host',
        lab_name='mh_lab',
        test_runner='MH',
        test_runner_version='v1')
    mh_host.put()
    goats_host = datastore_test_util.CreateHost(
        cluster='goats_cluster',
        hostname='goats_host',
        lab_name='goats_lab',
        test_runner='GOATS',
        test_runner_version='v3.2')
    goats_host.put()
    api_request = {'test_harness_versions': ['v1', 'v3.2']}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(host_collection.host_infos))

  def testListHosts_filterByPools(self):
    """Tests ListHosts returns hosts the under pools."""
    api_request = {'pools': ['paid']}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(host_collection.host_infos))
    for host in host_collection.host_infos:
      self.assertEqual('paid', host.host_group)

  def testListHosts_filterByHostStates(self):
    """Tests ListHosts returns hosts the under host states."""
    host_4 = datastore_test_util.CreateHost(
        cluster='paid',
        hostname='host_4',
        lab_name='alab',
        host_state=api_messages.HostState.KILLING,
    )
    host_4.put()
    api_request = {'host_states': ['KILLING', 'RUNNING']}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(host_collection.host_infos))
    self.assertEqual('RUNNING', host_collection.host_infos[0].host_state)
    self.assertEqual('KILLING', host_collection.host_infos[1].host_state)

  def testListHosts_filterByExtraInfo(self):
    """Tests ListHosts returns hosts the under extra info."""
    extra_info_0 = {}
    extra_info_0['url'] = 'abc.com'
    extra_info_0['say'] = 'hello'
    host_01 = datastore_test_util.CreateHost(
        cluster='free',
        hostname='host_01',
        host_state=api_messages.HostState.RUNNING,
        extra_info=extra_info_0)
    api_request = {'flated_extra_info': 'url:abc.com'}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListHosts',
                                          api_request)
    host_collection = protojson.decode_message(api_messages.HostInfoCollection,
                                               api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(host_collection.host_infos))
    self.assertEqual(host_collection.host_infos[0].hostname, host_01.hostname)

  @mock.patch.object(note_manager, 'PublishMessage')
  def testAddOrUpdateHostNote_addWithTextOfflineReasonAndRecoveryAction(
      self, mock_publish_host_note_message):
    """Tests adding a non-existing host note."""
    lab_name = 'lab-name-1'
    api_request = {
        'hostname': self.ndb_host_0.hostname,
        'user': 'user-1',
        'message': 'message-1',
        'offline_reason': 'offline-reason-1',
        'recovery_action': 'recovery-action-1',
        'lab_name': lab_name,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterHostApi.AddOrUpdateNote', api_request)
    self.assertEqual('200 OK', api_response.status)
    host_note = protojson.decode_message(api_messages.Note,
                                         api_response.body)
    host_note_event = api_messages.NoteEvent(
        note=host_note, lab_name=lab_name)
    # Assert datastore id is generated.
    self.assertIsNotNone(host_note.id)
    # Assert fields equal.
    self.assertEqual(api_request['hostname'], host_note.hostname)
    self.assertEqual(api_request['user'], host_note.user)
    self.assertEqual(api_request['message'], host_note.message)
    self.assertEqual(api_request['offline_reason'], host_note.offline_reason)
    self.assertEqual(api_request['recovery_action'], host_note.recovery_action)
    # Assert PredefinedMessage entities are written into datastore.
    self.assertIsNotNone(datastore_entities.PredefinedMessage.query().filter(
        datastore_entities.PredefinedMessage.content ==
        api_request['offline_reason']).get())
    self.assertIsNotNone(datastore_entities.PredefinedMessage.query().filter(
        datastore_entities.PredefinedMessage.content ==
        api_request['recovery_action']).get())
    # Side Effect: Assert HostInfoHistory is written into datastore.
    histories = list(
        datastore_entities.HostInfoHistory.query(
            datastore_entities.HostInfoHistory.hostname ==
            self.ndb_host_0.hostname).fetch())
    self.assertEqual(1, len(histories))
    self.assertEqual(int(host_note.id), histories[0].extra_info['host_note_id'])
    mock_publish_host_note_message.assert_called_once_with(
        host_note_event, common.PublishEventType.HOST_NOTE_EVENT)

  @mock.patch.object(note_manager, 'PublishMessage')
  def testAddOrUpdateHostNote_updateWithTextOfflineReasonAndRecoveryAction(
      self, mock_publish_host_note_message):
    """Tests updating an existing host note."""
    api_request_1 = {
        'hostname': self.ndb_host_0.hostname,
        'user': 'user-1',
        'message': 'message-1',
        'offline_reason': 'offline-reason-1',
        'recovery_action': 'recovery-action-1',
        'lab_name': 'lab-name-1',
    }
    api_response_1 = self.testapp.post_json(
        '/_ah/api/ClusterHostApi.AddOrUpdateNote', api_request_1)
    self.assertEqual('200 OK', api_response_1.status)
    host_note_1 = protojson.decode_message(api_messages.Note,
                                           api_response_1.body)
    new_lab_name = 'lab-name-2'
    api_request_2 = {
        'id': int(host_note_1.id),
        'hostname': self.ndb_host_0.hostname,
        'user': 'user-2',
        'message': 'message-2',
        'offline_reason': 'offline-reason-2',
        'recovery_action': 'recovery-action-2',
        'lab_name': new_lab_name,
    }
    api_response_2 = self.testapp.post_json(
        '/_ah/api/ClusterHostApi.AddOrUpdateNote', api_request_2)
    self.assertEqual('200 OK', api_response_1.status)
    host_note_2 = protojson.decode_message(api_messages.Note,
                                           api_response_2.body)
    host_note_event = api_messages.NoteEvent(
        note=host_note_2, lab_name=new_lab_name)
    # Assert two requests modified the same datastore entity.
    self.assertEqual(host_note_1.id, host_note_2.id)
    # Assert the fields finally equal to the ones in the 2nd request.
    self.assertEqual(api_request_2['hostname'], host_note_2.hostname)
    self.assertEqual(api_request_2['user'], host_note_2.user)
    self.assertEqual(api_request_2['message'], host_note_2.message)
    self.assertEqual(api_request_2['offline_reason'],
                     host_note_2.offline_reason)
    self.assertEqual(api_request_2['recovery_action'],
                     host_note_2.recovery_action)
    # Side Effect: Assert HostInfoHistory is written into datastore.
    histories = list(
        datastore_entities.HostInfoHistory.query(
            datastore_entities.HostInfoHistory.hostname ==
            self.ndb_host_0.hostname).fetch())
    self.assertEqual(1, len(histories))
    self.assertEqual(int(host_note_1.id),
                     histories[0].extra_info['host_note_id'])
    mock_publish_host_note_message.assert_called_with(
        host_note_event, common.PublishEventType.HOST_NOTE_EVENT)

  @mock.patch.object(note_manager, 'PublishMessage')
  def testAddOrUpdateHostNote_UpdateWithDedupTextPredefinedMessage(
      self, mock_publish_host_note_message):
    """Tests updating an existing host note."""
    api_request_1 = {
        'hostname': self.ndb_host_0.hostname,
        'user': 'user-1',
        'message': 'message-1',
        'offline_reason': 'offline-reason-1',
        'recovery_action': 'recovery-action-1',
        'lab_name': 'lab-name-1',
    }
    api_response_1 = self.testapp.post_json(
        '/_ah/api/ClusterHostApi.AddOrUpdateNote', api_request_1)
    self.assertEqual('200 OK', api_response_1.status)
    host_note_1 = protojson.decode_message(api_messages.HostNote,
                                           api_response_1.body)
    api_request_2 = {
        'id': int(host_note_1.id),
        'hostname': self.ndb_host_0.hostname,
        'user': 'user-2',
        'message': 'message-2',
        'offline_reason': 'offline-reason-1',
        'recovery_action': 'recovery-action-1',
        'lab_name': 'lab-name-1',
    }
    api_response_2 = self.testapp.post_json(
        '/_ah/api/ClusterHostApi.AddOrUpdateNote', api_request_2)
    self.assertEqual('200 OK', api_response_1.status)
    host_note_2 = protojson.decode_message(api_messages.HostNote,
                                           api_response_2.body)
    # Assert two requests modified the same datastore entity.
    self.assertEqual(host_note_1.id, host_note_2.id)
    # Assert the fields finally equal to the ones in the 2nd request.
    self.assertEqual(api_request_2['hostname'],
                     host_note_2.hostname)
    self.assertEqual(api_request_2['user'], host_note_2.user)
    self.assertEqual(api_request_2['message'], host_note_2.message)
    self.assertEqual(api_request_2['offline_reason'],
                     host_note_2.offline_reason)
    self.assertEqual(api_request_2['recovery_action'],
                     host_note_2.recovery_action)
    # Side Effect: Assert PredefinedMessage is created only in first call.
    predefine_messages = list(datastore_entities.PredefinedMessage.query(
        datastore_entities.PredefinedMessage.lab_name == 'lab-name-1').fetch())
    self.assertEqual(2, len(predefine_messages))

  @mock.patch.object(note_manager, 'PublishMessage')
  def testAddOrUpdateHostNote_addWithIdOfflineReasonAndRecoveryAction(
      self, mock_publish_host_note_message):
    """Tests adding a host note with existing predefined messages."""
    offline_reason = 'offline-reason'
    recovery_action = 'recovery-action'
    lab_name = 'lab-name'
    predefined_message_entities = [
        datastore_entities.PredefinedMessage(
            key=ndb.Key(datastore_entities.PredefinedMessage, 111),
            lab_name=lab_name,
            type=api_messages.PredefinedMessageType.HOST_OFFLINE_REASON,
            content=offline_reason,
            used_count=2),
        datastore_entities.PredefinedMessage(
            key=ndb.Key(datastore_entities.PredefinedMessage, 222),
            lab_name=lab_name,
            type=api_messages.PredefinedMessageType.HOST_RECOVERY_ACTION,
            content=recovery_action,
            used_count=5),
    ]
    offline_reason_key, recovery_action_key = ndb.put_multi(
        predefined_message_entities)
    api_request = {
        'hostname': self.ndb_host_0.hostname,
        'user': 'user-1',
        'message': 'message-1',
        'offline_reason_id': 111,
        'recovery_action_id': 222,
        'lab_name': lab_name,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterHostApi.AddOrUpdateNote', api_request)
    self.assertEqual('200 OK', api_response.status)
    host_note = protojson.decode_message(api_messages.Note,
                                         api_response.body)
    host_note_event = api_messages.NoteEvent(
        note=host_note, lab_name=lab_name)
    # Assert datastore id is generated.
    self.assertIsNotNone(host_note.id)
    # Assert fields equal.
    self.assertEqual(api_request['hostname'], host_note.hostname)
    self.assertEqual(api_request['user'], host_note.user)
    self.assertEqual(api_request['message'], host_note.message)
    self.assertEqual(offline_reason, host_note.offline_reason)
    self.assertEqual(recovery_action, host_note.recovery_action)
    # Assert PredefinedMessage used_count fields are updated.
    self.assertEqual(3, offline_reason_key.get().used_count)
    self.assertEqual(6, recovery_action_key.get().used_count)
    # Side Effect: Assert HostInfoHistory is written into datastore.
    histories = list(
        datastore_entities.HostInfoHistory.query(
            datastore_entities.HostInfoHistory.hostname ==
            self.ndb_host_0.hostname).fetch())
    self.assertEqual(1, len(histories))
    self.assertEqual(int(host_note.id), histories[0].extra_info['host_note_id'])
    mock_publish_host_note_message.assert_called_once_with(
        host_note_event, common.PublishEventType.HOST_NOTE_EVENT)

  @mock.patch.object(note_manager, 'PublishMessage')
  def testAddOrUpdateHostNote_InvalidIdOfflineReasonAndRecoveryAction(
      self, mock_publish_host_note_message):
    """Tests adding a Host note with existing predefined messages."""
    offline_reason = 'offline-reason'
    recovery_action = 'recovery-action'
    lab_name = 'lab-name'
    predefined_message_entities = [
        datastore_entities.PredefinedMessage(
            key=ndb.Key(datastore_entities.PredefinedMessage, 111),
            lab_name=lab_name,
            type=api_messages.PredefinedMessageType.HOST_OFFLINE_REASON,
            content=offline_reason,
            used_count=2),
        datastore_entities.PredefinedMessage(
            key=ndb.Key(datastore_entities.PredefinedMessage, 222),
            lab_name=lab_name,
            type=api_messages.PredefinedMessageType.HOST_RECOVERY_ACTION,
            content=recovery_action,
            used_count=5),
    ]
    ndb.put_multi(predefined_message_entities)

    # Invalid recovery action.
    api_request = {
        'hostname': self.ndb_host_0.hostname,
        'user': 'user-1',
        'message': 'message-1',
        'recovery_action_id': 111,
        'lab_name': lab_name,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterHostApi.AddOrUpdateNote',
        api_request,
        expect_errors=True)
    self.assertEqual('400 Bad Request', api_response.status)
    # Non-existing offline reason.
    api_request = {
        'hostname': self.ndb_host_0.hostname,
        'user': 'user-1',
        'message': 'message-1',
        'offline_reason_id': 333,
        'lab_name': lab_name,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterHostApi.AddOrUpdateNote',
        api_request,
        expect_errors=True)
    self.assertEqual('400 Bad Request', api_response.status)

  def testGetHost(self):
    """Tests GetHost."""
    api_request = {'hostname': self.ndb_host_0.hostname}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.GetHost',
                                          api_request)
    host = protojson.decode_message(api_messages.HostInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.AssertEqualHostInfo(self.ndb_host_0, host)
    self.assertEqual(1, len(host.device_infos))
    self.assertEqual(self.ndb_device_1.device_serial,
                     host.device_infos[0].device_serial)
    self.assertEqual(0, len(host.notes))

  def testGetHost_noDevices(self):
    """Tests GetHost when a host has no devices."""
    api_request = {'hostname': self.ndb_host_2.hostname}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.GetHost',
                                          api_request)
    host = protojson.decode_message(api_messages.HostInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.AssertEqualHostInfo(self.ndb_host_2, host)
    self.assertEqual(0, len(host.device_infos))

  def testGetHost_includeHidden(self):
    """Tests GetHost including hidden devices."""
    api_request = {'hostname': self.ndb_host_0.hostname, 'include_hidden': True}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.GetHost',
                                          api_request)
    host = protojson.decode_message(api_messages.HostInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.AssertEqualHostInfo(self.ndb_host_0, host)
    self.assertEqual(2, len(host.device_infos))
    self.assertItemsEqual(['device_0', 'device_1'],
                          [d.device_serial for d in host.device_infos])
    self.assertEqual(0, len(host.notes))

  def testGetHost_includeNotes(self):
    """Tests GetHost including notes when they are available."""
    api_request = {'hostname': self.ndb_host_0.hostname, 'include_notes': True}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.GetHost',
                                          api_request)
    host = protojson.decode_message(api_messages.HostInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.AssertEqualHostInfo(self.ndb_host_0, host)
    self.assertEqual(1, len(host.notes))
    self.assertEqual(self.note.user, host.notes[0].user)
    self.assertEqual(self.note.timestamp, host.notes[0].timestamp)
    self.assertEqual(self.note.message, host.notes[0].message)

  def testGetHost_includeNotesNoneAvailable(self):
    """Tests GetHost including notes when none are available."""
    api_request = {'hostname': self.ndb_host_1.hostname, 'include_notes': True}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.GetHost',
                                          api_request)
    host = protojson.decode_message(api_messages.HostInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.AssertEqualHostInfo(self.ndb_host_1, host)
    self.assertEqual(0, len(host.notes))

  def testGetHost_includeHistoryState(self):
    """Tests GetHost including state history."""
    timestamp1 = datetime.datetime(2015, 10, 9, 1)
    timestamp2 = datetime.datetime(2015, 10, 9, 2)
    state1 = api_messages.HostState.RUNNING
    state2 = api_messages.HostState.GONE
    history_key1 = ndb.Key(
        datastore_entities.HostStateHistory,
        self.ndb_host_1.hostname + str(timestamp1),
        parent=self.ndb_host_1.key)
    ndb_host_1_state_history1 = datastore_entities.HostStateHistory(
        key=history_key1,
        hostname=self.ndb_host_1.hostname,
        timestamp=timestamp1,
        state=state1)
    ndb_host_1_state_history1.put()
    history_key2 = ndb.Key(
        datastore_entities.HostStateHistory,
        self.ndb_host_1.hostname + str(timestamp2),
        parent=self.ndb_host_1.key)
    ndb_host_1_state_history2 = datastore_entities.HostStateHistory(
        key=history_key2,
        hostname=self.ndb_host_1.hostname,
        timestamp=timestamp2,
        state=state2)
    ndb_host_1_state_history2.put()
    api_request = {
        'hostname': self.ndb_host_1.hostname,
        'include_host_state_history': True
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.GetHost',
                                          api_request)
    host = protojson.decode_message(api_messages.HostInfo, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.AssertEqualHostInfo(self.ndb_host_1, host)
    self.assertEqual(2, len(host.state_history))
    self.assertEqual(host.state_history[0].state, state2.name)
    self.assertEqual(host.state_history[0].timestamp, timestamp2)
    self.assertEqual(host.state_history[1].state, state1.name)
    self.assertEqual(host.state_history[1].timestamp, timestamp1)

  def testNewNote_withNoneExisting(self):
    """Tests adding a note to a host when none exist already."""
    user = 'some_user'
    timestamp = datetime.datetime(2015, 10, 18, 20, 46)
    message = 'The Message'
    offline_reason = 'Wires are disconnected'
    recovery_action = 'Press a button'
    api_request = {
        'hostname': self.ndb_host_1.hostname,
        'user': user,
        'timestamp': timestamp.isoformat(),
        'message': message,
        'offline_reason': offline_reason,
        'recovery_action': recovery_action,
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.NewNote',
                                          api_request)
    self.assertEqual('200 OK', api_response.status)
    api_request = {'hostname': self.ndb_host_1.hostname, 'include_notes': True}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.GetHost',
                                          api_request)
    host = protojson.decode_message(api_messages.HostInfo, api_response.body)
    self.assertEqual(1, len(host.notes))
    self.assertEqual(user, host.notes[0].user)
    self.assertEqual(timestamp, host.notes[0].timestamp)
    self.assertEqual(message, host.notes[0].message)
    self.assertEqual(offline_reason, host.notes[0].offline_reason)
    self.assertEqual(recovery_action, host.notes[0].recovery_action)

  def testNewNote_withExisting(self):
    """Tests adding a note to a host when one already exists."""
    user = 'some_user'
    timestamp = datetime.datetime(2015, 10, 18, 20, 46)
    message = 'The Message'
    api_request = {
        'hostname': self.ndb_host_0.hostname,
        'user': user,
        'timestamp': timestamp.isoformat(),
        'message': message
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.NewNote',
                                          api_request)
    self.assertEqual('200 OK', api_response.status)
    # Query the same host again. Notes should be sorted.
    api_request = {'hostname': self.ndb_host_0.hostname, 'include_notes': True}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.GetHost',
                                          api_request)
    host = protojson.decode_message(api_messages.HostInfo, api_response.body)
    self.assertEqual(2, len(host.notes))
    self.assertEqual(user, host.notes[0].user)
    self.assertEqual(timestamp, host.notes[0].timestamp)
    self.assertEqual(message, host.notes[0].message)
    self.assertEqual(self.note.user, host.notes[1].user)
    self.assertEqual(self.note.timestamp, host.notes[1].timestamp)
    self.assertEqual(self.note.message, host.notes[1].message)

  def testRemove(self):
    """Tests Remove."""
    # Check that the existing host is not set to hidden
    api_request = {'hostname': self.ndb_host_0.hostname}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.GetHost',
                                          api_request)
    host = protojson.decode_message(api_messages.HostInfo, api_response.body)
    self.assertFalse(host.hidden)
    # Call Remove
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.Remove',
                                          api_request)
    host = protojson.decode_message(api_messages.HostInfo, api_response.body)
    # Verify API response
    self.assertEqual('200 OK', api_response.status)
    self.assertTrue(host.hidden)
    # Verify by retrieving the host
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.GetHost',
                                          api_request)
    host = protojson.decode_message(api_messages.HostInfo, api_response.body)
    self.assertTrue(host.hidden)
    for device in host.device_infos:
      # hide a host will also hide all devices.
      self.assertTrue(device.hidden)

  def testRemove_missingHost(self):
    """Test Remove with an invalid hostname."""
    api_request = {'hostname': 'some-fake-hostname'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterHostApi.Remove', api_request, expect_errors=True)
    self.assertEqual('404 Not Found', api_response.status)

  def testRestore(self):
    """Tests Restore."""
    # Check that the existing host is set to hidden
    api_request = {'hostname': self.ndb_host_1.hostname}
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.GetHost',
                                          api_request)
    host = protojson.decode_message(api_messages.HostInfo, api_response.body)
    self.assertTrue(host.hidden)
    # Call Remove
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.Restore',
                                          api_request)
    host = protojson.decode_message(api_messages.HostInfo, api_response.body)
    # Verify API response
    self.assertEqual('200 OK', api_response.status)
    self.assertFalse(host.hidden)
    # Verify by retrieving the host
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.GetHost',
                                          api_request)
    host = protojson.decode_message(api_messages.HostInfo, api_response.body)
    self.assertFalse(host.hidden)
    for device in host.device_infos:
      # restore a host will not restore devices under the host.
      self.assertTrue(device.hidden)

  def testRestore_missingHost(self):
    """Test Remove with an invalid hostname."""
    api_request = {'hostname': 'some-fake-hostname'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterHostApi.Restore', api_request, expect_errors=True)
    self.assertEqual('404 Not Found', api_response.status)

  def testListHostNotes(self):
    note_entities = [
        datastore_entities.Note(
            type=common.NoteType.HOST_NOTE,
            hostname='host_1',
            user='user1',
            timestamp=datetime.datetime(1928, 1, 1),
            message='message_1',
            offline_reason='offline_reason_1',
            recovery_action='recovery_action_1'),
        datastore_entities.Note(
            type=common.NoteType.HOST_NOTE,
            hostname='host_1',
            user='user2',
            timestamp=datetime.datetime(1918, 1, 1),
            message='message_2',
            offline_reason='offline_reason_2',
            recovery_action='recovery_action_2'),
        datastore_entities.Note(
            type=common.NoteType.HOST_NOTE,
            hostname='host_1',
            user='user3',
            timestamp=datetime.datetime(1988, 1, 1),
            message='message_3',
            offline_reason='offline_reason_3',
            recovery_action='recovery_action_3'),
        datastore_entities.Note(
            type=common.NoteType.HOST_NOTE,
            hostname='host_2',
            user='user4',
            timestamp=datetime.datetime(2008, 1, 1),
            message='message_4',
            offline_reason='offline_reason_4',
            recovery_action='recovery_action_4'),
    ]
    ndb.put_multi(note_entities)

    # The result will be sorted by timestamp in descending order.  `
    api_request = {
        'hostname': 'host_1',
        'count': 2,
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListNotes',
                                          api_request)
    host_note_collection_msg = protojson.decode_message(
        api_messages.NoteCollection, api_response.body)
    self.assertTrue(host_note_collection_msg.more)
    self.assertIsNotNone(host_note_collection_msg.next_cursor)
    note_msgs = host_note_collection_msg.notes
    self.assertEqual(2, len(note_msgs))
    self.assertEqual(note_msgs[0].hostname, note_entities[2].hostname)
    self.assertEqual(note_msgs[0].user, note_entities[2].user)
    self.assertEqual(note_msgs[0].timestamp,
                     note_entities[2].timestamp)
    self.assertEqual(note_msgs[0].message, note_entities[2].message)
    self.assertEqual(note_msgs[0].offline_reason,
                     note_entities[2].offline_reason)
    self.assertEqual(note_msgs[0].recovery_action,
                     note_entities[2].recovery_action)
    self.assertEqual(note_msgs[1].hostname, note_entities[0].hostname)
    self.assertEqual(note_msgs[1].user, note_entities[0].user)
    self.assertEqual(note_msgs[1].timestamp,
                     note_entities[0].timestamp)
    self.assertEqual(note_msgs[1].message, note_entities[0].message)
    self.assertEqual(note_msgs[1].offline_reason,
                     note_entities[0].offline_reason)
    self.assertEqual(note_msgs[1].recovery_action,
                     note_entities[0].recovery_action)

  def testListHostNotes_includeDeviceNotes(self):
    note_entities = [
        datastore_entities.Note(
            type=common.NoteType.HOST_NOTE,
            hostname='host_1',
            user='user1',
            timestamp=datetime.datetime(1928, 1, 1),
            message='message_1',
            offline_reason='offline_reason_1',
            recovery_action='recovery_action_1'),
        datastore_entities.Note(
            type=common.NoteType.HOST_NOTE,
            hostname='host_1',
            user='user2',
            timestamp=datetime.datetime(1918, 1, 1),
            message='message_2',
            offline_reason='offline_reason_2',
            recovery_action='recovery_action_2'),
        datastore_entities.Note(
            type=common.NoteType.HOST_NOTE,
            hostname='host_1',
            user='user3',
            timestamp=datetime.datetime(1988, 1, 1),
            message='message_3',
            offline_reason='offline_reason_3',
            recovery_action='recovery_action_3'),
        datastore_entities.Note(
            type=common.NoteType.DEVICE_NOTE,
            hostname='host_1',
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
        'hostname': 'host_1',
        'count': 2,
        'include_device_notes': True,
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListNotes',
                                          api_request)
    host_note_collection_msg = protojson.decode_message(
        api_messages.NoteCollection, api_response.body)
    self.assertTrue(host_note_collection_msg.more)
    note_msgs = host_note_collection_msg.notes
    self.assertEqual(2, len(note_msgs))
    self.assertEqual(note_msgs[0].hostname, note_entities[3].hostname)
    self.assertEqual(note_msgs[0].user, note_entities[3].user)
    self.assertEqual(note_msgs[0].timestamp,
                     note_entities[3].timestamp)
    self.assertEqual(note_msgs[0].message, note_entities[3].message)
    self.assertEqual(note_msgs[0].offline_reason,
                     note_entities[3].offline_reason)
    self.assertEqual(note_msgs[0].recovery_action,
                     note_entities[3].recovery_action)
    self.assertEqual(note_msgs[1].hostname, note_entities[2].hostname)
    self.assertEqual(note_msgs[1].user, note_entities[2].user)
    self.assertEqual(note_msgs[1].timestamp,
                     note_entities[2].timestamp)
    self.assertEqual(note_msgs[1].message, note_entities[2].message)
    self.assertEqual(note_msgs[1].offline_reason,
                     note_entities[2].offline_reason)
    self.assertEqual(note_msgs[1].recovery_action,
                     note_entities[2].recovery_action)

    # query the second page to make sure the cursor works
    api_request = {
        'hostname': 'host_1',
        'count': 3,
        'include_device_notes': True,
        'cursor': host_note_collection_msg.next_cursor,
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListNotes',
                                          api_request)
    host_note_collection_msg = protojson.decode_message(
        api_messages.NoteCollection, api_response.body)
    self.assertTrue(host_note_collection_msg.more)
    note_msgs = host_note_collection_msg.notes
    self.assertEqual(2, len(note_msgs))
    self.assertEqual(note_msgs[0].hostname, note_entities[0].hostname)
    self.assertEqual(note_msgs[0].user, note_entities[0].user)
    self.assertEqual(note_msgs[0].timestamp,
                     note_entities[0].timestamp)
    self.assertEqual(note_msgs[0].message, note_entities[0].message)
    self.assertEqual(note_msgs[0].offline_reason,
                     note_entities[0].offline_reason)
    self.assertEqual(note_msgs[0].recovery_action,
                     note_entities[0].recovery_action)
    self.assertEqual(note_msgs[1].hostname, note_entities[1].hostname)
    self.assertEqual(note_msgs[1].user, note_entities[1].user)
    self.assertEqual(note_msgs[1].timestamp,
                     note_entities[1].timestamp)
    self.assertEqual(note_msgs[1].message, note_entities[1].message)
    self.assertEqual(note_msgs[1].offline_reason,
                     note_entities[1].offline_reason)
    self.assertEqual(note_msgs[1].recovery_action,
                     note_entities[1].recovery_action)

  def testListHostNotes_withCursorAndOffsetAndBackwards(self):
    note_entities = [
        datastore_entities.Note(
            type=common.NoteType.HOST_NOTE,
            hostname='host_1',
            user='user1',
            timestamp=datetime.datetime(1928, 1, 1),
            message='message_1',
            offline_reason='offline_reason_1',
            recovery_action='recovery_action_1'),
        datastore_entities.Note(
            type=common.NoteType.HOST_NOTE,
            hostname='host_1',
            user='user2',
            timestamp=datetime.datetime(1918, 1, 1),
            message='message_2',
            offline_reason='offline_reason_2',
            recovery_action='recovery_action_2'),
        datastore_entities.Note(
            type=common.NoteType.HOST_NOTE,
            hostname='host_1',
            user='user3',
            timestamp=datetime.datetime(1988, 1, 1),
            message='message_3',
            offline_reason='offline_reason_3',
            recovery_action='recovery_action_3'),
        datastore_entities.Note(
            type=common.NoteType.HOST_NOTE,
            hostname='host_1',
            user='user4',
            timestamp=datetime.datetime(2008, 1, 1),
            message='message_4',
            offline_reason='offline_reason_4',
            recovery_action='recovery_action_4'),
    ]
    ndb.put_multi(note_entities)

    # The result will be sorted by timestamp in descending order.  `
    api_request = {
        'hostname': 'host_1',
        'count': 2,
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListNotes',
                                          api_request)
    host_note_collection_msg = protojson.decode_message(
        api_messages.NoteCollection, api_response.body)
    self.assertTrue(host_note_collection_msg.more)
    self.assertIsNotNone(host_note_collection_msg.next_cursor)
    note_msgs = host_note_collection_msg.notes
    self.assertEqual(2, len(note_msgs))
    self.assertEqual(note_msgs[0].hostname, note_entities[3].hostname)
    self.assertEqual(note_msgs[0].user, note_entities[3].user)
    self.assertEqual(note_msgs[0].timestamp,
                     note_entities[3].timestamp)
    self.assertEqual(note_msgs[0].message, note_entities[3].message)
    self.assertEqual(note_msgs[0].offline_reason,
                     note_entities[3].offline_reason)
    self.assertEqual(note_msgs[0].recovery_action,
                     note_entities[3].recovery_action)
    self.assertEqual(note_msgs[1].hostname, note_entities[2].hostname)
    self.assertEqual(note_msgs[1].user, note_entities[2].user)
    self.assertEqual(note_msgs[1].timestamp,
                     note_entities[2].timestamp)
    self.assertEqual(note_msgs[1].message, note_entities[2].message)
    self.assertEqual(note_msgs[1].offline_reason,
                     note_entities[2].offline_reason)
    self.assertEqual(note_msgs[1].recovery_action,
                     note_entities[2].recovery_action)

    # fetch next page
    api_request = {
        'hostname': 'host_1',
        'count': 2,
        'cursor': host_note_collection_msg.next_cursor,
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListNotes',
                                          api_request)
    host_note_collection_msg = protojson.decode_message(
        api_messages.NoteCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertIsNotNone(host_note_collection_msg.prev_cursor)  # has previous
    note_msgs = host_note_collection_msg.notes
    self.assertEqual(2, len(note_msgs))
    self.assertEqual(note_msgs[0].hostname, note_entities[0].hostname)
    self.assertEqual(note_msgs[0].user, note_entities[0].user)
    self.assertEqual(note_msgs[0].timestamp,
                     note_entities[0].timestamp)
    self.assertEqual(note_msgs[0].message, note_entities[0].message)
    self.assertEqual(note_msgs[0].offline_reason,
                     note_entities[0].offline_reason)
    self.assertEqual(note_msgs[0].recovery_action,
                     note_entities[0].recovery_action)
    self.assertEqual(note_msgs[1].hostname, note_entities[1].hostname)
    self.assertEqual(note_msgs[1].user, note_entities[1].user)
    self.assertEqual(note_msgs[1].timestamp,
                     note_entities[1].timestamp)
    self.assertEqual(note_msgs[1].message, note_entities[1].message)
    self.assertEqual(note_msgs[1].offline_reason,
                     note_entities[1].offline_reason)
    self.assertEqual(note_msgs[1].recovery_action,
                     note_entities[1].recovery_action)

    # fetch previous page (same as first page)
    api_request = {
        'hostname': 'host_1',
        'count': 2,
        'cursor': host_note_collection_msg.prev_cursor,
        'backwards': True,
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.ListNotes',
                                          api_request)
    host_note_collection_msg = protojson.decode_message(
        api_messages.NoteCollection, api_response.body)
    note_msgs = host_note_collection_msg.notes
    self.assertEqual(2, len(note_msgs))
    self.assertEqual(note_msgs[0].hostname, note_entities[3].hostname)
    self.assertEqual(note_msgs[0].user, note_entities[3].user)
    self.assertEqual(note_msgs[0].timestamp,
                     note_entities[3].timestamp)
    self.assertEqual(note_msgs[0].message, note_entities[3].message)
    self.assertEqual(note_msgs[0].offline_reason,
                     note_entities[3].offline_reason)
    self.assertEqual(note_msgs[0].recovery_action,
                     note_entities[3].recovery_action)
    self.assertEqual(note_msgs[1].hostname, note_entities[2].hostname)
    self.assertEqual(note_msgs[1].user, note_entities[2].user)
    self.assertEqual(note_msgs[1].timestamp,
                     note_entities[2].timestamp)
    self.assertEqual(note_msgs[1].message, note_entities[2].message)
    self.assertEqual(note_msgs[1].offline_reason,
                     note_entities[2].offline_reason)
    self.assertEqual(note_msgs[1].recovery_action,
                     note_entities[2].recovery_action)

  def testBatchGetHostNotes(self):
    note_entities = [
        datastore_entities.Note(
            type=common.NoteType.HOST_NOTE,
            hostname='host_1',
            user='user1',
            timestamp=datetime.datetime(1928, 1, 1),
            message='message_1',
            offline_reason='offline_reason_1',
            recovery_action='recovery_action_1'),
        datastore_entities.Note(
            type=common.NoteType.HOST_NOTE,
            hostname='host_1',
            user='user2',
            timestamp=datetime.datetime(1918, 1, 1),
            message='message_2',
            offline_reason='offline_reason_2',
            recovery_action='recovery_action_2'),
        datastore_entities.Note(
            type=common.NoteType.HOST_NOTE,
            hostname='host_1',
            user='user3',
            timestamp=datetime.datetime(1988, 1, 1),
            message='message_3',
            offline_reason='offline_reason_3',
            recovery_action='recovery_action_3'),
        datastore_entities.Note(
            hostname='host_2',
            user='user4',
            timestamp=datetime.datetime(2008, 1, 1),
            message='message_4',
            offline_reason='offline_reason_4',
            recovery_action='recovery_action_4'),
    ]
    keys = ndb.put_multi(note_entities)

    # The result will be sorted by timestamp in descending order.  `
    api_request = {
        'hostname': 'host_1',
        'ids': [keys[0].id(), keys[1].id(), keys[3].id()],
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterHostApi.BatchGetNotes', api_request)
    host_note_collection_msg = protojson.decode_message(
        api_messages.NoteCollection, api_response.body)
    note_msgs = host_note_collection_msg.notes
    self.assertEqual(2, len(note_msgs))
    self.assertEqual(note_msgs[0].hostname, note_entities[0].hostname)
    self.assertEqual(note_msgs[0].user, note_entities[0].user)
    self.assertEqual(note_msgs[0].timestamp,
                     note_entities[0].timestamp)
    self.assertEqual(note_msgs[0].message, note_entities[0].message)
    self.assertEqual(note_msgs[0].offline_reason,
                     note_entities[0].offline_reason)
    self.assertEqual(note_msgs[0].recovery_action,
                     note_entities[0].recovery_action)
    self.assertEqual(note_msgs[1].hostname, note_entities[1].hostname)
    self.assertEqual(note_msgs[1].user, note_entities[1].user)
    self.assertEqual(note_msgs[1].timestamp,
                     note_entities[1].timestamp)
    self.assertEqual(note_msgs[1].message, note_entities[1].message)
    self.assertEqual(note_msgs[1].offline_reason,
                     note_entities[1].offline_reason)
    self.assertEqual(note_msgs[1].recovery_action,
                     note_entities[1].recovery_action)

  def testAssign(self):
    """Tests Assign."""
    api_request = {
        'hostnames': [self.ndb_host_0.hostname, self.ndb_host_1.hostname],
        'assignee': 'assignee@example.com',
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.Assign',
                                          api_request)
    self.assertEqual('200 OK', api_response.status)
    self.ndb_host_0 = self.ndb_host_0.key.get()
    self.assertEqual('assignee@example.com', self.ndb_host_0.assignee)
    self.ndb_host_1 = self.ndb_host_1.key.get()
    self.assertEqual('assignee@example.com', self.ndb_host_1.assignee)

  def testUnassign(self):
    """Tests Unassign."""
    self.ndb_host_1.assignee = 'assignee@example.com'
    self.ndb_host_1.put()
    self.ndb_host_2.assignee = 'assignee@example.com'
    self.ndb_host_2.put()

    api_request = {
        'hostnames': [self.ndb_host_0.hostname, self.ndb_host_1.hostname],
    }
    api_response = self.testapp.post_json('/_ah/api/ClusterHostApi.Unassign',
                                          api_request)
    self.assertEqual('200 OK', api_response.status)
    self.ndb_host_0 = self.ndb_host_0.key.get()
    self.assertIsNone(self.ndb_host_0.assignee)
    self.ndb_host_1 = self.ndb_host_1.key.get()
    self.assertIsNone(self.ndb_host_1.assignee)

  def testListHostHistories(self):
    """Tests ListHistories returns all host histories."""
    device_manager._CreateHostInfoHistory(self.ndb_host_0).put()
    self.ndb_host_0.host_state = api_messages.HostState.KILLING
    self.ndb_host_0.timestamp += datetime.timedelta(hours=1)
    device_manager._CreateHostInfoHistory(self.ndb_host_0).put()
    self.ndb_host_0.host_state = api_messages.HostState.GONE
    self.ndb_host_0.timestamp += datetime.timedelta(hours=1)
    device_manager._CreateHostInfoHistory(self.ndb_host_0).put()
    api_request = {'hostname': self.ndb_host_0.hostname}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterHostApi.ListHistories', api_request)
    host_history_collection = protojson.decode_message(
        api_messages.HostInfoHistoryCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(3, len(host_history_collection.histories))
    self.assertEqual(api_messages.HostState.GONE.name,
                     host_history_collection.histories[0].host_state)
    self.assertEqual(api_messages.HostState.KILLING.name,
                     host_history_collection.histories[1].host_state)
    self.assertEqual(api_messages.HostState.RUNNING.name,
                     host_history_collection.histories[2].host_state)

  def testListHostHistories_withCursorAndOffsetAndBackwards(self):
    """Tests ListHistories returns histories applying a count and offset."""
    device_manager._CreateHostInfoHistory(self.ndb_host_0).put()
    self.ndb_host_0.host_state = api_messages.HostState.KILLING
    self.ndb_host_0.timestamp += datetime.timedelta(hours=1)
    device_manager._CreateHostInfoHistory(self.ndb_host_0).put()
    self.ndb_host_0.host_state = api_messages.HostState.GONE
    self.ndb_host_0.timestamp += datetime.timedelta(hours=1)
    device_manager._CreateHostInfoHistory(self.ndb_host_0).put()
    # fetch first page
    api_request = {'hostname': self.ndb_host_0.hostname, 'count': 2}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterHostApi.ListHistories', api_request)
    host_history_collection = protojson.decode_message(
        api_messages.HostInfoHistoryCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(host_history_collection.histories))
    self.assertEqual(api_messages.HostState.GONE.name,
                     host_history_collection.histories[0].host_state)
    self.assertEqual(api_messages.HostState.KILLING.name,
                     host_history_collection.histories[1].host_state)
    # fetch next page
    api_request = {
        'hostname': self.ndb_host_0.hostname,
        'count': 2,
        'cursor': host_history_collection.next_cursor
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterHostApi.ListHistories', api_request)
    host_history_collection = protojson.decode_message(
        api_messages.HostInfoHistoryCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(1, len(host_history_collection.histories))
    self.assertEqual(api_messages.HostState.RUNNING.name,
                     host_history_collection.histories[0].host_state)

    # fetch previous page (same as first page)
    api_request = {
        'hostname': self.ndb_host_0.hostname,
        'count': 2,
        'cursor': host_history_collection.prev_cursor,
        'backwards': True
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterHostApi.ListHistories', api_request)
    host_history_collection = protojson.decode_message(
        api_messages.HostInfoHistoryCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(2, len(host_history_collection.histories))
    self.assertEqual(api_messages.HostState.GONE.name,
                     host_history_collection.histories[0].host_state)
    self.assertEqual(api_messages.HostState.KILLING.name,
                     host_history_collection.histories[1].host_state)


if __name__ == '__main__':
  unittest.main()
