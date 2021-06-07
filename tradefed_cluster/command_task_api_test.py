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

"""Tests for command_task_api module."""

import datetime
import unittest

import grpc
import mock
from protorpc import protojson

from tradefed_cluster.util import ndb_shim as ndb

from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import command_manager
from tradefed_cluster import command_task_api
from tradefed_cluster import command_task_matcher  from tradefed_cluster import command_task_store
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import env_config  from tradefed_cluster import metric


TIMESTAMP = datetime.datetime(2018, 4, 30, 0, 0, 0)
REQUEST_ID = '1001'


class CommandTaskApiTest(api_test.ApiTest):

  def setUp(self):
    api_test.ApiTest.setUp(self)
    request_key = ndb.Key(
        datastore_entities.Request, REQUEST_ID,
        namespace=common.NAMESPACE)
    self.request = datastore_test_util.CreateRequest(
        request_id=request_key.id(),
        user='user1',
        command_line='command_line')
    self.request.put()
    self.command = self._AddCommand(
        REQUEST_ID,
        '1',
        command_line='cmd',
        cluster='example_cluster',
        run_target='hammerhead',
        run_count=1,
        ants_invocation_id='i123',
        ants_work_unit_id='w123')
    self.plugin_patcher = mock.patch(
        '__main__.env_config.CONFIG.plugin')
    self.plugin_patcher.start()
    self.host = datastore_test_util.CreateHost('cluster', 'hostname', 'alab')

  def tearDown(self):
    self.plugin_patcher.stop()
    api_test.ApiTest.tearDown(self)

  def _AddCommand(self,
                  request_id,
                  command_id,
                  command_line,
                  cluster,
                  run_target,
                  run_count=1,
                  priority=None,
                  shard_count=None,
                  shard_index=None,
                  ants_invocation_id=None,
                  ants_work_unit_id=None):
    """Adds a mock command and add a corresponding task to task store."""
    key = ndb.Key(
        datastore_entities.Request,
        request_id,
        datastore_entities.Command,
        command_id,
        namespace=common.NAMESPACE)
    plugin_data = {'ants_invocation_id': ants_invocation_id,
                   'ants_work_unit_id': ants_work_unit_id}
    command = datastore_entities.Command(
        key=key,
        request_id=request_id,
        command_line=command_line,
        cluster=cluster,
        run_target=run_target,
        run_count=run_count,
        shard_count=shard_count,
        shard_index=shard_index,
        priority=priority,
        plugin_data=plugin_data)
    command.put()
    command_manager.ScheduleTasks([command])
    return command

  def testEnsureCommandConsistency_errorCommand(self):
    """Final command should be inconsistent."""
    # Marking existing command as Error. Request will remain as queued.
    self.command.state = common.CommandState.ERROR
    self.command.put()

    is_consistent = (
        command_task_api.CommandTaskApi()._EnsureCommandConsistency(
            REQUEST_ID, '1', '%s-1-0' % REQUEST_ID))
    self.assertFalse(is_consistent)
    # tasks is deleted from task store.
    task = command_task_store.GetTask('%s-1-0' % REQUEST_ID)
    self.assertIsNone(task)

  def testEnsureCommandConsistency_cancelledCommand(self):
    """Cancelled command should be inconsistent."""
    # Marking existing command as cancelled. Request will remain as queued.
    self.command.state = common.CommandState.CANCELED
    self.command.put()

    is_consistency = (
        command_task_api.CommandTaskApi()._EnsureCommandConsistency(
            REQUEST_ID, '1', '%s-1-0' % REQUEST_ID))
    self.assertFalse(is_consistency)
    # tasks is deleted from task store.
    task = command_task_store.GetTask('%s-1-0' % REQUEST_ID)
    self.assertIsNone(task)
    # Both request and command should be cancelled
    command = self.command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.CANCELED, command.state)
    request = self.command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.CANCELED, request.state)

  def testEnsureCommandConsistency_cancelledCommand_otherTask(self):
    """Cancelled command should not cancel unrelated commands."""
    self._AddCommand(REQUEST_ID, '2', 'command', 'cluster', 'run_target1')
    self.command.state = common.CommandState.CANCELED
    self.command.put()
    is_consistency = (
        command_task_api.CommandTaskApi()._EnsureCommandConsistency(
            REQUEST_ID, '1', '%s-1-0' % REQUEST_ID))
    self.assertFalse(is_consistency)
    task = command_task_store.GetTask('%s-2-0' % REQUEST_ID)
    self.assertIsNotNone(task)

  def testEnsureCommandConsistency_cancelledRequest(self):
    """Task for canceled request should be inconsistant."""
    # Marking existing request as cancelled. Command will remain as queued.
    self.request.state = common.RequestState.CANCELED
    self.request.put()
    task = command_task_store.GetTask('%s-1-0' % REQUEST_ID)
    self.assertIsNotNone(task)

    is_consistency = (
        command_task_api.CommandTaskApi()._EnsureCommandConsistency(
            REQUEST_ID, '1', '%s-1-0' % REQUEST_ID))
    self.assertFalse(is_consistency)

    task = command_task_store.GetTask('%s-1-0' % REQUEST_ID)
    self.assertIsNone(task)
    # Both request and command should be cancelled
    command = self.command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.CANCELED, command.state)
    request = self.command.key.parent().get(use_cache=False)
    self.assertEqual(common.RequestState.CANCELED, request.state)

  def testEnsureCommandConsistency_cancelledRequest_otherTasks(self):
    """Cancelled request should not cancel unrelated commands."""
    self._AddCommand(REQUEST_ID, '2', 'command', 'cluster', 'run_target1')
    self.request.state = common.RequestState.CANCELED
    self.request.put()

    is_consistency = (
        command_task_api.CommandTaskApi()._EnsureCommandConsistency(
            REQUEST_ID, '1', '%s-1-0' % REQUEST_ID))
    self.assertFalse(is_consistency)

    self.assertIsNotNone(command_task_store.GetTask('%s-2-0' % REQUEST_ID))

  def testEnsureCommandConsistency_commandFinalized(self):
    """Tasks for finalized command or request should be inconsistent."""
    # Marking existing request as cancelled. Command is completed.
    self.request.state = common.RequestState.CANCELED
    self.request.put()
    self.command.state = common.CommandState.COMPLETED
    self.command.put()
    self.assertIsNotNone(command_task_store.GetTask('%s-1-0' % REQUEST_ID))

    is_consistency = (
        command_task_api.CommandTaskApi()._EnsureCommandConsistency(
            REQUEST_ID, '1', '%s-1-0' % REQUEST_ID))

    self.assertFalse(is_consistency)
    self.assertIsNone(command_task_store.GetTask('%s-1-0' % REQUEST_ID))

    # Command state should stay the same.
    command = self.command.key.get(use_cache=False)
    self.assertEqual(common.CommandState.COMPLETED, command.state)

  def testEnsureCommandConsistency_deletedCommandAndRequest(self):
    """Tasks for deleted command and request should be inconsistent."""
    self.assertIsNotNone(command_task_store.GetTask('%s-1-0' % REQUEST_ID))
    self.command.key.delete()
    self.request.key.delete()
    is_consistency = (
        command_task_api.CommandTaskApi()._EnsureCommandConsistency(
            REQUEST_ID, '1', '%s-1-0' % REQUEST_ID))
    self.assertFalse(is_consistency)

    self.assertIsNone(command_task_store.GetTask('%s-1-0' % REQUEST_ID))

  def testCreateCommandAttempt(self):
    request_id = 'request_id'
    command_id = 'command_id'
    leased_tasks = [
        command_task_api.CommandTask(
            task_id='task_id0',
            request_id=request_id,
            command_id=command_id,
            device_serials=['d1'],
            plugin_data=[
                api_messages.KeyValuePair(key='key0', value='value0'),
                api_messages.KeyValuePair(key='key1', value='value1'),
                api_messages.KeyValuePair(key='hostname', value='ahost'),
                api_messages.KeyValuePair(key='lab_name', value='alab'),
                api_messages.KeyValuePair(key='host_group', value='cluster'),
            ]),
        command_task_api.CommandTask(
            task_id='task_id1',
            request_id=request_id,
            command_id=command_id,
            device_serials=['d2', 'd3'],
            plugin_data=[
                api_messages.KeyValuePair(key='key2', value='value2'),
                api_messages.KeyValuePair(key='key3', value='value3'),
                api_messages.KeyValuePair(key='hostname', value='ahost'),
                api_messages.KeyValuePair(key='lab_name', value='alab'),
                api_messages.KeyValuePair(key='host_group', value='agroup'),
            ])
    ]
    command_task_api.CommandTaskApi()._CreateCommandAttempt(leased_tasks)
    attempts = command_manager.GetCommandAttempts(request_id='request_id',
                                                  command_id='command_id')

    self.assertEqual(2, len(attempts))
    self.assertEqual('command_id', attempts[0].command_id)
    self.assertEqual('task_id0', attempts[0].task_id)
    self.assertEqual('ahost', attempts[0].hostname)
    self.assertEqual(['d1'], attempts[0].device_serials)
    self.assertEqual(
        {'host_group': 'cluster', 'hostname': 'ahost', 'lab_name': 'alab',
         'key0': 'value0', 'key1': 'value1'},
        attempts[0].plugin_data)
    self.assertIsNotNone(attempts[0].last_event_time)
    self.assertEqual('command_id', attempts[1].command_id)
    self.assertEqual('task_id1', attempts[1].task_id)
    self.assertEqual('ahost', attempts[1].hostname)
    self.assertEqual(['d2', 'd3'], attempts[1].device_serials)
    self.assertEqual(
        {'host_group': 'agroup', 'hostname': 'ahost', 'lab_name': 'alab',
         'key2': 'value2', 'key3': 'value3'},
        attempts[1].plugin_data)
    self.assertIsNotNone(attempts[1].last_event_time)

  @mock.patch.object(common, 'Now')
  @mock.patch.object(metric, 'RecordCommandTimingMetric')
  @mock.patch.object(command_manager, 'Touch')
  @mock.patch.object(
      command_task_api.CommandTaskApi, '_EnsureCommandConsistency')
  @mock.patch.object(
      command_task_api.CommandTaskApi, '_CreateCommandAttempt')
  def testLeaseHostTasks(
      self, create_command_attempt, ensure_consistency, mock_touch,
      record_timing, mock_now):
    mock_now.return_value = TIMESTAMP
    mock_touch.side_effect = [
        mock.MagicMock(create_time=TIMESTAMP),
        mock.MagicMock(create_time=TIMESTAMP)]
    ensure_consistency.return_value = True
    self._AddCommand(
        self.request.key.id(),
        '2',
        'command',
        'cluster',
        'run_target1',
        ants_invocation_id='i123',
        ants_work_unit_id='w123')
    self._AddCommand(
        self.request.key.id(),
        '3',
        'command',
        'cluster2',
        'run_target3',
        ants_invocation_id='',
        ants_work_unit_id='')

    request = {
        'hostname': 'hostname',
        'cluster': 'cluster',
        'device_infos': [
            {
                'device_serial': 'd1',
                'hostname': 'hostname',
                'run_target': 'run_target1',
                'state': common.DeviceState.AVAILABLE,
                'group_name': 'group1'
            },
            {
                'device_serial': 'd2',
                'hostname': 'hostname',
                'run_target': 'run_target2',
                'state': common.DeviceState.AVAILABLE,
                'group_name': 'group1'
            },
            {
                'device_serial': 'd3',
                'hostname': 'hostname',
                'run_target': 'run_target3',
                'state': common.DeviceState.AVAILABLE,
                'group_name': 'group2'
            },
        ],
        'next_cluster_ids': ['cluster2', 'cluster3']
    }
    response = self.testapp.post_json(
        '/_ah/api/CommandTaskApi.LeaseHostTasks', request)
    self.assertEqual('200 OK', response.status)
    task_list = protojson.decode_message(command_task_api.CommandTaskList,
                                         response.body)

    self.assertEqual(2, len(task_list.tasks))
    task = task_list.tasks[0]
    self.assertEqual('command', task.command_line)
    self.assertEqual('2', task.command_id)
    self.assertEqual('%s-2-0' % REQUEST_ID, task.task_id)
    self.assertEqual(['d1'], task.device_serials)
    self.assertIsNone(task.shard_count)
    self.assertIsNone(task.shard_index)

    task = task_list.tasks[1]
    self.assertEqual('command', task.command_line)
    self.assertEqual('3', task.command_id)
    self.assertEqual('%s-3-0' % REQUEST_ID, task.task_id)
    self.assertEqual(['d3'], task.device_serials)
    self.assertIsNone(task.shard_count)
    self.assertIsNone(task.shard_index)

    create_command_attempt.assert_has_calls([mock.call([
        command_task_api.CommandTask(
            task_id='1001-2-0',
            request_id='1001',
            command_id='2',
            command_line='command',
            device_serials=['d1'],
            run_index=0,
            attempt_index=0,
            plugin_data=[
                api_messages.KeyValuePair(key='ants_invocation_id',
                                          value='i123'),
                api_messages.KeyValuePair(key='ants_work_unit_id',
                                          value='w123'),
                api_messages.KeyValuePair(key='host_group', value='cluster'),
                api_messages.KeyValuePair(key='hostname', value='hostname'),
                api_messages.KeyValuePair(key='lab_name', value='alab'),
                api_messages.KeyValuePair(
                    key='tfc_command_attempt_queue_end_timestamp',
                    value='1525071600000'),
                api_messages.KeyValuePair(
                    key='tfc_command_attempt_queue_start_timestamp',
                    value='1525071600000'),
            ]),
        command_task_api.CommandTask(
            task_id='1001-3-0',
            request_id='1001',
            command_id='3',
            command_line='command',
            device_serials=['d3'],
            run_index=0,
            attempt_index=0,
            plugin_data=[
                api_messages.KeyValuePair(key='ants_invocation_id', value=''),
                api_messages.KeyValuePair(key='ants_work_unit_id', value=''),
                api_messages.KeyValuePair(key='host_group', value='cluster'),
                api_messages.KeyValuePair(key='hostname', value='hostname'),
                api_messages.KeyValuePair(key='lab_name', value='alab'),
                api_messages.KeyValuePair(
                    key='tfc_command_attempt_queue_end_timestamp',
                    value='1525071600000'),
                api_messages.KeyValuePair(
                    key='tfc_command_attempt_queue_start_timestamp',
                    value='1525071600000'),
            ])
    ])])
    ensure_consistency.assert_has_calls([
        mock.call(REQUEST_ID, '2', '%s-2-0' % REQUEST_ID),
        mock.call(REQUEST_ID, '3', '%s-3-0' % REQUEST_ID)])
    mock_touch.assert_has_calls([
        mock.call(REQUEST_ID, '2'),
        mock.call(REQUEST_ID, '3')])
    record_timing.assert_has_calls([
        mock.call(
            cluster_id='cluster',
            run_target='run_target1',
            create_timestamp=TIMESTAMP,
            command_action=metric.CommandAction.LEASE,
            count=True),
        mock.call(
            cluster_id='cluster2',
            run_target='run_target3',
            create_timestamp=TIMESTAMP,
            command_action=metric.CommandAction.LEASE,
            count=True)])

  @mock.patch.object(command_manager, 'Touch')
  @mock.patch.object(
      command_task_api.CommandTaskApi, '_EnsureCommandConsistency')
  def testLeaseHostTasks_withNumTasks(self, ensure_consistency, mock_touch):
    ensure_consistency.return_value = True
    mock_touch.return_value = mock.MagicMock(create_time=TIMESTAMP)

    self._AddCommand(
        self.request.key.id(), '2', 'cmd', 'cluster', 'run_target1')
    self._AddCommand(
        self.request.key.id(), '3', 'cmd', 'cluster', 'run_target1')
    self._AddCommand(
        self.request.key.id(), '4', 'cmd', 'cluster', 'run_target1')
    request = {
        'hostname': 'hostname',
        'cluster': 'cluster',
        'device_infos': [
            {
                'device_serial': 'd1',
                'run_target': 'run_target1',
                'state': common.DeviceState.AVAILABLE,
            },
            {
                'device_serial': 'd2',
                'run_target': 'run_target1',
                'state': common.DeviceState.AVAILABLE,
            },
            {
                'device_serial': 'd3',
                'run_target': 'run_target1',
                'state': common.DeviceState.AVAILABLE,
            },
        ],
        'num_tasks': 2
    }
    response = self.testapp.post_json(
        '/_ah/api/CommandTaskApi.LeaseHostTasks', request)
    self.assertEqual('200 OK', response.status)
    task_list = protojson.decode_message(command_task_api.CommandTaskList,
                                         response.body)

    self.assertEqual(2, len(task_list.tasks))

  @mock.patch.object(
      command_task_api.CommandTaskApi, '_EnsureCommandConsistency')
  def testLeaseHostTasks_inconsistencyCommand(self, ensure_consistency):
    ensure_consistency.return_value = False
    self._AddCommand(REQUEST_ID, '2', 'command', 'cluster', 'run_target1')

    request = {
        'hostname': 'hostname',
        'cluster': 'cluster',
        'device_infos': [
            {
                'device_serial': 'd1',
                'hostname': 'hostname',
                'run_target': 'run_target1',
                'state': common.DeviceState.AVAILABLE,
            },
        ],
        'next_cluster_ids': ['cluster2', 'cluster3']
    }
    response = self.testapp.post_json(
        '/_ah/api/CommandTaskApi.LeaseHostTasks', request)
    self.assertEqual('200 OK', response.status)
    task_list = protojson.decode_message(command_task_api.CommandTaskList,
                                         response.body)

    self.assertEqual(0, len(task_list.tasks))
    ensure_consistency.assert_called_once_with(
        REQUEST_ID, '2', '%s-2-0' % REQUEST_ID)

  @mock.patch.object(command_task_store, 'LeaseTask')
  def testLeaseHostTasks_datastoreContention(self, mock_lease_task):
    mock_lease_task.side_effect = [mock.MagicMock(), grpc.RpcError()]
    self._AddCommand(
        self.request.key.id(),
        '2',
        'command',
        'cluster',
        'run_target1',
        ants_invocation_id='i123',
        ants_work_unit_id='w123')
    self._AddCommand(
        self.request.key.id(),
        '3',
        'command',
        'cluster2',
        'run_target3',
        ants_invocation_id='',
        ants_work_unit_id='')

    request = {
        'hostname': 'hostname',
        'cluster': 'cluster',
        'device_infos': [
            {
                'device_serial': 'd1',
                'hostname': 'hostname',
                'run_target': 'run_target1',
                'state': common.DeviceState.AVAILABLE,
                'group_name': 'group1'
            },
            {
                'device_serial': 'd2',
                'hostname': 'hostname',
                'run_target': 'run_target2',
                'state': common.DeviceState.AVAILABLE,
                'group_name': 'group1'
            },
            {
                'device_serial': 'd3',
                'hostname': 'hostname',
                'run_target': 'run_target3',
                'state': common.DeviceState.AVAILABLE,
                'group_name': 'group2'
            },
        ],
        'next_cluster_ids': ['cluster2', 'cluster3']
    }
    response = self.testapp.post_json(
        '/_ah/api/CommandTaskApi.LeaseHostTasks', request)
    self.assertEqual('200 OK', response.status)
    task_list = protojson.decode_message(command_task_api.CommandTaskList,
                                         response.body)

    self.assertEqual(1, len(task_list.tasks))

  @mock.patch.object(common, 'Now')
  @mock.patch.object(metric, 'RecordCommandTimingMetric')
  @mock.patch.object(command_manager, 'Touch')
  @mock.patch.object(
      command_task_api.CommandTaskApi, '_EnsureCommandConsistency')
  @mock.patch.object(
      command_task_api.CommandTaskApi, '_CreateCommandAttempt')
  def testLeaseHostTasks_nonExistHost(
      self, create_command_attempt, ensure_consistency, mock_touch,
      record_timing, mock_now):
    mock_now.return_value = TIMESTAMP
    mock_touch.side_effect = [mock.MagicMock(create_time=TIMESTAMP)]
    ensure_consistency.return_value = True
    self._AddCommand(
        self.request.key.id(),
        '2',
        'command',
        'non-exist-group1',
        'run_target1',
        ants_invocation_id='i123',
        ants_work_unit_id='w123')

    request = {
        'hostname': 'non-exist-host',
        'cluster': 'non-exist-group1',
        'device_infos': [
            {
                'device_serial': 'd1',
                'hostname': 'hostname',
                'run_target': 'run_target1',
                'state': common.DeviceState.AVAILABLE,
                'group_name': 'non-exist-group1'
            },
        ],
        'next_cluster_ids': ['cluster2', 'cluster3']
    }
    response = self.testapp.post_json(
        '/_ah/api/CommandTaskApi.LeaseHostTasks', request)
    self.assertEqual('200 OK', response.status)
    task_list = protojson.decode_message(command_task_api.CommandTaskList,
                                         response.body)

    self.assertEqual(1, len(task_list.tasks))
    task = task_list.tasks[0]
    self.assertEqual('command', task.command_line)
    self.assertEqual('2', task.command_id)
    self.assertEqual('%s-2-0' % REQUEST_ID, task.task_id)
    self.assertEqual(['d1'], task.device_serials)

    plugin_data = [
        api_messages.KeyValuePair(key='ants_invocation_id', value='i123'),
        api_messages.KeyValuePair(key='ants_work_unit_id', value='w123'),
        api_messages.KeyValuePair(key='host_group', value='non-exist-group1'),
        api_messages.KeyValuePair(key='hostname', value='non-exist-host'),
        api_messages.KeyValuePair(key='lab_name', value='UNKNOWN'),
        api_messages.KeyValuePair(
            key='tfc_command_attempt_queue_end_timestamp',
            value='1525071600000'),
        api_messages.KeyValuePair(
            key='tfc_command_attempt_queue_start_timestamp',
            value='1525071600000'),
    ]
    create_command_attempt.assert_has_calls([
        mock.call(
            [command_task_api.CommandTask(
                task_id='1001-2-0',
                request_id='1001',
                command_id='2',
                command_line='command',
                device_serials=['d1'],
                run_index=0,
                attempt_index=0,
                plugin_data=plugin_data)])])
    ensure_consistency.assert_has_calls([
        mock.call(REQUEST_ID, '2', '%s-2-0' % REQUEST_ID)])
    mock_touch.assert_has_calls([
        mock.call(REQUEST_ID, '2')])
    record_timing.assert_has_calls([
        mock.call(
            cluster_id='non-exist-group1',
            run_target='run_target1',
            create_timestamp=TIMESTAMP,
            command_action=metric.CommandAction.LEASE,
            count=True)])


if __name__ == '__main__':
  unittest.main()
