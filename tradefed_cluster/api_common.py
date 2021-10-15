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

"""Common components for tradefed cluster api."""
import endpoints

from tradefed_cluster.util import ndb_shim as ndb


# client ID would be anonymous from GAE apps
ANONYMOUS = "anonymous"

# Used for multiclass apis.
tradefed_cluster_api = endpoints.api(
    name="tradefed_cluster",
    version="v1",
    description="Tradefed Cluster API",
    allowed_client_ids=[
        ANONYMOUS,
        endpoints.API_EXPLORER_CLIENT_ID
    ],
    scopes=[endpoints.EMAIL_SCOPE]
)


def method(request_type, response_type, **kwargs):
  """API method decorator."""
  endpoints_wrapper = endpoints.method(request_type, response_type, **kwargs)
  def _wrapper(api_method):
    # Wraps execution in an NDB context
    api_method = ndb.with_ndb_context(api_method)
    # Configures endpoint
    api_method = endpoints_wrapper(api_method)
    return api_method
  return _wrapper

