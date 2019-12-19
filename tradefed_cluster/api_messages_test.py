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

"""Tests for api_messages."""

import datetime
import json
import unittest

from protorpc import protojson

from google.appengine.ext import ndb

from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities

TIMESTAMP = datetime.datetime(2015, 5, 7)


class FakeEntity(object):
  pass


class ApiMessagesTest(unittest.TestCase):

  def testCommandAttemptFromEntity(self):
    """Tests coverting a CommandAttempt entity to a message."""
    entity = datastore_entities.CommandAttempt(
        key=ndb.Key(
            datastore_entities.Request, '1',
            datastore_entities.Command, '2',
            datastore_entities.CommandAttempt, '3'),
        command_id='2',
        attempt_id='3',
        task_id='4',
        state=common.CommandState.UNKNOWN,
        hostname='hostname',
        device_serial='device_serial',
        start_time=TIMESTAMP,
        end_time=TIMESTAMP,
        status='status',
        error='error',
        summary='summary',
        total_test_count=1000,
        failed_test_count=100,
        create_time=TIMESTAMP,
        update_time=TIMESTAMP)
    message = datastore_entities.ToMessage(entity)
    self.AssertEqualCommandAttempt(entity, message)

  def testRequestFromEntity(self):
    """Tests converting a Request entity to a message."""
    request = datastore_entities.Request(
        id='id',
        user='user',
        command_line='command_line',
        state=common.RequestState.UNKNOWN,
        shard_count=2,
        run_count=3,
        cluster='cluster',
        run_target='run_target')
    message = datastore_entities.ToMessage(request)
    self.AssertEqualRequest(request, message)

  def testRequestFromEntity_cancelRequest(self):
    """Tests converting a cancelled Request entity to a message."""
    request = datastore_entities.Request(
        id='id',
        user='user',
        command_line='command_line',
        state=common.RequestState.CANCELED,
        cancel_reason=common.CancelReason.QUEUE_TIMEOUT)
    message = datastore_entities.ToMessage(request)
    self.assertEqual(request.key.id(), message.id)
    self.assertEqual(request.command_line, message.command_line)
    self.assertEqual(request.state, message.state)
    self.assertEqual(request.cancel_reason, message.cancel_reason)

  def testMessageFromEntity_cancelRequest_invalidRequest(self):
    """Tests converting a Request object to a message."""
    request_key = ndb.Key(datastore_entities.Request, '123')
    request = datastore_entities.Request(
        key=request_key,
        user='user',
        command_line='command_line',
        state=common.RequestState.UNKNOWN,
        cancel_reason=common.CancelReason.INVALID_REQUEST,
        shard_count=2,
        run_count=3,
        cluster='cluster',
        run_target='run_target')
    message = datastore_entities.ToMessage(request)
    self.AssertEqualRequest(request, message)

  def testRequestFromEntity_multipleCommandsAndAttempts(self):
    """Tests converting a Request object with multiple Commands."""
    request_key = ndb.Key(datastore_entities.Request, '123')
    request = datastore_entities.Request(
        key=request_key,
        user='user',
        command_line='command_line',
        state=common.RequestState.UNKNOWN,
        cancel_reason=common.CancelReason.QUEUE_TIMEOUT,
        shard_count=2,
        run_count=3,
        cluster='cluster',
        run_target='run_target')
    command1_key = ndb.Key(datastore_entities.Command, '456',
                           parent=request_key)
    cmd1 = datastore_entities.Command(
        key=command1_key,
        command_line='command_line1',
        cluster='cluster',
        run_target='run_target',
        run_count=10,
        state=common.CommandState.QUEUED,
        start_time=TIMESTAMP,
        end_time=None,
        create_time=TIMESTAMP,
        update_time=TIMESTAMP,
        shard_count=2,
        shard_index=0)
    command2_key = ndb.Key(datastore_entities.Command, '457',
                           parent=request_key)
    cmd2 = datastore_entities.Command(
        key=command2_key,
        command_line='command_line2',
        cluster='cluster',
        run_target='run_target',
        run_count=10,
        state=common.CommandState.QUEUED,
        start_time=TIMESTAMP,
        end_time=None,
        create_time=TIMESTAMP,
        update_time=TIMESTAMP,
        shard_count=2,
        shard_index=1)
    command_attempt1_key = ndb.Key(
        datastore_entities.CommandAttempt, '890',
        parent=command1_key)
    cmd_attempt1 = datastore_entities.CommandAttempt(
        key=command_attempt1_key,
        task_id='task_id',
        attempt_id='attempt_id',
        state=common.CommandState.UNKNOWN,
        hostname='hostname',
        device_serial='device_serial',
        start_time=TIMESTAMP,
        end_time=TIMESTAMP,
        status='status',
        error='error',
        summary='summary',
        total_test_count=1000,
        failed_test_count=100,
        create_time=TIMESTAMP,
        update_time=TIMESTAMP)
    command_attempt2_key = ndb.Key(
        datastore_entities.CommandAttempt, '891',
        parent=command1_key)
    cmd_attempt2 = datastore_entities.CommandAttempt(
        key=command_attempt2_key,
        task_id='task_id',
        attempt_id='attempt_id',
        state=common.CommandState.UNKNOWN,
        hostname='hostname',
        device_serial='device_serial',
        start_time=TIMESTAMP,
        end_time=TIMESTAMP,
        status='status',
        error='error',
        summary='summary',
        total_test_count=1000,
        failed_test_count=100,
        create_time=TIMESTAMP,
        update_time=TIMESTAMP)
    commands = [cmd1, cmd2]
    command_attempts = [cmd_attempt1, cmd_attempt2]

    message = datastore_entities.ToMessage(
        request,
        command_attempts=command_attempts,
        commands=commands)
    self.AssertEqualRequest(request, message)
    self.assertEqual(len(message.commands), len(commands))
    for command, command_msg in zip(commands, message.commands):
      self.AssertEqualCommand(command, command_msg)
    self.assertEqual(len(message.command_attempts), len(command_attempts))
    for attempt, msg in zip(command_attempts, message.command_attempts):
      self.AssertEqualCommandAttempt(attempt, msg)

  def testCommandFromEntity(self):
    """Tests converting a Command entity to a message."""
    command_key = ndb.Key(
        datastore_entities.Request, '1',
        datastore_entities.Command, '2')
    cmd = datastore_entities.Command(
        key=command_key,
        command_line='command_line2',
        cluster='cluster',
        run_target='run_target',
        run_count=10,
        state=common.CommandState.QUEUED,
        start_time=TIMESTAMP,
        end_time=None,
        create_time=TIMESTAMP,
        update_time=TIMESTAMP,
        cancel_reason=common.CancelReason.QUEUE_TIMEOUT,
        shard_count=2,
        shard_index=1)
    message = datastore_entities.ToMessage(cmd)
    self.AssertEqualCommand(cmd, message)

  def AssertEqualRequest(self, request, request_message):
    """Helper to compare request entities and messages."""
    self.assertEqual(request.key.id(), request_message.id)
    self.assertEqual(request.user, request_message.user)
    self.assertEqual(request.command_line, request_message.command_line)
    self.assertEqual(request.state, request_message.state)
    self.assertEqual(request.cancel_message, request_message.cancel_message)
    self.assertEqual(request.cluster, request_message.cluster)
    self.assertEqual(request.run_target, request_message.run_target)
    self.assertEqual(request.shard_count, request_message.shard_count)
    self.assertEqual(request.run_count, request_message.run_count)
    if request.cancel_reason is None:
      self.assertIsNone(request_message.cancel_reason)
    else:
      self.assertEqual(request.cancel_reason, request_message.cancel_reason)

  def AssertEqualCommand(self, command, command_message):
    """Helper to compare command entities and messages."""
    self.assertEqual(command.key.id(), command_message.id)
    self.assertEqual(command.key.parent().id(), command_message.request_id)
    self.assertEqual(command.command_line, command_message.command_line)
    self.assertEqual(command.cluster, command_message.cluster)
    self.assertEqual(command.run_target, command_message.run_target)
    self.assertEqual(command.run_count, command_message.run_count)
    self.assertEqual(command.state, command_message.state)
    self.assertEqual(command.start_time, command_message.start_time)
    self.assertEqual(command.end_time, command_message.end_time)
    self.assertEqual(command.create_time, command_message.create_time)
    self.assertEqual(command.update_time, command_message.update_time)
    self.assertEqual(command.shard_count, command_message.shard_count)
    self.assertEqual(command.shard_index, command_message.shard_index)

  def AssertEqualCommandAttempt(self, entity, message):
    """Helper to compare command attempt entities and messages."""
    _, _, _, command_id, _, attempt_id = entity.key.flat()
    self.assertEqual(command_id, message.command_id)
    self.assertEqual(entity.task_id, message.task_id)
    self.assertEqual(attempt_id, message.attempt_id)
    self.assertEqual(entity.state, message.state)
    self.assertEqual(entity.hostname, message.hostname)
    self.assertEqual(entity.device_serial, message.device_serial)
    self.assertEqual(entity.start_time, message.start_time)
    self.assertEqual(entity.end_time, message.end_time)
    self.assertEqual(entity.status, message.status)
    self.assertEqual(entity.error, message.error)
    self.assertEqual(entity.summary, message.summary)
    self.assertEqual(entity.total_test_count, message.total_test_count)
    self.assertEqual(entity.failed_test_count, message.failed_test_count)
    self.assertEqual(entity.create_time, message.create_time)
    self.assertEqual(entity.update_time, message.update_time)

  def testRequestEventMessage_legacyClientCompatibility(self):
    """Tests whether RequestEventMessage is compatible with legacy clients."""
    request = datastore_entities.Request(
        id='request_id',
        user='user',
        command_line='command_line')
    message = api_messages.RequestEventMessage(
        type='request_state_changed',
        request_id=request.key.id(),
        new_state=common.RequestState.RUNNING,
        request=datastore_entities.ToMessage(request))

    obj = json.loads(protojson.encode_message(message))

    self.assertEqual('request_state_changed', obj.get('type'))
    self.assertEqual('request_id', obj.get('request_id'))
    self.assertEqual('RUNNING', obj.get('new_state'))

  def testNoteFromEntity(self):
    """Tests converting a Note datastore entity a corresponding message."""
    note_entity = datastore_entities.Note(user='user0',
                                          timestamp=TIMESTAMP,
                                          message='Hello, World',
                                          offline_reason='something reasonable',
                                          recovery_action='press the button')
    note_message = datastore_entities.ToMessage(note_entity)
    self.assertEqual(note_entity.user, note_message.user)
    self.assertEqual(note_entity.timestamp, note_message.timestamp)
    self.assertEqual(note_entity.message, note_message.message)
    self.assertEqual(note_entity.offline_reason, note_message.offline_reason)
    self.assertEqual(note_entity.recovery_action, note_message.recovery_action)

  def testNoteFromEntity_invalidEntity(self):
    """Tests converting an invalid Note entity."""
    fake_note_entity = FakeEntity()
    with self.assertRaises(AssertionError):
      datastore_entities.ToMessage(fake_note_entity)

  def testStateHistoryFromEntity(self):
    """Tests converting a DeviceStateHistory datastore entity a message."""
    entity = datastore_entities.DeviceStateHistory(device_serial='a1',
                                                   timestamp=TIMESTAMP,
                                                   state='Gone')
    message = datastore_entities.ToMessage(entity)
    self.assertEqual(entity.timestamp, message.timestamp)
    self.assertEqual(entity.state, message.state)

  def testStateHistoryFromEntity_invalidEntity(self):
    """Tests converting an invalid StateHistory entity."""
    fake_state_history_entity = FakeEntity()
    with self.assertRaises(AssertionError):
      datastore_entities.ToMessage(fake_state_history_entity)

  def testHostFromEntity_invalidEntity(self):
    """Tests converting an invalid Host entity."""
    fake_host_entity = FakeEntity()
    with self.assertRaises(AssertionError):
      datastore_entities.ToMessage(fake_host_entity)

  def _CreateMockHostInfoEntity(self):
    """Helper function to get mock host info entity."""
    d1_count = datastore_entities.DeviceCountSummary(
        run_target='d1',
        total=10,
        offline=1,
        available=5,
        allocated=4,
        timestamp=TIMESTAMP)
    d2_count = datastore_entities.DeviceCountSummary(
        run_target='d2',
        total=5,
        offline=1,
        available=3,
        allocated=1,
        timestamp=TIMESTAMP)
    host_config_entity = datastore_entities.HostConfig(
        hostname='hostname',
        tf_global_config_path='path',
        host_login_name='loginname')
    return datastore_entities.HostInfo(
        hostname='hostname',
        lab_name='alab',
        host_group='atp-us-mtv-43',
        physical_cluster='acluster',
        pools=['apct', 'asit'],
        host_state=api_messages.HostState.RUNNING,
        host_config=host_config_entity,
        assignee='auser',
        extra_info={
            'host_url': 'aurl',
        },
        device_count_summaries=[d1_count, d2_count])

  def testHostInfoFromEntity(self):
    """Test converting from host_info to host_info message."""
    host_info_entity = self._CreateMockHostInfoEntity()
    host_info_message = datastore_entities.ToMessage(host_info_entity)
    self.assertEqual(host_info_entity.hostname, host_info_message.hostname)
    self.assertEqual('RUNNING', host_info_message.host_state)
    self.assertEqual('alab', host_info_message.lab_name)
    self.assertEqual('acluster', host_info_message.cluster)
    self.assertEqual('atp-us-mtv-43', host_info_message.host_group)
    self.assertEqual(['apct', 'asit'], host_info_message.pools)
    self.assertEqual('auser', host_info_message.assignee)
    host_config_entity = host_info_entity.host_config
    self.assertEqual(
        host_config_entity.hostname, host_info_message.host_config.hostname)
    self.assertEqual(host_config_entity.host_login_name,
                     host_info_message.host_config.host_login_name)
    self.assertEqual(host_config_entity.tf_global_config_path,
                     host_info_message.host_config.tf_global_config_path)
    self.assertEqual(
        host_info_entity.extra_info,
        api_messages.KeyValuePairMessagesToMap(
            host_info_message.extra_info))
    self.assertEqual(2, len(host_info_message.device_count_summaries))
    self.assertEqual('d1',
                     host_info_message.device_count_summaries[0].run_target)
    self.assertEqual(10, host_info_message.device_count_summaries[0].total)
    self.assertEqual(1, host_info_message.device_count_summaries[0].offline)
    self.assertEqual(5, host_info_message.device_count_summaries[0].available)
    self.assertEqual(4, host_info_message.device_count_summaries[0].allocated)
    self.assertEqual('d2',
                     host_info_message.device_count_summaries[1].run_target)
    self.assertEqual(5, host_info_message.device_count_summaries[1].total)
    self.assertEqual(1, host_info_message.device_count_summaries[1].offline)
    self.assertEqual(3, host_info_message.device_count_summaries[1].available)
    self.assertEqual(1, host_info_message.device_count_summaries[1].allocated)
    self.assertTrue(host_info_message.is_bad)

  def _CreateMockDeviceInfoEntity(self):
    """Helper function to create mock device info entity."""
    return datastore_entities.DeviceInfo(
        device_serial='adevice',
        hostname='hostname',
        lab_name='alab',
        physical_cluster='acluster',
        host_group='atp-us-mtv-43',
        pools=['apct', 'asit'],
        device_type=api_messages.DeviceTypeMessage.PHYSICAL,
        state='Available',
        extra_info={
            'device_url': 'aurl',
            'product': 'aproduct',
            'last_known_build_id': 'P1234',
            'sim_state': 'unknown',
        })

  def testDeviceInfoFromEntity(self):
    """Test converting from device_info to device_info message."""
    entity = self._CreateMockDeviceInfoEntity()
    msg = datastore_entities.ToMessage(entity)
    self.assertEqual(entity.device_serial, msg.device_serial)
    self.assertEqual(entity.hostname, msg.hostname)
    self.assertEqual('Available', msg.state)
    self.assertEqual('alab', msg.lab_name)
    self.assertEqual('acluster', msg.cluster)
    self.assertEqual('atp-us-mtv-43', msg.host_group)
    self.assertEqual(['apct', 'asit'], msg.pools)
    self.assertEqual(
        entity.extra_info,
        api_messages.KeyValuePairMessagesToMap(
            msg.extra_info))

  def testPredefinedMessageFromEntity(self):
    entity = datastore_entities.PredefinedMessage(
        key=ndb.Key(datastore_entities.PredefinedMessage, 123456789),
        lab_name='lab-name-01',
        type=api_messages.PredefinedMessageType.DEVICE_OFFLINE_REASON,
        content='device offline reason 1',
        create_timestamp=TIMESTAMP,
        used_count=4)
    msg = datastore_entities.ToMessage(entity)
    self.assertEqual('123456789', msg.id)
    self.assertEqual(entity.lab_name, msg.lab_name)
    self.assertEqual(entity.type, msg.type)
    self.assertEqual(entity.content, msg.content)
    self.assertEqual(entity.create_timestamp, msg.create_timestamp)
    self.assertEqual(entity.used_count, msg.used_count)

  def testDeviceNoteFromEntity(self):
    entity = datastore_entities.DeviceNote(
        key=ndb.Key(datastore_entities.DeviceNote, 123456789),
        device_serial='device_serial_1',
        note=datastore_entities.Note(
            user='user_1',
            timestamp=TIMESTAMP,
            offline_reason='offline_reason_1',
            recovery_action='recovery_action_1',
            message='message_1'))
    msg = datastore_entities.ToMessage(entity)
    self.assertEqual('123456789', msg.id)
    self.assertEqual(entity.device_serial, msg.device_serial)
    self.assertEqual(entity.note.user, msg.user)
    self.assertEqual(entity.note.timestamp, msg.update_timestamp)
    self.assertEqual(entity.note.offline_reason, msg.offline_reason)
    self.assertEqual(entity.note.recovery_action, msg.recovery_action)
    self.assertEqual(entity.note.message, msg.message)

  def testHostNoteFromEntity(self):
    entity = datastore_entities.HostNote(
        key=ndb.Key(datastore_entities.HostNote, 123456789),
        hostname='hostname_1',
        note=datastore_entities.Note(
            user='user_1',
            timestamp=TIMESTAMP,
            offline_reason='offline_reason_1',
            recovery_action='recovery_action_1',
            message='message_1'))
    msg = datastore_entities.ToMessage(entity)
    self.assertEqual('123456789', msg.id)
    self.assertEqual(entity.hostname, msg.hostname)
    self.assertEqual(entity.note.user, msg.user)
    self.assertEqual(entity.note.timestamp, msg.update_timestamp)
    self.assertEqual(entity.note.offline_reason, msg.offline_reason)
    self.assertEqual(entity.note.recovery_action, msg.recovery_action)
    self.assertEqual(entity.note.message, msg.message)

  def testLabInfoFromEntity(self):
    """Test converting from lab_info to lab_info message."""
    key = ndb.Key(datastore_entities.LabInfo, 'alab')
    lab_info = datastore_entities.LabInfo(
        key=key,
        lab_name='alab',
        update_timestamp=TIMESTAMP,
        owners=['user1', 'user2', 'user3'])
    msg = datastore_entities.ToMessage(lab_info)
    self.assertEqual(lab_info.lab_name, msg.lab_name)
    self.assertEqual(lab_info.owners, msg.owners)
    self.assertEqual(lab_info.update_timestamp, msg.update_timestamp)


if __name__ == '__main__':
  unittest.main()
