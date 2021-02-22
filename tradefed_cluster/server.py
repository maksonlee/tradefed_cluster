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

"""WSGI application dispatchers."""
import re

from tradefed_cluster import api
from tradefed_cluster import command_attempt_monitor
from tradefed_cluster import command_event_handler
from tradefed_cluster import command_monitor
from tradefed_cluster import commander
from tradefed_cluster import config_syncer_gcs_to_ndb
from tradefed_cluster import device_history_cleaner
from tradefed_cluster import device_info_reporter
from tradefed_cluster import device_monitor
from tradefed_cluster import harness_image_metadata_syncer
from tradefed_cluster import notification_handler
from tradefed_cluster import notifier
from tradefed_cluster import request_sync_monitor
from tradefed_cluster.services import task_scheduler


class RegexDispatcher(object):
  """Dispatches to WSGI applications using regular expressions."""

  def __init__(self, apps):
    """Initializes the dispatcher.

    Args:
      apps: list of regex and WSGI app tuples
    """
    self.apps = apps

  def __call__(self, environ, start_response):
    """Dispatches to the first WSGI app that matches the request path."""
    path = environ.get('PATH_INFO', '/')
    for regex, app in self.apps:
      if re.match(regex + r'\Z', path):
        return app(environ, start_response)
    # No matching app found
    start_response('404 Not Found', [])
    return []

APP = RegexDispatcher([
    (r'/_ah/api/.*', api.APP),
    (r'/_ah/queue/default', task_scheduler.APP),
])

TFC = RegexDispatcher([
    # Task handlers
    (r'/_ah/queue/(default|host-event-queue-ndb|notification-work-queue)',
     task_scheduler.APP),
    (r'/_ah/queue/command-attempt-sync-queue', command_attempt_monitor.APP),
    (r'/_ah/queue/command-event-queue', command_event_handler.APP),
    (r'/_ah/queue/command-sync-queue', command_monitor.APP),
    (r'/_ah/queue/host-sync-queue', device_monitor.APP),
    (r'/_ah/queue/request-state-notification-queue', notifier.APP),
    (r'/_ah/queue/request-sync-queue', request_sync_monitor.APP),
    (r'/_ah/queue/test-request-queue', commander.APP),
    # Cron handlers
    (r'/cron/monitor/devices/ndb', device_monitor.APP),
    (r'/cron/report/devices', device_info_reporter.APP),
    (r'/cron/cleanup/device_history', device_history_cleaner.APP),
    (r'/cron/notifier_update_request_status', notification_handler.APP),
    (r'/cron/syncer/sync_gcs_ndb', config_syncer_gcs_to_ndb.APP),
    (r'/cron/syncer/sync_harness_image_metadata',
     harness_image_metadata_syncer.APP)
])
