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

"""A module for streamz metric objects shared across the application."""

import datetime
import enum
import logging

import pytz

from tradefed_cluster import env_config
from tradefed_cluster.util import metric_util


METRIC_FIELD_CLUSTER = 'cluster'
METRIC_FIELD_HOSTNAME = 'hostname'
METRIC_FIELD_TEST_RUNNER = 'test_runner'
METRIC_FIELD_TYPE = 'type'
METRIC_FIELD_RUN_TARGET = 'run_target'
METRIC_FIELD_ACTION = 'action'
METRIC_FIELD_QUEUE = 'queue'
METRIC_FIELD_STATE = 'state'


def _Metric(name, descriptor):
  """A helper factory for Metric.

  Args:
    name: a metric name.
    descriptor: a metric_client.MetricDescriptor object.
  Returns:
    a metric_client.Metric object.
  """
  return metric_util.Metric(
      name, descriptor=descriptor, client=env_config.CONFIG.metric_client)


QUEUE_METRIC_FIELDS = [
    (METRIC_FIELD_QUEUE, str),
]

# A metric object for the number of tasks remaining in a queue.
queue_size = _Metric(
    'queue/size',
    metric_util.MetricDescriptor(
        type_=metric_util.MetricType.VALUE,
        value_type=int,
        desc='Number of tasks remaining in the queue',
        fields=QUEUE_METRIC_FIELDS))

# A metric object for the number of tasks leased in the last minute.
queue_leased = _Metric(
    'queue/leased',
    metric_util.MetricDescriptor(
        type_=metric_util.MetricType.VALUE,
        value_type=int,
        desc='Number of tasks leased in the last minute',
        fields=QUEUE_METRIC_FIELDS))

# A metric object for the delta from now to the oldest ETA.
queue_eta = _Metric(
    'queue/eta',
    metric_util.MetricDescriptor(
        type_=metric_util.MetricType.VALUE,
        value_type=int,
        desc='Seconds from now to the oldest ETA',
        fields=QUEUE_METRIC_FIELDS,
        units=metric_util.Units.SECONDS))

COMMAND_EVENT_METRIC_FIELDS = [
    (METRIC_FIELD_HOSTNAME, str),
    (METRIC_FIELD_TYPE, str),
]

# A metric object to count number of command events for a type.
command_event_type_count = _Metric(
    'command_event/type',
    metric_util.MetricDescriptor(
        type_=metric_util.MetricType.COUNTER,
        desc='Number of command events of this type',
        fields=COMMAND_EVENT_METRIC_FIELDS))

# A metric object to count number of command events using legacy pipeline
command_event_legacy_processing_count = _Metric(
    'command_event/legacy_processing_count',
    metric_util.MetricDescriptor(
        type_=metric_util.MetricType.COUNTER,
        desc='Command event legacy processing counts'))

COMMAND_ATTEMPT_METRIC_FIELDS = [
    (METRIC_FIELD_CLUSTER, str),
    (METRIC_FIELD_RUN_TARGET, str),
    (METRIC_FIELD_HOSTNAME, str),
    (METRIC_FIELD_STATE, str),
]

# A metric object to count command attempts.
command_attempt_count = _Metric(
    'command_attempt/count',
    metric_util.MetricDescriptor(
        type_=metric_util.MetricType.COUNTER,
        desc='Command attempt counts',
        fields=COMMAND_ATTEMPT_METRIC_FIELDS))


def RecordCommandAttemptMetric(cluster_id, run_target, hostname, state):
  """Record timing metrics on command attempts.

  Args:
    cluster_id: Cluster ID of the command leased
    run_target: Run target of the command leased
    hostname: Hostname that leased the command
    state: State of the command attempt
  """
  metric_fields = {
      METRIC_FIELD_CLUSTER: cluster_id,
      METRIC_FIELD_RUN_TARGET: run_target,
      METRIC_FIELD_HOSTNAME: hostname,
      METRIC_FIELD_STATE: state
  }
  command_attempt_count.Increment(metric_fields)


COMMAND_METRIC_FIELDS = [
    (METRIC_FIELD_CLUSTER, str),
    (METRIC_FIELD_RUN_TARGET, str),
    (METRIC_FIELD_ACTION, str),
    (METRIC_FIELD_HOSTNAME, str),
]


class CommandAction(enum.Enum):
  """Applicable actions for command metrics."""

  LEASE = 1  # Latency to lease a command
  RESCHEDULE = 2  # Latency to reschedule a command
  CANCEL = 3  # Latency to cancel a command
  INVOCATION_FETCH_BUILD = 4  # Time taken to fetch build
  INVOCATION_SETUP = 5  # Time taken to setup the test (preparers)
  ENSURE_LEASABLE = 6  # Latency to ensure that a command is leasable
  INVOCATION_COMPLETED = 7  # Time taken for an invocation to complete

# A metric object to measure command timing breakdown.
command_timing = _Metric(
    'command/timing',
    metric_util.MetricDescriptor(
        type_=metric_util.MetricType.EVENT,
        desc='Command timing breakdown',
        fields=COMMAND_METRIC_FIELDS,
        units=metric_util.Units.SECONDS))

# A metric object to count command actions.
command_action_count = _Metric(
    'command/action_count',
    metric_util.MetricDescriptor(
        type_=metric_util.MetricType.COUNTER,
        desc='Command action counts',
        fields=COMMAND_METRIC_FIELDS))


def RecordCommandTimingMetric(cluster_id,
                              run_target,
                              command_action,
                              hostname=None,
                              latency_secs=None,
                              create_timestamp=None,
                              count=False):
  """Record timing metrics on command tasks.

  Either latency_secs or create_timestamp must be specified.

  Args:
    cluster_id: Cluster ID of the command leased
    run_target: Run target of the command leased
    command_action: CommandAction to log
    hostname: Hostname that leased the command
    latency_secs: Latency of the action in seconds
    create_timestamp: Task creation timestamp
    count: Increments the counter metric
  """
  metric_fields = {
      METRIC_FIELD_CLUSTER: cluster_id,
      METRIC_FIELD_RUN_TARGET: run_target,
      METRIC_FIELD_HOSTNAME: hostname,
      METRIC_FIELD_ACTION: command_action.name
  }

  if latency_secs is None:
    if (create_timestamp.tzinfo is not None and
        create_timestamp.tzinfo.utcoffset(create_timestamp) is not None):
      # create_timestamp is an aware datetime. Making it naive.
      create_timestamp = create_timestamp.astimezone(pytz.utc)
      create_timestamp = create_timestamp.replace(tzinfo=None)
    latency_secs = (
        datetime.datetime.utcnow() - create_timestamp).total_seconds()
  logging.debug(
      '%s command for cluster %s and run target %s took %s seconds',
      command_action.name, cluster_id, run_target, latency_secs)
  command_timing.Record(latency_secs, metric_fields)
  if count:
    command_action_count.Increment(metric_fields)


_TEST_RUNNER_METRIC_FIELDS = [
    (METRIC_FIELD_CLUSTER, str),
    (METRIC_FIELD_HOSTNAME, str),
    (METRIC_FIELD_TEST_RUNNER, str),
]

_test_runner_version_metric = _Metric(
    'host/test_runner_version',
    metric_util.MetricDescriptor(
        type_=metric_util.MetricType.VALUE,
        value_type=str,
        desc="Host's test runner version.",
        fields=_TEST_RUNNER_METRIC_FIELDS))


def SetHostTestRunnerVersion(
    runner, runner_version, cluster, hostname):
  """Set tf version for host.

  Args:
    runner: test runner on the host
    runner_version: test runner version
    cluster: cluster name
    hostname: hostname
  """
  _test_runner_version_metric.Set(
      runner_version,
      {METRIC_FIELD_CLUSTER: cluster,
       METRIC_FIELD_HOSTNAME: hostname,
       METRIC_FIELD_TEST_RUNNER: runner})
