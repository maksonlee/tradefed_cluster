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

"""Tests cluster_api module."""

import datetime
import unittest

from protorpc import protojson

from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import cluster_api
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from google.appengine.ext import ndb


class ClusterApiTest(api_test.ApiTest):

  TIMESTAMP = datetime.datetime.utcfromtimestamp(1431712965)

  def setUp(self):
    api_test.ApiTest.setUp(self)
    self.cluster_0 = datastore_test_util.CreateCluster(
        cluster='free',
        total_devices=10,
        offline_devices=1,
        available_devices=2,
        allocated_devices=7,
        device_count_timestamp=self.TIMESTAMP)
    self.cluster_1 = datastore_test_util.CreateCluster(
        cluster='paid',
        total_devices=2,
        offline_devices=0,
        available_devices=1,
        allocated_devices=1,
        device_count_timestamp=self.TIMESTAMP)
    datastore_test_util.CreateHost(cluster='free', hostname='host_0')
    datastore_test_util.CreateDevice(
        cluster='free',
        hostname='host_0',
        device_serial='device_0',
        device_type=api_messages.DeviceTypeMessage.PHYSICAL,
        battery_level='100',
        run_target='shamu')
    datastore_test_util.CreateHost(cluster='free', hostname='host_1')
    datastore_test_util.CreateDevice(
        cluster='free',
        hostname='host_1',
        device_serial='device_1',
        device_type=api_messages.DeviceTypeMessage.PHYSICAL,
        timestamp=self.TIMESTAMP,
        run_target='flounder')

    datastore_test_util.CreateHost(cluster='paid', hostname='host_2')
    datastore_test_util.CreateDevice(
        cluster='paid',
        hostname='host_2',
        device_serial='device_2',
        device_type=api_messages.DeviceTypeMessage.PHYSICAL,
        run_target='shamu')
    # A hidden device
    datastore_test_util.CreateDevice(
        cluster='paid',
        hostname='host_2',
        device_serial='device_3',
        device_type=api_messages.DeviceTypeMessage.PHYSICAL,
        run_target='shamu',
        hidden=True)
    # A hidden host
    datastore_test_util.CreateHost(
        cluster='paid', hostname='host_3', hidden=True)

    self.note = datastore_entities.Note(user='user0',
                                        timestamp=self.TIMESTAMP,
                                        message='Hello, World')
    cluster_note = datastore_entities.ClusterNote(cluster='free')
    cluster_note.note = self.note
    cluster_note.put()

  def AssertEqualClusterInfo(self, cluster_entity, cluster_message):
    # Helper to compare cluster entities and messages
    self.assertEqual(cluster_entity.cluster, cluster_message.cluster_id)
    self.assertEqual(
        cluster_entity.total_devices, cluster_message.total_devices)
    self.assertEqual(
        cluster_entity.offline_devices, cluster_message.offline_devices)
    self.assertEqual(
        cluster_entity.available_devices, cluster_message.available_devices)
    self.assertEqual(
        cluster_entity.allocated_devices, cluster_message.allocated_devices)
    self.assertEqual(
        cluster_entity.device_count_timestamp,
        cluster_message.device_count_timestamp)

  def testListClusters(self):
    """Tests ListClusters."""
    api_request = {}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterApi.ListClusters', api_request)
    cluster_collection = protojson.decode_message(
        cluster_api.ClusterInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    clusters = [c for c in cluster_collection.cluster_infos]
    for c in clusters:
      self.assertEqual(0, len(c.host_infos))
      self.assertEqual(0, len(c.run_targets))
      if c.cluster_id == 'free':
        self.AssertEqualClusterInfo(self.cluster_0, c)
      elif c.cluster_id == 'paid':
        self.AssertEqualClusterInfo(self.cluster_1, c)
      else:
        # No other cluster should exist
        self.fail()

  def testListClusters_includeHosts(self):
    """Tests ListClusters returns all visible clusters, hosts, and devices."""
    api_request = {'include_hosts': True}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterApi.ListClusters', api_request)
    cluster_collection = protojson.decode_message(
        cluster_api.ClusterInfoCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    clusters = [c for c in cluster_collection.cluster_infos]
    hosts = []
    for c in clusters:
      if c.cluster_id == 'free':
        self.AssertEqualClusterInfo(self.cluster_0, c)
        self.assertItemsEqual(
            ('shamu', 'flounder'), (rt.name for rt in c.run_targets))
      elif c.cluster_id == 'paid':
        self.AssertEqualClusterInfo(self.cluster_1, c)
        self.assertEqual('shamu', c.run_targets[0].name)
      else:
        # No other cluster should exist
        self.fail()
      for host in c.host_infos:
        hosts.append(host)
    devices = []
    for host in hosts:
      for device in host.device_infos:
        devices.append(device)
    self.assertEqual(2, len(clusters))
    self.assertEqual(3, len(hosts))
    self.assertEqual(3, len(devices))
    self.assertItemsEqual(['free', 'paid'],
                          [c.cluster_id for c in clusters])
    self.assertItemsEqual(['host_0', 'host_1', 'host_2'],
                          [h.hostname for h in hosts])
    self.assertItemsEqual(['device_0', 'device_1', 'device_2'],
                          [d.device_serial for d in devices])

  def testGetCluster(self):
    """Tests GetCluster returns hosts in order with their devices."""
    api_request = {'cluster_id': 'free'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterApi.GetCluster', api_request)
    cluster_info = protojson.decode_message(api_messages.ClusterInfo,
                                            api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual('free', cluster_info.cluster_id)
    self.assertEqual(0, len(cluster_info.host_infos))

  def testGetCluster_includeHosts(self):
    """Tests GetCluster returns hosts in order with their devices."""
    api_request = {'cluster_id': 'free', 'include_hosts': True}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterApi.GetCluster', api_request)
    cluster_info = protojson.decode_message(api_messages.ClusterInfo,
                                            api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual('free', cluster_info.cluster_id)
    self.assertEqual(2, len(cluster_info.host_infos))
    self.assertEqual('host_0', cluster_info.host_infos[0].hostname)
    self.assertEqual(1, len(cluster_info.host_infos[0].device_infos))
    self.assertEqual('device_0',
                     cluster_info.host_infos[0].device_infos[0].device_serial)
    self.assertEqual('100',
                     cluster_info.host_infos[0].device_infos[0].battery_level)
    self.assertIsNone(cluster_info.host_infos[0].device_infos[0].timestamp)
    self.assertEqual('host_1', cluster_info.host_infos[1].hostname)
    self.assertEqual(1, len(cluster_info.host_infos[1].device_infos))
    self.assertEqual('device_1',
                     cluster_info.host_infos[1].device_infos[0].device_serial)
    self.assertEqual(self.TIMESTAMP,
                     cluster_info.host_infos[1].device_infos[0].timestamp)
    self.assertEqual(0, len(cluster_info.notes))
    self.assertItemsEqual(['shamu', 'flounder'],
                          [r.name for r in cluster_info.run_targets])

  def testGetCluster_missingCluster(self):
    """Tests GetCluster for an inexistent one."""
    api_request = {'cluster_id': 'fakecluster'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterApi.GetCluster', api_request, expect_errors=True)
    self.assertEqual('404 Not Found', api_response.status)

  def testGetCluster_includeNotes(self):
    """Tests GetCluster returns hosts in order with their devices."""
    api_request = {'cluster_id': 'free', 'include_notes': True}
    api_response = self.testapp.post_json('/_ah/api/ClusterApi.GetCluster',
                                          api_request)
    cluster_info = protojson.decode_message(api_messages.ClusterInfo,
                                            api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual('free', cluster_info.cluster_id)
    self.assertEqual(1, len(cluster_info.notes))
    self.assertEqual(self.note.user, cluster_info.notes[0].user)
    self.assertEqual(self.note.timestamp, cluster_info.notes[0].timestamp)
    self.assertEqual(self.note.message, cluster_info.notes[0].message)

  def testGetCluster_includeNotesNoneAvailable(self):
    """Tests GetCluster including notes when they are available."""
    api_request = {'cluster_id': 'paid', 'include_notes': True}
    api_response = self.testapp.post_json('/_ah/api/ClusterApi.GetCluster',
                                          api_request)
    cluster_info = protojson.decode_message(api_messages.ClusterInfo,
                                            api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertEqual('paid', cluster_info.cluster_id)
    self.assertEqual(0, len(cluster_info.notes))

  def testNewNote_withNoneExisting(self):
    """Tests adding a note to a cluster when none exist already."""
    user = 'some_user'
    timestamp = datetime.datetime(2015, 10, 18, 20, 46)
    message = 'The Message'
    api_request = {'cluster_id': 'paid',
                   'user': user,
                   'timestamp': timestamp.isoformat(),
                   'message': message
                  }
    api_response = self.testapp.post_json('/_ah/api/ClusterApi.NewNote',
                                          api_request)
    self.assertEqual('200 OK', api_response.status)
    api_request = {'cluster_id': 'paid', 'include_notes': True}
    api_response = self.testapp.post_json('/_ah/api/ClusterApi.GetCluster',
                                          api_request)
    cluster_info = protojson.decode_message(api_messages.ClusterInfo,
                                            api_response.body)
    self.assertEqual(1, len(cluster_info.notes))
    self.assertEqual(user, cluster_info.notes[0].user)
    self.assertEqual(timestamp, cluster_info.notes[0].timestamp)
    self.assertEqual(message, cluster_info.notes[0].message)

  def testNewNote_withExisting(self):
    """Tests adding a note to a cluster when one already exists."""
    user = 'some_user'
    timestamp = datetime.datetime(2015, 10, 18, 20, 46)
    message = 'The Message'
    api_request = {'cluster_id': 'free',
                   'user': user,
                   'timestamp': timestamp.isoformat(),
                   'message': message
                  }
    api_response = self.testapp.post_json('/_ah/api/ClusterApi.NewNote',
                                          api_request)
    self.assertEqual('200 OK', api_response.status)
    # Query the same cluster again. Notes should be sorted.
    api_request = {'cluster_id': 'free', 'include_notes': True}
    api_response = self.testapp.post_json('/_ah/api/ClusterApi.GetCluster',
                                          api_request)
    cluster_info = protojson.decode_message(api_messages.ClusterInfo,
                                            api_response.body)
    self.assertEqual(2, len(cluster_info.notes))
    self.assertEqual(user, cluster_info.notes[0].user)
    self.assertEqual(timestamp, cluster_info.notes[0].timestamp)
    self.assertEqual(message, cluster_info.notes[0].message)
    self.assertEqual(self.note.user, cluster_info.notes[1].user)
    self.assertEqual(self.note.timestamp, cluster_info.notes[1].timestamp)
    self.assertEqual(self.note.message, cluster_info.notes[1].message)

  def testCreatePredefinedMessage_succeed(self):
    lab_name = 'lab_1'
    content = 'device went down'
    api_request = {
        'type': 'DEVICE_OFFLINE_REASON',
        'lab_name': lab_name,
        'content': content,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterApi.CreatePredefinedMessage', api_request)
    self.assertEqual('200 OK', api_response.status)
    created_predefined_message = protojson.decode_message(
        api_messages.PredefinedMessage, api_response.body)
    self.assertEqual(api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
                     created_predefined_message.type)
    self.assertEqual(lab_name, created_predefined_message.lab_name)
    self.assertEqual(content, created_predefined_message.content)
    self.assertIsNotNone(created_predefined_message.id)
    self.assertEqual(0, created_predefined_message.used_count)

  def testCreatePredefinedMessage_failConflict(self):
    lab_name = 'lab_1'
    content = 'device went down'
    datastore_entities.PredefinedMessage(
        lab_name=lab_name,
        type=api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
        content=content).put()
    api_request = {
        'type': 'DEVICE_OFFLINE_REASON',
        'lab_name': lab_name,
        'content': content,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterApi.CreatePredefinedMessage', api_request,
        expect_errors=True)
    self.assertEqual('409 Conflict', api_response.status)

  def testListPredefinedMessages_filtersAndOrdering(self):
    """Test list PredefinedMessages."""
    pred_msg_entities = [
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-1',
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content='content-1',
            used_count=2),
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-2',
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content='content-2',
            used_count=1),
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-2',
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content='content-3',
            used_count=3),
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-4',
            type=api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
            content='content-4',
            used_count=3),
    ]
    ndb.put_multi(pred_msg_entities)
    api_request = {'type': 'DEVICE_RECOVERY_ACTION',
                   'lab_name': 'lab-name-2'}
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterApi.ListPredefinedMessages', api_request)
    pred_msgs = protojson.decode_message(
        api_messages.PredefinedMessageCollection,
        api_response.body).predefined_messages
    # The results are filtered by type and lab name.
    self.assertEqual(2, len(pred_msgs))
    # The results are sorted by count in descending order.
    self.assertEqual(pred_msg_entities[1].lab_name, pred_msgs[1].lab_name)
    self.assertEqual(pred_msg_entities[1].content, pred_msgs[1].content)
    self.assertEqual(pred_msg_entities[1].type, pred_msgs[1].type)
    self.assertEqual(pred_msg_entities[1].used_count, pred_msgs[1].used_count)
    self.assertEqual(pred_msg_entities[2].lab_name, pred_msgs[0].lab_name)
    self.assertEqual(pred_msg_entities[2].content, pred_msgs[0].content)
    self.assertEqual(pred_msg_entities[2].type, pred_msgs[0].type)
    self.assertEqual(pred_msg_entities[2].used_count, pred_msgs[0].used_count)

  def testListPredefinedMessages_countAndCursor(self):
    """Test list PredefinedMessages."""
    pred_msg_entities = [
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-2',
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content='content-1',
            used_count=4),
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-2',
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content='content-2',
            used_count=3),
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-2',
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content='content-3',
            used_count=2),
        datastore_entities.PredefinedMessage(
            lab_name='lab-name-2',
            type=api_messages.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
            content='content-4',
            used_count=1),
    ]
    ndb.put_multi(pred_msg_entities)
    # look up the first page
    api_request = {
        'type': 'DEVICE_RECOVERY_ACTION',
        'lab_name': 'lab-name-2',
        'count': 2,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterApi.ListPredefinedMessages', api_request)
    pred_msg_collection = protojson.decode_message(
        api_messages.PredefinedMessageCollection,
        api_response.body)
    pred_msgs = pred_msg_collection.predefined_messages
    self.assertEqual(2, len(pred_msgs))
    self.assertEqual(pred_msg_entities[0].content, pred_msgs[0].content)
    self.assertEqual(pred_msg_entities[1].content, pred_msgs[1].content)
    # look up the second page with next_cursor
    api_request = {
        'type': 'DEVICE_RECOVERY_ACTION',
        'lab_name': 'lab-name-2',
        'count': 2,
        'cursor': pred_msg_collection.next_cursor,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterApi.ListPredefinedMessages', api_request)
    pred_msg_collection = protojson.decode_message(
        api_messages.PredefinedMessageCollection,
        api_response.body)
    pred_msgs = pred_msg_collection.predefined_messages
    self.assertEqual(2, len(pred_msgs))
    self.assertEqual(pred_msg_entities[2].content, pred_msgs[0].content)
    self.assertEqual(pred_msg_entities[3].content, pred_msgs[1].content)
    # look up the first page again with prev_cursor of the second page
    api_request = {
        'type': 'DEVICE_RECOVERY_ACTION',
        'lab_name': 'lab-name-2',
        'count': 2,
        'cursor': pred_msg_collection.prev_cursor,
        'backwards': True,
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ClusterApi.ListPredefinedMessages', api_request)
    pred_msg_collection = protojson.decode_message(
        api_messages.PredefinedMessageCollection,
        api_response.body)
    pred_msgs = pred_msg_collection.predefined_messages
    self.assertEqual(2, len(pred_msgs))
    self.assertEqual(pred_msg_entities[0].content, pred_msgs[0].content)
    self.assertEqual(pred_msg_entities[1].content, pred_msgs[1].content)


if __name__ == '__main__':
  unittest.main()
