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

"""Tests for tradefed_cluster.report_api."""

import datetime
import unittest

import mock
from protorpc import protojson

from tradefed_cluster import api_test
from tradefed_cluster import datastore_entities
from tradefed_cluster import device_info_reporter
from tradefed_cluster import report_api

DATE_0 = datetime.date(2015, 11, 2)
UPDATE_TIME_0 = datetime.datetime(2015, 11, 2, 12)
DATE_1 = datetime.date(2015, 11, 3)
UPDATE_TIME_1 = datetime.datetime(2015, 11, 3, 13)
DATE_2 = datetime.date(2015, 11, 4)
UPDATE_TIME_2 = datetime.datetime(2015, 11, 4, 14)


def BuildSnapshotJobResult(date, timestamp):
  """Test helper to build snapshot results."""
  report_date = datetime.datetime.combine(date, datetime.time())
  return datastore_entities.SnapshotJobResult(
      report_date=report_date, timestamp=timestamp)


def BuildReportCount(count, total):
  """Test helper to build a ReportCount."""
  report_count = device_info_reporter.ReportCount()
  report_count.count = count
  report_count.total = total
  return report_count


class ReportApiTest(api_test.ApiTest):

  @mock.patch.object(device_info_reporter.DeviceReport, 'GetReportCounts')
  def testBuildRecordGroups(self, mock_count):
    # Test BuildRecordGroups()
    devices = [mock.MagicMock()]
    aggregation = 'cluster'
    states = ['Available', 'Allocated']
    mock_count.return_value = {
        'cluster0': BuildReportCount(10, 20),
        'cluster1': BuildReportCount(5, 10)
    }
    record_groups = report_api.BuildRecordGroups(
        devices=devices, aggregation=aggregation, states=states)
    self.assertEqual(2, len(record_groups))
    for r in record_groups:
      if r.groupByValue == 'cluster0':
        self.assertEqual(10, r.count)
        self.assertEqual(20, r.total)
      elif r.groupByValue == 'cluster1':
        self.assertEqual(5, r.count)
        self.assertEqual(10, r.total)
      else:
        self.fail()

  @mock.patch.object(report_api, 'BuildRecordGroups')
  @mock.patch.object(device_info_reporter, 'GetDeviceSnapshotForDate')
  def testBuildDailyRecord(self, mock_devices, mock_record_groups):
    # Test BuildDailyRecord()
    devices = [mock.MagicMock()]
    mock_devices.return_value = device_info_reporter.DeviceSnapshot(
        date=DATE_0, update_time=UPDATE_TIME_0, devices=devices)
    record_groups = [report_api.RecordGroup()]
    mock_record_groups.return_value = record_groups
    aggregation = 'cluster'
    states = ['Available', 'Allocated']
    daily_record = report_api.BuildDailyRecord(
        date=DATE_0, aggregation=aggregation, states=states, cluster_prefix='c')
    mock_devices.assert_called_once_with(date=DATE_0, cluster_prefix='c')
    mock_record_groups.assert_called_once_with(
        devices=devices, aggregation=aggregation, states=states)
    # Converting DATE_0 into datetime object
    record_date = datetime.datetime.combine(DATE_0, datetime.time())
    self.assertEqual(record_date, daily_record.date)
    self.assertEqual(record_groups, daily_record.recordGroups)
    self.assertEqual(UPDATE_TIME_0, daily_record.updateDate)

  @mock.patch.object(report_api, 'BuildRecordGroups')
  @mock.patch.object(device_info_reporter, 'GetDeviceSnapshotForDate')
  def testBuildDailyRecord_noSnapshot(self, mock_devices, mock_record_groups):
    # Test BuildDailyRecord() when there is no snapshot
    mock_devices.return_value = device_info_reporter.DeviceSnapshot(
        date=DATE_0, update_time=UPDATE_TIME_1, devices=[])
    record_groups = [report_api.RecordGroup()]
    mock_record_groups.return_value = record_groups
    aggregation = 'cluster'
    states = ['Available', 'Allocated']
    daily_record = report_api.BuildDailyRecord(
        date=DATE_0, aggregation=aggregation, states=states)
    mock_record_groups.assert_called_once_with(
        devices=[], aggregation=aggregation, states=states)
    # Converting DATE_0 into datetime object
    record_date = datetime.datetime.combine(DATE_0, datetime.time())
    self.assertEqual(record_date, daily_record.date)
    self.assertEqual(record_groups, daily_record.recordGroups)
    self.assertEqual(UPDATE_TIME_1, daily_record.updateDate)

  @mock.patch.object(report_api, 'BuildRecordGroups')
  @mock.patch.object(device_info_reporter, 'GetDeviceSnapshotForDate')
  def testBuildDailyRecord_noDate(self, mock_devices, mock_record_groups):
    # Test BuildDailyRecord() when no date is given
    devices = [mock.MagicMock()]
    mock_devices.return_value = device_info_reporter.DeviceSnapshot(
        date=DATE_1, update_time=UPDATE_TIME_1, devices=devices)
    record_groups = [report_api.RecordGroup()]
    mock_record_groups.return_value = record_groups
    aggregation = 'cluster'
    states = ['Available', 'Allocated']
    daily_record = report_api.BuildDailyRecord(
        date=None, aggregation=aggregation, states=states)
    mock_record_groups.assert_called_once_with(
        devices=devices, aggregation=aggregation, states=states)
    # Converting DATE_1 into datetime object
    record_date = datetime.datetime.combine(DATE_1, datetime.time())
    self.assertEqual(record_date, daily_record.date)
    self.assertEqual(record_groups, daily_record.recordGroups)
    self.assertEqual(UPDATE_TIME_1, daily_record.updateDate)

  @mock.patch.object(report_api, 'BuildRecordGroups')
  def testBuildReport(self, mock_record_groups):
    # Test BuildReport
    record_groups_0 = [report_api.RecordGroup(
        groupByField='field', groupByValue='a', count=1, total=2)]
    record_groups_1 = [report_api.RecordGroup(
        groupByField='field', groupByValue='b', count=3, total=3)]
    mock_record_groups.side_effect = [record_groups_0, record_groups_1]
    api_request = {
        'groupByKey': 'product_variant',
        'startDate': DATE_0.isoformat(),
        'endDate': DATE_1.isoformat(),
        'states': ['Available', 'Allocated'],
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ReportApi.BuildReport', api_request)
    self.assertEqual('200 OK', api_response.status)
    report = protojson.decode_message(report_api.Report, api_response.body)
    daily_records = report.dailyRecords
    self.assertEqual(2, len(daily_records))
    self.assertEqual(record_groups_0, daily_records[0].recordGroups)
    self.assertEqual(record_groups_1, daily_records[1].recordGroups)

  @mock.patch.object(report_api, 'BuildRecordGroups')
  def testBuildReport_noDates(self, mock_record_groups):
    # Test BuildReport with no given dates
    record_groups_0 = [report_api.RecordGroup(
        groupByField='field', groupByValue='a', count=1, total=2)]
    record_groups_1 = [report_api.RecordGroup(
        groupByField='field', groupByValue='b', count=3, total=3)]
    # Since no dates are provided, only record_groups_0 should be returned
    mock_record_groups.side_effect = [record_groups_0, record_groups_1]
    api_request = {
        'groupByKey': 'product',
        'states': ['Available', 'Allocated'],
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ReportApi.BuildReport', api_request)
    self.assertEqual('200 OK', api_response.status)
    report = protojson.decode_message(report_api.Report, api_response.body)
    daily_records = report.dailyRecords
    self.assertEqual(1, len(daily_records))
    self.assertEqual(record_groups_0, daily_records[0].recordGroups)

  def testBuildReport_invalidDateRange(self):
    # Test BuildReport where start date is after end date
    # Should return an empty report
    api_request = {
        'groupByKey': 'product_variant',
        'startDate': DATE_1.isoformat(),
        'endDate': DATE_0.isoformat(),
        'states': ['Available', 'Allocated'],
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ReportApi.BuildReport', api_request)
    self.assertEqual('200 OK', api_response.status)
    report = protojson.decode_message(report_api.Report, api_response.body)
    self.assertFalse(hasattr(report, 'daily_records'))

  def testBuildReport_invalidStates(self):
    # Test BuildReport without passing any state.
    api_request = {
        'groupByKey': 'product_variant',
        'startDate': DATE_0.isoformat(),
        'endDate': DATE_1.isoformat(),
    }
    api_response = self.testapp.post_json(
        '/_ah/api/ReportApi.BuildReport', api_request, expect_errors=True)
    self.assertEqual('400 Bad Request', api_response.status)


if __name__ == '__main__':
  unittest.main()
