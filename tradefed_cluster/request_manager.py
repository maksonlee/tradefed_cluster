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

"""Module for managing test requests."""
import collections
import json
import logging
import re
import zlib

from protorpc import protojson

from tradefed_cluster.util import ndb_shim as ndb

from tradefed_cluster import api_messages
from tradefed_cluster import command_error_type_config
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config
from tradefed_cluster.services import task_scheduler
from tradefed_cluster.util import command_util

REQUEST_QUEUE = "test-request-queue"
SPONGE_URI_PATTERN = r".*(https?://(?:sponge|g3c).corp.example.com\S*).*"


class RequestSummary(object):
  """Request summary from request's commands."""

  def __init__(self):
    # set the default value to 0, so the value can be incement directly.
    self.running_count = 0
    self.canceled_count = 0
    self.completed_count = 0
    self.error_count = 0
    self.fatal_count = 0
    self.total_count = 0
    self.start_time = None
    self.end_time = None
    self.cancel_reason = None


def EvaluateState(request_id, force=False):
  """Attempts to evaluate request state from its commands.

  Args:
    request_id: a request's id, str
    force: Whether to force an update regardless of the dirty bit.
  Returns:
    updated request, read only
  """
  _UpdateState(request_id, force=force)
  return NotifyRequestState(request_id)


def CancelRequest(request_id, cancel_reason=None):
  """Cancel a request by its id.

  Args:
    request_id: request's id, str
    cancel_reason: a enum cancel reason.
  """
  # TODO: Request manager should cancel all commands.
  request = GetRequest(request_id)
  if request:
    _UpdateState(
        request_id,
        state=common.RequestState.CANCELED, force=True,
        cancel_reason=cancel_reason or common.CancelReason.UNKNOWN)
    NotifyRequestState(request_id)
    DeleteFromQueue(request_id)


@ndb.transactional
def _UpdateState(request_id, state=None, force=False, cancel_reason=None):
  """Attempts to update the state of a request.

  Attempts to update the state of a request based on the request's current
  state and the state of its child commands. Depending on those factors, the
  state may not change, or may even change to a state different from the
  input.
  This function should be used in another function in a transaction.

  Args:
    request_id: request id, str
    state: The new state of the request.
    force: Whether to force an update regardless of the dirty bit.
    cancel_reason: A machine readable enum cancel reason.
  Returns:
    updated request, read only
  """
  request = GetRequest(request_id)
  logging.info("Attempting to update %s from %s to %s",
               request.key.id(),
               common.RequestState(request.state).name,
               state.name if state is not None else "")
  if not (force or request.dirty):
    logging.info("%s doesn't need to be updated", request.key.id())
    return request
  if state is None:
    state = request.state
  summary = GetRequestSummary(request.key.id())
  start_time = summary.start_time
  end_time = summary.end_time

  # COMPLETED, ERROR, and CANCELLED state transitions can be from any
  # other state.
  if (summary.total_count and
      summary.completed_count == summary.total_count):
    state = common.RequestState.COMPLETED
  elif summary.error_count + summary.fatal_count > 0:
    state = common.RequestState.ERROR
  elif state != common.RequestState.CANCELED and summary.canceled_count > 0:
    state = common.RequestState.CANCELED
    if cancel_reason is None:
      # propagate command's cancel_reason to request
      cancel_reason = summary.cancel_reason
    logging.debug(
        "UpdateState request %s to CANCELED state with reason: %s.",
        request_id, cancel_reason)

  # UNKNOWN, RUNNING and QUEUED state transitions depend on the current
  # state.
  elif state in (
      common.RequestState.UNKNOWN,
      common.RequestState.RUNNING,
      common.RequestState.QUEUED,
      ):
    if summary.running_count > 0:
      state = common.RequestState.RUNNING
    elif summary.total_count > 0:
      state = common.RequestState.QUEUED

  if state < common.RequestState.RUNNING:
    start_time = None
  if state <= common.RequestState.RUNNING:
    end_time = None

  if cancel_reason is not None:
    logging.debug(
        "updateState update request %s with cancel reason: %s.",
        request_id, cancel_reason)
  if state != request.state:
    logging.info("Updating request %s in ds from %s to %s",
                 request.key.id(),
                 common.RequestState(request.state).name,
                 common.RequestState(state).name)
    request.notify_state_change = True
    request.state = state
  request.start_time = start_time or request.start_time
  request.end_time = end_time or request.end_time
  if cancel_reason:
    request.cancel_reason = cancel_reason
  request.dirty = False
  request.put()
  return request


def Poke(request_id):
  """Poke a request to notify its state via notifier."""
  NotifyRequestState(request_id, force=True)


def NotifyRequestState(request_id, force=False):
  """Notifies about request state change and updates flag.

  Args:
    request_id: request id, str
    force: Whether or not to force notification regardless of
           notify_state_change bit.
  Returns:
    request, read only.
  """
  request = GetRequest(request_id)
  if not request:
    logging.warning("Could not find request for request_id %s", request_id)
    return None
  if not(force or request.notify_state_change):
    logging.warning("Skipping notification for request_id %s because it is not"
                    " dirty and we are not forcing notification.",
                    request.key.id())
    return request
  logging.debug(
      "NotifyRequestState notify request %s to %s state with reason %s",
      request_id, request.state, request.cancel_reason)

  if(common.ObjectEventType.REQUEST_STATE_CHANGED in
     env_config.CONFIG.object_event_filter):
    message = CreateRequestEventMessage(request)
    return SendRequestStateNotification(request_id, message)
  return request


@ndb.transactional(xg=True)
def SendRequestStateNotification(request_id, message):
  request = GetRequest(request_id)
  payload = zlib.compress(protojson.encode_message(message))
  task_scheduler.AddTask(
      queue_name=common.OBJECT_EVENT_QUEUE, payload=payload, transactional=True)
  request.notify_state_change = False
  request.put()
  return request


def CreateRequestEventMessage(request):
  """Creates a notifier message containing request state change information.

  Args:
    request: a request entity
  Returns:
    a message used for notifying request state changes
  """
  request_id = request.key.id()
  commands = GetCommands(request_id)
  attempts = GetCommandAttempts(request_id)

  summaries = []
  errors = []
  total_test_count = 0
  failed_test_count = 0
  passed_test_count = 0
  failed_test_run_count = 0
  device_lost_detected = 0
  result_links = set()
  total_run_time_sec = 0
  error_type = None
  error_reason = None

  for command in commands:
    run_count = command.run_count
    for attempt in reversed(attempts):
      if attempt.key.parent() != command.key:
        continue
      if attempt.start_time and attempt.end_time:
        run_time = (attempt.end_time - attempt.start_time).total_seconds()
        if run_time > 0:
          total_run_time_sec += run_time

      summary = attempt.summary or "No summary available."
      result_match = re.match(SPONGE_URI_PATTERN, summary)
      result_link = result_match.group(1) if result_match else ""

      if attempt.device_lost_detected:
        # Count devices lost regardless of the state of the attempt
        device_lost_detected += attempt.device_lost_detected

      if run_count > 0 and attempt.state == common.CommandState.COMPLETED:
        if attempt.total_test_count:
          total_test_count += attempt.total_test_count
        if attempt.failed_test_count:
          failed_test_count += attempt.failed_test_count
        if attempt.passed_test_count:
          passed_test_count += attempt.passed_test_count
        if attempt.failed_test_run_count:
          failed_test_run_count += attempt.failed_test_run_count
        summaries.append("Attempt %s: %s" % (attempt.attempt_id, summary))
        if result_link:
          result_links.add(result_link)
        run_count -= 1

      # Only surface failed attempts if the command is in an ERROR state.
      elif (attempt.state in (common.CommandState.ERROR,
                              common.CommandState.FATAL)
            and attempt.state == command.state):
        error = attempt.error or "No error message available."
        # Set request's error_type and reason as first non-empty error's
        # mapping value
        if error_type is None and attempt.error:
          error_reason, error_type = (
              command_error_type_config.GetConfig(attempt.error))
        errors.append("Attempt %s: %s %s (ERROR)" %
                      (attempt.attempt_id, result_link, error))
        if result_link:
          result_links.add(result_link)

  summary = "\n".join(summaries + errors)
  logging.debug(
      "notifier notify request %s change to state %s with reason %s.",
      request.key.id(), request.state, request.cancel_reason or error_reason)
  message = api_messages.RequestEventMessage(
      type=common.ObjectEventType.REQUEST_STATE_CHANGED,
      request_id=str(request.key.id()),
      new_state=request.state,
      request=datastore_entities.ToMessage(request),
      summary=summary,
      total_test_count=total_test_count,
      failed_test_count=failed_test_count,
      passed_test_count=passed_test_count,
      result_links=list(result_links),
      total_run_time_sec=int(total_run_time_sec),
      error_reason=error_reason,
      error_type=error_type,
      event_time=common.Now(),
      failed_test_run_count=failed_test_run_count,
      device_lost_detected=device_lost_detected)
  return message


def GetCommands(request_id):
  """Returns all commands entities for the request.

  Args:
    request_id: request id, str
  Returns:
    a list of Command entities.
  """
  request_key = ndb.Key(datastore_entities.Request, request_id,
                        namespace=common.NAMESPACE)
  return (datastore_entities.Command
          .query(ancestor=request_key).fetch())


def GetRequestSummary(request_id):
  """Builds a request summary based on state of child commands.

  The running_count, canceled_count, completed_count, error_count
  and fatal_count are the number of commands for this request on these states.
  The total_count is the number of all commands for this request regardless
  of their current state.
  The start_time is the earliest start time of all the commands for this
  request. The end_time is the latest end_time of all the commands for this
  request. They may be none if the request has no commands or their command
  attempts have not started or ended.

  Args:
    request_id: request id, str
  Returns:
    a Request summary object.
  """
  commands = GetCommands(request_id)
  summary = RequestSummary()
  summary.total_count = len(commands)

  command_state_map = collections.defaultdict(list)
  for command in commands:
    command_state_map[command.state].append(command.key.id())
    if command.state == common.CommandState.RUNNING:
      summary.running_count += 1
    elif command.state == common.CommandState.CANCELED:
      summary.canceled_count += 1
      # summary's cancel_reason is the first canceled command's reason
      if not summary.cancel_reason:
        summary.cancel_reason = command.cancel_reason
    elif command.state == common.CommandState.COMPLETED:
      summary.completed_count += 1
    elif command.state == common.CommandState.ERROR:
      summary.error_count += 1
    elif command.state == common.CommandState.FATAL:
      summary.fatal_count += 1
    if command.start_time:
      if not summary.start_time:
        summary.start_time = command.start_time
      else:
        summary.start_time = min(command.start_time, summary.start_time)
    if command.end_time:
      if not summary.end_time:
        summary.end_time = command.end_time
      else:
        summary.end_time = max(command.end_time, summary.end_time)

  command_map_str = "\n\t".join(
      "{}: {}".format(state, ids) for state, ids in command_state_map.items())
  logging.debug("Request summary:\n\t%s", command_map_str)
  return summary


def GetCommandAttempts(request_id):
  """Returns all command attempt entities for the request in create time order.

  Args:
    request_id: request id, str
  Returns:
    a list of CommandAttempt entities.
  """
  request_key = ndb.Key(datastore_entities.Request, request_id,
                        namespace=common.NAMESPACE)
  query = datastore_entities.CommandAttempt.query(ancestor=request_key)
  return sorted(query.fetch(), key=lambda x: x.create_time)


def GetCommandAttempt(request_id, command_id, attempt_id):
  """Returns the command attempt that matches the attempt id.

  Args:
    request_id: id for the parent request
    command_id: id for the parent command
    attempt_id: id for the attempt
  Returns:
    a CommandAttempt entity
  """
  return ndb.Key(
      datastore_entities.Request, request_id,
      datastore_entities.Command, command_id,
      datastore_entities.CommandAttempt, attempt_id,
      namespace=common.NAMESPACE).get()


def CreateRequest(user,
                  command_line,
                  priority=None,
                  queue_timeout_seconds=None,
                  type_=None,
                  request_id=None,
                  cluster=None,
                  run_target=None,
                  run_count=None,
                  shard_count=None,
                  plugin_data=None,
                  max_retry_on_test_failures=None,
                  prev_test_context=None):
  """Create a new request and add it to the request_queue.

  Args:
    user: a requesting user.
    command_line: a command line string.
    priority: a request priority.
    queue_timeout_seconds: a request timeout in seconds.
    type_: a request type.
    request_id: request_id, used for easy testing.
    cluster: the cluster to run the test.
    run_target: the run target to run the test.
    run_count: run count.
    shard_count: shard count.
    plugin_data: a map that contains the plugin data.
    max_retry_on_test_failures: the max number of completed but failed attempts
        for each command.
    prev_test_context: a previous test context.
  Returns:
    a Request entity, read only.
  """
  if not request_id:
    request_id = _CreateRequestId()
  if not type_:
    # For an unmanaged request, parameters can passed via a command line.
    command_line_obj = command_util.CommandLine(command_line)
    cluster = cluster or command_line_obj.GetOption("--cluster")
    run_target = run_target or command_line_obj.GetOption("--run-target")
    run_count = (run_count or
                 int(command_line_obj.GetOption("--run-count", 1)) or
                 1)
    # If shard_count field is set, use it, otherwise if it's local sharding
    # fake one shard_count and the actual "shard-count" will let Tradefed shard
    # the config
    if not shard_count and command_line_obj.GetOption("--shard-index") is None:
      shard_count = 1
    else:
      shard_count = (
          shard_count or int(command_line_obj.GetOption("--shard-count", 1)) or
          1)

  key = ndb.Key(
      datastore_entities.Request, request_id,
      namespace=common.NAMESPACE)

  request = datastore_entities.Request(
      key=key,
      user=user,
      command_line=command_line,
      state=common.RequestState.UNKNOWN,
      priority=priority,
      queue_timeout_seconds=queue_timeout_seconds,
      type=type_,
      cluster=cluster,
      run_target=run_target,
      run_count=run_count,
      shard_count=shard_count,
      plugin_data=plugin_data,
      max_retry_on_test_failures=max_retry_on_test_failures,
      prev_test_context=prev_test_context)
  request.put()
  return request


def _CreateRequestId():
  """Create a request id.

  This is to avoid conflict with the other TFC.

  Returns:
    request_id, str
  """
  # TODO: this only need to be run once, but there is no hurt to run
  # multiple times. This to allocate ids we already used, so new id will not
  # use those.
  datastore_entities.Request.allocate_ids(max=30000000)
  while True:
    id_, _ = datastore_entities.Request.allocate_ids(1)
    id_ = str(id_)
    if not datastore_entities.Request.get_by_id(
        id_, namespace=common.NAMESPACE):
      return id_
    logging.warning("Request %r already exist.", id_)


def AddToQueue(request):
  """Adds the request to the request queue.

  Args:
    request: request entity, read only
  """
  task_name = str(request.key.id())
  payload = json.dumps({
      "id": request.key.id(),
      "user": request.user,
      "command_line": request.command_line,
      "priority": request.priority,
      "queue_timeout_seconds": request.queue_timeout_seconds
  })
  compressed_payload = zlib.compress(payload)
  task_scheduler.AddTask(
      queue_name=REQUEST_QUEUE, name=task_name, payload=compressed_payload)


def DeleteFromQueue(request_id):
  """Deletes the request from the request queue.

  Args:
    request_id: request id, str
  """
  try:
    task_scheduler.DeleteTask(REQUEST_QUEUE, request_id)
  except task_scheduler.Error:
    logging.warning(
        "Failed to delete request %s from the queue.",
        request_id,
        exc_info=True)


def GetRequest(request_id):
  """Returns a request.

  Args:
    request_id: a request ID.
  Returns:
    a Request object, read only
  """
  return ndb.Key(
      datastore_entities.Request, str(request_id),
      namespace=common.NAMESPACE).get()


def GetRequests(user=None, state=None, offset=None, count=None):
  """Returns a list of requests matching the given arguments.

  Args:
    user: a requesting user.
    state: a request state value.
    offset: a start offset of requests to retrieve.
    count: max number of requests to retrieve.
  Returns:
    a list of Request objects.
  """
  query = datastore_entities.Request.query(namespace=common.NAMESPACE)
  if user:
    query = query.filter(datastore_entities.Request.user == user)
  if state is not None:
    query = query.filter(datastore_entities.Request.state == state)
  # Sort by create_time instead of id. Id is string, sort by id is incorrect.
  query = query.order(-datastore_entities.Request.create_time)
  if offset is not None and count is not None:
    return query.fetch(offset=offset, limit=count)
  else:
    return query.fetch(limit=common.DEFAULT_ROW_COUNT)


def SetTestEnvironment(request_id, test_env):
  """Sets a test environment for a request.

  Args:
    request_id: a request ID.
    test_env: a ndb_models.TestEnvironment object.
  """
  request_key = ndb.Key(
      datastore_entities.Request, request_id,
      namespace=common.NAMESPACE)
  test_env_to_put = datastore_entities.TestEnvironment.query(
      ancestor=request_key).get()
  if not test_env_to_put:
    test_env_to_put = datastore_entities.TestEnvironment(parent=request_key)
  test_env_to_put.populate(**test_env.to_dict())
  test_env_to_put.put()


def GetTestEnvironment(request_id):
  """Returns a test environment object for a request.

  Args:
    request_id: a request ID.
  Returns:
    a datastore_entities.TestEnvironment object.
  """
  request_key = ndb.Key(
      datastore_entities.Request, request_id,
      namespace=common.NAMESPACE)
  return datastore_entities.TestEnvironment.query(ancestor=request_key).get()


def AddTestResource(request_id, name, url):
  """Addes a test resource to a request.

  Args:
    request_id: a request ID.
    name: a resource name.
    url: a resource URL.
  """
  request_key = ndb.Key(datastore_entities.Request, request_id,
                        namespace=common.NAMESPACE)
  resource = datastore_entities.TestResource(
      parent=request_key, name=name, url=url)
  resource.put()


def GetTestResources(request_id):
  """Returns a list of test resources.

  Args:
    request_id: a request ID.
  Returns:
    a list of datastore_entities.TestResource objects.
  """
  request_key = ndb.Key(datastore_entities.Request, request_id,
                        namespace=common.NAMESPACE)
  query = datastore_entities.TestResource.query(ancestor=request_key)
  return list(query)
