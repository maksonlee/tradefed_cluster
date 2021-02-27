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

"""Tests for device_info_reporter."""

import datetime
import gzip
import json
import os.path
import unittest

import mock
import six
import webtest

from tradefed_cluster import api_messages
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_test_util
from tradefed_cluster import device_info_reporter
from tradefed_cluster import env_config
from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.util import email_sender

DATE = datetime.date(2016, 7, 25)
TIMESTAMP = datetime.datetime(2016, 7, 26)
TEMPLATE_DIR, TEMPLATE_NAME = (
    os.path.split(env_config.CONFIG.device_report_template_path))


class DeviceInfoReporterTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    testbed_dependent_test.TestbedDependentTest.setUp(self)
    env_config.CONFIG.should_send_report = True
    self.reporter_webapp = webtest.TestApp(device_info_reporter.APP)
    self.ndb_host_1 = datastore_test_util.CreateHost(
        'free', 'atl-1001.mtv', timestamp=TIMESTAMP,
        extra_info={
            'gcertstatus':
                ('LOAS2 expires in 10h 14m\n'
                 'corp/normal expires in 10h 47m\n')
        })
    self.ndb_host_2 = datastore_test_util.CreateHost(
        'free', 'atl-1002.mtv', timestamp=TIMESTAMP,
        extra_info={
            'gcertstatus':
                ('LOAS2 expires in 1485h 14m\n'
                 'corp/normal expires in 18h 47m\n')
        })
    self.ndb_device = datastore_test_util.CreateDevice(
        'free', 'atl-1001.mtv', 'a100', product='shamu', run_target='shamu',
        state='Allocated', timestamp=TIMESTAMP, last_recovery_time=TIMESTAMP)
    self.ndb_device_2 = datastore_test_util.CreateDevice(
        'free', 'atl-1001.mtv', 'a200', product='flounder',
        run_target='flo', timestamp=TIMESTAMP, last_recovery_time=TIMESTAMP)

  @mock.patch.object(device_info_reporter, 'GetDevicesToReport')
  @mock.patch.object(device_info_reporter, '_GetCurrentDate', return_value=DATE)
  def testGet(self, mock_date, mock_devices):
    # Tests that the handler does the expected calls
    mock_devices.return_value = datastore_entities.DeviceInfo.query().fetch()
    response = self.reporter_webapp.get('/')
    self.assertEqual(200, response.status_int)
    mock_date.assert_called_once_with()
    mock_devices.assert_called_once_with()

  def testGetLoasSeconds_hoursAndMinutes(self):
    loas_status = (
        'LOAS2 expires in 1485h 14m\n'
        'corp/normal expires in 18h 47m\n')
    actual = device_info_reporter._GetLoasSeconds(loas_status)
    expected_seconds = 1485 * 60 * 60 + 14 * 60
    self.assertEqual(expected_seconds, actual)

  def testHostReport_offlineHosts(self):
    hosts = device_info_reporter.GetHostsToReport()
    report = device_info_reporter.HostReport(hosts=hosts)
    self.assertEqual(2, len(report.hosts))
    self.assertEqual(2, len(report.hosts_checkin))
    self.assertEqual(0, len(report.hosts_loas))

  @mock.patch.object(device_info_reporter, '_Now')
  def testHostReport_loas(self, now):
    now.return_value = TIMESTAMP
    hosts = device_info_reporter.GetHostsToReport()
    report = device_info_reporter.HostReport(hosts=hosts)
    self.assertEqual(2, len(report.hosts))
    self.assertEqual(0, len(report.hosts_checkin))
    self.assertEqual(1, len(report.hosts_loas))

  @mock.patch.object(device_info_reporter, '_Now')
  def testHostReport_withoutEventTimestamp(self, now):
    now.return_value = TIMESTAMP
    # Create host list without timestamp
    hosts = [
        datastore_test_util.CreateHost('free', 'atl-1001.mtv', timestamp=None)
    ]
    report = device_info_reporter.HostReport(hosts=hosts)
    self.assertEqual(1, len(report.hosts))
    self.assertEqual(1, len(report.hosts_checkin))
    self.assertEqual(0, len(report.hosts_loas))

  @mock.patch.object(device_info_reporter, '_Now')
  def testHostReport_noExtraInfo(self, now):
    now.return_value = TIMESTAMP
    ndb_host = datastore_test_util.CreateHost(
        'free', 'atl-1001.mtv', timestamp=TIMESTAMP)
    report = device_info_reporter.HostReport(hosts=[ndb_host])
    self.assertEqual(1, len(report.hosts))
    self.assertEqual(0, len(report.hosts_checkin))
    self.assertEqual(0, len(report.hosts_loas))

  def testGetDevicesToReport(self):
    # Test GetDevicesToReport()
    datastore_test_util.CreateDevice(
        'free', 'atl-1001.mtv', 'null-300', product='shamu',
        run_target='shamu', state='Allocated',
        device_type=api_messages.DeviceTypeMessage.NULL)
    devices = device_info_reporter.GetDevicesToReport()
    self.assertEqual(2, len(devices))
    for d in devices:
      self.assertEqual(d.physical_cluster, d.cluster)

  def testGetDevicesToReport_withCluster(self):
    # Test GetDevicesToReport() with cluster
    devices = device_info_reporter.GetDevicesToReport(cluster_prefix='fre')
    self.assertEqual(2, len(devices))
    devices = device_info_reporter.GetDevicesToReport(cluster_prefix='fro')
    self.assertEqual(0, len(devices))

  def testGetHostsToReport(self):
    # Test GetHostsToReport().
    hosts = device_info_reporter.GetHostsToReport()
    self.assertEqual(2, len(hosts))

  def testGetHostsToReport_withCluster(self):
    # Test GetHostsToReport() with cluster.
    hosts = device_info_reporter.GetHostsToReport(cluster_prefix='fre')
    self.assertEqual(2, len(hosts))
    hosts = device_info_reporter.GetHostsToReport(cluster_prefix='fro')
    self.assertEqual(0, len(hosts))

  @mock.patch.object(device_info_reporter, 'UploadDeviceSnapshotJobResult')
  def testStoreDeviceSnapshot(self, mock_job_result):
    # Test StoreDeviceSnapshot()
    devices = device_info_reporter.GetDevicesToReport()
    device_snapshot = device_info_reporter.DeviceSnapshot(
        date=DATE, update_time=TIMESTAMP, devices=devices)
    device_info_reporter.StoreDeviceSnapshot(device_snapshot)
    json_data = json.dumps(device_info_reporter._DevicesToDicts(devices))
    # Read back.
    with self.mock_file_storage.OpenFile(device_snapshot.filename) as f:
      gz = gzip.GzipFile(mode='r', fileobj=f)
      self.assertEqual(json_data, six.ensure_str(gz.read()))
    mock_job_result.assert_called_once_with(device_snapshot)

  def testGetDeviceSnapshotForDate(self):
    # Test GetDeviceSnapshotForDate()
    date_0 = datetime.date(2016, 7, 25)
    date_1 = datetime.date(2016, 7, 26)
    devices = device_info_reporter.GetDevicesToReport()
    device_snapshot_0 = device_info_reporter.DeviceSnapshot(
        date=date_0, update_time=TIMESTAMP, devices=devices)
    device_info_reporter.StoreDeviceSnapshot(device_snapshot_0)
    device_snapshot_1 = device_info_reporter.DeviceSnapshot(
        date=date_1, update_time=TIMESTAMP, devices=[])
    device_info_reporter.StoreDeviceSnapshot(device_snapshot_1)
    snapshot_20160725 = device_info_reporter.GetDeviceSnapshotForDate(date_0)
    self.assertEqual(2, len(snapshot_20160725.devices))
    self.assertEqual(date_0, snapshot_20160725.date)
    self.assertEqual(TIMESTAMP, snapshot_20160725.update_time)
    snapshot_20160726 = device_info_reporter.GetDeviceSnapshotForDate(date_1)
    self.assertEqual(0, len(snapshot_20160726.devices))
    self.assertEqual(date_1, snapshot_20160726.date)
    self.assertEqual(TIMESTAMP, snapshot_20160726.update_time)

  def testGetDeviceSnapshotForDate_withCluster(self):
    # Test GetDeviceSnapshotForDate() with date for a cluster
    date_0 = datetime.date(2016, 7, 25)
    devices = device_info_reporter.GetDevicesToReport()
    device_snapshot_0 = device_info_reporter.DeviceSnapshot(
        date=date_0, update_time=TIMESTAMP, devices=devices)
    device_info_reporter.StoreDeviceSnapshot(device_snapshot_0)
    snapshot_0 = device_info_reporter.GetDeviceSnapshotForDate(
        date=date_0, cluster_prefix='fre')
    self.assertEqual(2, len(snapshot_0.devices))
    self.assertEqual(date_0, snapshot_0.date)
    self.assertEqual(TIMESTAMP, snapshot_0.update_time)
    snapshot_1 = device_info_reporter.GetDeviceSnapshotForDate(
        date=date_0, cluster_prefix='fro')
    self.assertEqual(0, len(snapshot_1.devices))
    self.assertEqual(date_0, snapshot_1.date)
    self.assertEqual(TIMESTAMP, snapshot_1.update_time)

  def testGetDeviceSnapshotForDate_noDate(self):
    # Test GetDeviceSnapshotForDate() when date is None
    snapshot = device_info_reporter.GetDeviceSnapshotForDate()
    self.assertEqual(2, len(snapshot.devices))

  @mock.patch.object(device_info_reporter, 'GetDevicesToReport')
  def testGetDeviceSnapshotForDate_noDateWithCluster(self, mock_get):
    # Test GetDeviceSnapshotForDate() without date for a cluster
    devices = [mock.MagicMock()]
    mock_get.return_value = devices
    snapshot = device_info_reporter.GetDeviceSnapshotForDate(cluster_prefix='c')
    self.assertEqual(devices, snapshot.devices)
    mock_get.assert_called_once_with(cluster_prefix='c')

  def testUploadDeviceSnapshotJobResult(self):
    # Test UploadDeviceSnapshotJobResult()
    device_snapshot = device_info_reporter.DeviceSnapshot(
        date=DATE, update_time=TIMESTAMP, devices=[])
    job_result = device_info_reporter.UploadDeviceSnapshotJobResult(
        device_snapshot=device_snapshot)
    self.assertEqual(DATE, job_result.report_date.date())
    self.assertEqual(TIMESTAMP, job_result.timestamp)
    self.assertEqual(device_snapshot.filename, job_result.filename)

  def testDeviceReport(self):
    # Test DeviceReport class
    devices = device_info_reporter.GetDevicesToReport()
    report = device_info_reporter.DeviceReport(
        devices=devices, aggregation='product', states=['Allocated'])
    counts = report.GetReportCounts()
    self.assertEqual(1, counts['shamu'].total)
    self.assertEqual(1, counts['shamu'].count)
    self.assertEqual(1, counts['flounder'].total)
    self.assertEqual(0, counts['flounder'].count)

  def testReportCount(self):
    # Test ReportCount class
    target = device_info_reporter.ReportCount()
    target.count = 1
    target.total = 10
    self.assertEqual(0.1, target.rate)

  def testBuildReportEmailSubject(self):
    # Test _BuildReportEmailSubject()
    timestamp = datetime.datetime(2016, 8, 30, 6, 20, 30)
    subject = device_info_reporter._BuildReportEmailSubject('foobar', timestamp)
    self.assertEqual(
        '[TFC] Automated Device Report (foobar) - 2016-08-30 06:20', subject)

  def testFilterDevices(self):
    # Test FilterDevices()
    datastore_test_util.CreateDevice(
        'foobar',
        'atl-1003.mtv',
        'a300',
        product='walleye',
        run_target='walleye',
        timestamp=TIMESTAMP)
    devices = device_info_reporter.GetDevicesToReport()
    free_devices = device_info_reporter.FilterDevices(devices, 'free')
    self.assertEqual(2, len(free_devices))
    self.assertEqual('free', free_devices[0].physical_cluster)
    self.assertEqual('shamu', free_devices[0].product)
    self.assertEqual('free', free_devices[1].physical_cluster)
    self.assertEqual('flounder', free_devices[1].product)
    foo_devices = device_info_reporter.FilterDevices(devices, 'foo')
    self.assertEqual(1, len(foo_devices))
    self.assertEqual('foobar', foo_devices[0].physical_cluster)
    self.assertEqual('walleye', foo_devices[0].product)

  @mock.patch.object(env_config.CONFIG, 'should_send_report', True)
  @mock.patch.object(email_sender, 'SendEmail')
  @mock.patch.object(email_sender, 'Render')
  @mock.patch.object(device_info_reporter, '_BuildReportEmailSubject')
  def testEmailDeviceReport(self, mock_subject, mock_render, mock_send):
    # Test EmailDeviceReport()
    product_report = mock.MagicMock()
    cluster_report = mock.MagicMock()
    host_report = mock.MagicMock()
    timestamp = mock.MagicMock()
    rendered = mock.MagicMock()
    mock_subject.return_value = 'subject'
    mock_render.return_value = rendered
    report_config = datastore_entities.ReportEmailConfig(
        cluster_prefix='foobar', recipients=['nobody@example.com'])
    device_info_reporter.EmailDeviceReport(
        report_config=report_config,
        product_report=product_report,
        cluster_report=cluster_report,
        host_report=host_report,
        timestamp=timestamp)
    mock_subject.assert_called_once_with('foobar', timestamp)
    mock_render.assert_called_once_with(
        template_dir=TEMPLATE_DIR,
        template_name=TEMPLATE_NAME,
        cluster_prefix='foobar',
        product_report=product_report,
        cluster_report=cluster_report,
        host_report=host_report,
        timestamp=timestamp)
    mock_send.assert_called_once_with(
        sender=device_info_reporter.DEFAULT_SENDER,
        recipient='nobody@example.com',
        subject='subject',
        html_body=rendered,
        reply_to=device_info_reporter.DEFAULT_REPLY_TO)

  @mock.patch.object(env_config.CONFIG, 'should_send_report', True)
  @mock.patch.object(email_sender, 'SendEmail')
  @mock.patch.object(email_sender, 'Render')
  @mock.patch.object(device_info_reporter, '_BuildReportEmailSubject')
  def testEmailDeviceReportWithNoRecipients(self, mock_subject,
                                            mock_render, mock_send):
    # Test EmailDeviceReport()
    product_report = mock.MagicMock()
    cluster_report = mock.MagicMock()
    host_report = mock.MagicMock()
    timestamp = mock.MagicMock()
    rendered = mock.MagicMock()
    mock_subject.return_value = 'subject'
    mock_render.return_value = rendered
    report_config = datastore_entities.ReportEmailConfig(
        cluster_prefix='foobar', recipients=[])
    device_info_reporter.EmailDeviceReport(
        report_config=report_config,
        product_report=product_report,
        cluster_report=cluster_report,
        host_report=host_report,
        timestamp=timestamp)
    mock_subject.assert_called_once_with('foobar', timestamp)
    mock_render.assert_called_once_with(
        template_dir=TEMPLATE_DIR,
        template_name=TEMPLATE_NAME,
        cluster_prefix='foobar',
        product_report=product_report,
        cluster_report=cluster_report,
        host_report=host_report,
        timestamp=timestamp)
    mock_send.assert_not_called()

if __name__ == '__main__':
  unittest.main()
