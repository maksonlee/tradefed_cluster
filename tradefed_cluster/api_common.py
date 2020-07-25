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

from tradefed_cluster.util.ndb_shim import ndb

from google import auth
from google.cloud.ndb import context as context_module

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


def with_ndb_context(method):
  """Decorator to wrap individual endpoints in NDB Context."""

  def wrap_endpoint(*args, **kwargs):
    """Wraps the endpoint method in a NDB Context."""
    context = context_module.get_context(raise_context_error=False)
    if not context:
      creds, project = auth.default()
      with ndb.Client(project=project, credentials=creds).context():
        return method(*args, **kwargs)
    # If endpoint is inside a NDB context don't create a new context.
    return method(*args, **kwargs)

  return wrap_endpoint
