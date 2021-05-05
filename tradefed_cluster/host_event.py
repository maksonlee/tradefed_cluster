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

"""A module for managing host events."""

import datetime

HOST_EVENT_QUEUE_NDB = "host-event-queue-ndb"
# TODO: TF should upload test runner and version.
TF_TEST_HARNESS = "TRADEFED"
UNKNOWN = "UNKNOWN"


class HostEvent(object):
  """A class representing a single host event."""

  def __init__(self, **kwargs):
    self.timestamp = kwargs.get("time")
    if not isinstance(self.timestamp, datetime.datetime):
      self.timestamp = datetime.datetime.utcfromtimestamp(self.timestamp)
    # TODO: deprecate type field, use event_type instead.
    self.type = kwargs.get("event_type", kwargs.get("type"))
    self.hostname = kwargs.get("hostname")
    self.lab_name = kwargs.get("lab_name")
    # TODO: deprecate physical_cluster, use host_group.
    self.cluster_id = kwargs.get("cluster", UNKNOWN)
    self.host_group = kwargs.get("host_group", self.cluster_id)
    # TODO: TF should upload test runner and version.
    if "tf_version" in kwargs:
      self.test_harness = kwargs.get("test_runner", TF_TEST_HARNESS)
      self.test_harness_version = kwargs.get(
          "test_runner_version", kwargs.get("tf_version", UNKNOWN))
    elif "test_runner" in kwargs:
      # TODO: deprecated test runner and test runner version.
      self.test_harness = kwargs.get("test_runner", UNKNOWN)
      self.test_harness_version = kwargs.get("test_runner_version", UNKNOWN)
    else:
      self.test_harness = kwargs.get("test_harness", UNKNOWN)
      self.test_harness_version = kwargs.get("test_harness_version", UNKNOWN)
    self.test_harness = self.test_harness.upper()

    self.device_info = kwargs.get("device_infos", [])
    self.data = kwargs.get("data", {})
    # TODO: deprecate clusters, use pools.
    self.next_cluster_ids = kwargs.get("next_cluster_ids", [])
    self.pools = kwargs.get("pools", self.next_cluster_ids)
    # TODO: deprecate state field, use host_state instead.
    self.host_state = kwargs.get("host_state", kwargs.get("state"))
    self.host_update_state = kwargs.get("host_update_state", UNKNOWN)
    self.host_update_task_id = kwargs.get("host_update_task_id")
    self.host_update_state_display_message = kwargs.get(
        "host_update_state_display_message")
