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

"""A commander module to process requests and schedule commands."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import json
import logging
import zlib

import flask

from tradefed_cluster import command_manager
from tradefed_cluster import command_monitor
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config
from tradefed_cluster import metric
from tradefed_cluster import request_manager
from tradefed_cluster.util import command_util

REQUEST_HANDLER_PATH = "/_ah/queue/%s" % request_manager.REQUEST_QUEUE

# The max number of command shards per request.
# LINT.IfChange(max_shard_count)
DEFAULT_MAX_SHARDS = 20
RUN_TARGET_TO_MAX_SHARDS_MAP = {
    # Allow more shards for virtual device run targets.
    "RemoteAvdIDevice": 100,
    "TcpDevice": 100
}


APP = flask.Flask(__name__)


@common.RetryNdbContentionErrors
def _ProcessRequest(request_id):
  """Process a request and schedule corresponding commands.

  Args:
    request_id: request id, str
  """
  request_id = str(request_id)
  request = request_manager.GetRequest(request_id)
  if not request:
    logging.error("Request %d doesn't exist in ds.", request_id)
    return
  logging.debug("Processing request %s: %s",
                request_id, request)
  try:
    commands = _CreateCommands(request)
    if request.max_concurrent_tasks:
      # Only schedule (request.max_concurrent_tasks) commands.
      commands = commands[:request.max_concurrent_tasks]
    command_manager.ScheduleTasks(commands)
    command_monitor.Monitor(commands)
  except (AssertionError, ValueError) as e:
    logging.exception("Failed to process request %s", request_id)
    cancel_reason = None
    if isinstance(e, ValueError):
      cancel_reason = common.CancelReason.INVALID_REQUEST
    request_manager.CancelRequest(request_id, cancel_reason)
    command_manager.CancelCommands(request_id, cancel_reason)


def _CreateCommands(request):
  """Create a list of commands for a request."""
  expanded_command_infos = []
  shard_indexes = []
  for command_info in request.command_infos:
    if command_info.cluster is None:
      raise ValueError("cluster is not specified.")
    if not command_info.run_target:
      raise ValueError("run target is not defined.")
    # TODO: Check in db to see that it is a valid run target.
    if command_info.run_count < 1:
      raise ValueError("run count must be equal or greater than 1.")

    max_shards = RUN_TARGET_TO_MAX_SHARDS_MAP.get(
        command_info.run_target, DEFAULT_MAX_SHARDS)
    if not 0 < command_info.shard_count <= max_shards:
      raise ValueError("shard count %d is outside of range [1, %d]" %
                       (command_info.shard_count, max_shards))
    # TODO: Move validity check to request_manager.

    command_line = command_util.CommandLine(command_info.command_line)
    command_line.RemoveOptions([
        # TFC-specific options
        "--cluster",
        "--run-target",
        "--run-count",

        # TF conflicting options
        "--loop",             # causes TF to loop test runs continuously
        "--product-type",     # causes TF to fail device allocations
        "--test-iterations",  # specifies the number of iterations to run
    ])
    # Schedule commands and tag them with a run_target.
    # TF implicitly knows how to map a device to a run_target string. When
    # fetching commands, TF looks for only commands tagged with run_targets
    # which are available on itself.
    for shard_index in range(command_info.shard_count):
      # If the request is unmanaged, use command line to inject shard
      # parameters.
      if not request.type:
        # If local sharding was defined keep the original shard setup
        local_sharding = False
        if command_line.GetOption(
            "--shard-count") is not None and command_line.GetOption(
                "--shard-index") is None:
          local_sharding = True

        if not local_sharding:
          command_line.RemoveOptions(["--shard-count", "--shard-index"])
          if command_info.shard_count > 1:
            command_line.AddOption(
                "--shard-count", str(command_info.shard_count))
            command_line.AddOption("--shard-index", str(shard_index))
      expanded_command_infos.append(
          datastore_entities.CommandInfo(
              name=command_info.name,
              command_line=command_line.ToTFString(),
              cluster=command_info.cluster,
              run_target=command_info.run_target,
              run_count=command_info.run_count,
              shard_count=command_info.shard_count,
              allow_partial_device_match=(
                  command_info.allow_partial_device_match),
              test_bench=command_info.test_bench
              ))
      shard_indexes.append(shard_index)

  commands = command_manager.CreateCommands(
      request_id=request.key.id(),
      request_plugin_data=request.plugin_data,
      command_infos=expanded_command_infos,
      shard_indexes=shard_indexes,
      priority=request.priority,
      queue_timeout_seconds=request.queue_timeout_seconds,
      request_type=request.type)
  if request.prev_test_context:
    for command in commands:
      command_manager.UpdateTestContext(
          request_id=request.key.id(),
          command_id=command.key.id(),
          test_context=request.prev_test_context)
  return commands


@APP.route(REQUEST_HANDLER_PATH, methods=["POST"])
def HandleRequest():
  """Process a request message."""
  body = flask.request.get_data()
  try:
    body = zlib.decompress(body)
  except zlib.error:
    logging.warning(
        "payload may not be compressed: %s", body, exc_info=True)
  payload = json.loads(body)
  request_id = payload["id"]
  _ProcessRequest(request_id)
  return common.HTTP_OK


def ProcessCommandEvent(event):
  """Updates state of a command and coordinate command tasks.

  Args:
    event: a CommandEvent
  """
  command = command_manager.GetCommand(event.request_id, event.command_id)
  if not command:
    logging.warning(
        "unknown command %s %s; ignored", event.request_id, event.command_id)
    return

  is_updated = command_manager.UpdateCommandAttempt(event)

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
  command = command_manager.UpdateState(
      event.request_id,
      event.command_id,
      attempt_state=event.attempt_state,
      task_id=event.task_id)

  if common.IsFinalCommandState(command.state):
    # Deschedule command since the state indicates that it is not supposed
    # to run anymore.
    logging.debug("Command %r is finalized, delete all its tasks.",
                  command.key)
    command_manager.DeleteTasks(command)

  # Update AnTS.
  env_config.CONFIG.plugin.OnProcessCommandEvent(
      command_manager.GetCommand(event.request_id, event.command_id),
      command_manager.GetCommandAttempt(
          event.request_id, event.command_id, event.attempt_id),
      event_data=event.data)

  # Update request.
  request, request_summary = request_manager.EvaluateState(event.request_id)

  _CheckPendingCommands(request, request_summary)


def _CheckPendingCommands(request, request_summary):
  """Check pending commands and schedule if necessary."""
  if common.IsFinalRequestState(request.state):
    return
  if not request.max_concurrent_tasks:
    return
  if not request_summary or request_summary.pending_count <= 0:
    return
  logging.info(
      "Checking pending commands for request %s: max_concurrent_tasks=%d)",
      request.key.id(), request.max_concurrent_tasks)
  active_command_count = (
      request_summary.queued_count + request_summary.running_count)
  logging.info(
      "active_command_count = %d, pending_command_count = %d",

      active_command_count, request_summary.pending_count)
  next_command_count = min(
      request.max_concurrent_tasks - active_command_count,
      request_summary.pending_count)
  logging.info("next_command_count = %d", next_command_count)
  if 0 < next_command_count:
    logging.info("Scheduling %d next commands", next_command_count)
    next_commands = command_manager.GetCommands(
        request.key.id(), common.CommandState.UNKNOWN)[:next_command_count]
    command_manager.ScheduleTasks(next_commands)
    command_monitor.Monitor(next_commands)

