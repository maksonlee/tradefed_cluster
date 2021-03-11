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

"""API module to coordinate commands and attempts."""

import logging

import endpoints
from protorpc import message_types
from protorpc import remote

from tradefed_cluster import api_common
from tradefed_cluster import command_attempt_monitor
from tradefed_cluster import command_monitor
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import request_sync_monitor


@api_common.tradefed_cluster_api.api_class(
    resource_name="coordinator", path="coordinator")
class CoordinatorApi(remote.Service):
  """A class for coordinator API."""

  @endpoints.method(
      message_types.VoidMessage,
      message_types.VoidMessage,
      path="backfill-commands",
      http_method="POST",
      name="backfillCommands")
  @api_common.with_ndb_context
  def BackfillCommands(self, request):
    """Backfills all queued commands into sync queue."""
    logging.info("Backfilling queued commands to sync queue.")
    commands = datastore_entities.Command.query(
        datastore_entities.Command.state == common.CommandState.QUEUED,
        namespace=common.NAMESPACE)
    num_monitored = command_monitor.Monitor(commands)
    logging.info("Backfilled %d queued commands.", num_monitored)
    return message_types.VoidMessage()

  @endpoints.method(
      message_types.VoidMessage,
      message_types.VoidMessage,
      path="backfill-command-attempts",
      http_method="POST",
      name="backfillCommandAttempts")
  @api_common.with_ndb_context
  def BackfillCommandAttempts(self, request):
    """Backfills all running attempts into sync queue."""
    logging.info("Backfilling running command attempts to sync queue.")
    attempts = datastore_entities.CommandAttempt.query(
        datastore_entities.CommandAttempt.state == common.CommandState.RUNNING,
        namespace=common.NAMESPACE)
    num_monitored = command_attempt_monitor.Monitor(attempts)
    logging.info("Backfilled %d running command attempts.", num_monitored)
    return message_types.VoidMessage()

  @endpoints.method(
      message_types.VoidMessage,
      message_types.VoidMessage,
      path="backfill-requests",
      http_method="POST",
      name="backfillRequests")
  @api_common.with_ndb_context
  def BackfillRequestSyncs(self, request):
    logging.info("Backfilling non final requests to sync queue.")

    for state in (common.RequestState.UNKNOWN, common.RequestState.QUEUED,
                  common.RequestState.RUNNING):
      requests = datastore_entities.Request.query(
          datastore_entities.Request.state == state, namespace=common.NAMESPACE)
      for request in requests:
        request_sync_monitor.Monitor(request.key.id())

    return message_types.VoidMessage()
