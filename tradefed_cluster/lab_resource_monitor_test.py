# Lint as: python2, python3
# Copyright 2021 Google LLC
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

"""Tests for lab_resource_monitor."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import base64
import datetime
import json
import unittest

import mock

from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import lab_resource_monitor
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.util import ndb_shim as ndb
from tradefed_cluster.util import pubsub_client as pubsub_client_lib


class LabResourceMonitorTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super().setUp()
    self.env_patcher = mock.patch.object(
        lab_resource_monitor, 'PUBSUB_SUBSCRIPTION', 'asubscription')
    self.env_patcher.start()

  def tearDown(self):
    super().tearDown()
    self.env_patcher.stop()

  def _CreateHostResourceMessage(
      self, hostname, resource_name, resource_instance,
      tag, value, timestamp_str):
    return {
        'identifier': {'hostname': hostname},
        'attribute': [{'name': 'harness_version', 'value': 'aversion'}],
        'resource': [
            {
                'resource_name': resource_name,
                'resource_instance': resource_instance,
                'metric': [{'tag': tag, 'value': value}],
                'timestamp': timestamp_str
            }]
    }

  @mock.patch.object(common, 'Now')
  @mock.patch.object(pubsub_client_lib, 'PubSubClient')
  def testPull(self, mock_pubsub_client_class, mock_now):
    mock_pubsub_client = mock.MagicMock()
    mock_now.side_effect = [
        datetime.datetime(2021, 8, 6, 11, 12),
        datetime.datetime(2021, 8, 6, 11, 13),
        datetime.datetime(2021, 8, 6, 11, 14)
    ]
    mock_pubsub_client_class.return_value = mock_pubsub_client
    host_resource_message = {
        'host': self._CreateHostResourceMessage(
            'ahost', 'disk', '/tmp', 'used', 2.0,
            '2021-08-04T23:28:00.000Z')
    }
    mock_pubsub_client.PullMessages.side_effect = [[
        {
            'message': {
                'data': base64.encodebytes(json.dumps(
                    host_resource_message).encode())
            },
            'ackId': '123',
        }], []]
    lab_resource_monitor._Pull('atopic')
    mock_pubsub_client.assert_has_calls([
        mock.call.CreateSubscription('asubscription', 'atopic'),
        mock.call.PullMessages('asubscription', 100),
        mock.call.AcknowledgeMessages('asubscription', ['123']),
    ])
    host_resource = ndb.Key(datastore_entities.HostResource, 'ahost').get()
    self.assertEqual('ahost', host_resource.hostname)

  @mock.patch.object(common, 'Now')
  @mock.patch.object(pubsub_client_lib, 'PubSubClient')
  @mock.patch.object(lab_resource_monitor, '_ProcessMessage')
  def testPull_exception(
      self, mock_process, mock_pubsub_client_class, mock_now):
    mock_pubsub_client = mock.MagicMock()
    mock_now.side_effect = [
        datetime.datetime(2021, 8, 6, 11, 12),
        datetime.datetime(2021, 8, 6, 11, 13),
        datetime.datetime(2021, 8, 6, 11, 14)
    ]
    mock_pubsub_client_class.return_value = mock_pubsub_client
    host_resource_message1 = {
        'host': self._CreateHostResourceMessage(
            'ahost', 'disk', '/tmp', 'used', 2.0,
            '2021-08-04T23:28:00.000Z')}
    host_resource_message2 = {
        'host': self._CreateHostResourceMessage(
            'ahost2', 'disk', '/tmp', 'used', 2.0,
            '2021-08-04T23:31:00.000Z')}
    mock_pubsub_client.PullMessages.side_effect = [[
        {
            'message': {
                'data': base64.encodebytes(json.dumps(
                    host_resource_message1).encode())
            },
            'ackId': '123',
        }, {
            'message': {
                'data': base64.encodebytes(json.dumps(
                    host_resource_message2).encode())
            },
            'ackId': '124',
        }], []]
    mock_process.side_effect = [Exception(), None]
    lab_resource_monitor._Pull('atopic')
    mock_pubsub_client.assert_has_calls([
        mock.call.CreateSubscription('asubscription', 'atopic'),
        mock.call.PullMessages('asubscription', 100),
        mock.call.AcknowledgeMessages('asubscription', ['124']),
    ])
    mock_process.assert_has_calls([
        mock.call(host_resource_message1),
        mock.call(host_resource_message2),
    ])

  def testProcessMessage(self):
    lab_resource_message = {
        'host': self._CreateHostResourceMessage(
            'ahost', 'disk', '/tmp', 'used', 1.0, '2021-08-04T23:18:00.000Z')
    }
    lab_resource_monitor._ProcessMessage(lab_resource_message)
    host_resource = ndb.Key(datastore_entities.HostResource, 'ahost').get()
    self.assertEqual('ahost', host_resource.hostname)
    self.assertEqual(lab_resource_message['host'], host_resource.resource)
    self.assertEqual(
        datetime.datetime(2021, 8, 4, 23, 18),
        host_resource.event_timestamp)
    self.assertIsNotNone(host_resource.update_timestamp)
    lab_resource_message = {
        'host': self._CreateHostResourceMessage(
            'ahost', 'disk', '/tmp', 'used', 2.0, '2021-08-04T23:28:00.000Z')
    }
    lab_resource_monitor._ProcessMessage(lab_resource_message)
    host_resource = ndb.Key(datastore_entities.HostResource, 'ahost').get()
    self.assertEqual('ahost', host_resource.hostname)
    self.assertEqual(lab_resource_message['host'], host_resource.resource)
    self.assertEqual(
        datetime.datetime(2021, 8, 4, 23, 28),
        host_resource.event_timestamp)
    self.assertIsNotNone(host_resource.update_timestamp)

  def testProcessMessage_oldMessage(self):
    lab_resource_message = {
        'host': self._CreateHostResourceMessage(
            'ahost', 'disk', '/tmp', 'used', 1.0, '2021-08-04T23:18:00.000Z')
    }
    lab_resource_monitor._ProcessMessage(lab_resource_message)
    host_resource = ndb.Key(datastore_entities.HostResource, 'ahost').get()
    self.assertEqual('ahost', host_resource.hostname)
    self.assertEqual(lab_resource_message['host'], host_resource.resource)
    self.assertEqual(
        datetime.datetime(2021, 8, 4, 23, 18),
        host_resource.event_timestamp)
    self.assertIsNotNone(host_resource.update_timestamp)
    out_dated_lab_resource_message = {
        'host': self._CreateHostResourceMessage(
            'ahost', 'disk', '/tmp', 'used', 1.0, '2021-08-04T23:08:00.000Z')
    }
    lab_resource_monitor._ProcessMessage(out_dated_lab_resource_message)
    host_resource = ndb.Key(datastore_entities.HostResource, 'ahost').get()
    # The entity didn't change.
    self.assertEqual('ahost', host_resource.hostname)
    self.assertEqual(lab_resource_message['host'], host_resource.resource)
    self.assertEqual(
        datetime.datetime(2021, 8, 4, 23, 18),
        host_resource.event_timestamp)


if __name__ == '__main__':
  unittest.main()
