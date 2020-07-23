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

"""Module to reconcile request notifications that have previously failed."""

import logging

import flask

from google.appengine.api import modules

from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import request_manager
from tradefed_cluster.services import task_scheduler

NOTIFICATION_TASK_QUEUE = 'notification-work-queue'

APP = flask.Flask(__name__)


@APP.route('/')
@APP.route('/<path:fake>')
def HandleNotification(fake=None):
  """Handle Notification."""
  del fake
  logging.info('NotificationHandler START')
  NotifyPendingRequestStateChanges()
  logging.info('NotificationHandler END')


def NotifyPendingRequestStateChanges():
  """Notify all states that have the notify_test_status flag set."""
  keys = (datastore_entities.Request.query(namespace=common.NAMESPACE)
                    .filter(datastore_entities.Request.notify_state_change == True)
          .fetch(keys_only=True))
  for k in keys:
    task_scheduler.AddCallableTask(
        NotifyRequestState,
        request_id=k.id(),
        _queue=NOTIFICATION_TASK_QUEUE,
        _target='%s.%s' % (
            modules.get_current_version_name(),
            modules.get_current_module_name()))


def NotifyRequestState(request_id, force=False):
  """Notify state change for a given request id.

  Args:
    request_id: the request id for a given request, str
    force: force notification regardless of notify_state_change bit.
  """
  request_manager.NotifyRequestState(request_id, force=force)
