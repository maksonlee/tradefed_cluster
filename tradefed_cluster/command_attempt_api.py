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

"""API module to serve command attempt service calls."""

from protorpc import message_types
from protorpc import messages
from protorpc import remote

from google3.third_party.apphosting.python.endpoints.v1_1 import endpoints

from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import common
from tradefed_cluster import datastore_entities


@api_common.tradefed_cluster_api.api_class(resource_name="commandAttempts",
                                           path="commandAttempts")
class CommandAttemptApi(remote.Service):
  """A class for command attempt API service."""

  COMMAND_ATTEMPT_LIST_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      hostname=messages.StringField(1),
      device_serial=messages.StringField(2),
      offset=messages.IntegerField(3, variant=messages.Variant.INT32),
      count=messages.IntegerField(4, variant=messages.Variant.INT32)
  )

  @endpoints.method(
      COMMAND_ATTEMPT_LIST_RESOURCE,
      api_messages.CommandAttemptMessageCollection,
      path="/commandAttempts",
      http_method="GET",
      name="list"
  )
  def ListCommandAttempts(self, api_request):
    """Get command attempts satisfy the condition.

    Args:
      api_request: api request may contain a hostname or device serial
    Returns:
      collection of command attempts
    """
    query = datastore_entities.CommandAttempt.query(namespace=common.NAMESPACE)
    if api_request.hostname is not None:
      query = query.filter(
          datastore_entities.CommandAttempt.hostname == api_request.hostname)
    if api_request.device_serial is not None:
      query = query.filter(
          datastore_entities.CommandAttempt.device_serial
          == api_request.device_serial)
    query = query.order(-datastore_entities.CommandAttempt.create_time)
    if api_request.offset is not None and api_request.count is not None:
      offset = api_request.offset
      count = api_request.count
    else:
      offset = 0
      count = common.DEFAULT_ROW_COUNT

    command_attempt_entities = query.fetch(count, offset=offset)

    attempts = [
        datastore_entities.ToMessage(attempt)
        for attempt in command_attempt_entities]
    return api_messages.CommandAttemptMessageCollection(
        command_attempts=attempts)
