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

"""Configures for different environments."""

import os.path

from tradefed_cluster import common
from tradefed_cluster.plugins import metric_client
from tradefed_cluster.plugins import registry
from tradefed_cluster.util import env_util


class EnvConfig(env_util.EnvConfig):
  """Tradefed cluster environment configurations."""

  def __init__(self, base_env_config=env_util.CONFIG, **kwargs):
    env_util.EnvConfig.__init__(self, **base_env_config.__dict__)
    self.db_instance = '%s:main' % self.app_id
    self.app_region = 'us-central1'
    self.db_connect_str = None
    self.db_connect_args = None
    self.db_instance = None
    self.use_admin_api = True
    self.use_google_api = True
    self.event_queue_name = None
    self.object_event_filter = [
        common.ObjectEventType.REQUEST_STATE_CHANGED,
        common.ObjectEventType.COMMAND_ATTEMPT_STATE_CHANGED]

    self.device_info_snapshot_file_format = '/device_info_snapshots_dev/%s.gz'
    self.host_info_snapshot_file_format = '/host_info_snapshots_dev/%s.gz'
    self.should_send_report = False
    self.device_report_template_path = os.path.join(
        os.path.dirname(__file__),
        'email_templates',
        'device_report_template.html')
    self.plugin = registry.GetNoOpPlugin()
    self.metric_client = metric_client.MetricClient()
    self.extra_apis = []
    self.ignore_device_serials = []

    self.__dict__.update(kwargs)

CONFIG = EnvConfig()
