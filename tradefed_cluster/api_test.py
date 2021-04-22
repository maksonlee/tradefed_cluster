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

"""Module for API dependencies base class. Only used for tests."""

import endpoints
import webtest

from tradefed_cluster import cluster_api
from tradefed_cluster import cluster_device_api
from tradefed_cluster import cluster_host_api
from tradefed_cluster import command_attempt_api
from tradefed_cluster import command_event_api
from tradefed_cluster import command_task_api
from tradefed_cluster import coordinator_api
from tradefed_cluster import device_blocklist_api
from tradefed_cluster import device_snapshot_api
from tradefed_cluster import filter_hint_api
from tradefed_cluster import test_harness_image_api
from tradefed_cluster import host_event_api
from tradefed_cluster import lab_management_api
from tradefed_cluster import predefined_message_api
from tradefed_cluster import report_api
from tradefed_cluster import request_api
from tradefed_cluster import run_target_api
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster import acl_check_api


class ApiTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self, extra_apis=None):
    super(ApiTest, self).setUp()
    app = endpoints.apiserving._ApiServer(
        [
            cluster_api.ClusterApi,
            cluster_device_api.ClusterDeviceApi,
            cluster_host_api.ClusterHostApi,
            command_attempt_api.CommandAttemptApi,
            command_event_api.CommandEventApi,
            command_task_api.CommandTaskApi,
            coordinator_api.CoordinatorApi,
            device_blocklist_api.DeviceBlocklistApi,
            device_snapshot_api.DeviceSnapshotApi,
            filter_hint_api.FilterHintApi,
            test_harness_image_api.TestHarnessImageApi,
            host_event_api.HostEventApi,
            lab_management_api.LabManagementApi,
            predefined_message_api.PredefinedMessageApi,
            report_api.ReportApi,
            request_api.RequestApi,
            run_target_api.RunTargetApi,
            acl_check_api.AclApi,
        ] + (extra_apis or []),
        restricted=False)
    self.testapp = webtest.TestApp(app)
