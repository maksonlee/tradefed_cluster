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

"""Unit tests for device manager module."""

import datetime
import json
import unittest

import mock

from tradefed_cluster.util import ndb_shim as ndb

from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import device_manager
from tradefed_cluster import env_config
from tradefed_cluster import host_event
from tradefed_cluster import metric
from tradefed_cluster import testbed_dependent_test


class DeviceManagerTest(testbed_dependent_test.TestbedDependentTest):

  EMULATOR_SERIAL = "test.mtv.corp.example.com:emulator-5554"
  HOST_EVENT = {
      "time": 1331712965,
      "cluster": "test",
      "hostname": "test.mtv.corp.example.com",
      "lab_name": "alab",
      "tf_version": "0001",
      "event_type": "DEVICE_SNAPSHOT",
      "device_infos": [
          {
              "product": "unknown",
              "state": "Available",
              "device_serial": "emulator-5554",
              "sdk_version": "unknown",
              "product_variant": "unknown",
              "build_id": "unknown",
              "run_target": "emulator",
              "battery_level": "unknown"
          },
          {
              "product": "flounder",
              "state": "Available",
              "device_serial": "HT4A1JT01250",
              "sdk_version": "21",
              "product_variant": "flounder",
              "build_id": "LRX22C",
              "run_target": "flounder",
              "battery_level": "50",
              "mac_address": "58:a2:b5:7d:49:24",
              "sim_state": "READY",
              "sim_operator": "operator"
          },
          {
              "product": "flounder",
              "state": "Allocated",
              "device_serial": "",
              "sdk_version": "21",
              "product_variant": "flounder",
              "build_id": "LRX22C",
              "run_target": "flounder",
              "battery_level": "50"
          }],
      "data": {
          "prodcertstatus": "some LOAS status",
          "krbstatus": "some Kerberos status"
      },
      "next_cluster_ids": ["cluster1", "cluster2"]
  }

  HOST_EVENT_STATE_INFO = {
      "time": 1331712965,
      "cluster": "test",
      "event_type": "HOST_STATE_CHANGED",
      "hostname": "test.mtv.corp.example.com",
      "state": "RUNNING",
      "tf_start_time_seconds": 1331712960
  }

  HOST_EVENT_UPDATE_AVAILABLE = {
      "time": 1431712970,
      "data": {},
      "cluster": "test",
      "hostname": "test.mtv.corp.example.com",
      "tf_version": "0002",
      "event_type": "DEVICE_SNAPSHOT",
      "device_infos": [
          {
              "product": "shamu",
              "state": "Available",
              "device_serial": "HT4A1JT01250",
              "sdk_version": "22",
              "product_variant": "shamu",
              "build_id": "LRX22C",
              "run_target": "shamu",
              "battery_level": "100",
              "sim_state": "ABSENT",
              "sim_operator": ""
          }],
      "next_cluster_ids": ["cluster1"],
      "state": None,
      "tf_start_time_seconds": None
  }

  HOST_EVENT_MAC_UPDATE_AVAILABLE = {
      "time": 1431712970,
      "data": {},
      "cluster": "test",
      "hostname": "test.mtv.corp.example.com",
      "tf_version": "0002",
      "event_type": "DEVICE_SNAPSHOT",
      "device_infos": [
          {
              "product": "shamu",
              "state": "Available",
              "device_serial": "HT4A1JT01250",
              "sdk_version": "22",
              "product_variant": "shamu",
              "build_id": "LRX22C",
              "run_target": "shamu",
              "battery_level": "100",
              "sim_state": "ABSENT",
              "sim_operator": "",
              "mac_address": "58:a2:b5:7d:49:25",
          }],
      "state": None,
      "tf_start_time_seconds": None
  }

  HOST_EVENT_RUN_TARGET_UPDATE_AVAILABLE = {
      "time": 1431712970,
      "data": {},
      "cluster": "test",
      "hostname": "test.mtv.corp.example.com",
      "tf_version": "0002",
      "event_type": "DEVICE_SNAPSHOT",
      "device_infos": [
          {
              "product": "unknown",
              "state": "Available",
              "device_serial": "emulator-5554",
              "sdk_version": "unknown",
              "product_variant": "unknown",
              "build_id": "unknown",
              "run_target": "NullDevice",
              "battery_level": "unknown"
          }],
      "state": None,
      "tf_start_time_seconds": None
  }

  HOST_EVENT_UPDATE_UNAVAILABLE = {
      "time": 1431712970,
      "data": {},
      "cluster": "test",
      "hostname": "test.mtv.corp.example.com",
      "tf_version": "0002",
      "event_type": "DEVICE_SNAPSHOT",
      "device_infos": [
          {
              "product": "shamu",
              "state": "Unavailable",
              "device_serial": "HT4A1JT01250",
              "sdk_version": "22",
              "product_variant": "shamu",
              "build_id": "LRX22C",
              "run_target": "shamu",
              "battery_level": "100",
              "sim_state": "",
              "sim_operator": ""
          }],
      "state": None,
      "tf_start_time_seconds": None
  }

  HOST_EVENT_NO_DEVICES = {
      "time": 1431712965,
      "data": {},
      "cluster": "presubmit",
      "hostname": "test-2.mtv.corp.example.com",
      "tf_version": "0003",
      "event_type": "DEVICE_SNAPSHOT",
      "device_infos": []
  }

  HOST_EVENT_NO_DEVICES_UPDATE = {
      "time": 1431712990,
      "data": {},
      "cluster": "free",
      "hostname": "test-2.mtv.corp.example.com",
      "event_type": "DEVICE_SNAPSHOT",
      "tf_version": "0004",
      "device_infos": []
  }

  HOST_EVENT_FAKE_DEVICE = {
      "time": 1331712965,
      "data": {},
      "cluster": "test",
      "hostname": "test.mtv.corp.example.com",
      "tf_version": "0001",
      "event_type": "DEVICE_SNAPSHOT",
      "device_infos": [
          {
              "product": "unknown",
              "state": "Available",
              "device_serial": "0123456789ABCDEF",
              "sdk_version": "unknown",
              "product_variant": "unknown",
              "build_id": "unknown",
              "run_target": "unknown",
              "battery_level": "unknown"
          }]
  }

  HOST_EVENT_LOCALHOST_DEVICE = {
      "time": 1331712965,
      "data": {},
      "cluster": "test",
      "hostname": "test.mtv.corp.example.com",
      "tf_version": "0001",
      "event_type": "DEVICE_SNAPSHOT",
      "device_infos": [
          {
              "product": "unknown",
              "state": "Available",
              "device_serial": "127.0.0.1:123",
              "sdk_version": "unknown",
              "product_variant": "unknown",
              "build_id": "unknown",
              "run_target": "unknown",
              "battery_level": "unknown"
          }]
  }

  HOST_EVENT_WITH_TEST_RUNNER = {
      "time": 1431712965,
      "data": {},
      "hostname": "new_runner.mtv.corp.example.com",
      "test_runner": "new_runner",
      "test_runner_version": "v2",
      "event_type": "DEVICE_SNAPSHOT",
      "device_infos": [
          {
              "state": "Available",
              "device_serial": "new_runner_device",
              "run_target": "new_runner_run_target",
          },
      ]
  }

  def testIsHostEventValid(self):
    """Tests IsHostEventValid for a valid event."""
    self.assertTrue(device_manager.IsHostEventValid(self.HOST_EVENT))

  def testIsHostEventValid_none(self):
    """Tests IsHostEventValid for a None object."""
    self.assertFalse(device_manager.IsHostEventValid(None))

  def testIsHostEventValid_missingHostname(self):
    """Tests IsHostEventValid for an event with missing hostname."""
    host_event_dict = {
        "time": 1431712965,
        "data": {},
        "cluster": "presubmit",
        "tf_version": "0003",
        "event_type": "DEVICE_SNAPSHOT",
        "device_infos": []
    }
    self.assertFalse(device_manager.IsHostEventValid(host_event_dict))

  def testIsHostEventValid_missingTime(self):
    """Tests IsHostEventValid for an event with missing time."""
    host_event_dict = {
        "data": {},
        "cluster": "presubmit",
        "hostname": "test.mtv.corp.example.com",
        "tf_version": "0003",
        "event_type": "DEVICE_SNAPSHOT",
        "device_infos": []
    }
    self.assertFalse(device_manager.IsHostEventValid(host_event_dict))

  @mock.patch.object(metric, "SetHostTestRunnerVersion")
  def testHandleDeviceSnapshot(self, metric_set_version):
    """Tests that HandleDeviceSnapshot() stores device information properly."""
    some_host_event = host_event.HostEvent(**self.HOST_EVENT)
    device_manager.HandleDeviceSnapshotWithNDB(some_host_event)
    host = device_manager.GetHost("test.mtv.corp.example.com")
    metric_set_version.assert_called_once_with(
        device_manager.TF_TEST_RUNNER,
        host.test_runner_version,
        host.physical_cluster,
        host.hostname)
    device_0 = device_manager.GetDevice(device_serial=self.EMULATOR_SERIAL)
    device_1 = device_manager.GetDevice(device_serial="HT4A1JT01250")

    self.assertIsNotNone(device_0)
    self.assertEqual(self.EMULATOR_SERIAL, device_0.device_serial)
    self.assertEqual("emulator", device_0.run_target)
    self.assertEqual("unknown", device_0.build_id)
    self.assertEqual("unknown", device_0.extra_info["build_id"])
    self.assertEqual("unknown", device_0.product)
    self.assertEqual("unknown", device_0.extra_info["product"])
    self.assertEqual("unknown", device_0.product_variant)
    self.assertEqual("unknown", device_0.extra_info["product_variant"])
    self.assertEqual("unknown", device_0.sdk_version)
    self.assertEqual("unknown", device_0.extra_info["sdk_version"])
    self.assertEqual("Available", device_0.state)
    self.assertEqual("test.mtv.corp.example.com", device_0.hostname)
    self.assertEqual("alab", device_0.lab_name)
    self.assertEqual(api_messages.DeviceTypeMessage.EMULATOR,
                     device_0.device_type)
    self.assertEqual(
        datetime.datetime.utcfromtimestamp(self.HOST_EVENT["time"]),
        device_0.timestamp)
    self.assertEqual("unknown", device_0.battery_level)
    self.assertEqual("unknown", device_0.extra_info["battery_level"])
    # TODO: deprecate physical_cluster, use host_group.
    self.assertEqual("test", device_0.physical_cluster)
    self.assertEqual("test", device_0.host_group)
    # TODO: deprecate clusters, use pools.
    self.assertEqual(["test", "cluster1", "cluster2"], device_0.clusters)
    self.assertEqual(["cluster1", "cluster2"], device_0.pools)

    self.assertIsNotNone(device_1)
    self.assertEqual("HT4A1JT01250", device_1.device_serial)
    self.assertEqual("flounder", device_1.run_target)
    self.assertEqual("LRX22C", device_1.build_id)
    self.assertEqual("LRX22C", device_1.extra_info["build_id"])
    self.assertEqual("LRX22C", device_1.last_known_build_id)
    self.assertEqual("LRX22C", device_1.extra_info["last_known_build_id"])
    self.assertEqual("flounder", device_1.product)
    self.assertEqual("flounder", device_1.extra_info["product"])
    self.assertEqual("flounder", device_1.last_known_product)
    self.assertEqual("flounder", device_1.extra_info["last_known_product"])
    self.assertEqual("flounder", device_1.product_variant)
    self.assertEqual("flounder", device_1.extra_info["product_variant"])
    self.assertEqual("flounder", device_1.last_known_product_variant)
    self.assertEqual("flounder",
                     device_1.extra_info["last_known_product_variant"])
    self.assertEqual("21", device_1.sdk_version)
    self.assertEqual("21", device_1.extra_info["sdk_version"])
    self.assertEqual("Available", device_1.state)
    self.assertEqual("test.mtv.corp.example.com", device_1.hostname)
    self.assertEqual("alab", device_0.lab_name)
    self.assertEqual("58:a2:b5:7d:49:24", device_1.mac_address)
    self.assertEqual("58:a2:b5:7d:49:24", device_1.extra_info["mac_address"])
    self.assertEqual("READY", device_1.extra_info["sim_state"])
    self.assertEqual("operator", device_1.extra_info["sim_operator"])
    self.assertEqual(api_messages.DeviceTypeMessage.PHYSICAL,
                     device_1.device_type)
    self.assertEqual(
        datetime.datetime.utcfromtimestamp(self.HOST_EVENT["time"]),
        device_1.timestamp)
    self.assertEqual("50", device_1.battery_level)
    # TODO: deprecate physical_cluster, use host_group.
    self.assertEqual("test", device_1.physical_cluster)
    self.assertEqual("test", device_1.host_group)
    # TODO: deprecate clusters, use pools.
    self.assertEqual(["test", "cluster1", "cluster2"], device_1.clusters)
    self.assertEqual(["cluster1", "cluster2"], device_1.pools)

    host = device_manager.GetHost(self.HOST_EVENT["hostname"])
    self.assertIsNotNone(host)
    # TODO: deprecate physical_cluster, use host_group.
    self.assertEqual(self.HOST_EVENT["cluster"], host.physical_cluster)
    self.assertEqual(self.HOST_EVENT["cluster"], host.host_group)
    # TODO: deprecate clusters, use pools.
    self.assertEqual(["test", "cluster1", "cluster2"], host.clusters)
    self.assertEqual(["cluster1", "cluster2"], host.pools)
    self.assertEqual("alab", device_0.lab_name)
    self.assertEqual("tradefed", host.test_runner)
    self.assertEqual(self.HOST_EVENT["tf_version"], host.test_runner_version)
    self.assertEqual(
        datetime.datetime.utcfromtimestamp(self.HOST_EVENT["time"]),
        host.timestamp)
    self.assertEqual(self.HOST_EVENT["data"], host.extra_info)
    self.assertEqual(2, host.total_devices)
    self.assertEqual(2, host.available_devices)
    self._AssertHostSyncTask(self.HOST_EVENT["hostname"])

  @mock.patch.object(metric, "SetHostTestRunnerVersion")
  def testHandleDeviceSnapshotWithHostState(self, metric_set_version):
    """Tests that HandleDeviceSnapshot() stores Host State info properly."""
    some_host_event = host_event.HostEvent(**self.HOST_EVENT_STATE_INFO)
    device_manager.HandleDeviceSnapshotWithNDB(some_host_event)
    host = device_manager.GetHost(self.HOST_EVENT_STATE_INFO["hostname"])
    self.assertIsNotNone(host)
    self.assertEqual(self.HOST_EVENT_STATE_INFO["cluster"],
                     host.physical_cluster)
    self.assertEqual(
        datetime.datetime.utcfromtimestamp(self.HOST_EVENT_STATE_INFO["time"]),
        host.timestamp)
    self.assertEqual(api_messages.HostState(
        self.HOST_EVENT_STATE_INFO["state"]), host.host_state)
    metric_set_version.assert_not_called()

  def testHandleDeviceSnapshot_availableDevice(self):
    """Tests that HandleDeviceSnapshot() updates available devices."""
    some_host_event = host_event.HostEvent(**self.HOST_EVENT)
    device_manager.HandleDeviceSnapshotWithNDB(some_host_event)
    some_host_event = host_event.HostEvent(**self.HOST_EVENT_UPDATE_AVAILABLE)
    device_manager.HandleDeviceSnapshotWithNDB(some_host_event)
    device_1 = device_manager.GetDevice(device_serial="HT4A1JT01250")

    # All fields should be updated.
    self.assertIsNotNone(device_1)
    self.assertEqual("HT4A1JT01250", device_1.device_serial)
    self.assertEqual("shamu", device_1.run_target)
    self.assertEqual("LRX22C", device_1.build_id)
    self.assertEqual("shamu", device_1.product)
    self.assertEqual("shamu", device_1.product_variant)
    self.assertEqual("22", device_1.sdk_version)
    self.assertEqual("22", device_1.extra_info["sdk_version"])
    self.assertEqual("Available", device_1.state)
    self.assertEqual("58:a2:b5:7d:49:24", device_1.mac_address)
    self.assertEqual("58:a2:b5:7d:49:24", device_1.extra_info["mac_address"])
    self.assertEqual("ABSENT", device_1.extra_info["sim_state"])
    self.assertEqual("", device_1.extra_info["sim_operator"])
    self.assertEqual(api_messages.DeviceTypeMessage.PHYSICAL,
                     device_1.device_type)
    self.assertEqual("test.mtv.corp.example.com", device_1.hostname)
    self.assertEqual(
        datetime.datetime.utcfromtimestamp(
            self.HOST_EVENT_UPDATE_AVAILABLE["time"]),
        device_1.timestamp)
    self.assertEqual("100", device_1.battery_level)
    self.assertEqual("test", device_1.physical_cluster)
    self.assertEqual(["test", "cluster1"], device_1.clusters)
    host = device_manager.GetHost(self.HOST_EVENT["hostname"])
    self.assertIsNotNone(host)
    self.assertEqual("tradefed", host.test_runner)
    self.assertEqual(self.HOST_EVENT_UPDATE_AVAILABLE["tf_version"],
                     host.test_runner_version)
    self.assertEqual(
        self.HOST_EVENT_UPDATE_AVAILABLE["cluster"], host.physical_cluster)
    self.assertEqual(
        datetime.datetime.utcfromtimestamp(
            self.HOST_EVENT_UPDATE_AVAILABLE["time"]),
        host.timestamp)

  def testHandleDeviceSnapshot_availableDevice_updateRunTarget(self):
    """Tests that HandleDeviceSnapshot() updates run target."""
    some_host_event = host_event.HostEvent(**self.HOST_EVENT)
    device_manager.HandleDeviceSnapshotWithNDB(some_host_event)
    some_host_event = host_event.HostEvent(
        **self.HOST_EVENT_RUN_TARGET_UPDATE_AVAILABLE)
    device_manager.HandleDeviceSnapshotWithNDB(some_host_event)
    device_1 = device_manager.GetDevice(device_serial=self.EMULATOR_SERIAL)
    # Run target should be updated.
    self.assertIsNotNone(device_1)
    self.assertEqual(self.EMULATOR_SERIAL, device_1.device_serial)
    self.assertEqual("Available", device_1.state)
    self.assertEqual("NullDevice", device_1.run_target)
    self.assertEqual("unknown", device_1.product)
    self.assertEqual("test", device_1.physical_cluster)
    self.assertEqual(["test"], device_1.clusters)

  def testHandleDeviceSnapshot_availableDevice_updateMac(self):
    """Tests that HandleDeviceSnapshot() updates mac address."""
    some_host_event = host_event.HostEvent(**self.HOST_EVENT)
    device_manager.HandleDeviceSnapshotWithNDB(some_host_event)
    some_host_event = host_event.HostEvent(
        **self.HOST_EVENT_MAC_UPDATE_AVAILABLE)
    device_manager.HandleDeviceSnapshotWithNDB(some_host_event)
    device_1 = device_manager.GetDevice(device_serial="HT4A1JT01250")

    # MAC address should be updated.
    self.assertIsNotNone(device_1)
    self.assertEqual("HT4A1JT01250", device_1.device_serial)
    self.assertEqual("Available", device_1.state)
    self.assertEqual("58:a2:b5:7d:49:25", device_1.mac_address)

  def testHandleDeviceSnapshot_unavailableDevice(self):
    """Tests that HandleDeviceSnapshot() handles unavailable devices."""
    some_host_event = host_event.HostEvent(**self.HOST_EVENT)
    device_manager.HandleDeviceSnapshotWithNDB(some_host_event)
    some_host_event = host_event.HostEvent(**self.HOST_EVENT_UPDATE_UNAVAILABLE)
    device_manager.HandleDeviceSnapshotWithNDB(some_host_event)

    device_1 = device_manager.GetDevice(device_serial="HT4A1JT01250")

    # State, timestamp, and sdk version should be updated.
    # Product, product variant, run target, mac, extra_info should be the same.
    self.assertIsNotNone(device_1)
    self.assertEqual("HT4A1JT01250", device_1.device_serial)
    self.assertEqual("flounder", device_1.run_target)
    self.assertEqual("LRX22C", device_1.build_id)
    self.assertEqual("flounder", device_1.product)
    self.assertEqual("flounder", device_1.product_variant)
    self.assertEqual("22", device_1.sdk_version)
    self.assertEqual("Unavailable", device_1.state)
    self.assertEqual("test.mtv.corp.example.com", device_1.hostname)
    self.assertEqual("58:a2:b5:7d:49:24", device_1.mac_address)
    self.assertEqual("READY", device_1.extra_info["sim_state"])
    self.assertEqual("operator", device_1.extra_info["sim_operator"])
    self.assertEqual(api_messages.DeviceTypeMessage.PHYSICAL,
                     device_1.device_type)
    self.assertEqual(
        datetime.datetime.utcfromtimestamp(
            self.HOST_EVENT_UPDATE_UNAVAILABLE["time"]),
        device_1.timestamp)
    self.assertEqual("100", device_1.battery_level)

    host = device_manager.GetHost(self.HOST_EVENT["hostname"])
    self.assertIsNotNone(host)
    self.assertEqual("tradefed", host.test_runner)
    self.assertEqual(self.HOST_EVENT_UPDATE_UNAVAILABLE["tf_version"],
                     host.test_runner_version)
    self.assertEqual(
        self.HOST_EVENT_UPDATE_UNAVAILABLE["cluster"],
        host.physical_cluster)
    self.assertEqual(
        datetime.datetime.utcfromtimestamp(
            self.HOST_EVENT_UPDATE_UNAVAILABLE["time"]),
        host.timestamp)

    # Missing device should have been marked as gone
    device_2 = device_manager.GetDevice(device_serial=self.EMULATOR_SERIAL)
    self.assertEqual(common.DeviceState.GONE, device_2.state)

  def testHandleDeviceSnapshot_noDevices(self):
    """Tests that HandleDeviceSnapshot() handles hosts with no devices."""
    some_host_event = host_event.HostEvent(**self.HOST_EVENT_NO_DEVICES)
    device_manager.HandleDeviceSnapshotWithNDB(some_host_event)

    host = device_manager.GetHost(self.HOST_EVENT_NO_DEVICES["hostname"])
    self.assertIsNotNone(host)
    self.assertEqual("tradefed", host.test_runner)
    self.assertEqual(self.HOST_EVENT_NO_DEVICES["tf_version"],
                     host.test_runner_version)
    self.assertEqual(self.HOST_EVENT_NO_DEVICES["cluster"],
                     host.physical_cluster)
    self.assertEqual(
        datetime.datetime.utcfromtimestamp(self.HOST_EVENT_NO_DEVICES["time"]),
        host.timestamp)

  @mock.patch.object(
      env_config.CONFIG, "ignore_device_serials", ["0123456789ABCDEF"])
  def testHandleDeviceSnapshot_fakeDevices(self):
    """Tests that HandleDeviceSnapshot() handles hosts with fake devices."""
    some_host_event = host_event.HostEvent(**self.HOST_EVENT_FAKE_DEVICE)
    device_manager.HandleDeviceSnapshotWithNDB(some_host_event)

    host = device_manager.GetHost(self.HOST_EVENT_FAKE_DEVICE["hostname"])
    self.assertIsNotNone(host)
    self.assertEqual("tradefed", host.test_runner)
    self.assertEqual(self.HOST_EVENT_FAKE_DEVICE["tf_version"],
                     host.test_runner_version)
    self.assertEqual(self.HOST_EVENT_FAKE_DEVICE["cluster"],
                     host.physical_cluster)
    self.assertEqual(
        datetime.datetime.utcfromtimestamp(self.HOST_EVENT_FAKE_DEVICE["time"]),
        host.timestamp)
    device_0 = device_manager.GetDevice(device_serial="0123456789ABCDEF")
    self.assertIsNone(device_0)

  def testHandleDeviceSnapshot_localhostDevices(self):
    """Tests that HandleDeviceSnapshot() handles hosts with localhost serial."""
    some_host_event = host_event.HostEvent(**self.HOST_EVENT_LOCALHOST_DEVICE)
    device_manager.HandleDeviceSnapshotWithNDB(some_host_event)

    host = device_manager.GetHost(
        self.HOST_EVENT_LOCALHOST_DEVICE["hostname"])
    self.assertIsNotNone(host)
    self.assertEqual("tradefed", host.test_runner)
    self.assertEqual(self.HOST_EVENT_LOCALHOST_DEVICE["tf_version"],
                     host.test_runner_version)
    self.assertEqual(self.HOST_EVENT_LOCALHOST_DEVICE["cluster"],
                     host.physical_cluster)
    self.assertEqual(
        datetime.datetime.utcfromtimestamp(
            self.HOST_EVENT_LOCALHOST_DEVICE["time"]),
        host.timestamp)
    device_0 = device_manager.GetDevice(device_serial="127.0.0.1:123")
    self.assertIsNone(device_0)

  def testHandleDeviceSnapshot_updateHost(self):
    """Tests that HandleDeviceSnapshot() updates existing hosts."""
    old_host_event = host_event.HostEvent(**self.HOST_EVENT_NO_DEVICES)
    device_manager.HandleDeviceSnapshotWithNDB(old_host_event)
    new_host_event = host_event.HostEvent(**self.HOST_EVENT_NO_DEVICES_UPDATE)
    device_manager.HandleDeviceSnapshotWithNDB(new_host_event)

    # Hostname stays the same.
    # Cluster, TF version, and timestamp should have been updated.
    host = device_manager.GetHost(self.HOST_EVENT_NO_DEVICES["hostname"])
    self.assertIsNotNone(host)
    self.assertEqual("tradefed", host.test_runner)
    self.assertEqual(self.HOST_EVENT_NO_DEVICES_UPDATE["tf_version"],
                     host.test_runner_version)
    self.assertEqual(self.HOST_EVENT_NO_DEVICES_UPDATE["cluster"],
                     host.physical_cluster)
    self.assertEqual(
        datetime.datetime.utcfromtimestamp(
            self.HOST_EVENT_NO_DEVICES_UPDATE["time"]),
        host.timestamp)

  def testHandleDeviceSnapshot_withTestRunner(self):
    """Tests that HandleDeviceSnapshot handle event with test runner."""
    event = host_event.HostEvent(**self.HOST_EVENT_WITH_TEST_RUNNER)
    device_manager.HandleDeviceSnapshotWithNDB(event)

    host = device_manager.GetHost(self.HOST_EVENT_WITH_TEST_RUNNER["hostname"])
    self.assertIsNotNone(host)
    self.assertEqual("new_runner", host.test_runner)
    self.assertEqual("v2", host.test_runner_version)
    device = device_manager.GetDevice(device_serial="new_runner_device")
    self.assertEqual("new_runner", device.test_harness)

  @mock.patch.object(device_manager, "_DoUpdateGoneDevicesInNDB")
  def testUpdateGoneDevicesInNDB_alreadyGone(self, do_update):
    """Tests that devices are updated."""
    hostname = "somehost.mtv"
    cluster = "somecluster"
    serials = ["serial-001", "serial-002", "serial-003"]
    host = datastore_entities.HostInfo(
        id=hostname, hostname=hostname, physical_cluster=cluster)
    host.put()
    for s in serials:
      device = datastore_entities.DeviceInfo(
          id=s, parent=host.key,
          device_serial=s,
          hostname=hostname,
          state=common.DeviceState.GONE)
      device.put()
    timestamp = datetime.datetime.utcnow()
    device_manager._UpdateGoneDevicesInNDB(hostname, {}, timestamp)
    self.assertFalse(do_update.called)

  def testHandleDeviceSnapshot_olderTimestamp(self):
    """Tests that HandleDeviceSnapshot() ignores events if they are older."""
    new_host_event = host_event.HostEvent(**self.HOST_EVENT_NO_DEVICES_UPDATE)
    device_manager.HandleDeviceSnapshotWithNDB(new_host_event)
    host = device_manager.GetHost(self.HOST_EVENT_NO_DEVICES_UPDATE["hostname"])
    self.assertIsNotNone(host)
    self.assertEqual("tradefed", host.test_runner)
    self.assertEqual(self.HOST_EVENT_NO_DEVICES_UPDATE["tf_version"],
                     host.test_runner_version)
    self.assertEqual(self.HOST_EVENT_NO_DEVICES_UPDATE["cluster"],
                     host.physical_cluster)
    self.assertEqual(
        datetime.datetime.utcfromtimestamp(
            self.HOST_EVENT_NO_DEVICES_UPDATE["time"]),
        host.timestamp)
    # This event should be ignored
    old_host_event = host_event.HostEvent(**self.HOST_EVENT_NO_DEVICES)
    self.assertLess(old_host_event.timestamp, new_host_event.timestamp)
    device_manager.HandleDeviceSnapshotWithNDB(old_host_event)
    host = device_manager.GetHost(self.HOST_EVENT_NO_DEVICES_UPDATE["hostname"])
    self.assertIsNotNone(host)
    self.assertEqual("tradefed", host.test_runner)
    self.assertEqual(self.HOST_EVENT_NO_DEVICES_UPDATE["tf_version"],
                     host.test_runner_version)
    self.assertEqual(self.HOST_EVENT_NO_DEVICES_UPDATE["cluster"],
                     host.physical_cluster)
    self.assertEqual(
        datetime.datetime.utcfromtimestamp(
            self.HOST_EVENT_NO_DEVICES_UPDATE["time"]),
        host.timestamp)

  def testTransformDeviceSerial(self):
    """Tests TransformDeviceSerial for regular device serials."""
    hostname = "test.mtv.corp"
    serial = "some-generic-serial"
    result = device_manager._TransformDeviceSerial(hostname, serial)
    self.assertEqual(serial, result)

  def testTransformDeviceSerial_emulator(self):
    """Tests TransformDeviceSerial for emulator device serials."""
    hostname = "test.mtv.corp"
    serial = "emulator-5554"
    expected = "%s:%s" % (hostname, serial)
    result = device_manager._TransformDeviceSerial(hostname, serial)
    self.assertEqual(expected, result)

  def testTransformDeviceSerial_tcpDevice(self):
    """Tests TransformDeviceSerial for emulator device serials."""
    hostname = "test.mtv.corp"
    serial = "tcp-device-5554"
    expected = "%s:%s" % (hostname, serial)
    result = device_manager._TransformDeviceSerial(hostname, serial)
    self.assertEqual(expected, result)

  def testTransformDeviceSerial_nullDevice(self):
    """Tests TransformDeviceSerial for null device serials."""
    hostname = "test.mtv.corp"
    serial = "null-device-0"
    expected = "%s:%s" % (hostname, serial)
    result = device_manager._TransformDeviceSerial(hostname, serial)
    self.assertEqual(expected, result)

  def testTransformDeviceSerial_gceDevice(self):
    """Tests TransformDeviceSerial for gce device serials."""
    hostname = "test.mtv.corp"
    serial = "gce-device-0"
    expected = "%s:%s" % (hostname, serial)
    result = device_manager._TransformDeviceSerial(hostname, serial)
    self.assertEqual(expected, result)

  def testTransformDeviceSerial_localVirtualDevice(self):
    """Tests TransformDeviceSerial for local virtual device serials."""
    hostname = "test.mtv.corp"
    serial = "local-virtual-device-0"
    expected = "%s:%s" % (hostname, serial)
    result = device_manager._TransformDeviceSerial(hostname, serial)
    self.assertEqual(expected, result)

  def testTransformDeviceSerial_emptySerial(self):
    """Tests TransformDeviceSerial for empty device serials."""
    hostname = "test.mtv.corp"
    serial = ""
    result = device_manager._TransformDeviceSerial(hostname, serial)
    self.assertEqual("", result)

  def testUpdateDevices(self):
    """Test _updateDevices. 1 device (w/ empty serial) should be ignored."""
    hostname = self.HOST_EVENT["hostname"]
    device_manager._UpdateDevicesInNDB(host_event.HostEvent(**self.HOST_EVENT))

    devices = datastore_entities.DeviceInfo.query(
        ancestor=ndb.Key(datastore_entities.HostInfo, hostname)).fetch()
    self.assertEqual(2, len(devices))
    for device in devices:
      self.assertFalse(hasattr(device, "history"))
      _, host, _, serial = device.key.flat()
      histories = device_manager.GetDeviceHistory(host, serial)
      self.assertEqual(1, len(histories))

  def testGetDevice(self):
    """Tests that GetDevice returns a device in the ndb."""
    host = datastore_entities.HostInfo(
        id="atl-1001.mtv", hostname="atl-1001.mtv", physical_cluster="free")
    host.put()
    device = datastore_entities.DeviceInfo(
        id="device_serial", parent=host.key, device_serial="device_serial",
        run_target="shamu")
    device.put()
    device_queried = device_manager.GetDevice("atl-1001.mtv", "device_serial")
    self.assertEqual(device.device_serial, device_queried.device_serial)
    self.assertEqual(device.run_target, device_queried.run_target)

  def testGetDevice_withSerialOnly(self):
    """Tests that GetDevice returns a device in the ndb."""
    host = datastore_entities.HostInfo(
        id="atl-1001.mtv", hostname="atl-1001.mtv", physical_cluster="free")
    host.put()
    device = datastore_entities.DeviceInfo(
        id="device_serial", parent=host.key, device_serial="device_serial",
        run_target="shamu")
    device.put()
    device_queried = device_manager.GetDevice(device_serial="device_serial")
    self.assertEqual(device.device_serial, device_queried.device_serial)
    self.assertEqual(device.run_target, device_queried.run_target)

  def testGetDevice_nonExistent(self):
    """Tests that GetDevice returns None for non existent devices."""
    device_queried = device_manager.GetDevice(
        "hostname", "device_serial")
    self.assertIsNone(device_queried)

  def testGetDevice_multiple(self):
    # This happens when a device move from one host to another.
    host = datastore_entities.HostInfo(
        id="atl-1001.mtv", hostname="atl-1001.mtv", physical_cluster="free")
    host.put()
    device = datastore_entities.DeviceInfo(
        id="device_serial", parent=host.key, device_serial="device_serial",
        run_target="shamu", timestamp=datetime.datetime(2018, 4, 4))
    device.put()
    host1 = datastore_entities.HostInfo(
        id="atl-1002.mtv", hostname="atl-1002.mtv", physical_cluster="free")
    host1.put()
    device1 = datastore_entities.DeviceInfo(
        id="device_serial", parent=host1.key, device_serial="device_serial",
        run_target="shamu", timestamp=datetime.datetime(2018, 4, 5))
    device1.put()
    device_queried = device_manager.GetDevice(device_serial="device_serial")
    self.assertEqual(device1.device_serial, device_queried.device_serial)
    self.assertEqual(device1.run_target, device_queried.run_target)

  def testUpdateDeviceState_newDevice(self):
    """Test updating a state for a new device."""
    device = datastore_test_util.CreateDevice(
        "acluster", "ahost", "serial",
        timestamp=datetime.datetime(2015, 5, 6),
        state=common.DeviceState.AVAILABLE)

    timestamp = datetime.datetime(2015, 5, 7)
    device_state_history, device_history = device_manager._UpdateDeviceState(
        device, state=common.DeviceState.ALLOCATED, timestamp=timestamp)
    self.assertIsNotNone(device_state_history)
    self.assertEqual(timestamp, device_state_history.timestamp)
    self.assertEqual(common.DeviceState.ALLOCATED, device_state_history.state)
    self.assertIsNotNone(device_history)
    self.assertEqual(timestamp, device_history.timestamp)
    self.assertEqual(common.DeviceState.ALLOCATED, device_history.state)

  def testUpdateDeviceState_nonPhysicalDevice(self):
    """Test updating a state for a new device."""
    device = datastore_test_util.CreateDevice(
        "acluster", "ahost", "tcp-device-0",
        timestamp=datetime.datetime(2015, 5, 6),
        state=common.DeviceState.AVAILABLE)
    device_state_history, device_history = device_manager._UpdateDeviceState(
        device, common.DeviceState.ALLOCATED,
        datetime.datetime(2015, 5, 7))
    self.assertIsNone(device_state_history)
    self.assertIsNone(device_history)

  def testUpdateDeviceState_sameState(self):
    """Test updating the same state for a existing device."""
    device = datastore_test_util.CreateDevice(
        "acluster", "ahost", "serial",
        timestamp=datetime.datetime(2015, 5, 6),
        state=common.DeviceState.AVAILABLE)

    device_state_history, device_history = device_manager._UpdateDeviceState(
        device, state=common.DeviceState.AVAILABLE,
        timestamp=datetime.datetime(2015, 5, 7))
    self.assertIsNone(device_state_history)
    self.assertIsNone(device_history)

  def testIsKnownProperty(self):
    """Test _IsKnownProperty()."""
    self.assertTrue(device_manager._IsKnownProperty("something"))
    self.assertFalse(device_manager._IsKnownProperty(None))
    self.assertFalse(device_manager._IsKnownProperty(
        device_manager.UNKNOWN_PROPERTY))

  def testGetRunTargetsFromNDB(self):
    """Tests getting exisint run targets all devices."""
    datastore_test_util.CreateDevice(
        "free", "host1", "s1", run_target="shamu")
    datastore_test_util.CreateDevice(
        "free", "host1", "s2", run_target="hammerhead")
    run_targets = device_manager.GetRunTargetsFromNDB()
    self.assertItemsEqual(["shamu", "hammerhead"], run_targets)

  def testGetRunTargetsFromNDB_fromCluster(self):
    """Tests getting exising run targets from a given cluster."""
    datastore_test_util.CreateDevice(
        "mtv-43", "host1", "s1", run_target="shamu",
        next_cluster_ids=["free"])
    datastore_test_util.CreateDevice(
        "mtv-43", "host2", "s2", run_target="hammerhead",
        next_cluster_ids=["presubmit"])
    run_targets = device_manager.GetRunTargetsFromNDB(cluster="free")
    self.assertItemsEqual(["shamu"], run_targets)

  def testGetRunTargetsFromNDB_invalidCluster(self):
    """Tests getting exising run targets from from an invalid cluster."""
    datastore_test_util.CreateDevice(
        "mtv-43", "host1", "s1", run_target="shamu",
        next_cluster_ids=["free"])
    datastore_test_util.CreateDevice(
        "mtv-43", "host2", "s2", run_target="hammerhead",
        next_cluster_ids=["presubmit"])
    run_targets = device_manager.GetRunTargetsFromNDB(
        cluster="invalid_cluster")
    self.assertEqual(0, len(list(run_targets)))

  def testCalculateDeviceUtilization_invalidNumberOfDays(self):
    """Tests calculating utilization with invalid number of days."""
    with self.assertRaises(ValueError):
      device_manager.CalculateDeviceUtilization("serial", 0)

  def testCalculateDeviceUtilization_noHistory(self):
    """Tests calculating utilization when a device has no history."""
    utilization = device_manager.CalculateDeviceUtilization("serial")
    self.assertEqual(0, utilization)

  @mock.patch.object(device_manager, "_Now")
  def testCalculateDeviceUtilization_singleAllocatedRecord(self, mock_now):
    """Tests calculating utilization with a single record on allocated."""
    mock_now.return_value = datetime.datetime(2015, 11, 18)
    serial = "device-serial"
    state_0 = "Available"
    self._BuildDeviceStateHistory(timestamp=datetime.datetime(2015, 11, 15),
                                  serial=serial,
                                  state=state_0)
    # Allocated for half day
    state_1 = "Allocated"
    self._BuildDeviceStateHistory(timestamp=datetime.datetime(2015, 11, 17),
                                  serial=serial,
                                  state=state_1)
    # Device is gone
    state_2 = "Gone"
    self._BuildDeviceStateHistory(timestamp=datetime.datetime(2015, 11, 17, 12),
                                  serial=serial,
                                  state=state_2)
    # Utilization was 0.5 days out of 1 day.
    utilization = device_manager.CalculateDeviceUtilization(serial, 1)
    self.assertEqual(0.5, utilization)
    # Utilization was 0.5 days out of 3 days.
    utilization = device_manager.CalculateDeviceUtilization(serial, 3)
    self.assertEqual(0.5/3, utilization)
    # Utilization was 0.5 days out of 7 days (default).
    utilization = device_manager.CalculateDeviceUtilization(serial)
    self.assertEqual(0.5/7, utilization)

  @mock.patch.object(device_manager, "_Now")
  def testCalculateDeviceUtilization_multipleAllocatedRecord(self, mock_now):
    """Tests calculating utilization with multiple records on allocated."""
    mock_now.return_value = datetime.datetime(2015, 11, 20)
    serial = "device-serial"
    state_0 = "Available"
    self._BuildDeviceStateHistory(timestamp=datetime.datetime(2015, 11, 10),
                                  serial=serial,
                                  state=state_0)
    # Allocated for 1 day
    state_1 = "Allocated"
    self._BuildDeviceStateHistory(timestamp=datetime.datetime(2015, 11, 12),
                                  serial=serial,
                                  state=state_1)
    # Gone for 1 day
    state_2 = "Gone"
    self._BuildDeviceStateHistory(timestamp=datetime.datetime(2015, 11, 13),
                                  serial=serial,
                                  state=state_2)
    # Allocated for 2 days
    state_3 = "Allocated"
    self._BuildDeviceStateHistory(timestamp=datetime.datetime(2015, 11, 14),
                                  serial=serial,
                                  state=state_3)
    # Available for 2 days
    state_4 = "Available"
    self._BuildDeviceStateHistory(timestamp=datetime.datetime(2015, 11, 16),
                                  serial=serial,
                                  state=state_4)
    # Allocated afterwards until now
    state_5 = "Allocated"
    self._BuildDeviceStateHistory(timestamp=datetime.datetime(2015, 11, 18),
                                  serial=serial,
                                  state=state_5)
    # Utilization was 0 days out of 1 day (no state changes in the past day).
    utilization = device_manager.CalculateDeviceUtilization(serial, 1)
    self.assertEqual(0, utilization)
    # Utilization was 2 days out of 3 days.
    utilization = device_manager.CalculateDeviceUtilization(serial, 3)
    self.assertEqual(float(2)/3, utilization)
    # Utilization was 4 days out of 7 days (default).
    utilization = device_manager.CalculateDeviceUtilization(serial)
    self.assertEqual(float(4)/7, utilization)
    # Utilization was 5 days out of 10 days.
    utilization = device_manager.CalculateDeviceUtilization(serial, 10)
    self.assertEqual(float(5)/10, utilization)

  def testUpdateGoneDevicesInNDB(self):
    """Tests that devices are updated."""
    hostname = "somehost.mtv"
    cluster = "somecluster"
    serials = ["serial-001", "serial-002", "serial-003"]
    host = datastore_entities.HostInfo(
        id=hostname, hostname=hostname, physical_cluster=cluster)
    host.put()
    for s in serials:
      device = datastore_entities.DeviceInfo(
          id=s, parent=host.key,
          device_serial=s,
          hostname=hostname,
          state="Available")
      device.put()
    timestamp = datetime.datetime.utcnow()
    device_manager._UpdateGoneDevicesInNDB(hostname, {}, timestamp)
    devices = datastore_entities.DeviceInfo.query(ancestor=host.key).fetch()
    for d in devices:
      self.assertEqual("Gone", d.state)

  def testGetDeviceType(self):
    """Tests for _GetDeviceType."""
    self.assertEqual(
        api_messages.DeviceTypeMessage.EMULATOR,
        device_manager._GetDeviceType("emulator-5554"))
    self.assertEqual(
        api_messages.DeviceTypeMessage.TCP,
        device_manager._GetDeviceType("tcp-device-0"))
    self.assertEqual(
        api_messages.DeviceTypeMessage.NULL,
        device_manager._GetDeviceType("null-device-1"))
    self.assertEqual(
        api_messages.DeviceTypeMessage.PHYSICAL,
        device_manager._GetDeviceType("abc123"))
    self.assertEqual(
        api_messages.DeviceTypeMessage.GCE,
        device_manager._GetDeviceType("gce-device-11"))
    self.assertEqual(
        api_messages.DeviceTypeMessage.REMOTE,
        device_manager._GetDeviceType("remote-device-0"))
    self.assertEqual(
        api_messages.DeviceTypeMessage.LOCAL_VIRTUAL,
        device_manager._GetDeviceType("local-virtual-device-0"))

  def testUpdateHostWithDeviceSnapshotEvent_newHost(self):
    # Test  _UpdateHostWithDeviceSnapshotEvent for a new host
    event = host_event.HostEvent(**self.HOST_EVENT)
    device_manager._UpdateHostWithDeviceSnapshotEvent(event)
    ndb_host = device_manager.GetHost(self.HOST_EVENT["hostname"])
    self.assertFalse(ndb_host.hidden)
    self.assertEqual(["test", "cluster1", "cluster2"],
                     ndb_host.clusters)

  def testUpdateHostWithDeviceSnapshotEvent_existingHost(self):
    # Test _UpdateHostWithDeviceSnapshotEvent for an existing host
    event = host_event.HostEvent(**self.HOST_EVENT)
    datastore_entities.HostInfo(
        id=event.hostname,
        hostname=event.hostname,
        physical_cluster="some_other_cluster").put()
    device_manager._UpdateHostWithDeviceSnapshotEvent(event)
    ndb_host = device_manager.GetHost(self.HOST_EVENT["hostname"])
    self.assertFalse(ndb_host.hidden)
    self.assertEqual(event.cluster_id, ndb_host.physical_cluster)

  def testUpdateHostWithDeviceSnapshotEvent_removedHost(self):
    # Test _UpdateHostWithDeviceSnapshotEvent when the host is hidden (removed)
    event = host_event.HostEvent(**self.HOST_EVENT)
    datastore_entities.HostInfo(
        id=event.hostname,
        hostname=event.hostname,
        physical_cluster="some_other_cluster",
        hidden=True).put()
    device_manager._UpdateHostWithDeviceSnapshotEvent(event)
    ndb_host = device_manager.GetHost(self.HOST_EVENT["hostname"])
    self.assertEqual(event.cluster_id, ndb_host.physical_cluster)
    self.assertFalse(ndb_host.hidden)

  def testUpdateHostWithDeviceSnapshotEvent_extraInfo(self):
    # Test _UpdateHostWithHostChangedEvent for changing extra_info (b/35346971)
    hostname = "test-1.mtv.corp.example.com"
    data_1 = {
        "prodcertstatus": "LOAS1",
        "krbstatus": "KRB1"
    }
    host_event_1 = {
        "time": 1,
        "cluster": "test",
        "hostname": hostname,
        "tf_version": "0001",
        "event_type": "DEVICE_SNAPSHOT",
        "device_infos": [],
        "data": data_1
    }
    data_2 = {
        "prodcertstatus": "LOAS2",
        "krbstatus": "KRB2"
    }
    host_event_2 = {
        "time": 2,
        "cluster": "test",
        "hostname": hostname,
        "tf_version": "0001",
        "event_type": "DEVICE_SNAPSHOT",
        "device_infos": [],
        "data": data_2
    }
    event_1 = host_event.HostEvent(**host_event_1)
    device_manager._UpdateHostWithDeviceSnapshotEvent(event_1)
    ndb_host = device_manager.GetHost(hostname)
    self.assertEqual(data_1, ndb_host.extra_info)
    event_2 = host_event.HostEvent(**host_event_2)
    device_manager._UpdateHostWithDeviceSnapshotEvent(event_2)
    ndb_host = device_manager.GetHost(hostname)
    self.assertEqual(data_2, ndb_host.extra_info)

  def testUpdateHostWithDeviceSnapshotEvent_oldStateGone(self):
    # Test update host with RUNNING if the old state is GONE.
    hostname = "test-1.mtv.corp.example.com"
    host = datastore_entities.HostInfo(id=hostname)
    host.hostname = hostname
    host.physical_cluster = "test"
    host.timestamp = datetime.datetime.utcfromtimestamp(1)
    host.host_state = api_messages.HostState.GONE
    host.tf_start_time = datetime.datetime.utcfromtimestamp(12345)
    host.put()
    host_event_1 = {
        "time": 2,
        "cluster": "test",
        "event_type": "NOT_HOST_STATE_CHANGED",
        "hostname": hostname,
        "state": "RUNNING",
        "tf_start_time_seconds": 12345,
    }
    event_1 = host_event.HostEvent(**host_event_1)
    device_manager._UpdateHostWithDeviceSnapshotEvent(event_1)
    ndb_host = device_manager.GetHost(hostname)
    self.assertEqual(api_messages.HostState.RUNNING, ndb_host.host_state)
    host_history_list = device_manager.GetHostStateHistory(hostname)
    self.assertEqual(host_history_list[0].state, api_messages.HostState.RUNNING)

  def testUpdateHostWithHostChangedEvent_newState(self):
    # Test update host with a new state
    hostname = "test-1.mtv.corp.example.com"
    host_event_1 = {
        "time": 1,
        "cluster": "test",
        "event_type": "HOST_STATE_CHANGED",
        "hostname": hostname,
        "state": "RUNNING",
    }
    host_event_2 = {
        "time": 2,
        "cluster": "test",
        "event_type": "HOST_STATE_CHANGED",
        "hostname": hostname,
        "state": "RUNNING",
    }
    host_event_3 = {
        "time": 3,
        "cluster": "test",
        "event_type": "HOST_STATE_CHANGED",
        "hostname": hostname,
        "state": "QUITTING",
    }

    event_1 = host_event.HostEvent(**host_event_1)
    device_manager._UpdateHostWithHostChangedEvent(event_1)
    ndb_host = device_manager.GetHost(hostname)
    self.assertEqual(api_messages.HostState.RUNNING, ndb_host.host_state)
    event_2 = host_event.HostEvent(**host_event_2)
    device_manager._UpdateHostWithHostChangedEvent(event_2)
    ndb_host = device_manager.GetHost(hostname)
    self.assertEqual(api_messages.HostState.RUNNING, ndb_host.host_state)
    event_3 = host_event.HostEvent(**host_event_3)
    device_manager._UpdateHostWithHostChangedEvent(event_3)
    ndb_host = device_manager.GetHost(hostname)
    self.assertEqual(api_messages.HostState.QUITTING, ndb_host.host_state)
    host_state_histories = device_manager.GetHostStateHistory(hostname)
    self.assertEqual(2, len(host_state_histories))
    self.assertEqual(hostname, host_state_histories[0].hostname)
    self.assertEqual(
        api_messages.HostState.QUITTING, host_state_histories[0].state)
    self.assertEqual(event_3.timestamp, host_state_histories[0].timestamp)
    self.assertEqual(
        api_messages.HostState.RUNNING, host_state_histories[1].state)
    self.assertEqual(event_1.timestamp, host_state_histories[1].timestamp)

    host_histories = (
        datastore_entities.HostInfoHistory
        .query(ancestor=ndb.Key(datastore_entities.HostInfo, hostname))
        .order(-datastore_entities.HostInfoHistory.timestamp)
        .fetch())

    self.assertEqual(hostname, host_histories[0].hostname)
    self.assertEqual(
        api_messages.HostState.QUITTING, host_histories[0].host_state)
    self.assertEqual(event_3.timestamp, host_histories[0].timestamp)
    self.assertEqual(
        api_messages.HostState.RUNNING, host_histories[1].host_state)
    self.assertEqual(event_1.timestamp, host_histories[1].timestamp)

  def _BuildDeviceStateHistory(self, timestamp, serial, state):
    """Helper to build and persist device state history records."""
    device_snapshot = datastore_entities.DeviceStateHistory(
        timestamp=timestamp,
        device_serial=serial,
        state=state)
    device_snapshot.put()

  def testCountDeviceForHost(self):
    datastore_test_util.CreateHost("free", "host1")
    datastore_test_util.CreateDevice(
        "free", "host1", "s1",
        run_target="run_target1")
    datastore_test_util.CreateDevice(
        "free", "host1", "s2",
        run_target="run_target1")
    datastore_test_util.CreateDevice(
        "free", "host1", "s3",
        run_target="run_target2",
        state=common.DeviceState.ALLOCATED)
    datastore_test_util.CreateDevice(
        "free", "host1", "s4",
        run_target="run_target2",
        state=common.DeviceState.GONE)
    datastore_test_util.CreateDevice(
        "free", "host1", "s5",
        run_target="run_target1",
        state=common.DeviceState.GONE, hidden=True)
    device_manager._CountDeviceForHost("host1")
    host = device_manager.GetHost("host1")
    self.assertEqual(4, host.total_devices)
    self.assertEqual(2, host.available_devices)
    self.assertEqual(1, host.allocated_devices)
    self.assertEqual(1, host.offline_devices)
    self.assertEqual(2, len(host.device_count_summaries))
    for device_count_summary in host.device_count_summaries:
      if device_count_summary.run_target == "run_target1":
        self.assertEqual(2, device_count_summary.total)
        self.assertEqual(2, device_count_summary.available)
        self.assertEqual(0, device_count_summary.allocated)
        self.assertEqual(0, device_count_summary.offline)
      elif device_count_summary.run_target == "run_target2":
        self.assertEqual(2, device_count_summary.total)
        self.assertEqual(0, device_count_summary.available)
        self.assertEqual(1, device_count_summary.allocated)
        self.assertEqual(1, device_count_summary.offline)
      else:
        self.assertFalse(True)

  def testCountDeviceForHost_hostWithoutDevice(self):
    host = datastore_test_util.CreateHost(
        "free", "host2",
        device_count_summaries=[
            datastore_test_util.CreateDeviceCountSummary(
                run_target="run_target1",
                offline=1,
                available=5,
                allocated=4)])
    device_manager._CountDeviceForHost("host2")
    ndb.get_context().clear_cache()
    host = device_manager.GetHost("host2")
    self.assertEqual(0, len(host.device_count_summaries))
    self.assertEqual(0, host.total_devices)
    self.assertEqual(0, host.available_devices)
    self.assertEqual(0, host.allocated_devices)
    self.assertEqual(0, host.offline_devices)

  def _AssertHostSyncTask(self, hostname):
    tasks = self.taskqueue_stub.get_filtered_tasks()
    self.assertEqual(1, len(tasks))
    host_sync = datastore_entities.HostSync.get_by_id(hostname)
    self.assertEqual(host_sync.taskname, tasks[0].name)
    expected_payload = {
        "hostname": hostname
    }
    payload = json.loads(tasks[0].payload)
    self.assertEqual(expected_payload, payload)
    return tasks[0].name

  def testStartHostSync(self):
    device_manager.StartHostSync("host1")
    self._AssertHostSyncTask("host1")

  def testStartHostSync_alreadyExist(self):
    device_manager.StartHostSync("host1")
    self._AssertHostSyncTask("host1")
    self.assertIsNone(device_manager.StartHostSync("host1"))

  def testStartHostSync_differentTaskname(self):
    device_manager.StartHostSync("host1")
    self._AssertHostSyncTask("host1")
    self.assertIsNone(
        device_manager.StartHostSync("host1", "another_taskname"))

  @mock.patch.object(device_manager, "_Now")
  def testStartHostSync_staleTask(self, mock_now):
    now = datetime.datetime(2019, 11, 14, 10, 10)
    before = now - datetime.timedelta(minutes=40)
    mock_now.return_value = before
    old_taskname = device_manager.StartHostSync("host1")
    self._AssertHostSyncTask("host1")
    mock_now.return_value = now
    new_taskname = device_manager.StartHostSync("host1", "another_taskname")
    self.assertIsNotNone(new_taskname)
    self.assertNotEqual(old_taskname, new_taskname)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    # There will be 2 tasks, one for the stale one, the other is the new one.
    self.assertEqual(2, len(tasks))

  def testStartHostSync_sameTaskname(self):
    taskname = device_manager.StartHostSync("host1")
    self._AssertHostSyncTask("host1")
    new_taskname = device_manager.StartHostSync("host1", taskname)
    self.assertIsNotNone(new_taskname)
    self.assertNotEqual(taskname, new_taskname)

  def testStopHostSync(self):
    taskname = device_manager.StartHostSync("host1")
    self._AssertHostSyncTask("host1")
    device_manager.StopHostSync("host1", taskname)
    self.assertIsNone(datastore_entities.HostSync.get_by_id("host1"))

  @mock.patch.object(device_manager, "_Now")
  def testStopHostSync_staleTask(self, mock_now):
    now = datetime.datetime(2019, 11, 14, 10, 10)
    before = now - datetime.timedelta(minutes=40)
    mock_now.return_value = before
    device_manager.StartHostSync("host1")
    self._AssertHostSyncTask("host1")
    mock_now.return_value = now
    device_manager.StopHostSync("host1", "another_taskname")
    self.assertIsNone(datastore_entities.HostSync.get_by_id("host1"))

  def testStopHostSync_differentTaskname(self):
    device_manager.StartHostSync("host1")
    self._AssertHostSyncTask("host1")
    device_manager.StopHostSync("host1", "another_taskname")
    self.assertIsNotNone(datastore_entities.HostSync.get_by_id("host1"))

  @mock.patch.object(device_manager, "_Now")
  def testUpdateGoneHost(self, mock_now):
    now = datetime.datetime(2019, 11, 14, 10, 10)
    mock_now.return_value = now
    host = datastore_test_util.CreateHost("free", "host1")
    d1 = datastore_test_util.CreateDevice(
        "free", "host1", "s1", run_target="r1")
    d2 = datastore_test_util.CreateDevice(
        "free", "host1", "s2", run_target="r1")
    device_manager._CountDeviceForHost("host1")

    device_manager.UpdateGoneHost("host1")
    ndb.get_context().clear_cache()

    host = host.key.get()
    self.assertEqual(api_messages.HostState.GONE, host.host_state)
    d1 = d1.key.get()
    self.assertEqual(common.DeviceState.GONE, d1.state)
    d2 = d2.key.get()
    self.assertEqual(common.DeviceState.GONE, d2.state)
    host_histories = device_manager.GetHostStateHistory("host1")
    self.assertEqual(1, len(host_histories))
    self.assertEqual(now, host_histories[0].timestamp)
    self.assertEqual(api_messages.HostState.GONE, host_histories[0].state)
    device_histories = device_manager.GetDeviceHistory("host1", "s1")
    self.assertEqual(1, len(device_histories))
    self.assertEqual(now, device_histories[0].timestamp)
    self.assertEqual(common.DeviceState.GONE, device_histories[0].state)
    device_histories = device_manager.GetDeviceHistory("host1", "s2")
    self.assertEqual(1, len(device_histories))
    self.assertEqual(now, device_histories[0].timestamp)
    self.assertEqual(1, len(host.device_count_summaries))
    self.assertEqual(2, host.device_count_summaries[0].total)
    self.assertEqual("r1", host.device_count_summaries[0].run_target)
    self.assertEqual(2, host.device_count_summaries[0].offline)

  @mock.patch.object(device_manager, "_Now")
  def testUpdateGoneHost_alreadyGone(self, mock_now):
    now = datetime.datetime(2019, 11, 14, 10, 10)
    mock_now.return_value = now
    host = datastore_test_util.CreateHost(
        "free", "host1", host_state=api_messages.HostState.GONE)

    device_manager.UpdateGoneHost("host1")
    ndb.get_context().clear_cache()

    host = host.key.get()
    self.assertEqual(api_messages.HostState.GONE, host.host_state)
    host_histories = device_manager.GetHostStateHistory("host1")
    self.assertEqual(0, len(host_histories))

  @mock.patch.object(device_manager, "_Now")
  def testHideHost(self, mock_now):
    now = datetime.datetime(2019, 11, 14, 10, 10)
    mock_now.return_value = now
    host = datastore_test_util.CreateHost("free", "host1")
    d1 = datastore_test_util.CreateDevice("free", "host1", "s1")
    d2 = datastore_test_util.CreateDevice("free", "host1", "s2")

    device_manager.HideHost("host1")
    ndb.get_context().clear_cache()

    host = host.key.get()
    self.assertTrue(host.hidden)
    self.assertEqual(now, host.timestamp)
    d1 = d1.key.get()
    self.assertTrue(d1.hidden)
    self.assertEqual(now, d1.timestamp)
    d2 = d2.key.get()
    self.assertTrue(d2.hidden)
    self.assertEqual(now, d2.timestamp)

  @mock.patch.object(device_manager, "_Now")
  def testHideHost_alreadyHidden(self, mock_now):
    now = datetime.datetime(2019, 11, 14, 10, 10)
    before = now - datetime.timedelta(hours=10)
    mock_now.return_value = now
    host = datastore_test_util.CreateHost(
        "free", "host1", hidden=True, timestamp=before)

    device_manager.HideHost("host1")
    ndb.get_context().clear_cache()

    host = host.key.get()
    self.assertEqual(before, host.timestamp)

  @mock.patch.object(device_manager, "_Now")
  def testRestoreHost(self, mock_now):
    now = datetime.datetime(2019, 11, 14, 10, 10)
    mock_now.return_value = now
    host = datastore_test_util.CreateHost("free", "host1", hidden=True)

    device_manager.RestoreHost("host1")

    ndb.get_context().clear_cache()
    host = host.key.get()
    self.assertEqual(now, host.timestamp)
    self.assertFalse(host.hidden)

  @mock.patch.object(device_manager, "_Now")
  def testHideDevice(self, mock_now):
    now = datetime.datetime(2019, 11, 14, 10, 10)
    mock_now.return_value = now
    host = datastore_test_util.CreateHost("free", "host1")
    datastore_test_util.CreateDevice("free", "host1", "s1")
    d2 = datastore_test_util.CreateDevice("free", "host1", "s2")
    device_manager._CountDeviceForHost("host1")
    host = host.key.get()
    self.assertEqual(1, len(host.device_count_summaries))
    self.assertEqual(2, host.device_count_summaries[0].total)

    device_manager.HideDevice("s2", "host1")
    ndb.get_context().clear_cache()
    d2 = d2.key.get()
    self.assertEqual(now, d2.timestamp)
    self.assertTrue(d2.hidden)
    host = host.key.get()
    self.assertEqual(1, len(host.device_count_summaries))
    self.assertEqual(1, host.device_count_summaries[0].total)

  @mock.patch.object(device_manager, "_Now")
  def testRestoreDevice(self, mock_now):
    now = datetime.datetime(2019, 11, 14, 10, 10)
    mock_now.return_value = now
    host = datastore_test_util.CreateHost("free", "host1")
    datastore_test_util.CreateDevice("free", "host1", "s1")
    d2 = datastore_test_util.CreateDevice("free", "host1", "s2", hidden=True)
    device_manager._CountDeviceForHost("host1")
    host = host.key.get()
    self.assertEqual(1, len(host.device_count_summaries))
    self.assertEqual(1, host.device_count_summaries[0].total)

    device_manager.RestoreDevice("s2", "host1")
    ndb.get_context().clear_cache()
    d2 = d2.key.get()
    self.assertEqual(now, d2.timestamp)
    self.assertFalse(d2.hidden)
    host = host.key.get()
    self.assertEqual(1, len(host.device_count_summaries))
    self.assertEqual(2, host.device_count_summaries[0].total)

  def testAssignHosts(self):
    host1 = datastore_test_util.CreateHost("free", "host1")
    host2 = datastore_test_util.CreateHost("free", "host2")
    device_manager.AssignHosts(["host1", "host2"], "assignee")
    ndb.get_context().clear_cache()
    host1 = host1.key.get()
    self.assertEqual("assignee", host1.assignee)
    host2 = host2.key.get()
    self.assertEqual("assignee", host2.assignee)

  def testAssignHosts_invalidHost(self):
    host1 = datastore_test_util.CreateHost("free", "host1")
    host2 = datastore_test_util.CreateHost("free", "host2")
    device_manager.AssignHosts(
        ["host1", "host2", "invalid_host"], "assignee")
    ndb.get_context().clear_cache()
    host1 = host1.key.get()
    self.assertEqual("assignee", host1.assignee)
    host2 = host2.key.get()
    self.assertEqual("assignee", host2.assignee)

  def testGetDevicesOnHost(self):
    datastore_test_util.CreateHost("free", "host1")
    datastore_test_util.CreateDevice("free", "host1", "s1")
    datastore_test_util.CreateDevice("free", "host1", "s2")
    datastore_test_util.CreateDevice("free", "host1", "s3", hidden=True)

    devices = device_manager.GetDevicesOnHost("host1")

    self.assertEqual(2, len(devices))

  def testUpdateHostState(self):
    """Test UpdateHostState will update state and create state history."""
    hostname = "test-1.mtv.corp.example.com"
    timestamp1 = datetime.datetime.utcfromtimestamp(1)
    timestamp2 = datetime.datetime.utcfromtimestamp(2)
    host = datastore_test_util.CreateHost(
        "test", hostname,
        host_state=api_messages.HostState.GONE,
        timestamp=timestamp1)
    state_history, history = device_manager._UpdateHostState(
        host, api_messages.HostState.RUNNING,
        timestamp=timestamp2)
    self.assertIsNotNone(state_history)
    self.assertEqual(api_messages.HostState.RUNNING, host.host_state)
    self.assertEqual(timestamp2, host.timestamp)
    self.assertEqual(hostname, state_history.hostname)
    self.assertEqual(api_messages.HostState.RUNNING, state_history.state)
    self.assertEqual(api_messages.HostState.RUNNING, history.host_state)
    self.assertEqual(host.extra_info, history.extra_info)
    self.assertEqual(timestamp2, state_history.timestamp)

  def testUpdateHostState_sameState(self):
    """Test UpdateHostState will ignore same state."""
    hostname = "test-1.mtv.corp.example.com"
    timestamp1 = datetime.datetime.utcfromtimestamp(1)
    timestamp2 = datetime.datetime.utcfromtimestamp(2)
    host = datastore_test_util.CreateHost(
        "test", hostname,
        host_state=api_messages.HostState.RUNNING,
        timestamp=timestamp1)
    state_history, history = device_manager._UpdateHostState(
        host, api_messages.HostState.RUNNING,
        timestamp=timestamp2)
    self.assertIsNone(state_history)
    self.assertIsNone(history)
    self.assertEqual(api_messages.HostState.RUNNING, host.host_state)
    self.assertEqual(timestamp1, host.timestamp)

  def testCreateHostInfoHistory(self):
    """Test _CreateHostInfoHistory."""
    d1_count = datastore_entities.DeviceCountSummary(
        run_target="d1", total=10, offline=1, available=5, allocated=4)
    d2_count = datastore_entities.DeviceCountSummary(
        run_target="d2", total=5, offline=1, available=3, allocated=1)
    extra_info = {"key1": "value1", "key2": "value2"}
    host = datastore_test_util.CreateHost(
        "acluster", "ahost",
        extra_info=extra_info,
        device_count_summaries=[d1_count, d2_count])
    self.assertTrue(host.is_bad)
    host_history = device_manager._CreateHostInfoHistory(host)
    self.assertEqual(host.to_dict(), host_history.to_dict())

  @mock.patch.object(device_manager, "_Now")
  def testCreateAndSaveHostInfoHistoryFromHostNote(self, mock_now):
    now = datetime.datetime(2019, 11, 14, 10, 10)
    mock_now.return_value = now
    datastore_test_util.CreateHost("acluster", "ahost")
    key = device_manager.CreateAndSaveHostInfoHistoryFromHostNote(
        "ahost", "anoteid")
    host_history = key.get()
    self.assertEqual("ahost", host_history.hostname)
    self.assertEqual("anoteid", host_history.extra_info["host_note_id"])
    self.assertEqual(now, host_history.timestamp)

  @mock.patch.object(device_manager, "_Now")
  def testCreateAndSaveDeviceInfoHistoryFromDeviceNote(self, mock_now):
    now = datetime.datetime(2019, 11, 14, 10, 10)
    mock_now.return_value = now
    datastore_test_util.CreateDevice("acluster", "ahost", "aserial")
    key = device_manager.CreateAndSaveDeviceInfoHistoryFromDeviceNote(
        "aserial", "anoteid")
    device_history = key.get()
    self.assertEqual("aserial", device_history.device_serial)
    self.assertEqual("anoteid", device_history.extra_info["device_note_id"])
    self.assertEqual(now, device_history.timestamp)

  def testIsFastbootDevice(self):
    self.assertTrue(
        device_manager._IsFastbootDevice(
            common.DeviceState.AVAILABLE,
            api_messages.DeviceTypeMessage.PHYSICAL,
            "unknown", common.TestHarness.TRADEFED))

  def testIsFastbootDevice_MHDeviceNoProduct(self):
    self.assertFalse(
        device_manager._IsFastbootDevice(
            common.DeviceState.AVAILABLE,
            api_messages.DeviceTypeMessage.PHYSICAL,
            "unknown", common.TestHarness.MH))

  def testIsFastbootDevice_MHDeviceFastboot(self):
    self.assertTrue(
        device_manager._IsFastbootDevice(
            common.DeviceState.FASTBOOT,
            api_messages.DeviceTypeMessage.PHYSICAL,
            "unknown", common.TestHarness.MH))


if __name__ == "__main__":
  unittest.main()
