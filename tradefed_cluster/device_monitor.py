# Lint as: python2, python3
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
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import collections
import datetime
import json
import logging

import flask
import lazy_object_proxy
from protorpc import protojson
import six


from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_util
from tradefed_cluster import device_manager
from tradefed_cluster import env_config
from tradefed_cluster.util import ndb_shim as ndb
from tradefed_cluster.util import pubsub_client


ONE_HOUR = datetime.timedelta(hours=1)
FALLBACK_INACTIVE_TIME = datetime.timedelta(minutes=30)
CLOUD_TF_LAB_NAME = 'cloud-tf'

# TODO: Make the TTL configurable.
ONE_MONTH = datetime.timedelta(days=30)
# TODO: Make use of timeouts defined in lab config.
_DEFAULT_HOST_UPDATE_STATE_TIMEOUT = datetime.timedelta(hours=2)

BATCH = 1000

HOST_AND_DEVICE_PUBSUB_TOPIC = 'projects/%s/topics/%s' % (
    env_config.CONFIG.app_id, 'host_and_device')

APP = flask.Flask(__name__)


def _Now():
  """Returns the current time in UTC. Added to allow mocking in our tests."""
  return datetime.datetime.utcnow()


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

  for cluster, hosts in six.iteritems(cluster_to_hosts):
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


@APP.route(r'/cron/monitor/devices/ndb')
@ndb.toplevel
def MonitorDevice():
  """Reports all devices with their states."""
  logging.info('Starting NDBDeviceMonitor.')
  _ScanHosts()
  _UpdateClusters()
  _UpdateLabs()
  logging.info('Finished NDBDeviceMonitor.')
  return common.HTTP_OK


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
    logging.warning(
        'Unabled to send host message to pubsub: use_google_api=False')
    return
  host = device_manager.GetHost(hostname)
  devices = device_manager.GetDevicesOnHost(hostname)
  host_message = datastore_entities.ToMessage(host)
  host_message.device_infos = [datastore_entities.ToMessage(d) for d in devices]
  encoded_message = protojson.encode_message(host_message)  # pytype: disable=module-attr
  # TODO: find a better way to add event publish timestamp.
  msg_dict = json.loads(encoded_message)
  msg_dict['publish_timestamp'] = _Now().isoformat()
  data = common.UrlSafeB64Encode(json.dumps(msg_dict))
  _PubsubClient.PublishMessages(
      HOST_AND_DEVICE_PUBSUB_TOPIC,
      [{
          'data': data,
          'attributes': {
              'type': 'host',
          }
      }])


@ndb.transactional()
def _MarkHostUpdateStateIfTimedOut(hostname):
  """Mark HostUpdateState as TIMED_OUT if it times out.

  Args:
    hostname: text, the host to check the update timeouts.

  Returns:
    An instance of HostUpdateState entity, None if it does not exist previously.
  """
  host_update_state = datastore_entities.HostUpdateState.get_by_id(hostname)
  if not host_update_state:
    logging.info('No update state is found for host: %s.', hostname)
    return

  now = _Now()

  entities_to_update = []

  if (host_update_state.state and
      host_update_state.state in common.NON_FINAL_HOST_UPDATE_STATES):
    if host_update_state.update_timestamp:
      update_state_age = now - host_update_state.update_timestamp
      if _DEFAULT_HOST_UPDATE_STATE_TIMEOUT < update_state_age:
        logging.info('Host<%s> has HostUpdateState<%s> changed on %s, '
                     'which is %s seconds ago. '
                     'Marking update state as TIMED_OUT.',
                     hostname, host_update_state.state,
                     host_update_state.update_timestamp,
                     update_state_age.total_seconds())
        host_update_state.state = api_messages.HostUpdateState.TIMED_OUT
        host_update_state.update_timestamp = now
        entities_to_update.append(host_update_state)
        host_update_state_history = datastore_entities.HostUpdateStateHistory(
            parent=ndb.Key(datastore_entities.HostInfo, hostname),
            hostname=host_update_state.hostname,
            state=host_update_state.state,
            update_timestamp=now,
            update_task_id=host_update_state.update_task_id)
        entities_to_update.append(host_update_state_history)
      else:
        logging.debug('Host<%s> is in HostUpdateState<%s> since %s.',
                      hostname, host_update_state.state,
                      host_update_state.update_timestamp)
    else:
      logging.debug('Host<%s> has no timestamp in the HostUpdateState. '
                    'Auto adding a timestamp on it.',
                    hostname)
      host_update_state.update_timestamp = now
      entities_to_update.append(host_update_state)
      host_update_state_history = datastore_entities.HostUpdateStateHistory(
          parent=ndb.Key(datastore_entities.HostInfo, hostname),
          hostname=host_update_state.hostname,
          state=host_update_state.state,
          update_timestamp=now,
          update_task_id=host_update_state.update_task_id)
      entities_to_update.append(host_update_state_history)

  ndb.put_multi(entities_to_update)

  return host_update_state


@APP.route('/_ah/queue/%s' % device_manager.HOST_SYNC_QUEUE, methods=['POST'])
def HandleHostSyncTask():
  """Handle host sync tasks."""
  payload = flask.request.get_data()
  host_info = json.loads(payload)
  logging.debug('HostSyncTaskHandler syncing %s.', host_info)
  hostname = host_info[device_manager.HOSTNAME_KEY]
  host_sync_id = host_info.get(device_manager.HOST_SYNC_ID_KEY)
  _MarkHostUpdateStateIfTimedOut(hostname)
  should_sync = _SyncHost(hostname)
  if should_sync:
    device_manager.StartHostSync(hostname, host_sync_id)
    _PublishHostMessage(hostname)
    return common.HTTP_OK
  device_manager.StopHostSync(hostname, host_sync_id)
  return common.HTTP_OK
