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
import functools
import json
import logging

import flask
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
# TODO: the hosts lose lab name during update. Once the bug is
# fixed, we should use lab name only to decide the host type.
CLOUD_TF_HOST_NAME_PREFIX = 'cloud-tf'
DOCKERIZED_TF_GKE_NAME_PREFIX = 'dockerized-tf-gke'
_SERVICE_ACCOUNT_KEY_RESOURCE = 'service_account_key'
_SERVICE_ACCOUNT_KEY_EXPIRE_METRIC = 'expire'

# TODO: Make the TTL configurable.
ONE_MONTH = datetime.timedelta(days=30)
_DEFAULT_HOST_UPDATE_STATE_TIMEOUT = datetime.timedelta(hours=2)
_CUSTOMIZED_TIMEOUT_MULTIPLIER = 1.5
_TIMEDOUT_DISPLAY_MESSAGE_TMPL = (
    'Host <%s> has HostUpdateState<%s> '
    'changed on %s, '
    'which is %d sec ago, '
    'exceeding timeouts %d sec. ')

BATCH = 1000

HOST_AND_DEVICE_PUBSUB_TOPIC = 'projects/%s/topics/%s' % (
    env_config.CONFIG.app_id, 'host_and_device')

APP = flask.Flask(__name__)


def _UpdateClusters(hosts):
  """Update cluster NDB entities based on hosts.

  Args:
    hosts: list of HostInfo entity with required field, from the entire system.

  Returns:
    list of ClusterInfo, clusters to upsert.
  """
  logging.info('Updating clusters')

  cluster_to_hosts = collections.defaultdict(list)

  for host in hosts:
    cluster = host.physical_cluster or common.UNKNOWN_CLUSTER_NAME
    cluster_to_hosts[cluster].append(host)

  clusters_to_delete = []
  clusters_to_upsert = []
  query = datastore_entities.ClusterInfo.query()
  for cluster in query:
    if cluster.cluster not in cluster_to_hosts:
      clusters_to_delete.append(cluster.key)

  if clusters_to_delete:
    ndb.delete_multi(clusters_to_delete)
    logging.debug('Deleted clusters due to no hosts: %s', clusters_to_delete)

  query = datastore_entities.HostUpdateState.query()
  update_states_by_hostname = {
      update_state.hostname: update_state for update_state in query.fetch()}

  for cluster, hosts in six.iteritems(cluster_to_hosts):
    logging.info('Updating cluster %s', cluster)
    cluster_entity = datastore_entities.ClusterInfo(id=cluster)
    for host in hosts:
      if host.lab_name:
        cluster_entity.lab_name = host.lab_name
        break
    else:
      cluster_entity.lab_name = common.UNKNOWN_LAB_NAME
    cluster_entity.cluster = cluster
    cluster_entity.total_devices = 0
    cluster_entity.offline_devices = 0
    cluster_entity.available_devices = 0
    cluster_entity.allocated_devices = 0
    cluster_entity.device_count_timestamp = common.Now()
    host_update_states = []
    host_update_states_by_target_version = collections.defaultdict(list)
    host_count_by_harness_version = collections.Counter()
    for host in hosts:
      cluster_entity.total_devices += host.total_devices or 0
      cluster_entity.offline_devices += host.offline_devices or 0
      cluster_entity.available_devices += host.available_devices or 0
      cluster_entity.allocated_devices += host.allocated_devices or 0
      host_update_state = update_states_by_hostname.get(host.hostname)
      if host_update_state:
        host_update_states.append(host_update_state)
        host_update_states_by_target_version[
            host_update_state.target_version].append(host_update_state)
      if host.test_harness_version:
        host_count_by_harness_version[host.test_harness_version] += 1
      else:
        host_count_by_harness_version[common.UNKNOWN_TEST_HARNESS_VERSION] += 1
    cluster_entity.host_count_by_harness_version = host_count_by_harness_version
    cluster_entity.host_update_state_summary = _CreateHostUpdateStateSummary(
        host_update_states)
    for version, states in host_update_states_by_target_version.items():
      cluster_entity.host_update_state_summaries_by_version.append(
          _CreateHostUpdateStateSummary(states, target_version=version))
    clusters_to_upsert.append(cluster_entity)
  ndb.put_multi(clusters_to_upsert)
  logging.debug('Updated clusters.')
  return clusters_to_upsert


def _CreateHostUpdateStateSummary(host_update_states, target_version=None):
  """Create host update state summary entity.

  Args:
    host_update_states: list of HostUpdateState entities.
    target_version: optional string, the test harness version the hosts are
      running updates to.

  Returns:
    a HostUpdateStateSummary datastore entity.
  """
  summary = datastore_entities.HostUpdateStateSummary(
      total=len(host_update_states))
  if target_version:
    summary.target_version = target_version
  for host_update_state in host_update_states:
    if not host_update_state:
      continue
    if host_update_state.state == api_messages.HostUpdateState.PENDING:
      summary.pending += 1
    elif host_update_state.state == api_messages.HostUpdateState.SYNCING:
      summary.syncing += 1
    elif host_update_state.state == api_messages.HostUpdateState.SHUTTING_DOWN:
      summary.shutting_down += 1
    elif host_update_state.state == api_messages.HostUpdateState.RESTARTING:
      summary.restarting += 1
    elif host_update_state.state == api_messages.HostUpdateState.SUCCEEDED:
      summary.succeeded += 1
    elif (host_update_state.state ==
          api_messages.HostUpdateState.TIMED_OUT):
      summary.timed_out += 1
    elif host_update_state.state == api_messages.HostUpdateState.ERRORED:
      summary.errored += 1
    elif host_update_state.state == api_messages.HostUpdateState.UNKNOWN:
      summary.unknown += 1
  return summary


def _UpdateLabs(clusters):
  """Update lab NDB entities based on hosts.

  Args:
    clusters: a list of ClusterInfo.

  1. Add lab if the lab doesn't exist yet.
  2. Refresh the host update state summary in all labs based on the underlying
     host groups.
  """
  logging.info('Updating labs')
  labs_query = datastore_entities.LabInfo.query()
  labs_by_lab_names = {lab.lab_name: lab for lab in labs_query}
  clusters_by_lab_names = collections.defaultdict(list)

  for cluster_info in clusters:
    lab_name = cluster_info.lab_name or common.UNKNOWN_LAB_NAME
    clusters_by_lab_names[lab_name].append(cluster_info)

  labs = []
  for lab_name, cluster_infos in clusters_by_lab_names.items():
    lab_host_update_state_summary = datastore_entities.HostUpdateStateSummary()
    lab_host_update_state_summaries_by_version = collections.defaultdict(
        datastore_entities.HostUpdateStateSummary)
    host_count_by_harness_version = collections.Counter()

    for cluster_info in cluster_infos:
      if cluster_info and cluster_info.host_update_state_summary:
        lab_host_update_state_summary += cluster_info.host_update_state_summary
      if cluster_info and cluster_info.host_update_state_summaries_by_version:
        for summary in cluster_info.host_update_state_summaries_by_version:
          lab_host_update_state_summaries_by_version[
              summary.target_version] += summary
      if cluster_info and cluster_info.host_count_by_harness_version:
        host_count_by_harness_version += collections.Counter(
            cluster_info.host_count_by_harness_version)

    if lab_name in labs_by_lab_names:
      lab = labs_by_lab_names[lab_name]
    else:
      lab = datastore_entities.LabInfo(
          id=lab_name,
          lab_name=lab_name)
    lab.populate(
        host_update_state_summary=lab_host_update_state_summary,
        host_count_by_harness_version=host_count_by_harness_version,
        host_update_state_summaries_by_version=list(
            lab_host_update_state_summaries_by_version.values()),
        update_timestamp=common.Now())
    labs.append(lab)

  ndb.put_multi(labs)
  logging.info('Updated labs.')


def _ScanHosts():
  """Scan hosts and add host to host sync queue.

  Returns:
    list of HostInfo.
  """
  logging.info('Scan hosts.')
  hosts = []
  query = (
      datastore_entities.HostInfo.query()
      .filter(datastore_entities.HostInfo.hidden == False))  
  # LINT.IfChange(scan_host_projection)
  projection = [
      datastore_entities.HostInfo.lab_name,
      datastore_entities.HostInfo.physical_cluster,
      datastore_entities.HostInfo.hostname,
      datastore_entities.HostInfo.total_devices,
      datastore_entities.HostInfo.offline_devices,
      datastore_entities.HostInfo.available_devices,
      datastore_entities.HostInfo.allocated_devices,
      datastore_entities.HostInfo.test_harness_version,
  ]

  for host in datastore_util.BatchQuery(
      query, batch_size=BATCH, projection=projection):
    device_manager.StartHostSync(host.hostname)
    hosts.append(host)
  logging.info('Scanned hosts.')
  return hosts


@APP.route(r'/cron/monitor/devices/ndb')
@ndb.toplevel
def MonitorDevice():
  """Reports all devices with their states."""
  logging.info('Starting NDBDeviceMonitor.')
  hosts = _ScanHosts()
  clusters = _UpdateClusters(hosts)
  _UpdateLabs(clusters)
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
  if ((host.lab_name == CLOUD_TF_LAB_NAME or
       host.hostname.startswith(CLOUD_TF_HOST_NAME_PREFIX) or
       host.hostname.startswith(DOCKERIZED_TF_GKE_NAME_PREFIX)) and
      host.timestamp <= common.Now() - ONE_HOUR):
    logging.info(
        'Hiding cloud tf host [%s], because it last checked in longer than '
        'an hour ago on [%s]', host.hostname, host.timestamp)
    return True
  if host.timestamp <= common.Now() - ONE_MONTH:
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
    inactive_time = common.Now() - host.timestamp
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
    device_manager.ResetDeviceAffinities(hostname)
  return True


# TODO: Merge this code to notifier.
@functools.lru_cache()
def _CreatePubsubClient():
  """Create a client for Google Cloud Pub/Sub."""
  client = pubsub_client.PubSubClient()
  client.CreateTopic(HOST_AND_DEVICE_PUBSUB_TOPIC)
  return client


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
  msg_dict['publish_timestamp'] = common.Now().isoformat()
  data = common.UrlSafeB64Encode(json.dumps(msg_dict))
  _CreatePubsubClient().PublishMessages(
      HOST_AND_DEVICE_PUBSUB_TOPIC,
      [{
          'data': data,
          'attributes': {
              'type': 'host',
          }
      }])


def _GetCustomizedOrDefaultHostUpdateTimeout(hostname):
  """Get host update timeouts.

  If the timeouts are not defined in lab config, then get the default value.

  Args:
    hostname: text, the host to check the update timeouts.

  Returns:
    An instance of datetime.timedelta.
  """
  timeout_timedelta = _DEFAULT_HOST_UPDATE_STATE_TIMEOUT
  host_config = datastore_entities.HostConfig.get_by_id(hostname)
  if host_config and host_config.shutdown_timeout_sec:
    timeout_sec = (
        _CUSTOMIZED_TIMEOUT_MULTIPLIER * host_config.shutdown_timeout_sec)
    timeout_timedelta = datetime.timedelta(seconds=timeout_sec)
  return timeout_timedelta


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

  timeout_timedelta = _GetCustomizedOrDefaultHostUpdateTimeout(hostname)

  now = common.Now()

  entities_to_update = []

  if (host_update_state.state and
      host_update_state.state in common.NON_FINAL_HOST_UPDATE_STATES):
    if host_update_state.update_timestamp:
      update_state_age = now - host_update_state.update_timestamp
      if timeout_timedelta < update_state_age:
        display_message = (
            _TIMEDOUT_DISPLAY_MESSAGE_TMPL % (
                hostname, host_update_state.state,
                host_update_state.update_timestamp,
                update_state_age.total_seconds(),
                timeout_timedelta.total_seconds()))
        logging.info('Marking update state as TIMED_OUT: %s', display_message)
        host_update_state.state = api_messages.HostUpdateState.TIMED_OUT
        host_update_state.update_timestamp = now
        host_update_state.populate(
            state=api_messages.HostUpdateState.TIMED_OUT,
            update_timestamp=now,
            display_message=display_message)
        entities_to_update.append(host_update_state)
        host_update_state_history = datastore_entities.HostUpdateStateHistory(
            parent=ndb.Key(datastore_entities.HostInfo, hostname),
            hostname=host_update_state.hostname,
            state=host_update_state.state,
            update_timestamp=now,
            update_task_id=host_update_state.update_task_id,
            display_message=display_message)
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


def _CheckServiceAccountKeyExpiration(hostname):
  """Check host's service account is expiring or not.

  Args:
    hostname: hostname
  Returns:
    a list of service accounts that are going to expire.
  """
  host_resource = datastore_entities.HostResource.get_by_id(hostname)
  if not host_resource:
    return None
  expiring_keys = []
  for resource in host_resource.resource.get(
      common.LabResourceKey.RESOURCE, []):
    if (resource.get(common.LabResourceKey.RESOURCE_NAME) !=
        _SERVICE_ACCOUNT_KEY_RESOURCE):
      continue
    sa_key = resource.get(common.LabResourceKey.RESOURCE_INSTANCE)
    if not resource.get(common.LabResourceKey.METRIC):
      logging.error('There is no metric for %s', sa_key)
      continue
    expire_time = None
    for metric in resource[common.LabResourceKey.METRIC]:
      if (metric.get(common.LabResourceKey.TAG) ==
          _SERVICE_ACCOUNT_KEY_EXPIRE_METRIC):
        expire_time = metric.get(common.LabResourceKey.VALUE)
        break
    if not expire_time:
      logging.error('There is no expire time for %s', sa_key)
      continue
    if expire_time > (common.Now() + ONE_MONTH).timestamp():
      continue
    expiring_keys.append(sa_key)
  return expiring_keys


def _UpdateHostBadness(hostname):
  """Check if the host is bad or not."""
  host_info = device_manager.GetHost(hostname)
  if not host_info:
    logging.info('Host %s not found', hostname)
    return

  reason = ''
  if host_info.host_state == api_messages.HostState.GONE:
    reason += 'Host is gone.'

  for device_count_summary in host_info.device_count_summaries or []:
    if device_count_summary.offline:
      reason += ' Some devices are offline.'
      break

  expiring_keys = _CheckServiceAccountKeyExpiration(hostname)
  if expiring_keys:
    reason += ' %s are going to expire.' % expiring_keys

  if host_info.bad_reason != reason:
    _DoUpdateHostBadness(hostname, reason)


@ndb.transactional()
def _DoUpdateHostBadness(hostname, reason):
  """Update host's badness in transaction."""
  host_info = device_manager.GetHost(hostname)
  host_info.is_bad = bool(reason)
  host_info.bad_reason = reason
  host_info.put()


@APP.route('/_ah/queue/%s' % device_manager.HOST_SYNC_QUEUE, methods=['POST'])
def HandleHostSyncTask():
  """Handle host sync tasks."""
  payload = flask.request.get_data()
  host_info = json.loads(payload)
  logging.debug('HostSyncTaskHandler syncing %s.', host_info)
  hostname = host_info[device_manager.HOSTNAME_KEY]
  host_sync_id = host_info.get(device_manager.HOST_SYNC_ID_KEY)
  _MarkHostUpdateStateIfTimedOut(hostname)
  _UpdateHostBadness(hostname)
  should_sync = _SyncHost(hostname)
  if should_sync:
    device_manager.StartHostSync(hostname, host_sync_id)
    _PublishHostMessage(hostname)
    return common.HTTP_OK
  device_manager.StopHostSync(hostname, host_sync_id)
  return common.HTTP_OK
