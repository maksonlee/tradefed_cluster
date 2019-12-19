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

"""Tests for tradefed_cluster.device_snapshot_api."""

import datetime
import unittest

import mock
from protorpc import protojson

from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import datastore_entities
from tradefed_cluster import device_info_reporter
from tradefed_cluster import device_snapshot_api

DATE_0 = datetime.date(2015, 11, 2)
UPDATE_TIME_0 = datetime.datetime(2015, 11, 2, 12)


def BuildDeviceInfo(
    device_serial='serial', cluster='free', run_target='shamu',
    product='product', product_variant='variant', state='Available'):
  """Test helper to build device snapshots using a set of defaults."""
  return datastore_entities.DeviceInfo(
      device_serial=device_serial,
      cluster=cluster,
      device_type=api_messages.DeviceTypeMessage.EMULATOR,
      run_target=run_target,
      product=product,
      product_variant=product_variant,
      hostname='atl-100.mtv',
      build_id='MMB29H',
      sdk_version='23',
      timestamp=datetime.datetime(2015, 11, 7),
      hidden=False,
      battery_level='100',
      state=state)


class DeviceSnapshotApiTest(api_test.ApiTest):

  @mock.patch.object(device_info_reporter, 'GetDeviceSnapshotForDate')
  def testGetDeviceSnapshot(self, mock_get_devices):
    # Test GetDeviceSnapshot
    devices = [
        BuildDeviceInfo(device_serial='s0'),
        BuildDeviceInfo(device_serial='s1')]
    mock_get_devices.return_value = device_info_reporter.DeviceSnapshot(
        date=DATE_0, update_time=UPDATE_TIME_0, devices=devices)
    api_request = {'date': DATE_0.isoformat()}
    response = self.testapp.post_json(
        '/_ah/api/DeviceSnapshotApi.GetDeviceSnapshot', api_request)
    self.assertEqual('200 OK', response.status)
    mock_get_devices.assert_called_once_with(DATE_0)
    snapshot = protojson.decode_message(
        device_snapshot_api.DeviceSnapshot, response.body)
    self.assertEqual(2, len(snapshot.devices))
    self.assertEqual('s0', snapshot.devices[0].device_serial)
    self.assertEqual('s1', snapshot.devices[1].device_serial)

  @mock.patch.object(device_info_reporter, 'GetDeviceSnapshotForDate')
  def testGetDeviceSnapshot_noDate(self, mock_get_devices):
    # Test GetDeviceSnapshot with no date
    devices = [
        BuildDeviceInfo(device_serial='s0'),
        BuildDeviceInfo(device_serial='s1')]
    mock_get_devices.return_value = device_info_reporter.DeviceSnapshot(
        date=DATE_0, update_time=UPDATE_TIME_0, devices=devices)
    response = self.testapp.post_json(
        '/_ah/api/DeviceSnapshotApi.GetDeviceSnapshot', {})
    self.assertEqual('200 OK', response.status)
    mock_get_devices.assert_called_once_with(None)
    snapshot = protojson.decode_message(
        device_snapshot_api.DeviceSnapshot, response.body)
    self.assertEqual(2, len(snapshot.devices))
    self.assertEqual('s0', snapshot.devices[0].device_serial)
    self.assertEqual('s1', snapshot.devices[1].device_serial)
    self.assertEqual(DATE_0, snapshot.date.date())
    self.assertEqual(UPDATE_TIME_0, snapshot.updateTime)

  @mock.patch.object(device_info_reporter, 'GetDeviceSnapshotForDate')
  def testGetDeviceSnapshot_noDevices(self, mock_get_devices):
    # Test GetDeviceSnapshot when there is no snapshot
    mock_get_devices.return_value = device_info_reporter.DeviceSnapshot(
        date=DATE_0, update_time=UPDATE_TIME_0, devices=[])
    api_request = {'date': DATE_0.isoformat()}
    response = self.testapp.post_json(
        '/_ah/api/DeviceSnapshotApi.GetDeviceSnapshot', api_request)
    self.assertEqual('200 OK', response.status)
    mock_get_devices.assert_called_once_with(DATE_0)
    snapshot = protojson.decode_message(
        device_snapshot_api.DeviceSnapshot, response.body)
    self.assertEqual(0, len(snapshot.devices))

if __name__ == '__main__':
  unittest.main()

