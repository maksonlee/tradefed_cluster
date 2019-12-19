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

"""API module to serve run target service calls."""

from protorpc import message_types
from protorpc import messages
from protorpc import remote

import endpoints

from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import device_manager


class RunTargetCollection(messages.Message):
  """A class representing a collection of run targets."""
  run_targets = messages.MessageField(api_messages.RunTarget, 1, repeated=True)


@api_common.tradefed_cluster_api.api_class(resource_name="runTargets",
                                           path="runTargets")
class RunTargetApi(remote.Service):
  """A class for run target API service."""

  RUN_TARGET_LIST_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage, cluster=messages.StringField(1))

  @endpoints.method(RUN_TARGET_LIST_RESOURCE, RunTargetCollection,
                    path="/runTargets", http_method="GET", name="list")
  def ListRunTargets(self, request):
    """Fetches a list of run targets.

    Args:
      request: an API request.
    Returns:
      a RunTargetCollection object.
    """
    run_targets = device_manager.GetRunTargetsFromNDB(request.cluster)
    converted_run_targets = [
        api_messages.RunTarget(name=r) for r in run_targets]
    return RunTargetCollection(run_targets=converted_run_targets)

