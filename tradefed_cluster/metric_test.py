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

"""Tests for google3.wireless.android.test_tools.tradefed_cluster.metric."""

import datetime
import unittest

import mock
import pytz

from tradefed_cluster import metric

TIMESTAMP_NAIVE = datetime.datetime(2017, 10, 11)
TIMESTAMP_AWARE = pytz.utc.localize(datetime.datetime(2017, 10, 10, 21))
UTC_NOW = datetime.datetime(2017, 10, 11, 1)


class MetricTest(unittest.TestCase):

  @mock.patch('__main__.metric.datetime')
  @mock.patch.object(metric.command_timing, 'Record', autospec=True)
  def testRecordCommandTimingMetric_naiveDatetime(self, record, mock_datetime):
    mock_datetime.datetime.utcnow.return_value = UTC_NOW
    metric.RecordCommandTimingMetric(
        cluster_id='cluster',
        run_target='target',
        create_timestamp=TIMESTAMP_NAIVE,
        command_action=metric.CommandAction.LEASE)
    expected_latency = 60 * 60  # 1 hour in seconds
    expected_metric_fields = {
        metric.METRIC_FIELD_CLUSTER: 'cluster',
        metric.METRIC_FIELD_RUN_TARGET: 'target',
        metric.METRIC_FIELD_ACTION: 'LEASE',
    }
    record.assert_called_once_with(expected_latency, expected_metric_fields)

  @mock.patch('__main__.metric.datetime')
  @mock.patch.object(metric.command_timing, 'Record', autospec=True)
  def testRecordCommandTimingMetric_awareDatetime(self, record, mock_datetime):
    mock_datetime.datetime.utcnow.return_value = UTC_NOW
    metric.RecordCommandTimingMetric(
        cluster_id='cluster',
        run_target='target',
        create_timestamp=TIMESTAMP_AWARE,
        command_action=metric.CommandAction.RESCHEDULE)
    expected_latency = 4 * 60 * 60  # 4 hours in seconds
    expected_metric_fields = {
        metric.METRIC_FIELD_CLUSTER: 'cluster',
        metric.METRIC_FIELD_RUN_TARGET: 'target',
        metric.METRIC_FIELD_ACTION: 'RESCHEDULE',
    }
    record.assert_called_once_with(expected_latency, expected_metric_fields)

  @mock.patch.object(metric.command_action_count, 'Increment', autospec=True)
  @mock.patch.object(metric.command_timing, 'Record', autospec=True)
  def testRecordCommandTimingMetric_givenLatency(self, record, increment):
    metric.RecordCommandTimingMetric(
        cluster_id='cluster',
        run_target='target',
        command_action=metric.CommandAction.INVOCATION_FETCH_BUILD,
        latency_secs=100)
    expected_metric_fields = {
        metric.METRIC_FIELD_CLUSTER: 'cluster',
        metric.METRIC_FIELD_RUN_TARGET: 'target',
        metric.METRIC_FIELD_ACTION: 'INVOCATION_FETCH_BUILD',
    }
    record.assert_called_once_with(100, expected_metric_fields)
    increment.assert_not_called()

  @mock.patch.object(metric.command_action_count, 'Increment', autospec=True)
  @mock.patch.object(metric.command_timing, 'Record', autospec=True)
  def testRecordCommandTimingMetric_withCount(self, record, increment):
    metric.RecordCommandTimingMetric(
        cluster_id='cluster',
        run_target='target',
        command_action=metric.CommandAction.INVOCATION_FETCH_BUILD,
        latency_secs=100,
        count=True)
    expected_metric_fields = {
        metric.METRIC_FIELD_CLUSTER: 'cluster',
        metric.METRIC_FIELD_RUN_TARGET: 'target',
        metric.METRIC_FIELD_ACTION: 'INVOCATION_FETCH_BUILD',
    }
    record.assert_called_once_with(100, expected_metric_fields)
    increment.assert_called_once_with(expected_metric_fields)


if __name__ == '__main__':
  unittest.main()
