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
"""A module for appengine auths."""

from google.auth import compute_engine
from google.auth.transport import requests


def GetComputeEngineCredentials():
  """Get the compute engine credentials.

  Returns:
    An instance of compute_engine.Credentials.
  """
  credentials = compute_engine.Credentials()
  request = requests.Request()
  credentials.refresh(request)
  return credentials
