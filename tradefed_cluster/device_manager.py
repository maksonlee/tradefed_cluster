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

"""Module for device management."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import copy
import datetime
import json
import logging
import uuid

import six
from six.moves import zip

from tradefed_cluster import affinity_manager
from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config
from tradefed_cluster import harness_image_metadata_syncer
from tradefed_cluster import metric
from tradefed_cluster.services import task_scheduler
from tradefed_cluster.util import ndb_shim as ndb

MAX_DEVICE_HISTORY_SIZE = 100
MAX_HOST_HISTORY_SIZE = 100
DEFAULT_HOST_HISTORY_SIZE = 10
DEFAULT_HOST_UPDATE_STATE_HISTORY_SIZE = 10

LOCALHOST_IP = "127.0.0.1"

UNKNOWN_PROPERTY = "unknown"

NON_PHYSICAL_DEVICES_PREFIXES = (
    api_messages.TCP_DEVICE_PREFIX,
    api_messages.EMULATOR_DEVICE_PREFIX,
    api_messages.NULL_DEVICE_PREFIX,
    api_messages.GCE_DEVICE_PREFIX,
    api_messages.REMOTE_DEVICE_PREFIX,
    api_messages.LOCAL_VIRTUAL_DEVICE_PREFIX)

DEVICE_SERIAL_KEY = "device_serial"
RUN_TARGET_KEY = "run_target"
PRODUCT_KEY = "product"
LAST_KNOWN_PRODUCT_KEY = "last_known_product"
PRODUCT_VARIANT_KEY = "product_variant"
LAST_KNOWN_PRODUCT_VARIANT_KEY = "last_known_product_variant"
STATE_KEY = "state"
SIM_STATE_KEY = "sim_state"
SIM_OPERATOR_KEY = "sim_operator"
MAC_ADDRESS_KEY = "mac_address"
BUILD_ID_KEY = "build_id"
LAST_KNOWN_BUILD_ID_KEY = "last_known_build_id"
SDK_VERSION_KEY = "sdk_version"
BATTERY_LEVEL_KEY = "battery_level"
HOSTNAME_KEY = "hostname"
HOST_NOTE_ID_KEY = "host_note_id"
DEVICE_NOTE_ID_KEY = "device_note_id"
TEST_HARNESS_START_TIME_MS = "test_harness_start_time_ms"

DEVICE_SNAPSHOT_TYPES = ("DeviceSnapshot", "DEVICE_SNAPSHOT")
HOST_STATE_CHANGED_TYPES = ("HostStateChanged", "HOST_STATE_CHANGED")
HOST_UPDATE_STATE_CHANGED_TYPES = ("HostUpdateStateChanged",
                                   "HOST_UPDATE_STATE_CHANGED")

HOST_SYNC_QUEUE = "host-sync-queue"
HOST_SYNC_ID_KEY = "host_sync_id"
HOST_SYNC_INTERVAL = datetime.timedelta(minutes=5)
HOST_SYNC_STALE_TIMEOUT = 3 * HOST_SYNC_INTERVAL
ONE_MONTH = datetime.timedelta(days=30)


def IsHostEventValid(event):
  """Checks that a host event dictionary has the minimum required entries.

  Args:
    event: HostEvent dictionary to verify.
  Returns:
    True if the event is valid or False otherwise.
  """
  if not event:
    return False
  if not event.get(HOSTNAME_KEY):
    return False
  if not event.get("time"):
    return False
  return True


def HandleDeviceSnapshotWithNDB(event):
  """Handles a device snapshot host event.

  Args:
    event: HostEvent to handle.
  """
  logging.debug(
      "Processing snapshot for host [%s] in cluster [%s] at [%s] to NDB.",
      event.hostname, event.cluster_id, event.timestamp)
  host = GetHost(event.hostname)
  if host and host.timestamp and event.timestamp <= host.timestamp:
    logging.info(
        "Ignoring old event (%s) for host [%s] (%s).",
        event.timestamp, event.hostname, host.timestamp)
    return
  if event.type in HOST_STATE_CHANGED_TYPES:
    _UpdateHostWithHostChangedEvent(event)
  elif event.type in DEVICE_SNAPSHOT_TYPES:
    _UpdateDevicesInNDB(event)
    host = _UpdateHostWithDeviceSnapshotEvent(event)
    _CountDeviceForHost(event.hostname)
    metric.SetHostTestRunnerVersion(
        host.test_harness, host.test_harness_version,
        host.physical_cluster, host.hostname)
  elif event.type in HOST_UPDATE_STATE_CHANGED_TYPES:
    # Get the objective version early to avoid querying NDB entities other than
    # HostUpdateState.
    host_update_target_version = (
        harness_image_metadata_syncer.GetHarnessVersionFromImageUrl(
            event.data.get("host_update_target_image", "")))
    _UpdateHostUpdateStateWithEvent(
        event, target_version=host_update_target_version)
  else:
    logging.warning("Skip unsupported type of event: <%s>", event.type)
  StartHostSync(event.hostname)
  logging.debug("Processed snapshot.")


@ndb.transactional()
def _UpdateHostWithHostChangedEvent(event):
  """update the host with a host state changed event.

  Args:
    event: HostEvent object.
  """
  host = GetHost(event.hostname)
  if not host:
    host = datastore_entities.HostInfo(id=event.hostname)

  # For HostStateChangedEvent other than hostname, state and timestamp,
  # everything else are optional.
  host.hostname = event.hostname
  host.lab_name = event.lab_name or host.lab_name or common.UNKNOWN_LAB_NAME
  host.timestamp = event.timestamp
  host.test_harness = event.test_harness or host.test_harness
  host.test_harness_version = (
      event.test_harness_version or host.test_harness_version)
  host.extra_info = event.data or host.extra_info
  host.hidden = False
  entities_to_update = [host]
  _UpdateHostStateAndHistory(
      host, event.host_state, event.timestamp, entities_to_update)
  ndb.put_multi(entities_to_update)
  return


@ndb.transactional()
def _UpdateHostUpdateStateWithEvent(
    event, target_version=common.UNKNOWN_TEST_HARNESS_VERSION):
  """Update the host with a host update state change event.

  Args:
    event: HostEvent object.
    target_version: The test harness version which the host updates to.
  """
  entities_to_update = []

  host_update_state_enum = api_messages.HostUpdateState(event.host_update_state)
  host_update_state = datastore_entities.HostUpdateState.get_by_id(
      event.hostname)

  if not host_update_state:
    host_update_state = datastore_entities.HostUpdateState(
        id=event.hostname,
        hostname=event.hostname)

  if (host_update_state.update_timestamp and event.timestamp and
      host_update_state.update_timestamp > event.timestamp):
    logging.info("Ignore outdated event.")
  else:
    host_update_state.populate(
        state=host_update_state_enum,
        update_timestamp=event.timestamp,
        update_task_id=event.host_update_task_id,
        display_message=event.host_update_state_display_message,
        target_version=target_version)
    entities_to_update.append(host_update_state)

  host_update_state_history = datastore_entities.HostUpdateStateHistory(
      parent=ndb.Key(datastore_entities.HostInfo, event.hostname),
      hostname=event.hostname,
      state=host_update_state_enum,
      update_timestamp=event.timestamp,
      update_task_id=event.host_update_task_id,
      display_message=event.host_update_state_display_message,
      target_version=target_version)
  entities_to_update.append(host_update_state_history)

  ndb.put_multi(entities_to_update)


@ndb.transactional()
def _UpdateHostWithDeviceSnapshotEvent(event):
  """update the host if the event is host info.

  Update host state to RUNNING if the olds state is GONE.

  Args:
    event: HostEvent dictionary.
  Returns:
    a HostEntity.
  """
  host = GetHost(event.hostname)
  if not host:
    host = datastore_entities.HostInfo(id=event.hostname)
  host.hostname = event.hostname
  host.lab_name = event.lab_name
  # TODO: deprecate physical_cluster, use host_group.
  host.physical_cluster = event.cluster_id
  host.host_group = event.host_group
  host.timestamp = event.timestamp
  host.test_harness = event.test_harness
  host.test_harness_version = event.test_harness_version
  host.hidden = False
  # TODO: deprecate clusters, use pools.
  if event.cluster_id:
    host.clusters = [event.cluster_id] + event.next_cluster_ids
  else:
    host.clusters = event.next_cluster_ids[:]
  host.pools = event.pools
  entities_to_update = [host]
  if event.test_harness == common.TestHarness.TRADEFED:
    if _IsNewTestHarnessInstance(host, event):
      # If it's a new instance, we change the host state to RUNNING.
      _UpdateHostStateAndHistory(
          host,
          api_messages.HostState.RUNNING,
          event.timestamp,
          entities_to_update)
  elif event.host_state and host.host_state != event.host_state:
    # Update host state for non tradefed hosts if its state has changed
    _UpdateHostStateAndHistory(
        host, event.host_state, event.timestamp, entities_to_update)
  # Extra info need to be update after checking _IsNewTestHarnessInstance,
  # since we use insit_harness_start_time_ms in extra info.
  host.extra_info = event.data
  ndb.put_multi(entities_to_update)
  return host


def _UpdateHostStateAndHistory(host, state, timestamp, entities_to_update):
  """Update host state as well as the history.

  Args:
    host: a datastore_entities.HostInfo object.
    state: new host state.
    timestamp: the timestamp when the host state changed.
    entities_to_update: the array of historical entities.
  """
  host_state_history, host_history = _UpdateHostState(
      host, state, timestamp)
  if host_state_history:
    entities_to_update.append(host_state_history)
  if host_history:
    entities_to_update.append(host_history)


def _IsNewTestHarnessInstance(host, event):
  """Check if the even comes from a new test harness instance.

  Args:
    host: a datastore_entities.HostInfo object.
    event: a HostEvent object.
  Returns:
    True if it's a new instance, otherwise False .
  """
  if host.host_state in (None, api_messages.HostState.UNKNOWN,
                         api_messages.HostState.GONE):
    # The host was GONE or have never receive any event.
    logging.debug("%s state was %s.", host.hostname, host.host_state)
    return True
  if not (event.data or {}).get(TEST_HARNESS_START_TIME_MS):
    # The event doesn't have test_harness_start_time_ms, there is no way
    # to tell the event is from a new instance or not.
    return False
  if not (host.extra_info or {}).get(TEST_HARNESS_START_TIME_MS):
    # The old host doesn't have test_harness_start_time_ms but
    # the event has, so it must come from a new instance.
    logging.debug("%s doesn't have 'test_harness_start_time_ms '.",
                  host.hostname)
    return True
  # Last, compare event's test_harness_start_time_ms with host's.
  if (event.data.get(TEST_HARNESS_START_TIME_MS) >
      host.extra_info.get(TEST_HARNESS_START_TIME_MS)):
    logging.debug("%s has a new instance with start time %r.",
                  host.hostname, event.data.get(TEST_HARNESS_START_TIME_MS))
    return True
  return False


@ndb.transactional()
def _CountDeviceForHost(hostname):
  """Count devices for a host.

  Args:
    hostname: the host name to count.
  """
  host = GetHost(hostname)
  if not host:
    return
  devices = (
      datastore_entities.DeviceInfo
      .query(ancestor=ndb.Key(datastore_entities.HostInfo, hostname))
      .filter(datastore_entities.DeviceInfo.hidden == False)        .fetch(projection=[
          datastore_entities.DeviceInfo.run_target,
          datastore_entities.DeviceInfo.state]))
  _DoCountDeviceForHost(host, devices)
  host.put()


def _DoCountDeviceForHost(host, devices):
  """Actually count devices for a host."""
  if not host:
    return
  if not devices:
    logging.info("No devices reported for host [%s]", host.hostname)
    if not host.total_devices and not host.device_count_summaries:
      return
    # If there is no devices but the total_devices is not 0, we need to clear
    # the count.
  now = common.Now()
  host.total_devices = 0
  host.offline_devices = 0
  host.available_devices = 0
  host.allocated_devices = 0
  device_counts = {}
  for device in devices or []:
    device_count = device_counts.get(device.run_target)
    if not device_count:
      device_count = datastore_entities.DeviceCountSummary(
          run_target=device.run_target,
          timestamp=now)
      device_counts[device.run_target] = device_count
    device_count.total += 1
    host.total_devices += 1
    if device.state in common.DEVICE_AVAILABLE_STATES:
      host.available_devices += 1
      device_count.available += 1
    elif device.state in common.DEVICE_ALLOCATED_STATES:
      host.allocated_devices += 1
      device_count.allocated += 1
    else:
      host.offline_devices += 1
      device_count.offline += 1
  host.device_count_timestamp = now
  host.device_count_summaries = list(device_counts.values())


def _TransformDeviceSerial(hostname, serial):
  """Transforms the device serial from a device snapshot event.

  TODO: The logic that appends the hostname to the serial should
  be in TF and not here.

  Args:
    hostname: hostname of the device's host.
    serial: device serial
  Returns:
    A device serial. It will be prefixed with its hostname if it is an
    emulator, TCP device, or IP address.
  """
  if serial and serial.startswith(NON_PHYSICAL_DEVICES_PREFIXES):
    return "%s:%s" % (hostname, serial)
  else:
    return serial


def _UpdateDevicesInNDB(event):
  """Update the device entities to ndb with data from the given host event.

  Args:
    event: a host_event.HostEvent object.
  """
  logging.debug("Updating %d devices in ndb.", len(event.device_info))
  reported_devices = {}
  for device_data in event.device_info:
    device_serial = (_TransformDeviceSerial(
        hostname=event.hostname, serial=device_data.get(DEVICE_SERIAL_KEY)))
    if (not device_serial
        or device_serial in env_config.CONFIG.ignore_device_serials
        or device_serial.startswith(LOCALHOST_IP)):
      # Ignore empty serial, fake, and local host IP devices
      continue
    reported_devices[device_serial] = device_data
  _DoUpdateDevicesInNDB(reported_devices, event)
  _UpdateGoneDevicesInNDB(event.hostname, reported_devices, event.timestamp)
  ResetDeviceAffinities(event.hostname)
  logging.debug("Updated %d devices in ndb.", len(event.device_info))


def _DoUpdateDevicesInNDB(reported_devices, event):
  """Update device entities to ndb.

  Args:
    reported_devices: device serial to device data mapping.
    event: the event have hostname, cluster info and timestamp.
  """
  entities_to_update = []
  device_keys = []
  for device_serial in reported_devices.keys():
    device_key = ndb.Key(
        datastore_entities.HostInfo, event.hostname,
        datastore_entities.DeviceInfo, device_serial)
    device_keys.append(device_key)
  # If the device doesn't exist, the corresponding entry will be None.
  devices = ndb.get_multi(device_keys)
  for device, device_key in zip(devices, device_keys):
    entities_to_update.extend(
        _UpdateDeviceInNDB(
            device, device_key, reported_devices.get(device_key.id()),
            event))
  ndb.put_multi(entities_to_update)


def _UpdateDeviceInNDB(device, device_key, device_data, host_event):
  """Create or update device and its history entities.

  This function will not write to ndb. It just return the updated entities.

  Args:
    device: the device datastore entity
    device_key: device's key
    device_data: device data from host.
    host_event: the host event that include this device's information
  Returns:
    entities to update
  """
  entities_to_update = []
  device_serial = _TransformDeviceSerial(
      host_event.hostname, device_data.get(DEVICE_SERIAL_KEY))
  device_type = api_messages.GetDeviceType(device_serial)

  run_target = device_data.get(RUN_TARGET_KEY)
  product = device_data.get(PRODUCT_KEY)
  product_variant = device_data.get(PRODUCT_VARIANT_KEY)
  if not device:
    device = datastore_entities.DeviceInfo(
        key=device_key, product=product, product_variant=product_variant)
  if (device.timestamp and host_event.timestamp and
      device.timestamp > host_event.timestamp):
    logging.info("Ignore outdated event.")
    return []

  device.extra_info = device.extra_info or {}
  for extra_info in device_data.get("extra_info", []):
    device.extra_info[extra_info.get("key")] = extra_info.get("value")
  device_state = device_data.get(STATE_KEY, device_data.get("device_state"))
  if common.DeviceState.AVAILABLE == device_state:
    if _IsFastbootDevice(
        device_state, device_type, product, host_event.test_harness):
      device_state = common.DeviceState.FASTBOOT
    device.product = product
    device.extra_info[PRODUCT_KEY] = product
    if _IsKnownProperty(product):
      # TODO: remove the following fields once
      # we move the fields into extra_info.
      device.last_known_product = product
      device.extra_info[LAST_KNOWN_PRODUCT_KEY] = product
    device.product_variant = product_variant
    device.extra_info[PRODUCT_VARIANT_KEY] = product_variant
    if _IsKnownProperty(product_variant):
      device.last_known_product_variant = product_variant
      device.extra_info[LAST_KNOWN_PRODUCT_VARIANT_KEY] = product_variant
    device.extra_info[SIM_STATE_KEY] = device_data.get(SIM_STATE_KEY)
    device.extra_info[SIM_OPERATOR_KEY] = device_data.get(SIM_OPERATOR_KEY)
    device.hidden = False

  mac_address = device_data.get(MAC_ADDRESS_KEY)
  if _IsKnownProperty(mac_address):
    # Only update the MAC address if it is a known property. It may be
    # "unknown" if the device has no network connection
    device.mac_address = mac_address
    device.extra_info[MAC_ADDRESS_KEY] = mac_address

  device.device_serial = device_serial
  device.build_id = device_data.get(BUILD_ID_KEY)
  device.extra_info[BUILD_ID_KEY] = device.build_id
  if _IsKnownProperty(device.build_id):
    device.last_known_build_id = device.build_id
    device.extra_info[LAST_KNOWN_BUILD_ID_KEY] = device.build_id
  device.sdk_version = device_data.get(SDK_VERSION_KEY)
  device.extra_info[SDK_VERSION_KEY] = device.sdk_version
  device.hostname = host_event.hostname
  device.lab_name = host_event.lab_name
  device.test_harness = host_event.test_harness
  if host_event.cluster_id:
    device.physical_cluster = host_event.cluster_id
    device.clusters = ([host_event.cluster_id] +
                       (host_event.next_cluster_ids or []))
  device.host_group = host_event.host_group
  device.pools = host_event.pools
  device.timestamp = host_event.timestamp
  device.battery_level = device_data.get(BATTERY_LEVEL_KEY)
  device.extra_info[BATTERY_LEVEL_KEY] = device.battery_level
  device.device_type = device_type

  device_state_history, device_history = _UpdateDevicePropertiesAndGetHistory(
      device, host_event.timestamp, state=device_state, run_target=run_target)
  entities_to_update.append(device)
  if device_state_history:
    entities_to_update.append(device_state_history)
  if device_history:
    entities_to_update.append(device_history)
  return entities_to_update


def _IsFastbootDevice(device_state, device_type, product, test_harness):
  """Check if a device is in fastboot state or not.

  TF reports devices in fastboot as available stub devices (no properties)
  We only care about Physical devices in fastboot state

  Args:
    device_state: device's state
    device_type: device type
    product: device's product
    test_harness: device's test_harness
  Returns:
    True if the device is fastboot device, otherwise False.
  """
  if (common.TestHarness.TRADEFED == test_harness and
      common.DeviceState.AVAILABLE == device_state and
      api_messages.DeviceTypeMessage.PHYSICAL == device_type and
      not _IsKnownProperty(product)):
    return True
  return device_state == common.DeviceState.FASTBOOT


def _UpdateDevicePropertiesAndGetHistory(device,
                                         timestamp,
                                         state=None,
                                         run_target=None):
  """Updates the device properties with new values from host events.

  Changes in these fields will create a history.

  Args:
    device: a DeviceInfo object.
    timestamp: host event timestamp.
    state: device's new state
    run_target: device's new run_target

  Returns:
    the new device state history entity
    the new device info history entity
  """
  changed = False

  if state and device.state != state:
    device.state = state
    changed = True

  if run_target and device.run_target != run_target:
    if (_IsKnownProperty(run_target) and device.state
        == common.DeviceState.AVAILABLE) or device.run_target is None:
      # When the device first appears on a host (device.run_target will be None)
      # it can be assigned with "unknown" run target. For existing devices
      # "unknown" run target updates are ignored.
      device.run_target = run_target
      changed = True

  if not changed:
    return None, None

  device.timestamp = timestamp
  device_state_history = datastore_entities.DeviceStateHistory(
      parent=device.key,
      device_serial=device.device_serial,
      timestamp=device.timestamp,
      state=device.state)
  device_history = _CreateDeviceInfoHistory(device)
  return device_state_history, device_history


def _CreateDeviceInfoHistory(device_info):
  """Create DeviceInfoHistory from DeviceInfo."""
  device_info_dict = copy.deepcopy(device_info.to_dict())
  # flated_extra_info is computed property, can not be assigned.
  device_info_dict.pop("flated_extra_info")
  return datastore_entities.DeviceInfoHistory(
      parent=device_info.key,
      **device_info_dict)


def _UpdateHostState(host, host_state, timestamp):
  """Updates the host with new state and create state history.

  Args:
    host: a HostInfo object,
    host_state: new host state.
    timestamp: the timestamp when the host state changed.
  Returns:
    the new state history and the host history
  """
  if not host_state:
    return None, None
  host_state = api_messages.HostState(host_state)
  if host.host_state == host_state:
    # Ignore if the state doesn't change
    return None, None
  logging.debug(
      "Updating host %s sate history from state %s to new state %s in ndb.",
      host.hostname, host.host_state, host_state)
  host.host_state = host_state
  host.timestamp = timestamp
  host_state_history = datastore_entities.HostStateHistory(
      parent=host.key,
      hostname=host.hostname,
      timestamp=host.timestamp,
      state=host.host_state)
  host_history = None
  if host_state_history:
    host_history = _CreateHostInfoHistory(host)
  return host_state_history, host_history


def _CreateHostInfoHistory(host_info):
  """Create HostInfoHistory from HostInfo."""
  host_info_dict = copy.deepcopy(host_info.to_dict())
  # flated_extra_info is computed property, can not be assigned.
  host_info_dict.pop("flated_extra_info")
  return datastore_entities.HostInfoHistory(
      parent=host_info.key,
      **host_info_dict)


def _UpdateGoneDevicesInNDB(hostname, reported_devices, timestamp):
  """Updates devices in ndb that were not present in the host device snapshot.

  Devices that were previously reported for this host but no longer present
  on the latest snapshot are marked with Gone state.

  Args:
    hostname: Hostname for the current device snapshot.
    reported_devices: device serials that were reported present for the host.
    timestamp: time of the device snapshot
  """
  device_keys = (
      datastore_entities.DeviceInfo
      .query(ancestor=ndb.Key(datastore_entities.HostInfo, hostname))
      .filter(datastore_entities.DeviceInfo.hidden == False)        .fetch(keys_only=True))
  missing_device_keys = []
  for device_key in device_keys:
    if device_key.id() in reported_devices:
      continue
    missing_device_keys.append(device_key)
  logging.debug("There are %d missing devices.", len(missing_device_keys))
  if missing_device_keys:
    _DoUpdateGoneDevicesInNDB(missing_device_keys, timestamp)
    logging.debug("Updated %d missing devices.", len(missing_device_keys))


def _DoUpdateGoneDevicesInNDB(missing_device_keys, timestamp):
  """Do update gone devices in NDB within transactional."""
  entities_to_update = []
  devices = ndb.get_multi(missing_device_keys)
  for device in devices:
    if device.timestamp and device.timestamp > timestamp:
      logging.debug("Ignore outdated event.")
      continue
    if (device.state == common.DeviceState.GONE and
        device.timestamp and
        device.timestamp >= timestamp - ONE_MONTH):
      logging.debug("Ignore gone device.")
      continue
    if device.timestamp and device.timestamp < timestamp - ONE_MONTH:
      device.hidden = True
      device.timestamp = timestamp
    device_state_history, device_history = _UpdateDevicePropertiesAndGetHistory(
        device, timestamp, state=common.DeviceState.GONE)
    entities_to_update.append(device)
    if device_state_history:
      entities_to_update.append(device_state_history)
    if device_history:
      entities_to_update.append(device_history)
  ndb.put_multi(entities_to_update)


def StartHostSync(hostname, current_host_sync_id=None):
  """Start host sync.

  Start host sync, if there is no host sync task or the host sync task is old.

  Args:
    hostname: hostname
    current_host_sync_id: unique id for current host sync that trigger
      this add back.
  Returns:
    the new host_sync_id or None if not added
  """
  host_sync = datastore_entities.HostSync.get_by_id(hostname)
  now = common.Now()
  stale_time = common.Now() - HOST_SYNC_STALE_TIMEOUT
  if (host_sync and host_sync.host_sync_id and
      host_sync.host_sync_id != current_host_sync_id and
      host_sync.update_timestamp and
      host_sync.update_timestamp >= stale_time):
    logging.debug(
        "Another host sync %s is already scheduled.",
        host_sync.host_sync_id)
    return None
  if not host_sync:
    host_sync = datastore_entities.HostSync(id=hostname)
  elif (host_sync.update_timestamp and
        host_sync.update_timestamp < stale_time):
    logging.info(
        "The old sync %s is inactive since %s.",
        host_sync.host_sync_id, host_sync.update_timestamp)
  host_sync.host_sync_id = uuid.uuid4().hex
  payload = json.dumps({
      HOSTNAME_KEY: hostname,
      HOST_SYNC_ID_KEY: host_sync.host_sync_id,
  })
  task = task_scheduler.AddTask(
      queue_name=HOST_SYNC_QUEUE,
      payload=payload,
      eta=common.Now() + HOST_SYNC_INTERVAL)
  # the taskname is for debugging purpose.
  host_sync.taskname = task.name
  host_sync.update_timestamp = now
  host_sync.put()
  logging.debug("Host will sync by task %s with host_sync_id %s.",
                task.name, host_sync.host_sync_id)
  return host_sync.host_sync_id


def StopHostSync(hostname, current_host_sync_id):
  """Stop sync the host."""
  host_sync = datastore_entities.HostSync.get_by_id(hostname)
  stale_time = common.Now() - HOST_SYNC_STALE_TIMEOUT
  if not host_sync:
    logging.info("No host sync for %s.", hostname)
    return
  if (current_host_sync_id != host_sync.host_sync_id and
      host_sync.update_timestamp >= stale_time):
    logging.debug(
        "Another host sync %s is already scheduled.",
        host_sync.host_sync_id)
    return
  logging.debug("Stop host sync for %s.", hostname)
  host_sync.key.delete()


def GetDevicesOnHost(hostname):
  """Get device entities on a host."""
  return (datastore_entities.DeviceInfo
          .query(ancestor=ndb.Key(datastore_entities.HostInfo, hostname))
          .filter(datastore_entities.DeviceInfo.hidden == False)            .fetch())


def UpdateGoneHost(hostname):
  """Set a host and its devices to GONE."""
  logging.info("Set host %s and its devices to GONE.", hostname)
  host = GetHost(hostname)
  if host.host_state == api_messages.HostState.GONE:
    logging.info("Host %s is already GONE.", hostname)
    return
  entities_to_update = []
  now = common.Now()
  entities_to_update.append(host)
  _UpdateHostStateAndHistory(
      host, api_messages.HostState.GONE, now, entities_to_update)
  devices = GetDevicesOnHost(hostname)
  for device in devices or []:
    if device.state == common.DeviceState.GONE:
      continue
    logging.debug("Set device %s to GONE.", device.device_serial)
    device_state_history, device_history = _UpdateDevicePropertiesAndGetHistory(
        device, now, state=common.DeviceState.GONE)
    entities_to_update.append(device)
    if device_state_history:
      entities_to_update.append(device_state_history)
    if device_history:
      entities_to_update.append(device_history)
  _DoCountDeviceForHost(host, devices)
  ndb.put_multi(entities_to_update)


def HideHost(hostname):
  """Hide a host and its devices."""
  logging.info("Hide host %s.", hostname)
  host = GetHost(hostname)
  if not host:
    return None
  if host.hidden:
    logging.info("Host %s is already hidden.", hostname)
    return host
  now = common.Now()
  entities_to_update = []
  host.hidden = True
  host.timestamp = now
  entities_to_update.append(host)
  devices = GetDevicesOnHost(hostname)
  for device in devices or []:
    if device.hidden:
      continue
    logging.debug("Hide device %s.", device.device_serial)
    device.hidden = True
    device.timestamp = now
    entities_to_update.append(device)
  ndb.put_multi(entities_to_update)
  return host


def RestoreHost(hostname):
  """Restore a host and its devices."""
  logging.info("Restore host %s.", hostname)
  host = GetHost(hostname)
  if not host:
    return None
  if not host.hidden:
    logging.info("Host %s is not hidden.", hostname)
    return host
  now = common.Now()
  entities_to_update = []
  host.hidden = False
  host.timestamp = now
  entities_to_update.append(host)
  host.put()
  # We do not restore device for the host, since if devices are still
  # on the host it should report in next host event.
  return host


def HideDevice(device_serial, hostname):
  """Hide a device.

  Args:
    device_serial: device's serial
    hostname: device hostname
  Returns:
    the DeviceInfo entity.
  """
  device = _DoHideDevice(device_serial, hostname)
  if device:
    _CountDeviceForHost(hostname)
  return device


@ndb.transactional()
def _DoHideDevice(device_serial, hostname):
  """Actually hide the device.

  This need to run in a separate transaction otherwise _CountDeviceForHost
  doesn't work, since it will count device before the hide is committed.
  Both device serial and hostname are required since transactional
  only works for ancestor query.

  Args:
    device_serial: device's serial
    hostname: device hostname
  Returns:
    the DeviceInfo entity.
  """
  device = ndb.Key(
      datastore_entities.HostInfo, hostname,
      datastore_entities.DeviceInfo, device_serial).get()
  if not device:
    return None
  if device.hidden:
    logging.info("Device %s %s is already hidden.", device_serial, hostname)
    return device
  device.hidden = True
  device.timestamp = common.Now()
  device.put()
  return device


def RestoreDevice(device_serial, hostname):
  """Restore a device.

  Args:
    device_serial: device's serial
    hostname: device hostname
  Returns:
    the DeviceInfo entity.
  """
  device = _DoRestoreDevice(device_serial, hostname)
  if device:
    _CountDeviceForHost(hostname)
  return device


@ndb.transactional()
def _DoRestoreDevice(device_serial, hostname):
  """Actually restore the device.

  This need to run in a separate transaction otherwise _CountDeviceForHost
  doesn't work, since it will count device before the restore is committed.
  Both device serial and hostname are required since transactional
  only works for ancestor query.

  Args:
    device_serial: device's serial
    hostname: device hostname
  Returns:
    the DeviceInfo entity.
  """
  device = ndb.Key(
      datastore_entities.HostInfo, hostname,
      datastore_entities.DeviceInfo, device_serial).get()
  if not device:
    return None
  if not device.hidden:
    logging.info("Device %s %s is not hidden.", device_serial, hostname)
    return device
  device.hidden = False
  device.timestamp = common.Now()
  device.put()
  return device


def AssignHosts(hostnames, assignee):
  """Assign a list of hosts to an assignee.

  TODO: deprecated, use set_recovery_state

  If assignee is None, it's unassign the hosts.
  We are not using get_multi and put_multi here, because we need to use
  transactional when update a host entity. But a transaction can only have
  less than 25 entity group in a cross group transaction. So we do update
  one by one. If there is a performance issue, we need to optimize later.

  Args:
    hostnames: a list of string.
    assignee: username.
  """
  for hostname in hostnames:
    _AssignHost(hostname, assignee)


@ndb.transactional()
def _AssignHost(hostname, assignee):
  host = GetHost(hostname)
  if not host:
    logging.error("Host %s doesn't exist.", hostname)
    return
  host.assignee = assignee
  if not assignee:
    host.last_recovery_time = common.Now()
  host.put()


def SetHostsRecoveryState(host_recovery_state_requests):
  """Set hosts' recovery state.

  We are not using get_multi and put_multi here, because we need to use
  transactional when update a host entity. But a transaction can only have
  less than 25 entity group in a cross group transaction. So we do update
  one by one. If there is a performance issue, we need to optimize later.

  Args:
    host_recovery_state_requests: a list of host recovery state requests.
  """
  for request in host_recovery_state_requests:
    _SetHostRecoveryState(
        request.hostname, request.recovery_state, request.assignee)


@ndb.transactional()
def _SetHostRecoveryState(hostname, recovery_state, assignee=None):
  """Set host's recovery state."""
  host = GetHost(hostname)
  if not host:
    logging.error("Host %s doesn't exist.", hostname)
    return
  host.assignee = assignee
  entities_to_update = []
  if recovery_state == common.RecoveryState.VERIFIED:
    host.recovery_state = common.RecoveryState.VERIFIED
    host.assignee = host.assignee
    host.last_recovery_time = common.Now()
    host.timestamp = common.Now()
    entities_to_update.append(_CreateHostInfoHistory(host))
    devices = GetDevicesOnHost(hostname)
    for device in devices:
      if (device.recovery_state and
          device.recovery_state != common.RecoveryState.UNKNOWN):
        entities_to_update.extend(
            _BuildDeviceRecoveryState(device, common.RecoveryState.VERIFIED))
    # After it's verified, it goes into a state as no-one is recovering it.
    host.recovery_state = common.RecoveryState.UNKNOWN
    host.assignee = None
  else:
    host.recovery_state = recovery_state
  host.last_recovery_time = common.Now()
  host.timestamp = common.Now()
  entities_to_update.append(_CreateHostInfoHistory(host))
  entities_to_update.append(host)
  ndb.put_multi(entities_to_update)


def SetDevicesRecoveryState(device_recovery_state_requests):
  """Set devices' recovery state.

  We are not using get_multi and put_multi here, because we need to use
  transactional when update a device entity. But a transaction can only have
  less than 25 entity group in a cross group transaction. So we do update
  one by one. If there is a performance issue, we need to optimize later.

  Args:
    device_recovery_state_requests: a list of device recovery state requests.
  """
  host_to_recovery_state = {}
  for request in device_recovery_state_requests:
    _SetDeviceRecoveryState(
        request.hostname,
        request.device_serial,
        request.recovery_state)
    if (request.recovery_state == common.RecoveryState.FIXED and
        request.hostname not in host_to_recovery_state):
      host_to_recovery_state[request.hostname] = (
          common.RecoveryState.ASSIGNED, request.assignee)
  for hostname, (recovery_state, assignee) in six.iteritems(
      host_to_recovery_state):
    _SetHostRecoveryState(hostname, recovery_state, assignee)


@ndb.transactional()
def _SetDeviceRecoveryState(
    hostname, device_serial, recovery_state):
  """Set device's recovery state."""
  device = GetDevice(hostname, device_serial)
  if not device:
    logging.error("Device (%s, %s) doesn't exist.", hostname, device_serial)
    return
  entities_to_update = _BuildDeviceRecoveryState(device, recovery_state)
  ndb.put_multi(entities_to_update)


def _BuildDeviceRecoveryState(device, recovery_state):
  """Build device's recovery state and its history."""
  entities_to_update = []
  if recovery_state == common.RecoveryState.VERIFIED:
    device.recovery_state = common.RecoveryState.VERIFIED
    device.last_recovery_time = common.Now()
    device.timestamp = common.Now()
    entities_to_update.append(_CreateDeviceInfoHistory(device))
    device.recovery_state = common.RecoveryState.UNKNOWN
  else:
    device.recovery_state = recovery_state
  device.last_recovery_time = common.Now()
  device.timestamp = common.Now()
  entities_to_update.append(_CreateDeviceInfoHistory(device))
  entities_to_update.append(device)
  return entities_to_update


def _IsKnownProperty(value):
  """Helper to check if a value is not an unknown property."""
  return value and value != UNKNOWN_PROPERTY


def GetCluster(cluster_id):
  """Retrieve a cluster by it's id.

  Args:
    cluster_id: cluster's id
  Returns:
    ClusterInfo object
  """
  return datastore_entities.ClusterInfo.get_by_id(cluster_id)


def GetHost(hostname):
  """Retrieve a host given a hostname.

  Args:
    hostname: a hostname.
  Returns:
    The host entity corresponding to the given hostname.
  """
  return datastore_entities.HostInfo.get_by_id(hostname)


def GetDevice(hostname=None, device_serial=None):
  """Retrieve a device given a device serial and its hostname.

  Args:
    hostname: hostname
    device_serial: a device serial.
  Returns:
    The device information corresponding to the given device serial.
  """
  if hostname:
    return ndb.Key(
        datastore_entities.HostInfo, hostname,
        datastore_entities.DeviceInfo, device_serial).get()
  return (datastore_entities.DeviceInfo.query()
          .filter(
              datastore_entities.DeviceInfo.device_serial == device_serial)
          .order(-datastore_entities.DeviceInfo.timestamp).get())


def GetDeviceStateHistory(hostname, device_serial):
  """Retrieve a device's state history.

  Limit to MAX_HISTORY_SIZE

  Args:
    hostname: hostname
    device_serial: a device serial.
  Returns:
    a list of DeviceStateHistory entities.
  """
  device_key = ndb.Key(
      datastore_entities.HostInfo, hostname,
      datastore_entities.DeviceInfo, device_serial)
  return (datastore_entities.DeviceStateHistory.query(ancestor=device_key)
          .order(-datastore_entities.DeviceStateHistory.timestamp)
          .fetch(limit=MAX_DEVICE_HISTORY_SIZE))


def GetHostStateHistory(hostname, limit=DEFAULT_HOST_HISTORY_SIZE):
  """Function to get host state history from NDB.

  Args:
    hostname: host name.
    limit: an integer about the max number of state history returned.
  Returns:
    a list of host state history.
  """
  host_key = ndb.Key(datastore_entities.HostInfo, hostname)
  if limit < 0 or limit > MAX_HOST_HISTORY_SIZE:
    raise ValueError("size of host state history should be in range 0 to %d,"
                     "but got %d" % MAX_HOST_HISTORY_SIZE % limit)
  return (datastore_entities.HostStateHistory.query(ancestor=host_key)
          .order(-datastore_entities.HostStateHistory.timestamp)
          .fetch(limit=limit))


def GetHostUpdateStateHistories(hostname,
                                limit=DEFAULT_HOST_UPDATE_STATE_HISTORY_SIZE):
  """Function to get host update state history from NDB.

  Args:
    hostname: host name.
    limit: an integer about the max number of state history returned.

  Returns:
    A datastore entity list of HostUpdateStateHistory.
  """
  return (datastore_entities.HostUpdateStateHistory
          .query(ancestor=ndb.Key(datastore_entities.HostInfo, hostname))
          .order(-datastore_entities.HostUpdateStateHistory.update_timestamp)
          .fetch(limit=limit))


def GetRunTargetsFromNDB(cluster=None):
  """Fetches a list of run targets for all devices in a cluster (if provided).

  Args:
    cluster: Cluster ID to retrieve run targets from. If no cluster is provided,
      it will fetch all run targets.
  Returns:
    A generator containing all the distinct run target names.
  """
  query = datastore_entities.DeviceInfo.query(
      projection=[datastore_entities.DeviceInfo.run_target],
      distinct=True).filter(
          datastore_entities.DeviceInfo.hidden == False)    if cluster:
    query = query.filter(
        datastore_entities.DeviceInfo.clusters == cluster)
  return (h.run_target for h in query if h.run_target)


def CalculateDeviceUtilization(device_serial, days=7):
  """Calculates the device utilization rate over a number of days.

  Device utilization is defined as the time a device has been in allocated
  state over the given number of days.

  Args:
    device_serial: Serial for the device to calculate utilization for.
    days: Number of days to calculate utilization. Defaults to 7.
  Returns:
    A number representing the percent of time the device has been allocated.
  Raises:
    ValueError: if the given days are invalid
  """
  if days <= 0:
    raise ValueError("Number of days [%d] should be > 0" % (days))
  now = common.Now()
  requested_time = datetime.timedelta(days=days)
  start_date = now - requested_time

  query = datastore_entities.DeviceStateHistory.query()
  query = query.filter(
      datastore_entities.DeviceStateHistory.device_serial == device_serial)
  query = query.filter(
      datastore_entities.DeviceStateHistory.timestamp >= start_date)
  query = query.order(datastore_entities.DeviceStateHistory.timestamp)

  allocated_time = datetime.timedelta()
  record_start_time = None
  # If the device was allocated before the given days and continued to be,
  # it will miss that allocation time as part of this calculation.
  for record in query.iter():
    # May take a while depending how often this device changes states.
    if record.state == "Allocated":
      if not record_start_time:
        record_start_time = record.timestamp
    elif record_start_time:
      allocated_time += record.timestamp - record_start_time
      record_start_time = None

  if record_start_time:
    # Last known state was allocated
    allocated_time += now - record_start_time

  total_seconds = requested_time.total_seconds()
  allocated_seconds = allocated_time.total_seconds()
  return float(allocated_seconds) / float(total_seconds)


def CreateAndSaveDeviceInfoHistoryFromDeviceNote(device_serial, note_id):
  """Create and save DeviceInfoHistory from a DeviceNote.

  This method obtains current DeviceInfo based on device_serial, and create a
  DeviceInfoHistory with DeviceNote id in extra_info, then save to datastore.

  Args:
    device_serial: string, serial number of a lab device.
    note_id: int, the id of a DeviceNote.

  Returns:
    An instance of ndb.Key, the key of DeviceInfoHistory entity.
  """
  device = GetDevice(device_serial=device_serial)
  device.timestamp = common.Now()
  device_info_history = _CreateDeviceInfoHistory(device)
  if device_info_history.extra_info is None:
    device_info_history.extra_info = {}
  device_info_history.extra_info[DEVICE_NOTE_ID_KEY] = note_id
  key = device_info_history.put()
  return key


def CreateAndSaveHostInfoHistoryFromHostNote(hostname, note_id):
  """Create and save HostInfoHistory from a HostNote.

  This method obtains current HostInfo based on hostname, and create a
  HostInfoHistory with HosteNote id in extra_info, then save to datastore.

  Args:
    hostname: string, name of a lab host.
    note_id: int, the id of a HostNote.

  Returns:
    An instance of ndb.Key, the key of HostInfoHistory entity.
  """
  host = GetHost(hostname=hostname)
  host.timestamp = common.Now()
  host_info_history = _CreateHostInfoHistory(host)
  if host_info_history.extra_info is None:
    host_info_history.extra_info = {}
  host_info_history.extra_info[HOST_NOTE_ID_KEY] = note_id
  key = host_info_history.put()
  return key


def ResetDeviceAffinities(hostname):
  """Reset device affinities for unavailable devices on a given host.

  Args:
    hostname: a lab host's name.
  """
  devices = (
      datastore_entities.DeviceInfo
      .query(ancestor=ndb.Key(datastore_entities.HostInfo, hostname))
      .fetch())
  for device in devices:
    if device.state not in [
        common.DeviceState.ALLOCATED, common.DeviceState.AVAILABLE
    ]:
      affinity_manager.ResetDeviceAffinity(device.device_serial)
