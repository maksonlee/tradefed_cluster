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

"""API module to serve host event service calls.

Do not change this module's name (host_event_api) as the deferred library
uses it to execute the correct function for tasks in our push queue.
"""

import json
import logging

import endpoints
from protorpc import message_types
from protorpc import messages
from protorpc import protojson
from protorpc import remote

from google.appengine.api import modules
from google.appengine.ext import deferred

from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import device_manager
from tradefed_cluster import host_event

CHUNK_SIZE = 10


def chunks(l, n):
  """Yield successive n-sized chunks from a list.

  Args:
    l: List of elements to split
    n: Number of chunks to split into
  Yields:
    n-sized chunks
  """
  for i in range(0, len(l), n):
    yield l[i:i+n]


class HostEventType(messages.Enum):
  """The different types of host events."""
  DEVICE_SNAPSHOT = 1
  HOST_STATE_CHANGED = 2


class HostEventData(messages.Message):
  """Extra information from the host."""
  pass


class HostEvent(messages.Message):
  """A message class representing a cluster host event."""
  time = messages.IntegerField(1)
  event_type = messages.EnumField(HostEventType, 2)
  hostname = messages.StringField(3)
  # TODO: deprecate physical_cluster, use host_group.
  cluster = messages.StringField(4)
  host_group = messages.StringField(5)
  pools = messages.StringField(6, repeated=True)
  device_infos = messages.MessageField(
      api_messages.DeviceInfo, 7, repeated=True)
  data = messages.MessageField(HostEventData, 8)
  tf_version = messages.StringField(9)
  host_state = messages.EnumField(api_messages.HostState, 10)
  lab_name = messages.StringField(11)


class HostEventList(messages.Message):
  """A message class representing a list of cluster host events."""
  host_events = messages.MessageField(HostEvent, 1, repeated=True)


@api_common.tradefed_cluster_api.api_class(resource_name="host_events",
                                           path="host_events")
class HostEventApi(remote.Service):
  """A class for host events API service."""

  @endpoints.method(HostEventList, message_types.VoidMessage,
                    path="/host_events", http_method="POST", name="submit")
  def SubmitHostEvents(self, request):
    """Submit a bundle of cluster host events for processing.

    Args:
      request: a HostEventList
    Returns:
      a VoidMessage
    """
    # Convert the request message to json for the taskqueue payload
    encoded_message = protojson.encode_message(request)
    json_message = json.loads(encoded_message)
    host_events = json_message["host_events"]
    logging.info("Submitting host event message with size %d and %d events",
                 len(encoded_message), len(host_events))
    for event_chunk in chunks(host_events, CHUNK_SIZE):
      logging.info("Queuing host event chunk of size %d", len(event_chunk))
      deferred.defer(self._ProcessHostEventWithNDB, event_chunk,
                     _queue=host_event.HOST_EVENT_QUEUE_NDB,
                     _target="%s.%s" % (modules.get_current_version_name(),
                                        modules.get_current_module_name()))
    logging.debug("Submitted host event message.")
    return message_types.VoidMessage()

  def _ProcessHostEventWithNDB(self, events):
    """Deferred function to process submitted host events.

    Do not change this function's name (_ProcessHostEventWithNDB) as deferred
    stores it as part of the tasks in the push queue which is used to know
    what to execute when the tasked is dequeued.

    Args:
      events: a A list of host events.
    """
    # TODO: Batch process the host event.
    logging.debug("Processing %d events.", len(events))
    for e in events:
      logging.debug("Processing event: %s.", e)
      if not device_manager.IsHostEventValid(e):
        logging.warn("Host event is invalid. Ignoring: %s", e)
        continue
      event = host_event.HostEvent(**e)
      device_manager.HandleDeviceSnapshotWithNDB(event)
      logging.debug("Finished processing event.")
    logging.debug("Finished processing %d events.", len(events))
