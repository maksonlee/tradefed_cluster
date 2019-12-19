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

"""API module to serve device snapshot calls."""

import datetime
import logging

import dateutil.parser
from protorpc import message_types
from protorpc import messages
from protorpc import remote

import endpoints

from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import datastore_entities
from tradefed_cluster import device_info_reporter


# Constant to hold a time of 0 (0 hours, 0 minutes, 0 seconds)
ZERO_TIME = datetime.time()


# Camel case used on API messages.
class DeviceSnapshot(messages.Message):
  """Snapshot of all the devices for a given report date."""
  date = message_types.DateTimeField(1, required=True)
  devices = messages.MessageField(api_messages.DeviceInfo, 2, repeated=True)
  updateTime = message_types.DateTimeField(3)


@api_common.tradefed_cluster_api.api_class(
    resource_name='deviceSnapshots', path='deviceSnapshots')
class DeviceSnapshotApi(remote.Service):
  """A class for Device Snapshot API service."""

  DEVICE_SNAPSHOT_GET_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      date=messages.StringField(1),
  )

  @endpoints.method(
      DEVICE_SNAPSHOT_GET_RESOURCE,
      DeviceSnapshot,
      path='/deviceSnapshots',
      http_method='GET',
      name='get'
  )
  def GetDeviceSnapshot(self, request):
    """Gets a snapshot of all the devices and their properties for a given date.

    If no date is provided, it will return a snapshot of the current state of
    devices that would be reported.

    Args:
      request: an API request.
    Returns:
      a DeviceSnapshot object.
    """
    logging.info('GetDevicesSnapshot request: %s', request)
    date = None
    if request.date:
      date = dateutil.parser.parse(request.date).date()
    device_snapshot = device_info_reporter.GetDeviceSnapshotForDate(date)
    snapshot = DeviceSnapshot()
    snapshot.updateTime = device_snapshot.update_time
    # Message class does not support datetime.date so it has to be converted
    # to a datetime.datetime object
    report_date = datetime.datetime.combine(device_snapshot.date, ZERO_TIME)
    snapshot.date = report_date
    snapshot.devices = [
        datastore_entities.ToMessage(device_snapshot)
        for device_snapshot in device_snapshot.devices]
    return snapshot
