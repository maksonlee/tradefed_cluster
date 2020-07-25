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

"""Runs through cron, fetches device state statistics, and emits them."""
import base64
import collections
import datetime
import json
import logging

import lazy_object_proxy
from protorpc import protojson
import webapp2


from tradefed_cluster import api_messages
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_util
from tradefed_cluster import device_manager
from tradefed_cluster import env_config
from tradefed_cluster import metric
from tradefed_cluster.util import metric_util
from tradefed_cluster.util import ndb_shim as ndb
from tradefed_cluster.util import pubsub_client


ONE_HOUR = datetime.timedelta(hours=1)
FALLBACK_INACTIVE_TIME = datetime.timedelta(minutes=30)
CLOUD_TF_LAB_NAME = 'cloud-tf'

# TODO: Make the TTL configurable.
ONE_MONTH = datetime.timedelta(days=30)

BATCH = 1000

HOST_AND_DEVICE_PUBSUB_TOPIC = 'projects/%s/topics/%s' % (
    env_config.CONFIG.app_id, 'host_and_device')


def _Now():
  """Returns the current time in UTC. Added to allow mocking in our tests."""
  return datetime.datetime.utcnow()


def _BuildMetricFields(device):
  """Builds a dictionary of metric fields from a device entity.

  Args:
    device: Device entity
  Returns:
    Dictionary of metric fields
  """
  return {
      metric.METRIC_FIELD_CLUSTER: device.physical_cluster,
      metric.METRIC_FIELD_HOSTNAME: device.hostname,
      metric.METRIC_FIELD_RUN_TARGET: device.run_target,
      metric.METRIC_FIELD_SERIAL: device.device_serial
  }


def _ReportDeviceStateMetric(device, metric_batch):
  """Report metrics on a device state.

  Args:
    device: Device entity
    metric_batch: a metric_util.MetricBatch object.
  """
  device_metric_fields = _BuildMetricFields(device)
  try:
    # Report the device as visible
    metric.devices_visible.Set(1, device_metric_fields, batch=metric_batch)
    # Report offline devices
    if device.state in metric.DEVICE_OFFLINE_STATES:
      metric.devices_offline.Set(1, device_metric_fields, batch=metric_batch)
    else:
      metric.devices_offline.Set(0, device_metric_fields, batch=metric_batch)
    # Report individual device state
    for state in metric.DEVICE_STATES:
      device_metric = metric.GetDeviceStateMetric(state)
      if device.state == state:
        device_metric.Set(1, device_metric_fields, batch=metric_batch)
      else:
        device_metric.Set(0, device_metric_fields, batch=metric_batch)
  except Exception:      logging.warn(
        'failed to set device metric for %s',
        device_metric_fields,
        exc_info=True)


def _UpdateClusters():
  """Update cluster NDB entities based on hosts."""
  logging.debug('Updating clusters')
  logging.debug('Fetching all non-hidden hosts.')
  query = datastore_entities.HostInfo.query().filter(
      datastore_entities.HostInfo.hidden == False)    logging.debug('Fetched all non-hidden hosts.')
  cluster_to_hosts = collections.defaultdict(list)
  for host in datastore_util.BatchQuery(query, batch_size=BATCH):
    cluster_to_hosts[host.physical_cluster].append(host)
  clusters_to_delete = []
  clusters_to_upsert = []
  query = datastore_entities.ClusterInfo.query()
  for cluster in query:
    if cluster.cluster not in cluster_to_hosts:
      clusters_to_delete.append(cluster.key)
  ndb.delete_multi(clusters_to_delete)
  logging.debug('Deleted clusters due to no hosts: %s', clusters_to_delete)

  for cluster, hosts in cluster_to_hosts.iteritems():
    cluster_entity = datastore_entities.ClusterInfo(id=cluster)
    cluster_entity.cluster = cluster
    cluster_entity.total_devices = 0
    cluster_entity.offline_devices = 0
    cluster_entity.available_devices = 0
    cluster_entity.allocated_devices = 0
    cluster_entity.device_count_timestamp = _Now()
    for host in hosts:
      cluster_entity.total_devices += host.total_devices or 0
      cluster_entity.offline_devices += host.offline_devices or 0
      cluster_entity.available_devices += host.available_devices or 0
      cluster_entity.allocated_devices += host.allocated_devices or 0
    clusters_to_upsert.append(cluster_entity)
  ndb.put_multi(clusters_to_upsert)
  logging.debug('Updated clusters.')


def _UpdateLabs():
  """Update lab NDB entities based on hosts.

  Add lab if the lab doesn't exist yet.
  """
  logging.debug('Updating labs')
  labs = datastore_entities.LabInfo.query()
  lab_names = {lab.lab_name for lab in labs}
  query = datastore_entities.HostInfo.query().filter(
      datastore_entities.HostInfo.hidden == False)    labs_to_insert = []
  projection = [datastore_entities.HostInfo.lab_name]
  for host in datastore_util.BatchQuery(
      query, batch_size=BATCH, projection=projection):
    if not host.lab_name:
      continue
    if host.lab_name in lab_names:
      continue
    labs_to_insert.append(
        datastore_entities.LabInfo(
            id=host.lab_name,
            lab_name=host.lab_name,
            update_timestamp=_Now()))
    lab_names.add(host.lab_name)
  ndb.put_multi(labs_to_insert)
  logging.debug('Updated labs.')


def _ScanHosts():
  """Scan hosts and add host to host sync queue."""
  logging.debug('Scan hosts.')
  query = (
      datastore_entities.HostInfo.query()
      .filter(datastore_entities.HostInfo.hidden == False))    for host_key in datastore_util.BatchQuery(
      query, batch_size=BATCH, keys_only=True):
    device_manager.StartHostSync(host_key.id())
  logging.debug('Scanned hosts.')


def _ScanDevices():
  """Scan all devices, and send metrics for all devices."""
  logging.info('Scan devices.')
  metric_batch = metric_util.MetricBatch()
  query = (
      datastore_entities.DeviceInfo.query()
      .filter(datastore_entities.DeviceInfo.hidden == False))    projection = [
      datastore_entities.DeviceInfo.state,
      datastore_entities.DeviceInfo.physical_cluster,
      datastore_entities.DeviceInfo.hostname,
      datastore_entities.DeviceInfo.run_target,
      datastore_entities.DeviceInfo.device_serial,
  ]
  for device in datastore_util.BatchQuery(
      query, batch_size=BATCH, projection=projection):
    _ReportDeviceStateMetric(device, metric_batch)
  metric_batch.Emit()
  logging.info('Finished scan devices.')


class NDBDeviceMonitor(webapp2.RequestHandler):
  """A class for monitoring Device states in NDB."""

  @ndb.toplevel
  def get(self):
    """Reports all devices with their states."""
    logging.info('Starting NDBDeviceMonitor.')
    _ScanDevices()
    _ScanHosts()
    _UpdateClusters()
    _UpdateLabs()
    logging.info('Finished NDBDeviceMonitor.')


def _ShouldHideHost(host):
  """Check if host should be hidden or not.

  For cloud tf host, hide them when it's GONE.
  For other host, hide them if there is not event in one month.

  Args:
    host: host entity
  Returns:
    True if hide the host, otherwise False.
  """
  if not host.timestamp:
    return False
  if (host.lab_name == CLOUD_TF_LAB_NAME and
      host.timestamp <= _Now() - ONE_HOUR):
    logging.info(
        'Hiding cloud tf host [%s], because it last checked in longer than '
        'an hour ago on [%s]', host.hostname, host.timestamp)
    return True
  if host.timestamp <= _Now() - ONE_MONTH:
    logging.info(
        'Hiding host [%s], because it last checked in longer than a month '
        'ago on [%s]', host.hostname, host.timestamp)
    return True
  return False


def _SyncHost(hostname):
  """Sync the host.

  1. If the host is inactive for 1 hour, change the host and its device to GONE.
  2. If the host is inactive for 1 month, hide the host and its devices.

  We don't need to handle device inactive individually because:
  1. if the host is active, then the device inactive will be handled in host
     event processing.
  2. if the host is inactive, then it will be covered here.

  Args:
    hostname: the hostname.
  Returns:
    True if the need to resync the host, otherwise False.
  """
  host = device_manager.GetHost(hostname)
  if not host:
    logging.warning('%s not found.', hostname)
    return False
  if host.hidden:
    logging.warning('%s is hidden.', hostname)
    return False
  if _ShouldHideHost(host):
    device_manager.HideHost(hostname)
    return False
  if host.timestamp:
    inactive_time = _Now() - host.timestamp
  else:
    # TODO: Make sure devices have a timestamp for inactive time
    # if timestamp is None, force update
    inactive_time = FALLBACK_INACTIVE_TIME
  if (inactive_time > ONE_HOUR and
      host.host_state != api_messages.HostState.GONE):
    logging.info(
        'Set host %s to GONE, which has been inactive for %r.',
        hostname, inactive_time)
    device_manager.UpdateGoneHost(hostname)
  return True


# TODO: Merge this code to notifier.
def _CreatePubsubClient():
  """Create a client for Google Cloud Pub/Sub."""
  client = pubsub_client.PubSubClient()
  client.CreateTopic(HOST_AND_DEVICE_PUBSUB_TOPIC)
  return client


_PubsubClient = lazy_object_proxy.Proxy(_CreatePubsubClient)  

def _PublishHostMessage(hostname):
  """Publish host message to pubsub."""
  if not env_config.CONFIG.use_google_api:
    logging.warn(
        'Unabled to send host message to pubsub: use_google_api=False')
    return
  host = device_manager.GetHost(hostname)
  devices = device_manager.GetDevicesOnHost(hostname)
  host_message = datastore_entities.ToMessage(host)
  host_message.device_infos = [datastore_entities.ToMessage(d) for d in devices]
  encoded_message = protojson.encode_message(host_message)
  # TODO: find a better way to add event publish timestamp.
  msg_dict = json.loads(encoded_message)
  msg_dict['publish_timestamp'] = _Now().isoformat()
  data = base64.urlsafe_b64encode(json.dumps(msg_dict))
  _PubsubClient.PublishMessages(
      HOST_AND_DEVICE_PUBSUB_TOPIC,
      [{
          'data': data,
          'attributes': {
              'type': 'host',
          }
      }])


class HostSyncTaskHandler(webapp2.RequestHandler):
  """Task queue handler for monitor host."""

  def post(self):
    payload = self.request.body
    host_info = json.loads(payload)
    taskname = self.request.headers.get('X-AppEngine-TaskName')
    logging.debug(
        'HostSyncTaskHandler syncing %s with task %s',
        host_info, taskname)
    hostname = host_info[device_manager.HOSTNAME_KEY]
    should_sync = _SyncHost(hostname)
    if should_sync:
      device_manager.StartHostSync(hostname, taskname)
      _PublishHostMessage(hostname)
      return
    device_manager.StopHostSync(hostname, taskname)


APP = webapp2.WSGIApplication([
    (r'/cron/monitor/devices/ndb.*', NDBDeviceMonitor),
    ('/_ah/queue/%s' % device_manager.HOST_SYNC_QUEUE, HostSyncTaskHandler),
], debug=True)
