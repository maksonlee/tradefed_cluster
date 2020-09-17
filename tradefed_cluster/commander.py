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
from six.moves import range

from tradefed_cluster import command_manager
from tradefed_cluster import command_monitor
from tradefed_cluster import common
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
    command_manager.ScheduleTasks(commands)
    command_monitor.Monitor(commands)
  except ValueError:
    logging.exception("Invalid request %s", request_id)
    request_manager.CancelRequest(
        request_id, common.CancelReason.INVALID_REQUEST)


def _CreateCommands(request):
  """Create a list of commands for a request."""
  if request.cluster is None:
    raise ValueError("cluster is not specified.")
  if not request.run_target:
    raise ValueError("run target is not defined.")
  # TODO: Check in db to see that it is a valid run target.
  if request.run_count < 1:
    raise ValueError("run count must be equal or greater than 1.")

  max_shards = RUN_TARGET_TO_MAX_SHARDS_MAP.get(
      request.run_target, DEFAULT_MAX_SHARDS)
  if not 0 < request.shard_count <= max_shards:
    raise ValueError("shard count %d is outside of range [1, %d]" %
                     (request.shard_count, max_shards))
  # TODO: Move validity check to request_manager.

  command_line = command_util.CommandLine(request.command_line)
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
  command_lines = []
  shard_indexes = list(range(request.shard_count))
  for shard_index in shard_indexes:
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
        if request.shard_count > 1:
          command_line.AddOption("--shard-count", str(request.shard_count))
          command_line.AddOption("--shard-index", str(shard_index))
    command_lines.append(command_line.ToTFString())

  commands = command_manager.CreateCommands(
      request_id=request.key.id(),
      request_plugin_data=request.plugin_data,
      command_lines=command_lines,
      shard_count=request.shard_count,
      shard_indexes=shard_indexes,
      run_target=request.run_target,
      run_count=request.run_count,
      cluster=request.cluster,
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
    logging.warn(
        "payload may not be compressed: %s", body, exc_info=True)
  payload = json.loads(body)
  request_id = payload["id"]
  _ProcessRequest(request_id)
  return common.HTTP_OK
