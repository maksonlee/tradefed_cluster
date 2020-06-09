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
"""Test util for datastore related tests."""

from tradefed_cluster.util import ndb_shim as ndb

from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities


def CreateCluster(cluster,
                  total_devices=1,
                  offline_devices=0,
                  available_devices=1,
                  allocated_devices=0,
                  device_count_timestamp=None):
  """Create a cluster."""
  cluster = datastore_entities.ClusterInfo(
      id=cluster,
      cluster=cluster,
      total_devices=total_devices,
      offline_devices=offline_devices,
      available_devices=available_devices,
      allocated_devices=allocated_devices,
      device_count_timestamp=device_count_timestamp)
  cluster.put()
  return cluster


def CreateDeviceCountSummary(run_target, offline=0, available=0, allocated=0):
  """Create a device count summary."""
  return datastore_entities.DeviceCountSummary(
      run_target=run_target,
      total=offline + available + allocated,
      offline=offline,
      available=available,
      allocated=allocated)


def CreateHost(cluster,
               hostname,
               lab_name=None,
               hidden=False,
               timestamp=None,
               extra_info=None,
               device_count_timestamp=None,
               host_state=api_messages.HostState.UNKNOWN,
               tf_start_time=None,
               assignee=None,
               device_count_summaries=None,
               test_runner='tradefed',
               test_runner_version='1234'):
  """Create a host."""
  total_devices = 0
  offline_devices = 0
  available_devices = 0
  allocated_devices = 0
  for c in device_count_summaries or []:
    total_devices += c.total
    offline_devices += c.offline
    available_devices += c.available
    allocated_devices += c.allocated
  ndb_host = datastore_entities.HostInfo(
      id=hostname,
      hostname=hostname,
      lab_name=lab_name,
      physical_cluster=cluster,
      host_group=cluster,
      clusters=[cluster],
      pools=[cluster],
      timestamp=timestamp,
      extra_info=extra_info,
      hidden=hidden,
      total_devices=total_devices,
      offline_devices=offline_devices,
      available_devices=available_devices,
      allocated_devices=allocated_devices,
      device_count_timestamp=device_count_timestamp,
      host_state=host_state,
      tf_start_time=tf_start_time,
      assignee=assignee,
      device_count_summaries=device_count_summaries or [],
      test_runner=test_runner,
      test_runner_version=test_runner_version)
  ndb_host.put()
  return ndb_host


def CreateDevice(cluster,
                 hostname,
                 device_serial,
                 lab_name=None,
                 battery_level='100',
                 hidden=False,
                 device_type=api_messages.DeviceTypeMessage.PHYSICAL,
                 timestamp=None,
                 state='Available',
                 product='product',
                 run_target='run_target',
                 next_cluster_ids=None,
                 test_harness='tradefed'):
  """Create a device."""
  ndb_device = datastore_entities.DeviceInfo(
      id=device_serial,
      parent=ndb.Key(datastore_entities.HostInfo, hostname),
      device_serial=device_serial,
      hostname=hostname,
      battery_level=battery_level,
      device_type=device_type,
      hidden=hidden,
      lab_name=lab_name,
      physical_cluster=cluster,
      clusters=[cluster] + (next_cluster_ids if next_cluster_ids else []),
      timestamp=timestamp,
      state=state,
      product=product,
      run_target=run_target,
      test_harness=test_harness)
  ndb_device.put()
  return ndb_device


def CreateDeviceNote(device_serial,
                     user='user1',
                     offline_reason='offline_reason1',
                     recovery_action='recovery_action1',
                     message='message1',
                     timestamp=None):
  """Create a device note."""
  note = datastore_entities.Note(
      user=user,
      offline_reason=offline_reason,
      recovery_action=recovery_action,
      message=message,
      timestamp=timestamp)
  device_note = datastore_entities.DeviceNote(
      id=device_serial, device_serial=device_serial, note=note)
  device_note.put()
  return device_note


def CreateHostNote(hostname,
                   user='user1',
                   offline_reason='offline_reason1',
                   recovery_action='recovery_action1',
                   message='message1',
                   timestamp=None):
  """Create a host note."""
  note = datastore_entities.Note(
      user=user,
      offline_reason=offline_reason,
      recovery_action=recovery_action,
      message=message,
      timestamp=timestamp)
  host_note = datastore_entities.HostNote(
      id=hostname, hostname=hostname, note=note)
  host_note.put()
  return host_note


def CreateNote(hostname='host1',
               user='user1',
               offline_reason='offline_reason1',
               recovery_action='recovery_action1',
               message='message1',
               timestamp=None,
               cluster_id=None,
               device_serial=None,
               note_type=common.NoteType.UNKNOWN):
  """Create a host note."""
  note = datastore_entities.Note(
      user=user,
      offline_reason=offline_reason,
      recovery_action=recovery_action,
      message=message,
      timestamp=timestamp,
      cluster_id=cluster_id,
      hostname=hostname,
      device_serial=device_serial,
      type=note_type)
  note.put()
  return note


def CreateLabInfo(lab_name, owners=('owner1', 'owner2'), update_timestamp=None):
  """Create a lab info entity."""
  lab_info = datastore_entities.LabInfo(
      id=lab_name,
      lab_name=lab_name,
      owners=list(owners),
      update_timestamp=update_timestamp)
  lab_info.put()
  return lab_info
