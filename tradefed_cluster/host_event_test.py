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

"""Unit tests for host_event module."""

import datetime
import unittest

from tradefed_cluster import api_messages
from tradefed_cluster import host_event


class HostEventTest(unittest.TestCase):

  HOST_EVENT1 = {
      "time": 1431712965,
      "data": {},
      "cluster": "test",
      "hostname": "test.mtv.corp.example.com",
      "lab_name": "alab",
      "event_type": "DEVICE_SNAPSHOT",
      "device_infos": [
          {
              "product": "unknown",
              "state": "Available",
              "device_serial": "emulator-5554",
              "sdk_version": "unknown",
              "product_variant": "unknown",
              "build_id": "unknown",
              "run_target": "emulator"
          },
          {
              "product": "flounder",
              "state": "Available",
              "device_serial": "HT4A1JT01250",
              "sdk_version": "21",
              "product_variant": "flounder",
              "build_id": "LRX22C",
              "run_target": "flounder"
          }],
      "state": "RUNNING",
      "tf_start_time_seconds": 123456789,
      "tf_version": "v1"
  }
  HOST_EVENT2 = {
      "time": 1431712965,
      "hostname": "test.mtv.corp.example.com",
      "event_type": "HOST_STATE_CHANGED",
      "state": "KILLING",
      "tf_start_time_seconds": 123456789
  }
  HOST_EVENT3 = {
      "time": 1431712965,
      "data": {},
      "hostname": "test3.mtv.corp.example.com",
      "lab_name": "alab",
      "event_type": "DEVICE_SNAPSHOT",
      "state": "RUNNING",
      "tf_start_time_seconds": 123456789
  }
  MH_HOST_EVENT = {
      "time": 1431712965,
      "data": {},
      "cluster": "test2",
      "hostname": "test2.mtv.corp.example.com",
      "lab_name": "alab2",
      "event_type": "DEVICE_SNAPSHOT",
      "state": "RUNNING",
      "test_runner": "mobileharness",
      "test_runner_version": "v2",
  }

  def testHostEvent(self):
    event = host_event.HostEvent(**self.HOST_EVENT1)
    self.assertEqual("DEVICE_SNAPSHOT", event.type)
    self.assertEqual("test", event.cluster_id)
    self.assertEqual("test.mtv.corp.example.com", event.hostname)
    self.assertEqual("alab", event.lab_name)
    self.assertEqual(2, len(event.device_info))
    self.assertEqual(api_messages.HostState.RUNNING.name, event.host_state)
    self.assertEqual(datetime.datetime.utcfromtimestamp(123456789),
                     event.tf_start_time)
    self.assertEqual("v1", event.test_harness_version)
    self.assertEqual("TRADEFED", event.test_harness)

  def testHostEvent_newEvent(self):
    event = host_event.HostEvent(**self.MH_HOST_EVENT)
    self.assertEqual("DEVICE_SNAPSHOT", event.type)
    self.assertEqual("test2", event.cluster_id)
    self.assertEqual("test2.mtv.corp.example.com", event.hostname)
    self.assertEqual("alab2", event.lab_name)
    self.assertEqual(api_messages.HostState.RUNNING.name, event.host_state)
    self.assertEqual("v2", event.test_harness_version)
    self.assertEqual("MOBILEHARNESS", event.test_harness)

  def testHostEvent_noCluster(self):
    event = host_event.HostEvent(**self.HOST_EVENT3)
    self.assertEqual("DEVICE_SNAPSHOT", event.type)
    self.assertEqual("UNKNOWN", event.cluster_id)
    self.assertEqual("test3.mtv.corp.example.com", event.hostname)

  def testHostEvent_hostStateUpdate(self):
    event = host_event.HostEvent(**self.HOST_EVENT2)
    self.assertEqual("HOST_STATE_CHANGED", event.type)
    self.assertEqual("test.mtv.corp.example.com", event.hostname)
    self.assertEqual(api_messages.HostState.KILLING.name, event.host_state)


if __name__ == "__main__":
  unittest.main()
