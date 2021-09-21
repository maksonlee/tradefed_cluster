# Copyright 2021 Google LLC
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
"""The module to manage harness update schedules from a cron job."""

import datetime
import logging
import flask

from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster.util import ndb_shim as ndb

APP = flask.Flask(__name__)

# The minimum interval between touchin each PENDING update state entity.
_MIN_TOUCH_INTERVAL = datetime.timedelta(minutes=20)


@APP.route(r'/cron/scheduler/harness_update')
def ManageHarnessUpdateSchedules():
  """The job to manage update schedule based on update schedule aggregation."""
  percentage_field = (
      datastore_entities.ClusterConfig.max_concurrent_update_percentage)
  cluster_configs = list(datastore_entities.ClusterConfig.query()
                         .filter(0 < percentage_field < 100)
                         .fetch())
  for cluster_config in cluster_configs:

    query = (datastore_entities.HostConfig.query()
             .filter(datastore_entities.HostConfig.cluster_name ==
                     cluster_config.cluster_name))
    hostnames = [
        host_config.id() for host_config in query.fetch(keys_only=True)]

    _ManageHarnessUpdateScheduleForHosts(
        hostnames,
        cluster_config.max_concurrent_update_percentage)


def _ManageHarnessUpdateScheduleForHosts(
    hostnames, max_concurrent_update_percentage):
  """Manage update schedule for hosts."""
  hostnames = sorted(hostnames)

  metadatas = ndb.get_multi(
      ndb.Key(datastore_entities.HostMetadata, hostname)
      for hostname in hostnames)

  if all(metadata.allow_to_update for metadata in metadatas):
    logging.debug('All hosts are released to start update, skipping.')
    return

  update_states = ndb.get_multi(
      ndb.Key(datastore_entities.HostUpdateState, hostname)
      for hostname in hostnames)

  max_updates = max(len(hostnames) * max_concurrent_update_percentage // 100, 1)

  # Three lists of HostMetadata entities to track
  # 1. Hosts that are allowed to start update, but are not in a final state.
  #    Update jobs is running or expected to start running on them.
  # 2. Hosts that are not yet allowed to start update. Update jobs should not
  #    have started on them yet. And hosts to be start updates should be
  #    selected from this list.
  # 3. Hosts that are set to allowed already, and in a final state. This list
  #    is only for debugging purposes.
  allowed_but_unfinished = []
  not_allowed_yet = []
  finished = []
  for metadata, update_state in zip(metadatas, update_states):
    if not metadata.allow_to_update:
      not_allowed_yet.append(metadata)
    elif update_state.state in common.NON_FINAL_HOST_UPDATE_STATES:
      allowed_but_unfinished.append(metadata)
    else:
      finished.append(metadata)

  num_expect_updating = len(allowed_but_unfinished)
  num_can_be_added = max(max_updates - num_expect_updating, 0)

  logging.info(
      'Scheduling with max update limit %d.\n'
      'Hosts update schedule summary:\n'
      '  allowed_but_unfinished: %s\n'
      '  not_allowed_yet: %s\n'
      '  finished: %s\n'
      'Adding %d more hosts.',
      max_updates,
      [metadata.hostname for metadata in allowed_but_unfinished],
      [metadata.hostname for metadata in not_allowed_yet],
      [metadata.hostname for metadata in finished],
      num_can_be_added)

  if num_can_be_added <= 0:
    return

  # Mark hosts as allow_to_update.

  metadatas_to_allow = not_allowed_yet[:num_can_be_added]
  for metadata in metadatas_to_allow:
    metadata.allow_to_update = True
    _PutHostMetadata(metadata)

  # Touch remaining PENDING hosts, to prevent from being marked TIMED_OUT.

  hosts_still_not_allowed = set(
      metadata.hostname for metadata in not_allowed_yet[num_can_be_added:])

  for update_state in update_states:
    if (update_state.state == common.HostUpdateState.PENDING and
        update_state.hostname in hosts_still_not_allowed):
      _TouchHostUpdateState(update_state)


@ndb.transactional()
def _PutHostMetadata(hostmetadata):
  hostmetadata.put()


@ndb.transactional()
def _TouchHostUpdateState(update_state):
  time_now = datetime.datetime.utcnow()
  if (not update_state.update_timestamp or
      time_now - update_state.update_timestamp > _MIN_TOUCH_INTERVAL):
    update_state.populate(update_timestamp=time_now)
    update_state.put()



