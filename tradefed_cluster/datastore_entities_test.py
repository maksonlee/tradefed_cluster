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
import json
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


_TEST_BENCH_JSON = """
{
  "cluster": "acluster",
  "host": {
    "groups": [{
        "run_targets": [{
            "name": "rt1",
            "device_attributes": [
              {"name": "sim_state", "value": "READY", "operator": "="}]
          }, {
            "name": "rt2",
            "device_attributes": [
              {"name": "sim_state", "value": "ABSENT", "operator": "="}]
          }]
      }, {
        "run_targets": [{
            "name": "rt3",
            "device_attributes": [
              {"name": "sim_state", "value": "READY", "operator": "="}]
          }, {
            "name": "rt4",
            "device_attributes": [
              {"name": "sim_state", "value": "ABSENT", "operator": "="}]
          }]
      }]
  }
}
"""
_TEST_BENCH_MESSAGE = api_messages._TestBenchRequirement(
    cluster='acluster',
    host=api_messages._HostRequirement(
        groups=[
            api_messages._GroupRequirement(
                run_targets=[
                    api_messages._RunTargetRequirement(
                        name='rt1',
                        device_attributes=[
                            api_messages._DeviceAttributeRequirement(
                                name='sim_state',
                                value='READY',
                                operator='=')]),
                    api_messages._RunTargetRequirement(
                        name='rt2',
                        device_attributes=[
                            api_messages._DeviceAttributeRequirement(
                                name='sim_state',
                                value='ABSENT',
                                operator='=')])]),
            api_messages._GroupRequirement(
                run_targets=[
                    api_messages._RunTargetRequirement(
                        name='rt3',
                        device_attributes=[
                            api_messages._DeviceAttributeRequirement(
                                name='sim_state',
                                value='READY',
                                operator='=')]),
                    api_messages._RunTargetRequirement(
                        name='rt4',
                        device_attributes=[
                            api_messages._DeviceAttributeRequirement(
                                name='sim_state',
                                value='ABSENT',
                                operator='=')])])]))
_TEST_BENCH_ENTITY = datastore_entities.TestBench(
    cluster='acluster',
    host=datastore_entities.Host(
        groups=[
            datastore_entities.Group(
                run_targets=[
                    datastore_entities.RunTarget(
                        name='rt1',
                        device_attributes=[
                            datastore_entities.Attribute(
                                name='sim_state',
                                value='READY',
                                operator='=')]),
                    datastore_entities.RunTarget(
                        name='rt2',
                        device_attributes=[
                            datastore_entities.Attribute(
                                name='sim_state',
                                value='ABSENT',
                                operator='=')])]),
            datastore_entities.Group(
                run_targets=[
                    datastore_entities.RunTarget(
                        name='rt3',
                        device_attributes=[
                            datastore_entities.Attribute(
                                name='sim_state',
                                value='READY',
                                operator='=')]),
                    datastore_entities.RunTarget(
                        name='rt4',
                        device_attributes=[
                            datastore_entities.Attribute(
                                name='sim_state',
                                value='ABSENT',
                                operator='=')])])]))


class DatastoreEntitiesTest(testbed_dependent_test.TestbedDependentTest):

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

  def testtestCommandErrorConfigMapping(self):
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
        host_update_state_summary=datastore_entities.HostUpdateStateSummary(
            total=2))
    lab_info.put()
    lab_info_res = key.get()
    self.assertEqual('alab', lab_info_res.lab_name)
    self.assertIsNotNone(lab_info_res.update_timestamp)
    self.assertEqual(2, lab_info_res.host_update_state_summary.total)

  def testHostInfo(self):
    key = ndb.Key(datastore_entities.HostInfo, 'ahost')
    host_info = datastore_entities.HostInfo(
        key=key,
        hostname='ahost',
        host_state=api_messages.HostState.RUNNING,
        device_count_summaries=[
            datastore_entities.DeviceCountSummary(
                run_target='r1',
                total=1,
                available=1)])
    host_info.put()
    host_info_res = key.get()
    self.assertEqual('ahost', host_info_res.hostname)
    self.assertEqual(api_messages.HostState.RUNNING, host_info_res.host_state)
    self.assertFalse(host_info_res.is_bad)
    self.assertIsNotNone(host_info.timestamp)

  def testHostInfo_gone(self):
    key = ndb.Key(datastore_entities.HostInfo, 'ahost')
    host_info = datastore_entities.HostInfo(
        key=key,
        hostname='ahost',
        host_state=api_messages.HostState.GONE,
        timestamp=TIMESTAMP_NEW,
        device_count_summaries=[
            datastore_entities.DeviceCountSummary(
                run_target='r1',
                total=1,
                available=1)])
    host_info.put()
    host_info_res = key.get()
    self.assertEqual('ahost', host_info_res.hostname)
    self.assertEqual(TIMESTAMP_NEW,
                     host_info_res.timestamp.replace(tzinfo=None))
    self.assertEqual(api_messages.HostState.GONE, host_info_res.host_state)
    self.assertTrue(host_info_res.is_bad)

  def testHostInfo_withOfflineDevice(self):
    key = ndb.Key(datastore_entities.HostInfo, 'ahost')
    host_info = datastore_entities.HostInfo(
        key=key,
        hostname='ahost',
        host_state=api_messages.HostState.RUNNING,
        timestamp=TIMESTAMP_NEW,
        device_count_summaries=[
            datastore_entities.DeviceCountSummary(
                run_target='r1',
                total=1,
                offline=1)])
    host_info.put()
    host_info_res = key.get()
    self.assertEqual('ahost', host_info_res.hostname)
    self.assertEqual(TIMESTAMP_NEW,
                     host_info_res.timestamp.replace(tzinfo=None))
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

  def testHarnessImageMetadataToMessage(self):
    entity = datastore_entities.TestHarnessImageMetadata(
        repo_name='gcr.io/dockerized-tradefed/tradefed',
        digest='sha1',
        test_harness='tradefed',
        test_harness_version='111111',
        current_tags=['111111'],
        create_time=TIMESTAMP_OLD,
        sync_time=TIMESTAMP_NEW)
    msg = datastore_entities.ToMessage(entity)
    self.assertEqual('gcr.io/dockerized-tradefed/tradefed', msg.repo_name)
    self.assertEqual('sha1', msg.digest)
    self.assertEqual('tradefed', msg.test_harness)
    self.assertEqual('111111', msg.test_harness_version)
    self.assertEqual(['111111'], msg.tags)
    self.assertEqual(TIMESTAMP_OLD, msg.create_time)

  def testDeviceFlatExtraInfo(self):
    device = datastore_test_util.CreateDevice(
        'acluster', 'ahost', 'adevice',
        extra_info={
            'key1': 'value1',
            'key2': 'value2',
            'product': 'blueline',
            'sim_state': 'READY',
        })
    device = device.key.get()
    self.assertEqual(
        ['product:blueline', 'sim_state:READY'],
        device.flated_extra_info)

  def testDeviceFlatExtraInfo_longValue(self):
    device = datastore_test_util.CreateDevice(
        'acluster', 'ahost', 'adevice',
        extra_info={
            'product': 'v' * 1000,
            'sim_state': 'READY',
        })
    device = device.key.get()
    self.assertEqual(
        ['product:' + 'v'*80, 'sim_state:READY'],
        device.flated_extra_info)

  def testDeviceFlatExtraInfo_noneValue(self):
    device = datastore_test_util.CreateDevice(
        'acluster', 'ahost', 'adevice',
        extra_info={
            'product': 'v' * 1000,
            'sim_state': None,
        })
    device = device.key.get()
    self.assertEqual(
        ['product:' + 'v'*80, 'sim_state:'],
        device.flated_extra_info)

  def testHostFlatExtraInfo(self):
    host = datastore_test_util.CreateHost(
        'acluster', 'ahost',
        extra_info={
            'key1': 'value1',
            'key2': 'value2',
            'host_ip': '1.2.3.4',
            'label': 'v' * 1000,
        })
    host = host.key.get()
    self.assertEqual(
        ['host_ip:1.2.3.4',
         'label:' + 'v' * 80],
        host.flated_extra_info)

  def assertSameTestResource(self, entity, msg):
    self.assertIsInstance(entity, datastore_entities.TestResource)
    self.assertIsInstance(msg, api_messages.TestResource)
    self.assertEqual(entity.url, msg.url)
    self.assertEqual(entity.name, msg.name)
    self.assertEqual(entity.path, msg.path)
    self.assertEqual(entity.decompress, msg.decompress)
    self.assertEqual(entity.decompress_dir, msg.decompress_dir)
    if entity.params and msg.params:
      self.assertEqual(entity.params.decompress_files,
                       msg.params.decompress_files)
    else:
      self.assertIsNone(entity.params)
      self.assertIsNone(msg.params)

  def testTestResourceFromMessage(self):
    msg = api_messages.TestResource()
    self.assertSameTestResource(
        datastore_entities.TestResource.FromMessage(msg), msg)
    msg = api_messages.TestResource(
        url='url',
        name='name',
        path='path',
        decompress=True,
        decompress_dir='dir',
        params=api_messages.TestResourceParameters(decompress_files=['file']))
    self.assertSameTestResource(
        datastore_entities.TestResource.FromMessage(msg), msg)

  def testTestResourceToMessage(self):
    entity = datastore_entities.TestResource()
    self.assertSameTestResource(
        entity, datastore_entities.TestResourceToMessage(entity))
    entity = datastore_entities.TestResource(
        url='url',
        name='name',
        path='path',
        decompress=True,
        decompress_dir='dir',
        params=datastore_entities.TestResourceParameters(
            decompress_files=['file']))
    self.assertSameTestResource(
        entity, datastore_entities.TestResourceToMessage(entity))

  def testHostResourceFromJson(self):
    host_resource_dict = {
        'identifier': {'hostname': 'ahost'},
        'attribute': [{'name': 'harness_version', 'value': '4.148.0'}],
        'resource': [{
            'resource_name': 'disk_space',
            'resource_instance': '$EXTERNAL_STORAGE',
            'metric': [
                {'tag': 'avail', 'value': 100.0},
                {'tag': 'used', 'value': 9.051264}
            ],
            'timestamp': '2021-08-04T23:16:00.000Z'
        }, {
            'resource_name': 'memory_usage',
            'metric': [
                {'tag': 'avail', 'value': 100.0},
                {'tag': 'used', 'value': 9.051264}
            ],
            'timestamp': '2021-08-04T23:18:00.000Z'
        }]
    }
    entity = datastore_entities.HostResource.FromJson(host_resource_dict)
    entity.put()
    self.assertEqual('ahost', entity.hostname)
    self.assertEqual('ahost', entity.resource['identifier']['hostname'])
    self.assertEqual(
        datetime.datetime(2021, 8, 4, 23, 18),
        entity.event_timestamp)
    self.assertIsNotNone(entity.update_timestamp)

  def testHostResourceToMessage(self):
    entity = datastore_test_util.CreateHostResource('ahost')
    msg = datastore_entities.ToMessage(entity)
    self.assertEqual('ahost', msg.hostname)
    self.assertEqual(entity.resource, json.loads(msg.resource))
    self.assertEqual(entity.update_timestamp, entity.update_timestamp)
    self.assertEqual(entity.event_timestamp, entity.event_timestamp)

  def testCommandInfoFromMessage(self):
    entity = datastore_entities.CommandInfo.FromMessage(
        api_messages.CommandInfo(
            name='acommand',
            command_line='command line',
            cluster='acluster',
            run_target='arun_target'))
    self.assertEqual('acommand', entity.name)
    self.assertEqual('command line', entity.command_line)
    self.assertEqual('acluster', entity.cluster)
    self.assertEqual('arun_target', entity.run_target)

  def testCommandInfoFromMessage_withTestBench(self):
    entity = datastore_entities.CommandInfo.FromMessage(
        api_messages.CommandInfo(
            name='acommand',
            command_line='command line',
            cluster='acluster',
            run_target='arun_target',
            test_bench=_TEST_BENCH_MESSAGE))
    self.assertEqual('acommand', entity.name)
    self.assertEqual('command line', entity.command_line)
    self.assertEqual('acluster', entity.cluster)
    self.assertEqual('rt1,rt2;rt3,rt4', entity.run_target)
    self.assertEqual(_TEST_BENCH_ENTITY, entity.test_bench)

  def testTestBenchFromMessage(self):
    self.assertEqual(
        _TEST_BENCH_ENTITY,
        datastore_entities.TestBench.FromMessage(_TEST_BENCH_MESSAGE))

  def testTestBenchFromLegacy(self):
    test_bench = datastore_entities.TestBench.FromLegacyString(
        'rt1,rt2;rt3,rt4', 'acluster',
        test_bench_attributes=['sim=READY', 'battery>50'])
    self.assertEqual('acluster', test_bench.cluster)
    self.assertEqual(2, len(test_bench.host.groups))
    group = test_bench.host.groups[0]
    self.assertEqual(2, len(group.run_targets))
    run_target = group.run_targets[0]
    self.assertEqual('rt1', run_target.name)
    self.assertEqual(2, len(run_target.device_attributes))
    run_target = group.run_targets[1]
    self.assertEqual('rt2', run_target.name)
    self.assertEqual(2, len(run_target.device_attributes))
    group = test_bench.host.groups[1]
    run_target = group.run_targets[0]
    self.assertEqual('rt3', run_target.name)
    self.assertEqual(2, len(run_target.device_attributes))
    run_target = group.run_targets[1]
    self.assertEqual('rt4', run_target.name)
    self.assertEqual(2, len(run_target.device_attributes))
    device_attribute = run_target.device_attributes[0]
    self.assertEqual('sim', device_attribute.name)
    self.assertEqual('READY', device_attribute.value)
    self.assertEqual('=', device_attribute.operator)
    device_attribute = run_target.device_attributes[1]
    self.assertEqual('battery', device_attribute.name)
    self.assertEqual('50', device_attribute.value)
    self.assertEqual('>', device_attribute.operator)

  def testTestBenchFromJson(self):
    self.assertEqual(
        _TEST_BENCH_ENTITY,
        datastore_entities.TestBench.FromJson(
            json.loads(_TEST_BENCH_JSON), 'acluster'))

  def testTestBenchToLegacyRunTarget(self):
    test_bench = datastore_entities.TestBench.FromLegacyString(
        'rt1,rt2;rt3,rt4', 'acluster',
        test_bench_attributes=['sim=READY', 'battery>50'])
    self.assertEqual(
        'rt1,rt2;rt3,rt4',
        datastore_entities._TestBenchToLegacyRunTarget(test_bench))

  def testBuildTestBench_legacy(self):
    test_bench = datastore_entities.BuildTestBench(
        cluster='cluster', run_target='run_target5')
    self.assertEqual('cluster', test_bench.cluster)
    self.assertEqual(
        'run_target5',
        datastore_entities._TestBenchToLegacyRunTarget(test_bench))
    self.assertEqual(1, len(test_bench.host.groups))
    self.assertEqual(1, len(test_bench.host.groups[0].run_targets))
    self.assertEqual(
        'run_target5', test_bench.host.groups[0].run_targets[0].name)

  def testBuildTestBench_legacyWithMultipleRunTargets(self):
    test_bench = datastore_entities.BuildTestBench(
        'cluster', 'rt1,rt2;rt3,rt4',
        test_bench_attributes=['sim=READY'])
    self.assertEqual('cluster', test_bench.cluster)
    self.assertEqual(
        'rt1,rt2;rt3,rt4',
        datastore_entities._TestBenchToLegacyRunTarget(test_bench))
    self.assertEqual(2, len(test_bench.host.groups))
    self.assertEqual(2, len(test_bench.host.groups[0].run_targets))
    self.assertEqual(2, len(test_bench.host.groups[1].run_targets))
    self.assertEqual(
        'rt1', test_bench.host.groups[0].run_targets[0].name)
    self.assertEqual(
        'rt2', test_bench.host.groups[0].run_targets[1].name)
    self.assertEqual(
        'rt3', test_bench.host.groups[1].run_targets[0].name)
    self.assertEqual(
        'rt4', test_bench.host.groups[1].run_targets[1].name)

  def testBuildTestBench_jsonRunTarget(self):
    test_bench = datastore_entities.BuildTestBench(
        'acluster', _TEST_BENCH_JSON)
    self.assertEqual(_TEST_BENCH_ENTITY, test_bench)
    self.assertEqual('acluster', test_bench.cluster)
    self.assertEqual(
        'rt1,rt2;rt3,rt4',
        datastore_entities._TestBenchToLegacyRunTarget(test_bench))

  def testBuildTestBench_testBenchEntity(self):
    test_bench = datastore_entities.BuildTestBench(
        'cluster', 'run_target', test_bench=_TEST_BENCH_ENTITY)
    self.assertEqual(_TEST_BENCH_ENTITY, test_bench)
    self.assertEqual('acluster', test_bench.cluster)
    self.assertEqual(
        'rt1,rt2;rt3,rt4',
        datastore_entities._TestBenchToLegacyRunTarget(test_bench))

  def testBuildTestBench_testBenchMessage(self):
    test_bench = datastore_entities.BuildTestBench(
        'cluster', 'run_target', test_bench=_TEST_BENCH_MESSAGE)
    self.assertEqual(_TEST_BENCH_ENTITY, test_bench)
    self.assertEqual('acluster', test_bench.cluster)
    self.assertEqual(
        'rt1,rt2;rt3,rt4',
        datastore_entities._TestBenchToLegacyRunTarget(test_bench))

  def testAttributeFromString(self):
    self.assertEqual(
        datastore_entities.Attribute(
            name='attr1', value='val1', operator='='),
        datastore_entities.Attribute.FromString('attr1=val1'))
    self.assertEqual(
        datastore_entities.Attribute(
            name='attr1', value='val1', operator='>'),
        datastore_entities.Attribute.FromString('attr1>val1'))
    self.assertEqual(
        datastore_entities.Attribute(
            name='attr1', value='val1', operator='>='),
        datastore_entities.Attribute.FromString('attr1>=val1'))
    self.assertEqual(
        datastore_entities.Attribute(
            name='attr1', value='val1', operator='<'),
        datastore_entities.Attribute.FromString('attr1<val1'))
    self.assertEqual(
        datastore_entities.Attribute(
            name='attr1', value='val1', operator='<='),
        datastore_entities.Attribute.FromString('attr1<=val1'))

  def testAttributeFromString_invalidFormat(self):
    with self.assertRaises(ValueError):
      datastore_entities.Attribute.FromString('attr1')

  def testAttributeFromString_nonNumberForNumberAttribute(self):
    with self.assertRaises(ValueError):
      datastore_entities.Attribute.FromString('battery_level>unknown')


if __name__ == '__main__':
  unittest.main()
