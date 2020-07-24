# Copyright 2020 Google LLC
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
"""Tests for device blocklist api."""
import unittest

from protorpc import protojson

from tradefed_cluster import api_messages
from tradefed_cluster import api_test


class DeviceBlocklistApiTest(api_test.ApiTest):
  """Unit test for DeviceBlocklistApi."""

  def testNewDeviceBlocklist(self):
    """Tests NewDeviceBlocklist."""
    api_request = {
        'lab_name': 'alab',
        'user': 'auser',
        'note': 'lab outage'
    }
    api_response = self.testapp.post_json(
        '/_ah/api/DeviceBlocklistApi.NewDeviceBlocklist', api_request)
    msg = protojson.decode_message(
        api_messages.DeviceBlocklistMessage, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    self.assertIsNotNone(msg.create_timestamp)
    self.assertEqual('alab', msg.lab_name)
    self.assertEqual('auser', msg.user)
    self.assertEqual('lab outage', msg.note)


if __name__ == '__main__':
  unittest.main()
