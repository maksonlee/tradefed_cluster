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
import six

from tradefed_cluster import api_messages
from tradefed_cluster import command_error_type_config
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config
from tradefed_cluster.services import task_scheduler
from tradefed_cluster.util import ndb_shim as ndb

REQUEST_QUEUE = "test-request-queue"
SPONGE_URI_PATTERN = r".*(https?://(?:sponge|g3c).corp.example.com\S*).*"


class RequestSummary(object):
  """Request summary from request's commands."""

  def __init__(self):
    # set the default value to 0, so the value can be increment directly.
    self.pending_count = 0
    self.queued_count = 0
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
    (Request, RequestSummary)
  """
  request, request_summary = _UpdateState(request_id, force=force)
  NotifyRequestState(request_id)
  return request, request_summary


def CancelRequest(request_id, cancel_reason=None):
  """Cancel a request by its id.

  Args:
    request_id: request's id, str
    cancel_reason: a enum cancel reason.
  """
  # TODO: Request manager should cancel all commands.
  request = GetRequest(request_id)
  if request:
    _MarkRequestAsCanceled(request_id, cancel_reason)
    NotifyRequestState(request_id)
    DeleteFromQueue(request_id)


@ndb.transactional()
def _MarkRequestAsCanceled(request_id, cancel_reason):
  """Mark a request as canceled."""
  request = GetRequest(request_id)
  if common.IsFinalRequestState(request.state):
    logging.warning(
        "Cannot cancel request %s: already in a final state (%s)",
        request_id, common.RequestState(request.state).name)
    return
  request.state = common.RequestState.CANCELED
  request.cancel_reason = cancel_reason or common.CancelReason.UNKNOWN
  request.notify_state_change = True
  request.put()


@ndb.transactional()
def _UpdateState(request_id, force=False):
  """Attempts to update the state of a request.

  Attempts to update the state of a request based on the request's current
  state and the state of its child commands. Depending on those factors, the
  state may not change, or may even change to a state different from the
  input.
  This function should be used in another function in a transaction.

  Args:
    request_id: request id, str
    force: Whether to force an update regardless of the dirty bit.
  Returns:
    (Request, RequestSummary)
  """
  request = GetRequest(request_id)
  logging.info("Attempting to update request %s", request.key.id())
  if not (force or request.dirty):
    logging.info("Request %s doesn't need to be updated", request.key.id())
    return request, None
  summary = GetRequestSummary(request.key.id())

  # Evaluate the next state
  next_state = None
  # The logic current allows state transitions between the final states.
  # TODO: consider preventing state transitions between the final
  # states.
  finished_count = (
      summary.canceled_count +
      summary.completed_count +
      summary.error_count +
      summary.fatal_count)
  is_finished = summary.total_count and finished_count == summary.total_count
  if is_finished and summary.completed_count == summary.total_count:
    next_state = common.RequestState.COMPLETED
  elif is_finished and summary.error_count + summary.fatal_count > 0:
    next_state = common.RequestState.ERROR
  elif summary.canceled_count > 0:
    next_state = common.RequestState.CANCELED
    # propagate command's cancel_reason to request
    request.cancel_reason = summary.cancel_reason
  elif not common.IsFinalRequestState(request.state):
    if summary.running_count > 0:
      next_state = common.RequestState.RUNNING
    elif summary.queued_count > 0:
      next_state = common.RequestState.QUEUED
  if next_state and request.state != next_state:
    logging.info("Updating request %s from %s to %s",
                 request.key.id(),
                 common.RequestState(request.state).name,
                 common.RequestState(next_state).name)
    request.notify_state_change = True
    request.state = next_state

  request.start_time = summary.start_time
  if common.IsFinalRequestState(request.state):
    request.end_time = summary.end_time
  request.dirty = False
  request.put()
  return request, summary


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
  if not (force or request.notify_state_change):
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
  payload = zlib.compress(six.ensure_binary(protojson.encode_message(message)))  # pytype: disable=module-attr
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

      attempt = attempt.key.get(use_cache=False, use_memcache=False)
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
      elif (attempt.state == common.CommandState.CANCELED and
            attempt.state == command.state and attempt.error):
        # TF currently populates the error field on CANCELED attempts when
        # allocation fails. The error contains the whole command so it can be
        # very verbose, so we are surfacing only one of the attempt errors to
        # reduce noise.
        errors = [
            "Attempt %s: %s (CANCELED)" % (attempt.attempt_id, attempt.error)
        ]

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
    if command.state == common.CommandState.UNKNOWN:
      summary.pending_count += 1
    elif command.state == common.CommandState.QUEUED:
      summary.queued_count += 1
    elif command.state == common.CommandState.RUNNING:
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
                  command_infos,
                  priority=None,
                  queue_timeout_seconds=None,
                  type_=None,
                  request_id=None,
                  plugin_data=None,
                  max_retry_on_test_failures=None,
                  prev_test_context=None,
                  max_concurrent_tasks=None,
                  affinity_tag=None):
  """Create a new request and add it to the request_queue.

  Args:
    user: a requesting user.
    command_infos: a list of CommandInfo entities.
    priority: a request priority.
    queue_timeout_seconds: a request timeout in seconds.
    type_: a request type.
    request_id: request_id, used for easy testing.
    plugin_data: a map that contains the plugin data.
    max_retry_on_test_failures: the max number of completed but failed attempts
        for each command.
    prev_test_context: a previous test context.
    max_concurrent_tasks: the max number of concurrent tasks at any given time.
    affinity_tag: an affinity tag.
  Returns:
    a Request entity, read only.
  """
  if not request_id:
    request_id = _CreateRequestId()
  key = ndb.Key(
      datastore_entities.Request, request_id,
      namespace=common.NAMESPACE)
  request = datastore_entities.Request(
      key=key,
      user=user,
      command_infos=command_infos,
      priority=priority,
      queue_timeout_seconds=queue_timeout_seconds,
      type=type_,
      plugin_data=plugin_data,
      max_retry_on_test_failures=max_retry_on_test_failures,
      prev_test_context=prev_test_context,
      max_concurrent_tasks=max_concurrent_tasks,
      affinity_tag=affinity_tag,
      state=common.RequestState.UNKNOWN)
  request.put()
  return request


def _CreateRequestId():
  """Create a request id.

  This is to avoid conflict with the other TFC.

  Returns:
    request_id, str
  """
  while True:
    id_ = datastore_entities.Request.allocate_ids(1)[0].id()
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
  payload = json.dumps({"id": request.key.id()})
  compressed_payload = zlib.compress(six.ensure_binary(payload))
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
    test_env: a datastore_entities.TestEnvironment object.
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


def AddTestResource(request_id, test_resource):
  """Addes a test resource to a request.

  Args:
    request_id: a request ID.
    test_resource: a datastore_entities.TestResource object.
  """
  request_key = ndb.Key(datastore_entities.Request, request_id,
                        namespace=common.NAMESPACE)
  resource_to_put = datastore_entities.TestResource(parent=request_key)
  resource_to_put.CopyFrom(test_resource)
  resource_to_put.put()


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
