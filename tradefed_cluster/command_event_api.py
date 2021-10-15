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

"""API module to serve command event service calls."""

import json

from protorpc import message_types
from protorpc import protojson
from protorpc import remote

from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import command_event_handler


@api_common.tradefed_cluster_api.api_class(resource_name="command_events",
                                           path="command_events")
class CommandEventApi(remote.Service):
  """A class for command events API service."""

  @api_common.method(
      api_messages.CommandEventList,
      message_types.VoidMessage,
      path="/command_events",
      http_method="POST",
      name="submit")
  def SubmitCommandEvents(self, request):
    """Submit a bundle of cluster command events for processing.

    Args:
      request: a CommandEventList
    Returns:
      a VoidMessage
    """

    # Convert the request message to json for the taskqueue payload
    json_message = json.loads(protojson.encode_message(request))  # pytype: disable=module-attr
    command_event_handler.EnqueueCommandEvents(json_message["command_events"])
    return message_types.VoidMessage()
