# Lint as: python2, python3
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

"""A module for managing test commands."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import datetime
import json
import logging
import zlib

from protorpc import protojson
import six
from six.moves import range
from six.moves import zip

from tradefed_cluster import api_messages
from tradefed_cluster import command_task_store
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config
from tradefed_cluster import metric
from tradefed_cluster import request_manager
from tradefed_cluster.plugins import base as plugin_base
from tradefed_cluster.services import task_scheduler
from tradefed_cluster.util import ndb_shim as ndb

# Maximum number of tasks created for a single command with a run_count > 1

MAX_TASK_COUNT = 20


# Command is marked as CANCELED or ERROR if the number of attempts of that
# state exceeds floor(BASE + run_count *  RATIO).
MAX_CANCELED_COUNT_BASE = MAX_TASK_COUNT
MAX_CANCELED_COUNT_RATIO = 0.1
MAX_ERROR_COUNT_BASE = 3
MAX_ERROR_COUNT_RATIO = 0.1

COMMAND_ATTEMPT_SYNC_QUEUE = "command-attempt-sync-queue"

MAX_COMMAND_EVENT_DELAY_MIN = 15  # 15 min

REQUEST_ID_KEY = "request_id"
COMMAND_ID_KEY = "command_id"
ATTEMPT_ID_KEY = "attempt_id"

MAX_PRIORITY = 1000


class CommandTaskNotFoundError(Exception):
  """Raised when a command task is not found."""
  pass


class CommandSummary(object):
  """Command summary from command's attempts.

  The queued_count, running_count, canceled_count, completed_count, error_count
  and fatal_count are the number of command attempts for this command on
  these states.

  The start_time is the earliest start time of all the command attempts for
  this command. The end_time is the latest end_time of all the commands
  attempts for this command. They may be none if the command has no attempts
  or if its attempts have not started or ended.

  The runs holds the summary for individual runs and can be used to assign the
  next run_index and attempt_index for a command.
  """

  def __init__(self, run_count=1):
    """Initialized the command summary.

    Args:
      run_count: The number of runs the command has. This controls how the
        CommandAttempts are distributed between runs and attempts.
    """
    self.total_count = 0
    self.queued_count = 0
    self.running_count = 0
    self.canceled_count = 0
    self.completed_count = 0
    self.completed_fail_count = 0
    self.error_count = 0
    self.fatal_count = 0
    self.start_time = None
    self.end_time = None
    self.runs = [RunSummary() for _ in range(run_count)]

  def AddCommandAttempt(self, command_attempt):
    """Adds the command task to the command summary.

    Args:
      command_attempt: the CommandAttempt object.
    """
    self.total_count += 1
    if command_attempt.state == common.CommandState.QUEUED:
      self.queued_count += 1
    elif command_attempt.state == common.CommandState.RUNNING:
      self.running_count += 1
    elif command_attempt.state == common.CommandState.CANCELED:
      self.canceled_count += 1
    elif command_attempt.state == common.CommandState.COMPLETED:
      self.completed_count += 1
      if (command_attempt.failed_test_count is not None and
          command_attempt.failed_test_count > 0 or
          command_attempt.failed_test_run_count is not None and
          command_attempt.failed_test_run_count > 0):
        self.completed_fail_count += 1
    elif command_attempt.state == common.CommandState.ERROR:
      self.error_count += 1
    elif command_attempt.state == common.CommandState.FATAL:
      self.fatal_count += 1

    if command_attempt.start_time:
      if not self.start_time:
        self.start_time = command_attempt.start_time
      else:
        self.start_time = min(command_attempt.start_time, self.start_time)

    if command_attempt.end_time:
      if not self.end_time:
        self.end_time = command_attempt.end_time
      else:
        self.end_time = max(command_attempt.end_time, self.end_time)

    if (command_attempt.run_index is not None and
        0 <= command_attempt.run_index < len(self.runs)):
      run_summary = self.runs[command_attempt.run_index]
      run_summary.attempt_count += 1
      if command_attempt.state == common.CommandState.QUEUED:
        run_summary.queued_count += 1
      if command_attempt.state == common.CommandState.RUNNING:
        run_summary.running_count += 1
      elif command_attempt.state == common.CommandState.CANCELED:
        run_summary.canceled_count += 1
      elif command_attempt.state == common.CommandState.COMPLETED:
        run_summary.completed_count += 1
        if (command_attempt.failed_test_count is not None and
            command_attempt.failed_test_count > 0 or
            command_attempt.failed_test_run_count is not None and
            command_attempt.failed_test_run_count > 0):
          run_summary.completed_fail_count += 1
      elif command_attempt.state == common.CommandState.ERROR:
        run_summary.error_count += 1
      elif command_attempt.state == common.CommandState.FATAL:
        run_summary.fatal_count += 1

  def AddCommandTasks(self, tasks):
    for task in tasks:
      if task.run_index is not None and 0 <= task.run_index < len(self.runs):
        run_summary = self.runs[task.run_index]
        run_summary.active_task_id = task.task_id

  def ScheduleTask(self, task_id, max_retry_on_test_failures=0):
    """Increments the counts in the summary and appropriate run summary.

    Note that this doesn't actually schedule the next task, but treats the
    summary as if the next task was scheduled in the queued state.

    Args:
      task_id: The id of the current task to schedule.
      max_retry_on_test_failures: The max number of attempts with test failures
        to retry.

    Returns:
      run_index: the next run without have a completed or scheduled attempt.
      attempt_index: the attempt index of the task for the run
    """
    self.total_count += 1
    self.queued_count += 1
    run_index = 0
    run_summary = None

    for i, tmp_summary in enumerate(self.runs):
      # If max_retry_on_test_failures is set, ignore failed attempts up to
      # the number.
      completed_count = tmp_summary.completed_count
      if tmp_summary.completed_fail_count <= max_retry_on_test_failures:
        completed_count -= tmp_summary.completed_fail_count
        max_retry_on_test_failures -= tmp_summary.completed_fail_count
      # Find the run with the fewest attempts which doesn't have a successful,
      # queued, running attempt, or active_task. This helps distributed the
      # attempts between the runs.
      if ((not run_summary or
           tmp_summary.attempt_count < run_summary.attempt_count) and
          completed_count == 0 and
          tmp_summary.queued_count == 0 and
          tmp_summary.running_count == 0 and
          (tmp_summary.active_task_id is None or
           tmp_summary.active_task_id == task_id)):
        run_index = i
        run_summary = tmp_summary

    if not run_summary:
      # If all runs have a completed, queued, or running attempt, fall back to
      # the first run. This should not happen as tasks are only scheduled or
      # rescheduled if more attempts are needed.
      run_index = 0
      run_summary = self.runs[0]
      logging.warning("All runs have a complete or running attempt")

    run_summary.attempt_count += 1
    run_summary.queued_count += 1
    return run_index, run_summary.attempt_count - 1

  def GetState(self,
               state,
               max_retry_on_test_failures=0,
               max_canceled_count=1,
               max_error_count=1):
    """Gets the computed state.

    Args:
      state: the existing state or the state to update to. This allows for the
        summary to override the desired state. For example, if the desired state
        is CANCELLED while the determined state is COMPLETED.
      max_retry_on_test_failures: The max number of attempts with test failures
        to retry.
      max_canceled_count: The number of cancelled attempts before cancelling the
        command.
      max_error_count: The number of errored attempts before erroring the
        command.

    Returns:
      The computed state of the summary
    """
    # If max_retry_on_test_failures is set, ignore failed attempts up to
    # the number.
    completed_count = self.completed_count
    if self.completed_fail_count <= max_retry_on_test_failures:
      completed_count -= self.completed_fail_count

    if completed_count >= len(self.runs):
      return common.CommandState.COMPLETED
    if self.fatal_count > 0:
      return common.CommandState.FATAL
    if self.canceled_count >= max_canceled_count:
      return common.CommandState.CANCELED
    if self.error_count >= max_error_count:
      return common.CommandState.ERROR
    if common.IsFinalCommandState(state):
      return state
    if self.running_count > 0:
      return common.CommandState.RUNNING
    return common.CommandState.QUEUED


class RunSummary(object):
  """Run summary for a particular run index of a command's attempts."""

  def __init__(self):
    self.attempt_count = 0
    self.queued_count = 0
    self.running_count = 0
    self.canceled_count = 0
    self.completed_count = 0
    self.completed_fail_count = 0
    self.error_count = 0
    self.fatal_count = 0
    self.active_task_id = None


def GetCommandSummary(request_id, command_id, run_count):
  """Provides a summary of the attempts for this command.

  Args:
    request_id: request id, str
    command_id: command id, str
    run_count: the number of runs for the command.
  Returns:
    a Command summary object.
  """
  command_attempts = GetCommandAttempts(request_id, command_id)
  if not command_attempts:
    return None
  summary = CommandSummary(run_count)
  for attempt in command_attempts:
    summary.AddCommandAttempt(attempt)
  return summary


def GetActiveTaskCount(command):
  """Returns the number of active command tasks.

  Args:
    command: a command entity, read only
  Returns:
    the number of active command tasks.
  """
  count = command_task_store.GetActiveTaskCount(
      _GetCommandTaskIds(command))
  logging.debug("%r are active in command store.", count)
  return count


def GetActiveTasks(command):
  """Returns the active command tasks.

  Args:
    command: a command entity, read only

  Returns:
    the active command tasks.
  """
  tasks = command_task_store.GetTasks(_GetCommandTaskIds(command))
  return [t for t in tasks if t]


def EnsureLeasable(command):
  """Ensure a command is leasable.

  If some of tasks are not in a leasable state, this function will make them
  leasable by rescheduling. This is only called when command is in QUEUE state.

  Args:
    command: command entity, read only
  Raises:
    CommandTaskNotFoundError: if any of tasks is not found.
  """
  logging.debug("EnsureLeasable %r in %r.", command.key, command.state)
  has_tasks = False
  for task_id in _GetCommandTaskIds(command):
    task = command_task_store.GetTask(task_id)
    if not task:
      logging.info("Task %s not found", task_id)
      continue
    metric.RecordCommandTimingMetric(
        cluster_id=command.cluster,
        run_target=command.run_target,
        create_timestamp=command.create_time,
        command_action=metric.CommandAction.ENSURE_LEASABLE,
        count=True)
    command_task_store.RescheduleTask(
        task_id, task.run_index, task.attempt_index)
    logging.info("Done rescheduling task %s", task_id)
    has_tasks = True
  if not has_tasks:
    # If there are no command tasks, raise a CommandTaskNotFound error to cancel
    # the command.
    raise CommandTaskNotFoundError("Command %s is not leasable" % command)


def _UpdateState(
    request_id, command_id, state=None, force=False, cancel_reason=None,
    attempt_state=None, task_id=None):
  """Updates state of the command based on state of the command attempts.

  Attempts to update the state of a command to a new state, based on the
  command's current state and the states of the command attempts. Depending
  on those factors, the state may not change, or may even change to a state
  different from the input.

  It may update command's request's dirty bit, but it will not update any other
  field for the request.

  It may reschedule a task, setting the appropritate run_index and attempt_index
  based on the previous command attempts.

  Use in a function within a transaction

  Args:
    request_id: request id, str
    command_id: command id, str
    state: The new state the command should attempt to transition to.
    force: Whether to force the update regardless of the dirty bit.
    cancel_reason: cancel reason
    attempt_state: the state of the command attempt, used to determine if a task
      should be rescheduled
    task_id: the task id to reschedule
  Returns:
    command: a updated command entity, read only
  """
  entities_to_update = []
  request = request_manager.GetRequest(request_id)
  command = GetCommand(request_id, command_id)
  logging.info("Attempting to update command %s in state %s to state %s",
               command.key, command.state, state)
  summary = GetCommandSummary(request_id, command_id, command.run_count)

  max_retry_on_test_failures = request.max_retry_on_test_failures or 0
  if not (force or command.dirty):
    logging.info("%s doesn't need to be updated", command.key.id())
    _RescheduleOrDeleteTask(
        task_id, command, summary, attempt_state,
        max_retry_on_test_failures=max_retry_on_test_failures)
    return command

  state = state or command.state

  start_time = None
  end_time = None

  if summary:
    state = summary.GetState(
        state,
        max_retry_on_test_failures=max_retry_on_test_failures,
        max_canceled_count=_GetCommandMaxCancelCount(command),
        max_error_count=_GetCommandMaxErrorCount(command))
    start_time = summary.start_time
    end_time = summary.end_time

  if state and state != command.state:
    command.state = state
    # Set request dirty.
    request = request_manager.GetRequest(command.request_id)
    request.dirty = True
    entities_to_update.append(request)
    logging.info("New state for command %s is %s. Request set to dirty.",
                 command.key, state)

  if (command.state == common.CommandState.CANCELED and
      cancel_reason is not None):
    command.cancel_reason = cancel_reason

  _RescheduleOrDeleteTask(
      task_id, command, summary, attempt_state,
      max_retry_on_test_failures=max_retry_on_test_failures)

  command.start_time = start_time or command.start_time
  command.end_time = end_time or command.end_time
  command.dirty = False
  entities_to_update.append(command)
  ndb.put_multi(entities_to_update)
  return command


def _GetCommandMaxCancelCount(command):
  """Get a command's max error count."""
  return MAX_CANCELED_COUNT_BASE + int(
      command.run_count * MAX_CANCELED_COUNT_RATIO)


def _GetCommandMaxErrorCount(command):
  """Get a command's max error count."""
  return MAX_ERROR_COUNT_BASE + int(command.run_count * MAX_ERROR_COUNT_RATIO)


def _RescheduleOrDeleteTask(
    task_id, command, summary, attempt_state, max_retry_on_test_failures=0):
  """Reschdules a task if more tasks are needed, or deletes it.

  Args:
    task_id: the id of the task to schedule
    command: the command
    summary: the CommandSummary, needed for the next run_index and
      attempt_index. If none, will fall back to 0, 0.
    attempt_state: the state of the attempt, this is used to no-op for non-final
      command attempts.
    max_retry_on_test_failures: The max number of attempts with test failures
      to retry.
  """
  if not task_id:
    return

  if common.IsFinalCommandState(command.state):
    logging.debug("Command state %s is final.", attempt_state)
    return

  if not common.IsFinalCommandState(attempt_state):
    logging.debug("Attempt state %s is not final.", attempt_state)
    return

  active_tasks = GetActiveTasks(command)
  completed_count = 0
  run_index = 0
  attempt_index = 0
  if summary:
    summary.AddCommandTasks(active_tasks)
    completed_count = summary.completed_count
    if summary.completed_fail_count <= max_retry_on_test_failures:
      completed_count -= summary.completed_fail_count
    run_index, attempt_index = summary.ScheduleTask(
        task_id, max_retry_on_test_failures=max_retry_on_test_failures)

  logging.info(
      "command.state = %s, command.run_count = %r, completed_count = %r.",
      command.state.name, command.run_count, completed_count)

  # Since the task to rescheduled is active, we reschedule even if the active
  # tasks and completed runs are equal to the run_count.
  if len(active_tasks) + completed_count <= command.run_count:
    logging.debug(
        "active_task_count %r + completed_count %r <= run_count %r, "
        "reschedule %r.", len(active_tasks), completed_count, command.run_count,
        task_id)
    RescheduleTask(task_id, command, run_index, attempt_index)
  else:
    logging.debug(
        "active_task_count %r + completed_count %r <= run_count %r, "
        "delete %r", len(active_tasks), completed_count, command.run_count,
        task_id)
    DeleteTask(task_id)


def AddToSyncCommandAttemptQueue(attempt):
  """Add a command to the sync queue."""
  logging.info("Monitoring command attempt: %s", attempt.key)
  _, request_id, _, command_id, _, attempt_id = attempt.key.flat()
  payload = json.dumps({
      COMMAND_ID_KEY: command_id,
      REQUEST_ID_KEY: request_id,
      ATTEMPT_ID_KEY: attempt_id,
  })
  update_time = attempt.update_time or common.Now()
  task_scheduler.AddTask(
      queue_name=COMMAND_ATTEMPT_SYNC_QUEUE,
      payload=payload,
      eta=update_time + datetime.timedelta(minutes=MAX_COMMAND_EVENT_DELAY_MIN))


@ndb.transactional()
def UpdateCommandAttempt(event):
  """Updates a command attempt in datastore.

  Args:
    event: a CommandEvent.
  Returns:
    True if the command attempt state is updated, otherwise False
  """
  entities_to_update = []
  attempt_entity = GetCommandAttempt(event.request_id, event.command_id,
                                     event.attempt_id)

  attempt_state_changed = False
  if not attempt_entity:
    logging.error(
        "attempt cannot be found, request_id: %s, command_id: %s, attempt_id: %s",
        event.request_id, event.command_id, event.attempt_id)
    return False
  elif (attempt_entity.last_event_time and
        event.time and
        event.time < attempt_entity.last_event_time and
        not common.IsFinalCommandState(event.attempt_state)):
    logging.info("Ignore old '%s' command attempt event.",
                 event.attempt_state)
    return False

  # If a command attempt state is already final, it should not be updated.
  orig_state = attempt_entity.state
  if common.IsFinalCommandState(orig_state):

    logging.warning(
        "Command attempt %s in %s final state cannot be updated to %s.",
        attempt_entity.task_id,
        orig_state,
        event.attempt_state)
    return False
  elif event.attempt_state and orig_state != event.attempt_state:
    attempt_entity.state = event.attempt_state
    attempt_state_changed = True
    command = GetCommand(event.request_id, event.command_id)
    command.dirty = True
    entities_to_update.append(command)
  _UpdateCommandAttemptEntity(attempt_entity, event)
  entities_to_update.append(attempt_entity)
  ndb.put_multi(entities_to_update)

  if attempt_state_changed:
    logging.info("Attempt %s state changed from %s to %s", event.attempt_id,
                 orig_state, event.attempt_state)
    _NotifyAttemptState(attempt_entity, orig_state, event.time)
  return True


def _UpdateCommandAttemptEntity(attempt_entity, event):
  """Update attempt entity information with command event."""
  attempt_entity.hostname = event.hostname or attempt_entity.hostname
  # TODO Deprecated.
  attempt_entity.device_serial = (
      event.device_serial or attempt_entity.device_serial)
  attempt_entity.device_serials = (
      event.device_serials or attempt_entity.device_serials)
  if event.attempt_start_time:
    if (not attempt_entity.start_time or
        event.attempt_start_time < attempt_entity.start_time):
      attempt_entity.start_time = event.attempt_start_time
  attempt_entity.end_time = event.attempt_end_time or attempt_entity.end_time
  attempt_entity.status = event.status or attempt_entity.status
  attempt_entity.error = event.error or attempt_entity.error
  attempt_entity.error_reason = (
      event.error_reason or attempt_entity.error_reason)
  attempt_entity.error_type = event.error_type or attempt_entity.error_type
  attempt_entity.summary = event.summary or attempt_entity.summary
  if event.total_test_count is not None:
    attempt_entity.total_test_count = event.total_test_count
  if event.failed_test_count is not None:
    attempt_entity.failed_test_count = event.failed_test_count
  if event.passed_test_count is not None:
    attempt_entity.passed_test_count = event.passed_test_count
  if event.failed_test_run_count is not None:
    attempt_entity.failed_test_run_count = event.failed_test_run_count
  if event.device_lost_detected is not None:
    attempt_entity.device_lost_detected = event.device_lost_detected
  # If we process command events out of order, we should keep the latest
  # event timestamp.
  if (event.time is not None and
      (attempt_entity.last_event_time is None or
       event.time > attempt_entity.last_event_time)):
    attempt_entity.last_event_time = event.time
  if event.invocation_status is not None:
    attempt_entity.invocation_status = event.invocation_status
  attempt_entity.update_time = common.Now()


def _NotifyAttemptState(attempt_entity, old_state, event_time):
  """Notifies about attempt state change if notify_attempt_events config is on.

  Args:
    attempt_entity: entity for the attempt
    old_state: state of attempt before the change
    event_time: time of the event
  """
  if(common.ObjectEventType.COMMAND_ATTEMPT_STATE_CHANGED not in
     env_config.CONFIG.object_event_filter):
    return

  message = api_messages.CommandAttemptEventMessage(
      type=common.ObjectEventType.COMMAND_ATTEMPT_STATE_CHANGED,
      attempt=datastore_entities.ToMessage(attempt_entity),
      old_state=old_state,
      new_state=attempt_entity.state,
      event_time=event_time)
  payload = zlib.compress(six.ensure_binary(protojson.encode_message(message)))  # pytype: disable=module-attr
  task_scheduler.AddTask(
      queue_name=common.OBJECT_EVENT_QUEUE, payload=payload)


def ProcessCommandEvent(event):
  """Updates state of a command and coordinate command tasks.

  Args:
    event: a CommandEvent
  """
  command = GetCommand(event.request_id, event.command_id)
  if not command:
    logging.warning(
        "unknown command %s %s; ignored", event.request_id, event.command_id)
    return

  is_updated = UpdateCommandAttempt(event)

  # No need to coordinate if the event is old but continue if it is final.
  # We continue if it is final as datastore update to the command and the
  # attempt aren't done in the same transaction, so a failed command update
  # should be retried in that event.
  if not is_updated and not common.IsFinalCommandState(event.attempt_state):
    logging.debug("Command attempt is not updated.")
    return

  if common.IsFinalCommandState(event.attempt_state):
    metric.RecordCommandAttemptMetric(
        cluster_id=command.cluster,
        run_target=command.run_target,
        hostname=event.hostname,
        state=event.attempt_state.name)

  # Update command.
  command = _UpdateState(
      event.request_id,
      event.command_id,
      attempt_state=event.attempt_state,
      task_id=event.task_id)

  if common.IsFinalCommandState(command.state):
    # Deschedule command since the state indicates that it is not supposed
    # to run anymore.
    logging.debug("Command %r is finalized, delete all its tasks.",
                  command.key)
    DeleteTasks(command)

  # Update request.
  request_manager.EvaluateState(event.request_id)

  # Update AnTS.
  env_config.CONFIG.plugin.OnProcessCommandEvent(
      GetCommand(event.request_id, event.command_id),
      GetCommandAttempt(event.request_id, event.command_id, event.attempt_id),
      )


def ScheduleTasks(commands):
  """Schedules command tasks to run.

  Args:
    commands: a list of commands, read only
  """
  request_ids = _DoScheduleTasks(commands)
  for request_id in request_ids:
    request_manager.EvaluateState(request_id)


@ndb.transactional()
def _DoScheduleTasks(commands):
  """Schedule command tasks in a transaction.

  Args:
    commands: a list of Command objects.
  Returns:
    A set of affected Request IDs.
  """
  request_ids = {command.request_id for command in commands}
  # Ensure requests are in a pre-scheduled state (UNKNOWN).
  for request_id in request_ids:
    request = request_manager.GetRequest(request_id)
    if not request or request.state == common.RequestState.CANCELED:
      raise ValueError(
          "A request is CANCELED: request=%s" % request)
  for command in commands:
    if command.priority and (
        command.priority < 0 or MAX_PRIORITY < command.priority):
      raise ValueError("priority is out of range: %d" % command.priority)
    _ScheduleTasksToCommandTaskStore(command)
    _UpdateState(command.request_id, command.key.id(),
                 state=common.CommandState.QUEUED, force=True)
  return request_ids


def _ScheduleTasksToCommandTaskStore(command):
  """Schedules command tasks to CommandTaskStore to run.

  Args:
    command: command to schedule tasks, read only
  """
  for i, task_id in enumerate(_GetCommandTaskIds(command)):
    command_task_args = command_task_store.CommandTaskArgs(
        request_id=command.request_id,
        command_id=command.key.id(),
        task_id=task_id,
        command_line=command.command_line,
        run_count=command.run_count,
        run_index=i,
        attempt_index=0,
        shard_count=command.shard_count,
        shard_index=command.shard_index,
        cluster=command.cluster,
        run_target=command.run_target,
        priority=command.priority,
        request_type=command.request_type,
        plugin_data=command.plugin_data)
    if not command_task_store.CreateTask(command_task_args):
      logging.warning("task %s already exists", task_id)


def RescheduleTask(task_id, command, run_index, attempt_index):
  """Reschedules a command task.

  Args:
    task_id: a command task ID.
    command: a command entity, read only
    run_index: the new run index fo the task
    attempt_index: the new attempt index for the task
  Raises:
    CommandTaskNotFoundError: a task is not found.
  """
  command_task_store.RescheduleTask(task_id, run_index, attempt_index)
  metric.RecordCommandTimingMetric(
      cluster_id=command.cluster,
      run_target=command.run_target,
      create_timestamp=command.create_time,
      command_action=metric.CommandAction.RESCHEDULE,
      count=True)


def _GetCommandTaskIds(command):
  """Get a command's task ids."""
  # A task count is the number of tasks we put in the command queue for this
  # command. We cap this number to avoid a single command with large run count
  # dominating an entire cluster. If a task count is smaller than a run count,
  # completed tasks will be rescheduled as needed.
  task_count = min(command.run_count, MAX_TASK_COUNT)
  _, request_id, _, command_id = command.key.flat()
  return ["%s-%s-%s" % (request_id, command_id, i) for i in range(task_count)]


def CreateCommands(request_id,
                   run_target,
                   run_count,
                   cluster,
                   request_plugin_data=None,
                   state=None,
                   priority=None,
                   queue_timeout_seconds=None,
                   request_type=None,
                   command_lines=None,
                   shard_count=None,
                   shard_indexes=None):
  """Creates test commands for a request.

  Since IDs cannot be allocated within a transaction, this function acts as a
  wrapper around `_DoCreateCommands`, by allocating an integer range of IDs,
  and passing them to `_DoCreateCommands` to actually create the commands in a
  transaction:
  https://cloud.google.com/appengine/docs/standard/python/ndb/modelclass#Model_allocate_ids

  Args:
    request_id: a request ID, str
    run_target: a run target device.
    run_count: a run count.
    cluster: the id of the cluster on which to run the following command.
    request_plugin_data: a map of plugin data from request.
    state: the state of the command. Should only be used in tests.
    priority: a command priority.
    queue_timeout_seconds: a command timeout in seconds.
    request_type: a request type.
    command_lines: a list of command line string,
      all command lines are for the same request.
    shard_count: the request's shard count
    shard_indexes: the commands' corresponding shard index.
  Returns:
    a list of command entities, read only
  """
  request_id = str(request_id)
  if not command_lines:
    return []
  request_key = ndb.Key(
      datastore_entities.Request, request_id,
      namespace=common.NAMESPACE)
  command_ids = [command_id.id() for command_id in datastore_entities.Command\
                 .allocate_ids(size=len(command_lines), parent=request_key)]

  command_plugin_data_map = {}
  command_infos = []
  for cid, cl, i in zip(command_ids, command_lines, shard_indexes):
    command_infos.append(
        plugin_base.CommandInfo(
            command_id=cid,
            command_line=cl,
            run_count=run_count,
            shard_count=shard_count,
            shard_index=i))

  env_config.CONFIG.plugin.OnCreateCommands(
      command_infos,
      request_plugin_data,
      command_plugin_data_map)

  return _DoCreateCommands(request_id,
                           run_target,
                           run_count,
                           cluster,
                           command_plugin_data_map=command_plugin_data_map,
                           state=state,
                           priority=priority,
                           queue_timeout_seconds=queue_timeout_seconds,
                           request_type=request_type,
                           command_lines=command_lines,
                           command_ids=command_ids,
                           shard_count=shard_count,
                           shard_indexes=shard_indexes)


@ndb.transactional()
def _DoCreateCommands(request_id,
                      run_target,
                      run_count,
                      cluster,
                      command_plugin_data_map=None,
                      state=None,
                      priority=None,
                      queue_timeout_seconds=None,
                      request_type=None,
                      command_lines=None,
                      command_ids=None,
                      shard_count=None,
                      shard_indexes=None):
  """Creates or return existing test commands for a request.

  Args:
    request_id: a request ID, str
    run_target: a run target device.
    run_count: a run count.
    cluster: the id of the cluster on which to run the following command.
    command_plugin_data_map: a map of plugin data for each command.
    state: the state of the command. Should only be used in tests.
    priority: a command priority.
    queue_timeout_seconds: a command timeout in seconds.
    request_type: a request type.
    command_lines: a list of command line string,
      all command lines are for the same request.
    command_ids: auto generate ids are integers, so we need to pre-allocate
      some command id for commands.
    shard_count: the request's shard count
    shard_indexes: the commands' corresponding shard index.
  Returns:
    a list of command entities, read only
  """
  # TODO: Use the get commands in request_manager.
  request_key = ndb.Key(datastore_entities.Request, request_id,
                        namespace=common.NAMESPACE)

  # Ensure a request is not CANCELED.
  request = request_key.get()
  if not request or request.state == common.RequestState.CANCELED:
    raise ValueError("A request is CANCELED: request=%s" % request)

  existing_commands = (datastore_entities.Command
                       .query(ancestor=request_key,
                              namespace=common.NAMESPACE).fetch())
  if existing_commands:
    logging.info("existing")
    return existing_commands

  new_commands = []

  for command_line, command_id, shard_index in (list(
      zip(command_lines, command_ids, shard_indexes))):
    command_key = ndb.Key(
        datastore_entities.Command, str(command_id),
        parent=request_key, namespace=common.NAMESPACE)

    plugin_data_ = {}
    if command_plugin_data_map and command_id in command_plugin_data_map:
      plugin_data_ = command_plugin_data_map[command_id]

    command = datastore_entities.Command(
        key=command_key,
        request_id=request_id,
        command_line=command_line,
        cluster=cluster,
        run_target=run_target,
        run_count=run_count,
        state=state or common.CommandState.UNKNOWN,
        priority=priority,
        queue_timeout_seconds=queue_timeout_seconds,
        request_type=request_type,
        shard_count=shard_count if shard_count > 1 else None,
        shard_index=shard_index if shard_count > 1 else None,
        plugin_data=plugin_data_)
    new_commands.append(command)
  logging.info(new_commands)
  ndb.put_multi(new_commands)
  return new_commands


def GetCommand(request_id, command_id):
  """Returns a command.

  Args:
    request_id: request id, str
    command_id: command id, str
  Returns:
    a command entity.
  """
  return ndb.Key(
      datastore_entities.Request, request_id,
      datastore_entities.Command, command_id,
      namespace=common.NAMESPACE).get()


def GetCommandAttempt(request_id, command_id, attempt_id):
  """Returns a command attempt.

  Args:
    request_id: request id, str
    command_id: command id, str
    attempt_id: attempt id, str
  Returns:
    a command attempt entity.
  """
  return ndb.Key(
      datastore_entities.Request, request_id,
      datastore_entities.Command, command_id,
      datastore_entities.CommandAttempt, attempt_id,
      namespace=common.NAMESPACE).get()


def GetCommands(request_id, state=None):
  """Returns command objects for the given request ID.

  Args:
    request_id: a request id, str
    state: a CommandState.
  Returns:
    a list of Command entities.
  """
  request_key = ndb.Key(
      datastore_entities.Request, request_id,
      namespace=common.NAMESPACE)
  query = datastore_entities.Command.query(
      ancestor=request_key).order(datastore_entities.Command.create_time)

  if state is not None:
    query = query.filter(datastore_entities.Command.state == state)
  return query.fetch()


@ndb.transactional()
def Touch(request_id, command_id):
  """Renew update_time of this command."""
  command = GetCommand(request_id, command_id)
  if command:
    command.update_time = common.Now()
    command.put()
  return command


def DeleteTask(task_id):
  """Delete a task."""
  command_task_store.DeleteTasks([task_id])


def DeleteTasks(command):
  """Clears all command tasks."""
  logging.info("Deleting tasks for: %s", command.key)
  task_ids = _GetCommandTaskIds(command)
  command_task_store.DeleteTasks(task_ids)


def CancelCommands(request_id, cancel_reason=None):
  """Cancel all commands associated with a request id.

  Args:
    request_id: a request ID, str.
    cancel_reason: an optional enum cancel reason.
  """
  commands = GetCommands(request_id)
  for command in commands:
    Cancel(
        request_id, command.key.id(),
        cancel_reason or common.CancelReason.UNKNOWN)
  request_manager.CancelRequest(
      request_id,
      cancel_reason or common.CancelReason.UNKNOWN)


def Cancel(request_id, command_id, cancel_reason=None):
  """Cancel a command.

  Args:
    request_id: request id, str
    command_id: command id, str
    cancel_reason: cancel reason
  Returns:
    command: a command entity, read only
  """
  command = GetCommand(request_id, command_id)
  command = _UpdateState(
      request_id, command_id,
      state=common.CommandState.CANCELED, force=True,
      cancel_reason=cancel_reason)
  DeleteTasks(command)
  return command


def _GetCommandAttemptsFromCommandKey(command_key, state=None):
  """Returns command attempt entities for the given command key.

  Args:
    command_key: ndb.Key for a command.
    state: a CommandState.
  Returns:
    a list of CommandAttempt datastore entities in create time order.
  """
  query = datastore_entities.CommandAttempt.query(ancestor=command_key)
  if state is not None:
    query = query.filter(datastore_entities.CommandAttempt.state == state)
  return sorted(query.fetch(), key=lambda x: x.create_time)


def GetCommandAttempts(request_id, command_id, state=None):
  """Returns command attempt entities for the given command ID or state.

  Args:
    request_id: a request ID string.
    command_id: a command ID string.
    state: a CommandState.
  Returns:
    a list of CommandAttempt datastore entities.
  """
  command_key = ndb.Key(
      datastore_entities.Request, request_id,
      datastore_entities.Command, command_id,
      namespace=common.NAMESPACE)
  return _GetCommandAttemptsFromCommandKey(command_key, state)


def GetLastCommandActiveTime(command):
  """Calculate the last time the command or its attempts were active.

  Args:
    command: Command entity

  Returns:
    Datetime for latest time the command was active
  """
  attempts = _GetCommandAttemptsFromCommandKey(command.key)
  update_times = [command.update_time] + [a.last_event_time for a in attempts]
  return max([update_time for update_time in update_times if update_time])


def UpdateTestContext(request_id, command_id, test_context):
  """Updates a test context for a command.

  Args:
    request_id: a request ID.
    command_id: a command ID.
    test_context: a TestContext object.
  """
  command_key = ndb.Key(
      datastore_entities.Request, str(request_id),
      datastore_entities.Command, str(command_id),
      namespace=common.NAMESPACE)
  clone = datastore_entities.TestContext(**test_context.to_dict())
  old_test_context = datastore_entities.TestContext.query(
      ancestor=command_key).get()
  if old_test_context:
    clone.key = old_test_context.key
  else:
    new_id = ndb.Model.allocate_ids(size=1, parent=command_key)[0].id()
    clone.key = ndb.Key(
        datastore_entities.TestContext,
        new_id,
        parent=command_key,
        namespace=common.NAMESPACE)
  clone.put()
