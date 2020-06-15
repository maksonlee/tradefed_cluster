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

"""Runs through cron, dumps device information into cloud storage."""
# This import makes division operators consistent. That is, all divisions
# regardless of operand types (long, int, float) will return a float (PEP-238).
from __future__ import division
import collections
import datetime
import gzip
import json
import logging
import os.path
import re

import cloudstorage
import dateutil.parser
import webapp2

from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config
from tradefed_cluster.util import email_sender

# Note: Email configurations are now moved to NDB. For future
# changes refer to the datastore.

PRODUCT_AGGREGATION = 'product'
CLUSTER_AGGREGATION = 'cluster'
DEVICE_OFFLINE_STATES = [
    'Fastboot', 'Gone', 'Ignored', 'Unavailable', 'Unknown']
DEVICE_REPORT_TEMPLATE = 'device_report_template.html'
DEFAULT_SENDER = 'Tradefed Cluster <noreply@example.com>'
DEFAULT_REPLY_TO = 'android-test-infra@example.com'
REPORT_SUBJECT = '[TFC] Automated Device Report (%s) - %s'

# Regex for LOAS status
LOAS_REGEX = (r'LOAS2? cert expires in \d+h \d+m',
              r'LOAS2? cert expires in \d+m \d+s',
              r'LOAS2? cert expires in about \d+ days')
COMBINED_LOAS_REGEX = '(' + ')|('.join(LOAS_REGEX) + ')'
# Regex for time values
DAYS_REGEX = r'(\d+) days|(\d+)d'
HOURS_REGEX = r'(\d+)h'
MINUTES_REGEX = r'(\d+)m'

MINUTES_TO_SECONDS = 60
HOURS_TO_SECONDS = 60 * 60
DAYS_TO_SECONDS = 24 * 60 * 60
WEEK_TO_SECONDS = 7 * DAYS_TO_SECONDS


class DeviceSnapshot(object):
  """A class to represent a snapshot of devices."""

  def __init__(self, date, update_time, devices):
    self.date = date
    self.update_time = update_time
    self.devices = devices

  @property
  def filename(self):
    """Builds a device snapshot filename."""
    return (env_config.CONFIG.device_info_snapshot_file_format %
            str(self.date))


class ReportCount(object):
  """A class encapsulating a device report count."""

  def __init__(self):
    self.total = 0
    self.count = 0

  @property
  def rate(self):
    if self.total:
      return self.count / self.total
    return 0


def _GetSeconds(status):
  """Get the number of expiration seconds left out of a host status string."""
  days_match = re.search(DAYS_REGEX, status)
  days = int(days_match.group(1) or days_match.group(2)) if days_match else 0
  hours_match = re.search(HOURS_REGEX, status)
  hours = int(hours_match.group(1)) if hours_match else 0
  minutes_match = re.search(MINUTES_REGEX, status)
  minutes = int(minutes_match.group(1)) if minutes_match else 0
  return (days * DAYS_TO_SECONDS + hours * HOURS_TO_SECONDS +
          minutes * MINUTES_TO_SECONDS)


def _GetLoasSeconds(loas_status):
  """Get the LOAS seconds left to expiration."""
  if not re.search(COMBINED_LOAS_REGEX, loas_status):
    return 0
  return _GetSeconds(loas_status)


class HostReport(object):
  """A class to represent a report of hosts."""

  def __init__(self, hosts):
    self.hosts = hosts
    # Hosts with late last check-in
    self.hosts_checkin = []
    # Hosts with expiring or expired LOAS
    self.hosts_loas = []
    self._ClassifyHosts()

  def _ClassifyHosts(self):
    """Classify hosts into categories based on their last checkin and status."""
    logging.info('Classifying hosts')
    one_hour_ago = _Now() - datetime.timedelta(hours=1)
    for host in self.hosts:
      host.extra_info = host.extra_info or {}
      loas_info = host.extra_info.get('prodcertstatus', '')
      if host.timestamp < one_hour_ago:
        self.hosts_checkin.append(host)
      elif _GetLoasSeconds(loas_info) <= WEEK_TO_SECONDS:
        self.hosts_loas.append(host)
    logging.info('Offline hosts %d', len(self.hosts_checkin))
    logging.info('Hosts needing LOAS renewal %d', len(self.hosts_checkin))


class DeviceReport(object):
  """A class to represent a report of devices."""

  def __init__(self, devices, aggregation, states):
    self.devices = devices
    self.aggregation = aggregation
    self.states = states
    self.state_count_map = collections.defaultdict(int)
    self.state_total = 0  # total devices on the given states
    self.total = 0  # total devices checked
    self.count_map = collections.defaultdict(ReportCount)
    self._CalculateCounts()

  def _CalculateCounts(self):
    """Calculate the device counts for an aggregation and states."""
    logging.info(
        'Calculating report records for aggregation [%s] on states [%s]',
        self.aggregation, self.states)
    for state in self.states:
      # initialize the state counts for the given states
      self.state_count_map[state] = 0
    for device in self.devices:
      self.total += 1
      self.count_map[getattr(device, self.aggregation, 'unknown')].total += 1
      if device.state in self.states:
        self.count_map[getattr(device, self.aggregation, 'unknown')].count += 1
        self.state_count_map[device.state] += 1
        self.state_total += 1

  @property
  def rate(self):
    if self.total:
      return self.state_total / self.total
    return 0

  def GetReportCounts(self):
    """Returns a dictionary mapping an aggregation to its device count."""
    return self.count_map


def _GetNextString(s):
  """Get smallest string that larger than all strings prefix with s."""
  return s[:-1] + chr(ord(s[-1]) + 1)


def GetHostsToReport(cluster_prefix=None):
  """Get all the hosts that are applicable for a report from NDB.

  Args:
    cluster_prefix: Cluster prefix to filter by
  Returns:
    A list of hosts.
  """
  query = (datastore_entities.HostInfo.query()
           .filter(
               datastore_entities.HostInfo.hidden == False))    if cluster_prefix:
    query = query.filter(
        datastore_entities.HostInfo.physical_cluster >= cluster_prefix).filter(
            datastore_entities.HostInfo.physical_cluster <
            _GetNextString(cluster_prefix))
  return query.fetch()


def GetDevicesToReport(cluster_prefix=None):
  """Get all the devices that are applicable for a report from NDB.

  Args:
    cluster_prefix: Cluster prefix to filter by
  Returns:
    A list of physical devices.
  """
  query = (datastore_entities.DeviceInfo.query()
           .filter(datastore_entities.DeviceInfo.hidden == False)             .filter(datastore_entities.DeviceInfo.device_type ==
                   api_messages.DeviceTypeMessage.PHYSICAL))
  if cluster_prefix:
    query = (
        query.filter(
            datastore_entities.DeviceInfo.physical_cluster >= cluster_prefix)
        .filter(datastore_entities.DeviceInfo.physical_cluster <
                _GetNextString(cluster_prefix)))
  devices = []
  for d in query.iter():
    d.cluster = d.physical_cluster
    devices.append(d)
  return devices


def _DevicesToDicts(devices):
  """Transform a list of devices to a list of dict."""
  if not devices:
    return []
  dicts = []
  for device in devices:
    if isinstance(device, datastore_entities.DeviceInfo):
      d = device.to_dict()
      timestamp = d.get('timestamp')
      if timestamp:
        d['timestamp'] = timestamp.isoformat()
      device_type = d.get('device_type')
      if device_type is not None:
        d['device_type'] = int(device_type)
      if 'history' in d:
        del d['history']
      d['cluster'] = d.get('physical_cluster')
      dicts.append(d)
    else:
      dicts.append(device.ToDict())
  return dicts


def _Now():
  """Returns the current time in UTC."""
  return datetime.datetime.utcnow()


def _LocalizedNow():
  """Returns the current time in the default timezone."""
  return datetime.datetime.now(common.DEFAULT_TZ)


def _GetCurrentDate():
  """Return current date in the default timezone with no time component."""
  return _LocalizedNow().date()


def UploadDeviceSnapshotJobResult(device_snapshot):
  """Create a SnapshotJobResult entity to persist in Datastore.

  Args:
    device_snapshot: a DeviceSnapshot object to upload a job result
  Returns:
    The SnapshotJobResult model created
  """
  timestamp = device_snapshot.update_time
  logging.info(
      'Uploading job result for date [%s], file [%s] with time [%s]',
      device_snapshot.date, device_snapshot.filename, timestamp)
  job_result = datastore_entities.SnapshotJobResult.GetByReportDate(
      device_snapshot.date)
  if not job_result:
    job_result = datastore_entities.SnapshotJobResult.FromDate(
        device_snapshot.date)
  job_result.filename = device_snapshot.filename
  job_result.timestamp = timestamp
  job_result.put()
  return job_result


def StoreDeviceSnapshot(device_snapshot):
  """Store a snapshot of devices as a gzip file in cloud storage.

  Args:
    device_snapshot: a DeviceSnapshot object to store
  """
  logging.info('Storing snapshot with filename [%s]', device_snapshot.filename)
  json_data = json.dumps(_DevicesToDicts(device_snapshot.devices))
  with cloudstorage.open(
      device_snapshot.filename, 'w', 'text/plain',
      {'content-encoding': 'gzip'}) as f:
    gz = gzip.GzipFile(mode='w', fileobj=f)
    gz.write(json_data)
    gz.close()
  # Upload the result
  UploadDeviceSnapshotJobResult(device_snapshot)


def GetDeviceSnapshotForDate(date=None, cluster_prefix=None):
  """Retrieves a snapshot for a date and builds the device infos for it.

  Args:
    date: date to retrieve devices from
    cluster_prefix: Cluster prefix to filter the devices
  Returns:
    A DeviceSnapshot object for the requested date.
  """
  if not date:
    logging.info('Getting devices in their current state.')
    devices = GetDevicesToReport(cluster_prefix=cluster_prefix)
    return DeviceSnapshot(
        date=_GetCurrentDate(),
        update_time=_Now(),
        devices=devices)

  logging.info('Getting devices from date [%s]', date)
  job_result = datastore_entities.SnapshotJobResult.GetByReportDate(date)
  if not job_result or not job_result.filename:
    logging.warn('No record of snapshot found for date [%s]', date)
    return DeviceSnapshot(date=date, update_time=_Now(), devices=[])
  filename = job_result.filename
  # If we have a job result, the file should be in cloud storage
  with cloudstorage.open(filename) as f:
    gz = gzip.GzipFile(mode='r', fileobj=f)
    json_data = gz.read()
  device_dicts = json.loads(json_data)
  devices = []

  for d in device_dicts:
    # flated_extre_info is computed property, can not be assigned.
    del d['flated_extre_info']
    if (cluster_prefix and d.get('cluster')
        and not d.get('cluster').startswith(cluster_prefix)):
      # Ignore devices outside the given cluster
      continue
    d['timestamp'] = dateutil.parser.parse(d['timestamp'])
    d['device_type'] = api_messages.DeviceTypeMessage(d['device_type'])
    devices.append(datastore_entities.DeviceInfo(**d))
  return DeviceSnapshot(
      date=date, update_time=job_result.timestamp, devices=devices)


def _BuildReportEmailSubject(cluster_prefix, timestamp):
  """Helper to format a report email subject.

  Args:
    cluster_prefix: Cluster prefix of the report
    timestamp: datetime object for the timestamp of the report
  Returns:
    A formatted sting to be used as a report email subject
  """
  return REPORT_SUBJECT % (cluster_prefix,
                           timestamp.strftime(common.DATE_FORMAT))


def FilterDevices(devices, cluster_prefix):
  """Returns a filtered collection of devices by cluster prefix."""
  return [d for d in devices if d.physical_cluster.startswith(cluster_prefix)]


def EmailDeviceReport(report_config, product_report, cluster_report,
                      host_report, timestamp):
  """Emails a report.

  Args:
    report_config: a ReportEmailConfig
    product_report: a DeviceReport object with counts grouped by product
    cluster_report: a DeviceReport object with counts grouped by cluster
    host_report: a HostReport object containing hosts that require attention
    timestamp: report timestamp
  """
  if not env_config.CONFIG.device_report_template_path:
    logging.warn(
        'CONFIG.device_report_template_path is not set; '
        'can\'t send a device report.')
    return
  logging.info('Sending report email to [%s]', report_config.recipients)
  subject = _BuildReportEmailSubject(report_config.cluster_prefix, timestamp)
  template_dir, template_name = os.path.split(
      env_config.CONFIG.device_report_template_path)
  html_body = email_sender.Render(
      template_dir=template_dir,
      template_name=template_name,
      cluster_prefix=report_config.cluster_prefix,
      product_report=product_report,
      cluster_report=cluster_report,
      host_report=host_report,
      timestamp=timestamp)
  if not env_config.CONFIG.should_send_report:
    logging.debug('Not sending report emails on %s', env_config.CONFIG.env)
    logging.debug(html_body)
    return
  if not report_config.recipients:
    logging.error('No recipients specified in report config. check datastore')
    return
  for recipient in report_config.recipients:
    email_sender.SendEmail(
        sender=DEFAULT_SENDER,
        recipient=recipient,
        subject=subject,
        html_body=html_body,
        reply_to=DEFAULT_REPLY_TO)


class DeviceReportBuilder(webapp2.RequestHandler):
  """A class for reporting device information."""

  def get(self):
    """Builds a report using the current state of devices and emails it."""
    date = _GetCurrentDate()
    update_time = _Now()
    local_time = _LocalizedNow()
    devices = GetDevicesToReport()

    # Store the snapshot of all devices
    device_snapshot = DeviceSnapshot(
        devices=devices, update_time=update_time, date=date)
    StoreDeviceSnapshot(device_snapshot)

    for report_config in datastore_entities.ReportEmailConfig.query():
      filtered_devices = FilterDevices(
          devices=devices, cluster_prefix=report_config.cluster_prefix)
      logging.info(
          'Building report for cluster prefix [%s], date [%s] with %d devices',
          report_config.cluster_prefix, date, len(filtered_devices))
      hosts = GetHostsToReport(cluster_prefix=report_config.cluster_prefix)

      # Build and email a report
      product_report = DeviceReport(
          devices=filtered_devices,
          aggregation=PRODUCT_AGGREGATION,
          states=DEVICE_OFFLINE_STATES)
      cluster_report = DeviceReport(
          devices=filtered_devices,
          aggregation=CLUSTER_AGGREGATION,
          states=DEVICE_OFFLINE_STATES)
      host_report = HostReport(hosts=hosts)
      EmailDeviceReport(
          report_config=report_config,
          product_report=product_report,
          cluster_report=cluster_report,
          host_report=host_report,
          timestamp=local_time)
    logging.info('Done...')


APP = webapp2.WSGIApplication([
    (r'/.*', DeviceReportBuilder)
], debug=True)
