# Copyright 2020 Google LLC
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

"""App management service.

TFC is consists of multiple web apps. This service provides APIs to access and
manage them.
"""

from tradefed_cluster import env_config


def _GetPlugin():
  if not env_config.CONFIG.app_manager:
    raise ValueError('No app_manager is configured')
  return env_config.CONFIG.app_manager


def GetInfo(name):
  """Gets app info.

  Args:
    name: an app name.
  Returns:
    a AppInfo object.
  """
  return _GetPlugin().GetInfo(name)
