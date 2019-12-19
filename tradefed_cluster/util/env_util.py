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

"""A module for configurations for different environments."""

import os

ENV_PROD = 'prod'
ENV_STAGING = 'staging'
ENV_ALPHA = 'alpha'
ENV_BUILD_QA = 'build-qa'
ENV_QA = 'qa'
ENV_DEV = 'dev'

APP_ID = os.environ.get('APPLICATION_ID', '')
if '~' in APP_ID:
  _, APP_ID = APP_ID.split('~', 1)
# Indicates whether it is running in a development server.
if os.environ.get('SERVER_SOFTWARE', 'Development').startswith('Development'):
  ENV = ENV_DEV
elif APP_ID.endswith('-staging'):
  ENV = ENV_STAGING
elif APP_ID.endswith('-alpha'):
  ENV = ENV_ALPHA
elif APP_ID.endswith('-build-qa'):
  ENV = ENV_BUILD_QA
elif APP_ID.endswith('-qa'):
  ENV = ENV_QA
else:
  ENV = ENV_PROD

ZANZIBAR_SERVER_DEV = 'blade:acl-zanzibar-dev'
ZANZIBAR_SERVER_PROD = 'blade:acl-zanzibar-prod'


class EnvConfig(object):
  """Environments configurations."""

  def __init__(self, app_id=APP_ID, env=ENV, **kwargs):
    self.app_id = app_id
    self.env = env

    # update values
    self.__dict__.update(kwargs)


ENV_TO_CONFIG = {
    ENV_PROD: EnvConfig(
        env_suffix='',
        zanzibar_server=ZANZIBAR_SERVER_PROD
    ),
    ENV_STAGING: EnvConfig(
        env_suffix='-' + ENV_STAGING,
        zanzibar_server=ZANZIBAR_SERVER_PROD
    ),
    ENV_ALPHA: EnvConfig(
        env_suffix='-' + ENV_ALPHA,
        zanzibar_server=ZANZIBAR_SERVER_DEV
    ),
    ENV_BUILD_QA: EnvConfig(
        env_suffix='-' + ENV_BUILD_QA,
        zanzibar_server=ZANZIBAR_SERVER_DEV
    ),
    ENV_QA: EnvConfig(
        env_suffix='-' + ENV_QA,
        zanzibar_server=ZANZIBAR_SERVER_DEV
    ),
    ENV_DEV: EnvConfig(
        env_suffix='-' + ENV_ALPHA,
        zanzibar_server=ZANZIBAR_SERVER_DEV
    ),
}

CONFIG = ENV_TO_CONFIG.get(ENV)
