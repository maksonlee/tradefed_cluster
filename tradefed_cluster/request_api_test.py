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

"""Tests for request_api module."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import datetime
import json
import unittest
import zlib

import endpoints
import mock
from protorpc import protojson
from six.moves import range
from six.moves import zip

from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import command_manager
from tradefed_cluster import command_monitor
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import request_api
from tradefed_cluster import request_manager
from tradefed_cluster import request_sync_monitor
from tradefed_cluster.util import ndb_shim as ndb

START_TIME = datetime.datetime(2015, 1, 1)
END_TIME = datetime.datetime(2015, 5, 7)


class RequestApiTest(api_test.ApiTest):

  def setUp(self):
    api_test.ApiTest.setUp(self)
    self.request1 = request_manager.CreateRequest(
        request_id='1', user='user1', command_line='command_line1')
    self.request1.state = common.RequestState.RUNNING
    self.request1.put()
    self.request2 = request_manager.CreateRequest(
        request_id='2', user='user2', command_line='command_line2')
    self.request2.state = common.RequestState.COMPLETED
    self.request2.put()
    self.requests = [self.request1, self.request2]

    self.command1 = datastore_entities.Command(
        parent=self.request1.key,
        id='1',
        request_id='1',
        command_line='command_line',
        cluster='cluster',
        run_target='run_target',
        run_count=1,
        state=common.CommandState.RUNNING,
        start_time=START_TIME,
        end_time=None,
        create_time=START_TIME,
        update_time=START_TIME)
    self.command1.put()

    self.command2 = datastore_entities.Command(
        parent=self.request1.key,
        id='2',
        request_id='1',
        command_line='command_line',
        cluster='cluster',
        run_target='run_target',
        run_count=1,
        state=common.CommandState.RUNNING,
        start_time=START_TIME,
        end_time=None,
        create_time=START_TIME,
        update_time=START_TIME)
    self.command2.put()
    self.commands = [self.command1, self.command2]

  def testNewRequests(self):
    command_line = (
        'command_line1 --branch branch'
        ' --build-flavor build_target'
        ' --build-os linux')

    api_request = {
        'user': 'user1',
        'command_line': ('command_line1 --branch branch'
                         ' --build-flavor build_target'
                         ' --build-os linux'),
        'cluster': 'cluster',
        'run_target': 'run_target',
        'run_count': 1,
        'shard_count': 3,
        'plugin_data': [
            {'key': 'ants_invocation_id', 'value': 'i123'},
            {'key': 'ants_work_unit_id', 'value': 'w123'},
        ],
        'max_retry_on_test_failures': 10,
    }

    api_response = self.testapp.post_json('/_ah/api/RequestApi.NewRequest',
                                          api_request)

    return_request = protojson.decode_message(api_messages.RequestMessage,
                                              api_response.body)
    self.assertIsNotNone(return_request.id)
    self.assertEqual(common.NAMESPACE, return_request.api_module_version)
    request_entity = request_manager.GetRequest(return_request.id)
    self.assertEqual('user1', request_entity.user)
    self.assertEqual(command_line, request_entity.command_line)
    self.assertEqual(3, request_entity.shard_count)
    self.assertEqual(1, request_entity.run_count)
    self.assertEqual(10, request_entity.max_retry_on_test_failures)
    self.assertEqual('i123', request_entity.plugin_data.get(
        'ants_invocation_id'))
    self.assertEqual('w123', request_entity.plugin_data.get(
        'ants_work_unit_id'))

    tasks = self.mock_task_scheduler.GetTasks(
        queue_names=(request_manager.REQUEST_QUEUE,))
    self.assertEqual(len(tasks), 1)

    request_task = json.loads(zlib.decompress(tasks[0].payload))
    self.assertEqual(request_task['id'], return_request.id)
    self.assertEqual(request_task['command_line'], command_line)
    self.assertEqual(request_task['user'], 'user1')

    monitor_tasks = self.mock_task_scheduler.GetTasks(
        queue_names=(request_sync_monitor.REQUEST_SYNC_QUEUE,))
    self.assertLen(monitor_tasks, 1)

    monitor_task = json.loads(monitor_tasks[0].payload)
    self.assertEqual(monitor_task[request_sync_monitor.REQUEST_ID_KEY],
                     return_request.id)

  def testNewRequests_withEscape(self):
    command_line = (
        'command_line1 --branch branch'
        ' --build-flavor build_target'
        ' --build-os linux'
        ' --arg \'option=\'"\'"\'value\'"\'"\'\'')

    api_request = {
        'user': 'user1',
        'command_line': ('command_line1 --branch branch'
                         ' --build-flavor build_target'
                         ' --build-os linux'
                         ' --arg \'option=\'"\'"\'value\'"\'"\'\''),
        'cluster': 'cluster',
        'run_target': 'run_target',
        'run_count': 1,
        'shard_count': 3,
        'plugin_data': [
            {'key': 'ants_invocation_id', 'value': 'i123'},
            {'key': 'ants_work_unit_id', 'value': 'w123'},
        ],
    }

    api_response = self.testapp.post_json('/_ah/api/RequestApi.NewRequest',
                                          api_request)

    return_request = protojson.decode_message(api_messages.RequestMessage,
                                              api_response.body)
    self.assertIsNotNone(return_request.id)
    self.assertEqual(common.NAMESPACE, return_request.api_module_version)
    request_entity = request_manager.GetRequest(return_request.id)
    self.assertEqual('user1', request_entity.user)
    self.assertEqual(command_line, request_entity.command_line)
    self.assertEqual(3, request_entity.shard_count)
    self.assertEqual(1, request_entity.run_count)
    self.assertEqual('i123', request_entity.plugin_data.get(
        'ants_invocation_id'))
    self.assertEqual('w123', request_entity.plugin_data.get(
        'ants_work_unit_id'))

    tasks = self.mock_task_scheduler.GetTasks(
        queue_names=(request_manager.REQUEST_QUEUE,))
    self.assertEqual(len(tasks), 1)

    request_task = json.loads(zlib.decompress(tasks[0].payload))
    self.assertEqual(request_task['id'], return_request.id)
    self.assertEqual(request_task['command_line'], command_line)
    self.assertEqual(request_task['user'], 'user1')

    monitor_tasks = self.mock_task_scheduler.GetTasks(
        queue_names=(request_sync_monitor.REQUEST_SYNC_QUEUE,))
    self.assertLen(monitor_tasks, 1)

  def testNewRequests_missingFields(self):
    command_line = (
        'command_line1 --branch branch'
        ' --build-flavor build_target'
        ' --build-os linux')

    api_request = {
        'user': 'user1',
        'command_line': ('command_line1 --branch branch'
                         ' --build-flavor build_target'
                         ' --build-os linux'),
        'cluster': 'cluster',
        'run_target': 'run_target',
        'run_count': 1,
        'shard_count': 3,
    }

    api_response = self.testapp.post_json('/_ah/api/RequestApi.NewRequest',
                                          api_request)
    return_request = protojson.decode_message(api_messages.RequestMessage,
                                              api_response.body)

    self.assertIsNotNone(return_request.id)

    request_entity = request_manager.GetRequest(return_request.id)
    self.assertEqual(3, request_entity.shard_count)
    self.assertEqual(1, request_entity.run_count)
    self.assertEqual('cluster', request_entity.cluster)
    self.assertEqual('run_target', request_entity.run_target)
    self.assertEqual('user1', request_entity.user)
    self.assertEqual(command_line, request_entity.command_line)
    tasks = self.mock_task_scheduler.GetTasks(
        queue_names=(request_manager.REQUEST_QUEUE,))
    self.assertEqual(len(tasks), 1)
    request_task = json.loads(zlib.decompress(tasks[0].payload))
    self.assertEqual(request_task['id'], return_request.id)
    self.assertEqual(request_task['command_line'], command_line)
    self.assertEqual(request_task['user'], 'user1')
    self.assertIsNone(request_entity.plugin_data.get('ants_invocation_id'))
    self.assertIsNone(request_entity.plugin_data.get('ants_work_unit_id'))

    monitor_tasks = self.mock_task_scheduler.GetTasks(
        queue_names=(request_sync_monitor.REQUEST_SYNC_QUEUE,))
    self.assertLen(monitor_tasks, 1)

  def testNewRequests_emptyField(self):
    api_request = {
        'user': 'user1',
        'command_line': (
            'command_line1 --branch branch'
            ' --build-flavor build_target'
            ' --build-os linux'),
        'cluster': '',
        'run_target': 'run_target',
        'run_count': 1
    }

    api_response = self.testapp.post_json('/_ah/api/RequestApi.NewRequest',
                                          api_request, expect_errors=True)
    self.assertEqual('400 Bad Request', api_response.status)

  def testNewRequests_withTestEnvironmentAndTestResources(self):
    command_line = 'command_line1'
    api_request = {
        'user': 'user',
        'command_line': command_line,
        'type': 'MANAGED',
        'test_environment': {
            'env_vars': [
                {'key': 'foo1', 'value': 'bar1'},
                {'key': 'foo2', 'value': 'bar2'},
            ],
            'output_file_patterns': ['file1', 'file2'],
            'setup_scripts': ['script1', 'script2']
        },
        'test_resources': [
            {'url': 'url1', 'name': 'name1'},
            {'url': 'url2', 'name': 'name2'}
        ]
    }

    api_response = self.testapp.post_json(
        '/_ah/api/RequestApi.NewRequest', api_request)

    request_msg = protojson.decode_message(
        api_messages.RequestMessage, api_response.body)
    self.assertIsNotNone(request_msg.id)

    request_entity = request_manager.GetRequest(request_msg.id)
    self.assertEqual('user', request_entity.user)
    self.assertEqual(command_line, request_entity.command_line)
    self.assertEqual(api_messages.RequestType.MANAGED,
                     request_entity.type)

    test_env = request_manager.GetTestEnvironment(request_msg.id)
    self.assertEqual({'foo1': 'bar1', 'foo2': 'bar2'}, test_env.env_vars)
    self.assertEqual(
        api_request['test_environment']['output_file_patterns'],
        test_env.output_file_patterns)
    self.assertEqual(
        api_request['test_environment']['setup_scripts'],
        test_env.setup_scripts)
    test_resources = request_manager.GetTestResources(request_msg.id)
    self.assertEqual(len(api_request['test_resources']), len(test_resources))
    for i in range(len(api_request['test_resources'])):
      self.assertEqual(
          api_request['test_resources'][i]['url'], test_resources[i].url)
      self.assertEqual(
          api_request['test_resources'][i]['name'], test_resources[i].name)

    tasks = self.mock_task_scheduler.GetTasks(
        queue_names=(request_manager.REQUEST_QUEUE,))
    self.assertEqual(len(tasks), 1)
    request_task = json.loads(zlib.decompress(tasks[0].payload))
    self.assertEqual(request_msg.id, request_task['id'])
    self.assertEqual(command_line, request_task['command_line'])
    self.assertEqual('user', request_task['user'])

    monitor_tasks = self.mock_task_scheduler.GetTasks(
        queue_names=(request_sync_monitor.REQUEST_SYNC_QUEUE,))
    self.assertLen(monitor_tasks, 1)

  def testNewRequests_withTestBenchAttributes(self):
    api_request = {
        'user': 'user1',
        'command_line': 'command_line1',
        'cluster': 'cluster',
        'run_target': 'run_target',
        'test_bench_attributes': ['attr1=val1', 'attr2=val2'],
    }

    api_response = self.testapp.post_json('/_ah/api/RequestApi.NewRequest',
                                          api_request)

    return_request = protojson.decode_message(api_messages.RequestMessage,
                                              api_response.body)
    self.assertIsNotNone(return_request.id)
    request_entity = request_manager.GetRequest(return_request.id)
    run_target_json = json.loads(request_entity.run_target)
    run_target_json = run_target_json['host']['groups'][0]['run_targets'][0]
    self.assertEqual('run_target', run_target_json['name'])
    self.assertEqual('attr1', run_target_json['device_attributes'][0]['name'])
    self.assertEqual('val1', run_target_json['device_attributes'][0]['value'])
    self.assertEqual('attr2', run_target_json['device_attributes'][1]['name'])
    self.assertEqual('val2', run_target_json['device_attributes'][1]['value'])

  def testListRequests(self):
    for request_id in range(1, 11):
      request_id = str(request_id)
      request_manager.CreateRequest(
          user='user1', command_line='command_line1', request_id=request_id)
    api_request = {
        'user': 'user1',
        'state': 0,
        'offset': 1,
        'count': 2,
    }
    api_response = self.testapp.post_json('/_ah/api/RequestApi.ListRequest',
                                          api_request)
    request_collection = (protojson
                          .decode_message(api_messages.RequestMessageCollection,
                                          api_response.body))

    self.assertEqual(2, len(request_collection.requests))
    self.assertEqual('9', request_collection.requests[0].id)
    self.assertEqual('8', request_collection.requests[1].id)

  def testGetRequest(self):
    attempt = datastore_entities.CommandAttempt(
        parent=self.command1.key,
        id='attempt_id',
        task_id='task_id',
        attempt_id='attempt_id',
        state=common.CommandState.RUNNING,
        hostname='hostname',
        device_serial='device_serial',
        start_time=START_TIME,
        end_time=END_TIME,
        status='status',
        error='error',
        summary='summary',
        total_test_count=1000,
        failed_test_count=100,
        failed_test_run_count=10)
    attempt.put()

    api_request = {
        'request_id': 1,
    }
    api_response = self.testapp.post_json('/_ah/api/RequestApi.GetRequest',
                                          api_request)
    request = protojson.decode_message(api_messages.RequestMessage,
                                       api_response.body)

    self.assertEqual(request.id, '1')
    self.assertEqual(request.user, 'user1')
    self.assertEqual(request.command_line, 'command_line1')
    self.assertEqual(1, len(request.command_attempts))
    command_attempt = request.command_attempts[0]
    self.assertEqual('task_id', command_attempt.task_id)
    self.assertEqual('attempt_id', command_attempt.attempt_id)
    self.assertEqual(common.CommandState.RUNNING, command_attempt.state)
    self.assertEqual('hostname', command_attempt.hostname)
    self.assertEqual('device_serial', command_attempt.device_serial)
    self.assertEqual(START_TIME, command_attempt.start_time)
    self.assertEqual(END_TIME, command_attempt.end_time)
    self.assertEqual('status', command_attempt.status)
    self.assertEqual('summary', command_attempt.summary)
    self.assertEqual(1000, command_attempt.total_test_count)
    self.assertEqual(100, command_attempt.failed_test_count)
    self.assertEqual(10, command_attempt.failed_test_run_count)

    self.assertEqual(2, len(request.commands))
    for command, command_msg in zip(self.commands, request.commands):
      self.AssertEqualCommand(command, command_msg)

  def testGetRequest_noCommands(self):
    api_request = {
        'request_id': 2,
    }
    api_response = self.testapp.post_json('/_ah/api/RequestApi.GetRequest',
                                          api_request)
    request = protojson.decode_message(api_messages.RequestMessage,
                                       api_response.body)
    self.assertEqual('user2', request.user)
    self.assertEqual('command_line2', request.command_line)
    self.assertEqual(0, len(request.command_attempts))
    self.assertEqual(0, len(request.commands))

  @mock.patch.object(command_manager, 'CancelCommands')
  def testCancelRequest(self, cancel_command):
    api_request = {
        'request_id': 1,
    }
    api_response = self.testapp.post_json('/_ah/api/RequestApi.CancelRequest',
                                          api_request)
    request = protojson.decode_message(api_messages.RequestMessage,
                                       api_response.body)

    self.assertEqual(request.id, '1')
    self.assertEqual(request.user, 'user1')
    self.assertEqual(request.command_line, 'command_line1')
    cancel_command.assert_called_once_with(
        request_id='1', cancel_reason=common.CancelReason.REQUEST_API)

  @mock.patch.object(command_monitor, 'SyncCommand')
  @mock.patch.object(request_manager, 'Poke')
  def testPokeRequest(self, poke, sync):
    api_request = {
        'request_id': 1,
    }
    api_response = self.testapp.post_json('/_ah/api/RequestApi.PokeRequest',
                                          api_request)
    request = protojson.decode_message(api_messages.RequestMessage,
                                       api_response.body)

    self.assertEqual('200 OK', api_response.status)
    self.assertEqual(request.id, '1')
    self.assertEqual(request.user, 'user1')
    self.assertEqual(request.command_line, 'command_line1')
    poke.assert_called_once_with('1')
    sync.assert_has_calls([
        mock.call('1', '1', add_to_sync_queue=False),
        mock.call('1', '2', add_to_sync_queue=False),
    ])

  @mock.patch.object(request_manager, 'Poke')
  def testPokeRequest_invalidId(self, poke):
    api_request = {
        'request_id': 10,
    }
    api_response = self.testapp.post_json('/_ah/api/RequestApi.PokeRequest',
                                          api_request, expect_errors=True)
    self.assertEqual('404 Not Found', api_response.status)

  @mock.patch.object(command_monitor, 'SyncCommand')
  @mock.patch.object(request_manager, 'Poke')
  def testPokeRequests(self, poke, sync):
    api_request = {
        'request_ids': [1, 2],
        'final_only': False,
    }
    api_response = self.testapp.post_json('/_ah/api/RequestApi.PokeRequests',
                                          api_request)
    self.assertEqual('200 OK', api_response.status)
    poke.assert_has_calls([mock.call('1'), mock.call('2')])
    sync.assert_has_calls([
        mock.call('1', '1', add_to_sync_queue=False),
        mock.call('1', '2', add_to_sync_queue=False),
    ])

  @mock.patch.object(command_monitor, 'SyncCommand')
  @mock.patch.object(request_manager, 'Poke')
  def testPokeRequests_filterNonFinal(self, poke, sync):
    api_request = {
        'request_ids': [1, 2],
        'final_only': True,
    }
    api_response = self.testapp.post_json('/_ah/api/RequestApi.PokeRequests',
                                          api_request)
    self.assertEqual('200 OK', api_response.status)
    poke.assert_called_once_with('2')  # Only 1 request is non-final
    sync.assert_has_calls([
        mock.call('1', '1', add_to_sync_queue=False),
        mock.call('1', '2', add_to_sync_queue=False),
    ])

  @mock.patch.object(command_monitor, 'SyncCommand')
  @mock.patch.object(request_manager, 'Poke')
  def testPokeRequests_invalidIds(self, poke, sync):
    api_request = {
        'request_ids': [3, 4],
    }
    api_response = self.testapp.post_json('/_ah/api/RequestApi.PokeRequests',
                                          api_request)
    self.assertEqual('200 OK', api_response.status)
    poke.assert_not_called()
    sync.assert_not_called()

  def AssertEqualCommand(self, command, command_msg):
    """Helper method to compare a command object with its message."""
    self.assertEqual(command.key.id(), command_msg.id)
    self.assertEqual(command.request_id, command_msg.request_id)
    self.assertEqual(command.command_line, command_msg.command_line)
    self.assertEqual(command.cluster, command_msg.cluster)
    self.assertEqual(command.run_target, command_msg.run_target)
    self.assertEqual(command.run_count, command_msg.run_count)
    self.assertEqual(int(command.state), int(command_msg.state))
    self.assertEqual(command.start_time, command_msg.start_time)
    self.assertEqual(command.end_time, command_msg.end_time)
    self.assertEqual(command.create_time, command_msg.create_time)
    self.assertEqual(command.update_time, command_msg.update_time)

  def testGetInvocationProgress(self):
    mock_test_group_status = datastore_entities.TestGroupStatus(
        name='foo', total_test_count=100, completed_test_count=10,
        failed_test_count=1, is_complete=False, elapsed_time=1)
    attempt1 = datastore_entities.CommandAttempt(
        id='command_attempt1',
        parent=self.command1.key,
        invocation_status=datastore_entities.InvocationStatus(
            test_group_statuses=[mock_test_group_status]))
    attempt1.put()
    attempt2 = datastore_entities.CommandAttempt(
        id='command_attempt2',
        parent=self.command1.key,
        invocation_status=datastore_entities.InvocationStatus(
            test_group_statuses=[mock_test_group_status]))
    attempt2.put()

    req = {'request_id': 1}

    res = self.testapp.post_json(
        '/_ah/api/RequestApi.GetInvocationStatus', req)

    self.assertEqual('200 OK', res.status)
    obj = protojson.decode_message(
        api_messages.InvocationStatus, res.body)
    self.assertEqual(1, len(obj.test_group_statuses))
    self.assertEqual(
        mock_test_group_status.name, obj.test_group_statuses[0].name)
    self.assertEqual(
        mock_test_group_status.total_test_count,
        obj.test_group_statuses[0].total_test_count)
    self.assertEqual(
        mock_test_group_status.completed_test_count,
        obj.test_group_statuses[0].completed_test_count)
    self.assertEqual(
        mock_test_group_status.failed_test_count,
        obj.test_group_statuses[0].failed_test_count)
    self.assertEqual(
        mock_test_group_status.is_complete,
        obj.test_group_statuses[0].is_complete)
    self.assertEqual(
        mock_test_group_status.elapsed_time,
        obj.test_group_statuses[0].elapsed_time)

  def testGetTestContext(self):
    request_id = '1'
    command_id = '1'
    command_key = ndb.Key(
        datastore_entities.Request, str(request_id),
        datastore_entities.Command, command_id,
        namespace=common.NAMESPACE)
    key = ndb.Key(
        datastore_entities.TestContext,
        ndb.Model.allocate_ids(size=1, parent=command_key)[0].id(),
        parent=command_key,
        namespace=common.NAMESPACE)
    test_context = datastore_entities.TestContext(
        key=key,
        command_line='command_line',
        env_vars={'foo': 'bar', 'TFC_ATTEMPT_NUMBER': '0'},
        test_resources=[
            datastore_entities.TestResource(name='name', url='url', path='path')
        ])
    test_context.put()

    res = self.testapp.post_json('/_ah/api/RequestApi.GetTestContext', {
        'request_id': request_id,
        'command_id': command_id
    })

    # Reload after request
    test_context = test_context.key.get(use_cache=False, use_global_cache=False)
    obj = protojson.decode_message(
        api_messages.TestContext, res.body)
    self.assertEqual(test_context.command_line, obj.command_line)
    self.assertEqual(len(test_context.env_vars), len(obj.env_vars))
    for pair in obj.env_vars:
      self.assertEqual(pair.value, test_context.env_vars.get(pair.key))
    self.assertEqual(len(test_context.test_resources), len(obj.test_resources))
    for a, b in zip(test_context.test_resources, obj.test_resources):
      self.assertEqual(a.name, b.name)
      self.assertEqual(a.url, b.url)
      self.assertEqual(a.path, b.path)

  def testUpdateTestContext(self):
    request_id = 1
    command_id = 'command_id'
    command_line = 'command_line'
    env_vars = [{'key': 'foo', 'value': 'bar'}]
    test_resources = [{'name': 'name', 'url': 'url', 'path': 'path'}]

    self.testapp.post_json('/_ah/api/RequestApi.UpdateTestContext', {
        'request_id': request_id,
        'command_id': command_id,
        'command_line': command_line,
        'env_vars': env_vars,
        'test_resources': test_resources,
    })

    command_key = ndb.Key(
        datastore_entities.Request, str(request_id),
        datastore_entities.Command, command_id,
        namespace=common.NAMESPACE)
    rows = datastore_entities.TestContext.query(
        ancestor=command_key).fetch()
    self.assertEqual(1, len(rows))
    test_context = rows[0]
    self.assertEqual(command_line, test_context.command_line)
    self.assertEqual(len(env_vars), len(test_context.env_vars))
    for pair in env_vars:
      self.assertEqual(pair['value'], test_context.env_vars.get(pair['key']))
    self.assertEqual(len(test_resources), len(test_context.test_resources))
    for a, b in zip(test_resources, test_context.test_resources):
      self.assertEqual(a['name'], b.name)
      self.assertEqual(a['url'], b.url)
      self.assertEqual(a['path'], b.path)

  def testGetCommand(self):
    api_response = self.testapp.post_json('/_ah/api/RequestApi.GetCommand', {
        'request_id': '1',
        'command_id': '1'
    })
    self.assertEqual('200 OK', api_response.status)

    command = protojson.decode_message(api_messages.CommandMessage,
                                       api_response.body)
    self.assertEqual(command.id, '1')
    self.assertEqual(command.request_id, '1')
    self.assertEqual(command.command_line, 'command_line')
    self.assertEqual(command.state, common.CommandState.RUNNING)

  def testGetCommand_invalidId(self):
    api_response = self.testapp.post_json(
        '/_ah/api/RequestApi.GetCommand', {
            'request_id': '1',
            'command_id': 'invalid'
        },
        expect_errors=True)
    self.assertEqual('404 Not Found', api_response.status)

  def testBuildRunTarget(self):
    run_target = request_api._BuildRunTarget(
        'a_run_target', ['attr1=val1', 'attr2=val2'])
    run_target_json = json.loads(run_target)
    run_target_json = run_target_json['host']['groups'][0]['run_targets'][0]
    self.assertEqual('a_run_target', run_target_json['name'])
    self.assertEqual('attr1', run_target_json['device_attributes'][0]['name'])
    self.assertEqual('val1', run_target_json['device_attributes'][0]['value'])
    self.assertEqual('attr2', run_target_json['device_attributes'][1]['name'])
    self.assertEqual('val2', run_target_json['device_attributes'][1]['value'])

  def testBuildRunTarget_invalidFormat(self):
    with self.assertRaises(endpoints.BadRequestException):
      request_api._BuildRunTarget('a_run_target', ['attr1'])


if __name__ == '__main__':
  unittest.main()
