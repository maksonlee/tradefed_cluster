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

"""Monitor commands until they reach a final state."""
import datetime
import json
import logging

import flask

from tradefed_cluster import command_manager
from tradefed_cluster import common
from tradefed_cluster import metric
from tradefed_cluster import request_manager
from tradefed_cluster.services import task_scheduler

COMMAND_SYNC_QUEUE = 'command-sync-queue'

MAX_COMMAND_EVENT_DELAY_MIN = 15  # 15 min
MAX_COMMAND_INACTIVE_TIME_MIN = 2 * 60  # 2 hours

APP = flask.Flask(__name__)


def Monitor(commands):
  """Monitor the given commands."""
  num_monitored = 0
  for command in commands:
    logging.info('Monitoring command: %s', command.key)
    AddToSyncQueue(command)
    num_monitored += 1
  return num_monitored


def AddToSyncQueue(command):
  """Add a command to the sync queue."""
  _, request_id, _, command_id = command.key.flat()
  payload = json.dumps({
      command_manager.COMMAND_ID_KEY: command_id,
      command_manager.REQUEST_ID_KEY: request_id,
  })
  now = common.Now()
  update_time = command.update_time or now
  timeout_seconds = GetCommandQueueTimeoutSeconds(command)
  if command.state != common.CommandState.QUEUED:
    # Schedule next sync based on when attempt may be cancelled.
    next_sync = now + datetime.timedelta(minutes=MAX_COMMAND_EVENT_DELAY_MIN)
  else:
    next_sync = min(
        # Time to next ensure command is leasable
        now + datetime.timedelta(minutes=MAX_COMMAND_EVENT_DELAY_MIN),
        # Time to cancel command
        update_time + datetime.timedelta(seconds=timeout_seconds))
  logging.info(
      'Scheduling request [%s] command [%s] to be synced at %s',
      request_id,
      command_id,
      next_sync)
  task_scheduler.AddTask(
      queue_name=COMMAND_SYNC_QUEUE,
      payload=payload,
      eta=next_sync)


def _HandleCommandNotExecutable(request_id, command_id):
  """Handle a command that is no longer executable."""
  command_manager.Cancel(
      request_id,
      command_id,
      cancel_reason=common.CancelReason.COMMAND_NOT_EXECUTABLE)
  request_manager.EvaluateState(request_id)


def _HandleInactiveCommand(command, request_id, command_id):
  """Handle an inactive (timed out) command."""
  command_manager.Cancel(
      request_id, command_id, cancel_reason=common.CancelReason.QUEUE_TIMEOUT)
  request_manager.EvaluateState(request_id)
  metric.RecordCommandTimingMetric(
      cluster_id=command.cluster,
      run_target=command.run_target,
      create_timestamp=command.create_time,
      command_action=metric.CommandAction.CANCEL,
      count=True)


def GetCommandQueueTimeoutSeconds(command):
  """The amount of time in seconds of a queued command has to be leased."""
  if not command.queue_timeout_seconds:
    return MAX_COMMAND_INACTIVE_TIME_MIN * 60
  return command.queue_timeout_seconds


def SyncCommand(request_id, command_id, add_to_sync_queue=True):
  """Sync the command.

  Cancel the command if inactive, otherwise re-add to the sync queue to check
  back again later.

  Args:
    request_id: Request ID for the command to sync
    command_id: Command ID for the command to sync
    add_to_sync_queue: Flag to determine if this command should be added to the
      sync queue
  """
  command = command_manager.GetCommand(request_id, command_id)

  if not command:
    logging.warning('No command found to sync. Request %s Command %s',
                    request_id, command_id)
    return

  if command.state in common.FINAL_COMMAND_STATES:
    # No need to sync commands in final states
    logging.info('Command reached final state %s. Request %s Command %s',
                 command.state, request_id, command_id)
    return

  if command.state != common.CommandState.QUEUED:
    # Only consider queued commands for inactivity checks.
    if add_to_sync_queue:
      AddToSyncQueue(command)
    return

  last_active_time = command_manager.GetLastCommandActiveTime(command)
  inactive_time = common.Now() - last_active_time
  if datetime.timedelta(minutes=MAX_COMMAND_EVENT_DELAY_MIN) < inactive_time:
    # Ensure command is leasable. If a worker leases a command task but does
    # not report back within MAX_COMMAND_EVENT_DELAY, we need to make it
    # leasable again.
    logging.debug('%r has no events for %r minutes (> %r); ensuring leasable.',
                  command.key, inactive_time, MAX_COMMAND_EVENT_DELAY_MIN)
    try:
      command_manager.EnsureLeasable(command)
    except command_manager.CommandTaskNotFoundError:
      logging.exception('command %s %s is not leasable; cancelling...',
                        request_id, command_id)
      _HandleCommandNotExecutable(request_id, command_id)
      return

  timeout_seconds = GetCommandQueueTimeoutSeconds(command)
  if inactive_time > datetime.timedelta(seconds=timeout_seconds):
    # Command timed out.
    logging.info(
        ('Canceling command %s: last active %s, inactive time %s is greater '
         'than %d seconds'),
        command.key, last_active_time, inactive_time, timeout_seconds)
    _HandleInactiveCommand(command, request_id, command_id)
    return

  # Add to the sync queue to check again later.
  if add_to_sync_queue:
    AddToSyncQueue(command)


@APP.route('/_ah/queue/%s' % COMMAND_SYNC_QUEUE, methods=['POST'])
def HandleCommandTask():
  payload = flask.request.get_data()
  command_info = json.loads(payload)
  logging.debug('CommandTaskHandler syncing %s', command_info)
  SyncCommand(command_info[command_manager.REQUEST_ID_KEY],
              command_info[command_manager.COMMAND_ID_KEY])
  return common.HTTP_OK
