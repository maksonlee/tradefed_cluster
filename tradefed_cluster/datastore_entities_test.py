# Lint as: python2, python3
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

"""Tests for datastore_entities."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import datetime
import unittest

from six.moves import range

from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.util import ndb_shim as ndb

TIMESTAMP_OLD = datetime.datetime(2015, 5, 7)
TIMESTAMP_NEW = datetime.datetime(2015, 9, 29)


class DatastoreEntitiesTest(testbed_dependent_test.TestbedDependentTest):

  def testRequest(self):
    request_id = datastore_entities.Request.allocate_ids(1)[0].id()
    key = ndb.Key(
        datastore_entities.Request, str(request_id),
        namespace=common.NAMESPACE)
    datastore_entities.Request(
        key=key,
        user='user',
        command_line='command_line',
        state=common.RequestState.RUNNING,
        start_time=TIMESTAMP_NEW,
        end_time=TIMESTAMP_NEW).put()

    request = key.get(use_cache=False)
    self.assertEqual('user', request.user)
    self.assertEqual('command_line', request.command_line)
    self.assertEqual(common.RequestState.RUNNING, request.state)
    self.assertEqual(TIMESTAMP_NEW, request.start_time)
    self.assertEqual(TIMESTAMP_NEW, request.end_time)
    self.assertIsNotNone(request.create_time)
    self.assertIsNotNone(request.update_time)
    self.assertFalse(request.dirty)
    self.assertFalse(request.notify_state_change)

  def testClusterNote(self):
    cluster_note = datastore_entities.ClusterNote(cluster='free')
    key = ndb.Key(datastore_entities.Note,
                  datastore_entities.Note.allocate_ids(1)[0].id())
    note = datastore_entities.Note(key=key, user='user0',
                                   timestamp=TIMESTAMP_OLD,
                                   message='Hello, World')
    cluster_note.note = note
    cluster_note_key = cluster_note.put()
    queried_cluster_note = cluster_note_key.get()
    self.assertEqual('free', queried_cluster_note.cluster)
    self.assertEqual(cluster_note_key, queried_cluster_note.key)
    self.assertEqual(note.message, queried_cluster_note.note.message)
    self.assertEqual(note.timestamp, queried_cluster_note.note.timestamp)
    self.assertEqual(note.user, queried_cluster_note.note.user)

  def testClusterNote_nonExisting(self):
    query = datastore_entities.ClusterNote.query()
    query = query.filter(datastore_entities.ClusterNote.cluster == 'fake')
    notes = query.fetch(10)
    self.assertEqual([], notes)

  def testHostNote(self):
    host_note = datastore_entities.HostNote(hostname='host.name')
    note = datastore_entities.Note(user='user0',
                                   timestamp=TIMESTAMP_OLD,
                                   message='Hello, World')
    host_note.note = note
    host_note.put()
    query = datastore_entities.HostNote.query()
    query = query.filter(datastore_entities.HostNote.hostname == 'host.name')
    for query_host_note in query.iter():
      self.assertEqual('host.name', query_host_note.hostname)
      self.assertEqual(note.message, query_host_note.note.message)
      self.assertEqual(note.timestamp, query_host_note.note.timestamp)
      self.assertEqual(note.user, query_host_note.note.user)

  def testDeviceNote(self):
    count = 10
    for i in range(count):
      device_note = datastore_entities.DeviceNote(device_serial='serial_0')
      note = datastore_entities.Note(user=str(i),
                                     timestamp=TIMESTAMP_OLD,
                                     message='Hello, World')
      device_note.note = note
      device_note.put()
    query = datastore_entities.DeviceNote.query()
    query = query.filter(
        datastore_entities.DeviceNote.device_serial == 'serial_0')
    self.assertEqual(count, query.count())

  def testCommandErrorConfigMapping(self):
    """Test error config map between error and reason type map."""
    config = datastore_entities.CommandErrorConfigMapping(
        error_message='error1', reason='reason1',
        type_code=common.CommandErrorType.INFRA)
    config.put()
    queried = datastore_entities.CommandErrorConfigMapping.query(
        datastore_entities.CommandErrorConfigMapping.error_message == 'error1'
    ).get()
    self.assertEqual('reason1', queried.reason)
    self.assertEqual(common.CommandErrorType.INFRA, queried.type_code)

  def testReportEmailConfig(self):
    """Tests ReportEmailConfig store entity operations."""
    report_email_config = datastore_entities.ReportEmailConfig()
    report_email_config.cluster_prefix = 'cp0'
    report_email_config.recipients = ['nobody@example.com', 'nobody@example.com']
    key = report_email_config.put()
    queried = key.get()
    self.assertEqual('cp0', queried.cluster_prefix)
    self.assertEqual(['nobody@example.com', 'nobody@example.com'],
                     queried.recipients)

  def testPredefinedMessage(self):
    """Tests PredefinedMessage store entity operations."""
    predefined_message = datastore_entities.PredefinedMessage(
        lab_name='lab-name-1',
        type=common.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
        content='content-1',
        create_timestamp=TIMESTAMP_OLD,
        used_count=2)
    key = predefined_message.put()
    queried = key.get()
    self.assertEqual('lab-name-1', queried.lab_name)
    self.assertEqual(common.PredefinedMessageType.DEVICE_RECOVERY_ACTION,
                     queried.type)
    self.assertEqual('content-1', queried.content)
    self.assertEqual(2, queried.used_count)

  def testLabInfo(self):
    key = ndb.Key(datastore_entities.LabInfo, 'alab')
    lab_info = datastore_entities.LabInfo(
        key=key,
        lab_name='alab',
        update_timestamp=TIMESTAMP_NEW,
        owners=['user1', 'user2', 'user3'])
    lab_info.put()
    lab_info_res = key.get()
    self.assertEqual('alab', lab_info_res.lab_name)
    self.assertEqual(TIMESTAMP_NEW, lab_info_res.update_timestamp)
    self.assertEqual(['user1', 'user2', 'user3'], lab_info_res.owners)

  def testHostInfo(self):
    key = ndb.Key(datastore_entities.HostInfo, 'ahost')
    host_info = datastore_entities.HostInfo(
        key=key,
        hostname='ahost',
        host_state=api_messages.HostState.RUNNING,
        update_timestamp=TIMESTAMP_NEW,
        device_count_summaries=[
            datastore_entities.DeviceCountSummary(
                run_target='r1',
                total=1,
                available=1)])
    host_info.put()
    host_info_res = key.get()
    self.assertEqual('ahost', host_info_res.hostname)
    self.assertEqual(TIMESTAMP_NEW,
                     host_info_res.update_timestamp.replace(tzinfo=None))
    self.assertEqual(api_messages.HostState.RUNNING, host_info_res.host_state)
    self.assertFalse(host_info_res.is_bad)

  def testHostInfo_gone(self):
    key = ndb.Key(datastore_entities.HostInfo, 'ahost')
    host_info = datastore_entities.HostInfo(
        key=key,
        hostname='ahost',
        host_state=api_messages.HostState.GONE,
        update_timestamp=TIMESTAMP_NEW,
        device_count_summaries=[
            datastore_entities.DeviceCountSummary(
                run_target='r1',
                total=1,
                available=1)])
    host_info.put()
    host_info_res = key.get()
    self.assertEqual('ahost', host_info_res.hostname)
    self.assertEqual(TIMESTAMP_NEW,
                     host_info_res.update_timestamp.replace(tzinfo=None))
    self.assertEqual(api_messages.HostState.GONE, host_info_res.host_state)
    self.assertTrue(host_info_res.is_bad)

  def testHostInfo_withOfflineDevice(self):
    key = ndb.Key(datastore_entities.HostInfo, 'ahost')
    host_info = datastore_entities.HostInfo(
        key=key,
        hostname='ahost',
        host_state=api_messages.HostState.RUNNING,
        update_timestamp=TIMESTAMP_NEW,
        device_count_summaries=[
            datastore_entities.DeviceCountSummary(
                run_target='r1',
                total=1,
                offline=1)])
    host_info.put()
    host_info_res = key.get()
    self.assertEqual('ahost', host_info_res.hostname)
    self.assertEqual(TIMESTAMP_NEW,
                     host_info_res.update_timestamp.replace(tzinfo=None))
    self.assertEqual(api_messages.HostState.RUNNING, host_info_res.host_state)
    self.assertTrue(host_info_res.is_bad)

  def testDeviceBlocklist(self):
    blocklist = datastore_test_util.CreateDeviceBlocklist('alab', 'auser')
    res = blocklist.key.get()
    self.assertIsNotNone(res.create_timestamp)
    self.assertEqual('alab', res.lab_name)
    self.assertEqual('lab outage', res.note)
    self.assertEqual('auser', res.user)

  def testDeviceBlocklistArchive(self):
    blocklist = datastore_test_util.CreateDeviceBlocklist('alab', 'auser')
    blocklist_archive = (
        datastore_entities.DeviceBlocklistArchive.
        FromDeviceBlocklist(blocklist, 'another_user'))
    blocklist_archive.put()
    res = blocklist_archive.key.get()
    self.assertEqual(res.device_blocklist.create_timestamp, res.start_timestamp)
    self.assertIsNotNone(res.end_timestamp)
    self.assertEqual('another_user', res.archived_by)
    self.assertEqual('alab', res.device_blocklist.lab_name)
    self.assertEqual('lab outage', res.device_blocklist.note)
    self.assertEqual('auser', res.device_blocklist.user)

  def testDeviceBlocklistToMessage(self):
    blocklist = datastore_test_util.CreateDeviceBlocklist('alab', 'auser')
    msg = datastore_entities.ToMessage(blocklist)
    self.assertIsNotNone(msg.key_id)
    self.assertIsNotNone(msg.create_timestamp)
    self.assertEqual('alab', msg.lab_name)
    self.assertEqual('lab outage', msg.note)
    self.assertEqual('auser', msg.user)

  def testDeviceBlocklistArchiveToMessage(self):
    blocklist = datastore_test_util.CreateDeviceBlocklist('alab', 'auser')
    blocklist_archive = (
        datastore_entities.DeviceBlocklistArchive.
        FromDeviceBlocklist(blocklist, 'another_user'))
    blocklist_archive.put()
    msg = datastore_entities.ToMessage(blocklist_archive)
    self.assertEqual(msg.device_blocklist.create_timestamp, msg.start_timestamp)
    self.assertIsNotNone(msg.end_timestamp)
    self.assertEqual('another_user', msg.archived_by)
    self.assertEqual('alab', msg.device_blocklist.lab_name)
    self.assertEqual('lab outage', msg.device_blocklist.note)
    self.assertEqual('auser', msg.device_blocklist.user)


if __name__ == '__main__':
  unittest.main()
