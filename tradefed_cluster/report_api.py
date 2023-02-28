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

"""API module to serve device report calls."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import datetime
import logging

import dateutil.parser
import endpoints
from protorpc import message_types
from protorpc import messages
from protorpc import remote
import six


from tradefed_cluster import api_common
from tradefed_cluster import device_info_reporter


# Constant to hold a time of 0 (0 hours, 0 minutes, 0 seconds)
ZERO_TIME = datetime.time()


# Disabling invalid-name pylint to allow camel cases.

class RecordGroup(messages.Message):
  """A count of devices matching the criteria for a given group."""
  groupByField = messages.StringField(1, required=True)
  groupByValue = messages.StringField(2, required=True)
  count = messages.IntegerField(3, required=True)
  total = messages.IntegerField(4, required=True)


class DailyRecord(messages.Message):
  """A report record for a single day."""
  date = message_types.DateTimeField(1, required=True)
  updateDate = message_types.DateTimeField(2, required=True)
  recordGroups = messages.MessageField(RecordGroup, 3, repeated=True)


class Report(messages.Message):
  """Report of device states for a date range."""
  dailyRecords = messages.MessageField(DailyRecord, 1, repeated=True)


def BuildRecordGroups(devices, aggregation, states):
  """Helper to build record groups.

  Args:
    devices: List of device entities reported on the given date
    aggregation: Property to aggregate the devices by
    states: Device states to count
  Returns:
    A list of RecordGroup objects
  """
  daily_report = device_info_reporter.DeviceReport(
      devices=devices, aggregation=aggregation, states=states)
  record_groups = []
  for group, value in six.iteritems(daily_report.GetReportCounts()):
    record_groups.append(
        RecordGroup(
            groupByField=aggregation, groupByValue=group, count=value.count,
            total=value.total))
  return record_groups


def BuildDailyRecord(date, aggregation, states, cluster_prefix=None):
  """Helper to build a DailyRecord.

  Args:
    date: Date of the records
    aggregation: Property to aggregate the devices by
    states: Device states to count
    cluster_prefix: cluster prefix filter
  Returns:
    A DailyRecord
  """
  snapshot = device_info_reporter.GetDeviceSnapshotForDate(
      date=date, cluster_prefix=cluster_prefix)
  devices = snapshot.devices
  record_groups = BuildRecordGroups(
      devices=devices, aggregation=aggregation, states=states)
  # Message class does not support datetime.date so it has to be converted
  # to a datetime.datetime object
  report_date = datetime.datetime.combine(snapshot.date, ZERO_TIME)
  return DailyRecord(
      date=report_date, updateDate=snapshot.update_time,
      recordGroups=record_groups)


@api_common.tradefed_cluster_api.api_class(
    resource_name='reports', path='reports')
class ReportApi(remote.Service):
  """A class for report API service."""

  REPORT_BUILD_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      groupByKey=messages.StringField(1, required=True),
      startDate=messages.StringField(3, required=False),
      endDate=messages.StringField(4, required=False),
      states=messages.StringField(5, repeated=True),
      clusterPrefix=messages.StringField(6, required=False),
  )

  @api_common.method(
      REPORT_BUILD_RESOURCE,
      Report,
      path='/reports',
      http_method='GET',
      name='build')
  def BuildReport(self, request):
    """Builds a report containing the counts of devices in given states.

    The report will ignore devices that have been removed by users (ie. marked
    as hidden in our database).

    Args:
      request: an API request.
    Returns:
      a Report object.
    """
    logging.info('BuildReport request: %s', request)
    if not request.states:
      raise endpoints.BadRequestException('Missing states in request.')

    if not request.startDate or not request.endDate:
      # Generate a report using current data
      logging.info('Building report with current data')
      return Report(dailyRecords=[BuildDailyRecord(
          date=None,
          aggregation=request.groupByKey,
          states=request.states,
          cluster_prefix=request.clusterPrefix)])

    current_date = dateutil.parser.parse(request.startDate).date()
    end_date = dateutil.parser.parse(request.endDate).date()
    delta = datetime.timedelta(days=1)
    daily_records = []
    logging.info('Building report from [%s] to [%s]', current_date, end_date)
    while current_date <= end_date:
      logging.info('Building report for [%s]', current_date)
      daily_records.append(BuildDailyRecord(
          date=current_date,
          aggregation=request.groupByKey,
          states=request.states,
          cluster_prefix=request.clusterPrefix))
      current_date += delta
    return Report(dailyRecords=daily_records)
