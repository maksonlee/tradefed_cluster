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

"""Monitor command attempts until they reach a final state."""

import datetime
import json
import logging

import flask

from tradefed_cluster import command_event
from tradefed_cluster import command_manager
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster.util import ndb_shim as ndb


APP = flask.Flask(__name__)


def Now():
  """Get current datetime in UTC."""
  return datetime.datetime.utcnow()


def Monitor(attempts):
  """Monitor the given command attempts."""
  num_monitored = 0
  for attempt in attempts:
    command_manager.AddToSyncCommandAttemptQueue(attempt)
    num_monitored += 1
  return num_monitored


def SyncCommandAttempt(request_id, command_id, attempt_id):
  """Sync the command attempt.

  Reset (error) the attempt if running but inactive, otherwise re-add to the
  sync queue to check back again later.

  Args:
    request_id: Request ID for the command attempt to sync
    command_id: Command ID for the command attempt to sync
    attempt_id: Attempt ID for the command attempt to sync
  """
  now = Now()
  attempt_key = ndb.Key(
      datastore_entities.Request,
      request_id,
      datastore_entities.Command,
      command_id,
      datastore_entities.CommandAttempt,
      attempt_id,
      namespace=common.NAMESPACE)
  attempt = attempt_key.get()

  if not attempt:
    logging.warning(
        'No attempt found to sync. Request %s Command %s Attempt %s',
        request_id, command_id, attempt_id)
    return

  if attempt.state in common.FINAL_COMMAND_STATES:
    # No need to sync attempt in final states
    logging.info(
        'Attempt reached final state %s. Request %s Command %s Attempt %s',
        attempt.state, request_id, command_id, attempt_id)
    return

  inactive_time = now - attempt.update_time
  if inactive_time > datetime.timedelta(
      minutes=command_manager.MAX_COMMAND_EVENT_DELAY_MIN):
    logging.info('Resetting command task %s which has been inactive for %s.',
                 attempt.task_id, inactive_time)
    event = command_event.CommandEvent(
        task_id=attempt.task_id,
        attempt_id=attempt_id,
        type=common.InvocationEventType.INVOCATION_COMPLETED,
        data={'error': common.TASK_RESET_ERROR_MESSAGE},
        time=now)
    command_manager.ProcessCommandEvent(event)
    return

  # Add to the sync queue to check again later.
  command_manager.AddToSyncCommandAttemptQueue(attempt)


@APP.route(
    '/_ah/queue/%s' % command_manager.COMMAND_ATTEMPT_SYNC_QUEUE,
    methods=['POST'])
def HandleCommandAttemptTask():
  """Handle command attempt monitor tasks."""
  payload = flask.request.get_data()
  attempt_info = json.loads(payload)
  logging.debug('CommandAttemptTaskHandler syncing %s', attempt_info)
  SyncCommandAttempt(attempt_info[command_manager.REQUEST_ID_KEY],
                     attempt_info[command_manager.COMMAND_ID_KEY],
                     attempt_info[command_manager.ATTEMPT_ID_KEY])
  return common.HTTP_OK
