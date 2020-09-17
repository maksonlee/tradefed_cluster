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

"""A module to handle command events."""

import collections
import datetime
import json
import logging
import zlib

import flask
import six

from tradefed_cluster import command_event
from tradefed_cluster import command_manager
from tradefed_cluster import common
from tradefed_cluster import metric
from tradefed_cluster.services import task_scheduler

COMMAND_EVENT_QUEUE = "command-event-queue"
COMMAND_EVENT_HANDLER_PATH = "/_ah/queue/%s" % COMMAND_EVENT_QUEUE

# We ignore command events that being retried for a long time.
COMMAND_EVENT_TIMEOUT_DAYS = 7

TIMING_DATA_FIELDS_TO_COMMAND_ACTIONS = {
    "fetch_build_time_millis": metric.CommandAction.INVOCATION_FETCH_BUILD,
    "setup_time_millis": metric.CommandAction.INVOCATION_SETUP
}

DEFAULT_TRUNCATE_LENGTH = 1024

APP = flask.Flask(__name__)


def _Truncate(s, length=DEFAULT_TRUNCATE_LENGTH):
  """Truncate a string if longer than a given length.

  Args:
    s: a string or an object
    length: a truncate start length.
  Returns:
    A truncated string.
  """
  if not isinstance(s, str):
    s = str(s)
  if length < len(s):
    s = s[:length] + "...(total %s chars)" % len(s)
  return s


def EnqueueCommandEvents(events):
  """Enqueue the command events to COMMAND_EVENT_QUEUE.

  Args:
    events: a list of command event dicts.
  """
  logging.info("Received %d command event(s).", len(events))
  event_map = collections.defaultdict(list)
  # Group events by task_ids.
  for e in events:
    if "task_id" not in e:
      logging.warning("Skipping malformed command_event:\n%s", e)
      continue
    event_map[e["task_id"]].append(e)
  # Sort by task_ids to make it easy to test.
  for key in sorted(event_map.keys()):
    payload = zlib.compress(six.ensure_binary(json.dumps(event_map[key])))
    task_scheduler.AddTask(queue_name=COMMAND_EVENT_QUEUE, payload=payload)


def LogCommandEventMetrics(command, event):
  """Log metrics related to command events.

  Args:
    command: a command_manager.Command
    event: a command event
  """
  command_event_metric_fields = {
      metric.METRIC_FIELD_HOSTNAME: event.hostname or "",
      metric.METRIC_FIELD_TYPE: event.type or ""
  }
  metric.command_event_type_count.Increment(command_event_metric_fields)
  if (event.type != common.InvocationEventType.INVOCATION_COMPLETED or
      not command):
    return
  if command.start_time:
    metric.RecordCommandTimingMetric(
        cluster_id=command.cluster,
        run_target=command.run_target,
        create_timestamp=command.start_time,
        hostname=event.hostname,
        command_action=metric.CommandAction.INVOCATION_COMPLETED)
  # Invocation timing is only reported on InvocationCompleted events
  try:
    for key in TIMING_DATA_FIELDS_TO_COMMAND_ACTIONS:
      if key not in event.data:
        continue
      latency_secs = float(event.data.get(key)) / 1000
      metric.RecordCommandTimingMetric(
          cluster_id=command.cluster,
          run_target=command.run_target,
          command_action=TIMING_DATA_FIELDS_TO_COMMAND_ACTIONS[key],
          hostname=event.hostname,
          latency_secs=latency_secs)
  except:      # Protecting against bad data
    logging.warning("Failed to report timing metrics.", exc_info=True)


@common.RetryNdbContentionErrors
def ProcessCommandEvent(event):
  """Processes a command event.

  Args:
    event: a CommandEvent object.
  """
  logging.debug("Processing command event: %s", str(event))
  command = command_manager.GetCommand(event.request_id, event.command_id)
  LogCommandEventMetrics(command=command, event=event)
  command_manager.ProcessCommandEvent(event)


# The below handler is served in frontend module.
@APP.route(COMMAND_EVENT_HANDLER_PATH, methods=["POST"])
def HandleCommandEvent():
  """Process a command event message in COMMAND_EVENT_QUEUE."""
  payload = flask.request.get_data()
  try:
    payload = zlib.decompress(payload)
  except zlib.error:
    logging.warning("payload may not be compressed: %s", payload, exc_info=True)
  objs = json.loads(payload)
  # To handle non-batched objects.
  if not isinstance(objs, list):
    objs = [objs]
  failed_objs = []
  exception = None
  for obj in objs:
    try:
      logging.info(_Truncate(obj))
      event = command_event.CommandEvent(**obj)
      if (event.time + datetime.timedelta(days=COMMAND_EVENT_TIMEOUT_DAYS) <
          _Now()):
        logging.warn("Ignore event retried for %d days:\n%s",
                     COMMAND_EVENT_TIMEOUT_DAYS, event)
        continue
      if event.attempt_state == common.CommandState.UNKNOWN:
        logging.warn("Ignore unknown state event:\n%s.", event)
        continue
      ProcessCommandEvent(event)
    except Exception as e:        exception = e
      logging.warn("Failed to process (%s, %s), will retry.",
                   event.task_id, event.type, exc_info=True)
      # failed events will be retried later.
      failed_objs.append(obj)
  if failed_objs:
    logging.warn("%d/%d command events failed to process.",
                 len(failed_objs), len(objs))
    if len(failed_objs) == len(objs) and exception:
      raise exception      EnqueueCommandEvents(failed_objs)
  return common.HTTP_OK


def _Now():
  """Get utc now."""
  return datetime.datetime.utcnow()
