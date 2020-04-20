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

"""an API module to serve TF Cluster APIs."""

import endpoints

from tradefed_cluster import cluster_api
from tradefed_cluster import cluster_device_api
from tradefed_cluster import cluster_host_api
from tradefed_cluster import command_attempt_api
from tradefed_cluster import command_event_api
from tradefed_cluster import command_task_api
from tradefed_cluster import coordinator_api
from tradefed_cluster import device_snapshot_api
from tradefed_cluster import env_config
from tradefed_cluster import host_event_api
from tradefed_cluster import lab_management_api
from tradefed_cluster import report_api
from tradefed_cluster import request_api
from tradefed_cluster import run_target_api

API_HANDLERS = [
    cluster_api.ClusterApi,
    cluster_device_api.ClusterDeviceApi,
    cluster_host_api.ClusterHostApi,
    command_attempt_api.CommandAttemptApi,
    command_event_api.CommandEventApi,
    command_task_api.CommandTaskApi,
    coordinator_api.CoordinatorApi,
    device_snapshot_api.DeviceSnapshotApi,
    host_event_api.HostEventApi,
    lab_management_api.LabManagementApi,
    report_api.ReportApi,
    request_api.RequestApi,
    run_target_api.RunTargetApi,
] + env_config.CONFIG.extra_apis

APP = endpoints.api_server(API_HANDLERS)
