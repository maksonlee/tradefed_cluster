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
"""The module to sync test harness image metadata in a cron job."""

import datetime
import logging
import re
import flask
import requests

from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config
from tradefed_cluster.util import auth
from tradefed_cluster.util import ndb_shim as ndb

APP = flask.Flask(__name__)

# The url to read image metadata from GCR.
_LIST_TAGS_URL = 'https://gcr.io/v2/dockerized-tradefed/tradefed/tags/list'
# Authorization header template.
_AUTHORIZATION_TMPL = 'Bearer {}'
# Tradefed tag regex patterns
_HISTORICAL_GOLDEN_PATTERN = re.compile(
    r'^golden_tradefed_image_\d{8}_\d{4}_RC\d+$')
_VERSION_NUMBER_PATTERN = re.compile(r'^\d+$')
# Tradefed tags
_GOLDEN_TAG = 'golden'
_CANARY_TAG = 'canary'
_STAGING_TAG = 'staging'
# Default tradefed repo
_DEFAULT_TRADEFED_REPO = 'gcr.io/dockerized-tradefed/tradefed'
# Tradefed Harness name
_TRADEFED_HARNESS_NAME = 'tradefed'
# Template to create image metadata datastore key
_IMAGE_METADATA_KEY_TMPL = '{}:{}'


@APP.route(r'/cron/syncer/sync_harness_image_metadata')
def SyncHarnessImageMetadata():
  """The job to read image manifest from GCR and write to NDB."""
  if not env_config.CONFIG.should_sync_harness_image:
    return common.HTTP_OK
  logging.debug('"should_sync_harness_image" is enabled.')

  creds = auth.GetComputeEngineCredentials()
  try:
    response = requests.get(
        url=_LIST_TAGS_URL,
        headers={'Authorization': _AUTHORIZATION_TMPL.format(creds.token)})
  except requests.exceptions.HTTPError as http_error:
    logging.exception('Error in http request to get image manifest from GCR.')
    raise http_error
  response_json = response.json()
  manifest = response_json.get('manifest')
  if not manifest:
    raise KeyError(
        'No valid image manifest is in the response: {}'.format(response_json))

  time_now = datetime.datetime.utcnow()

  entities_to_update = []
  for digest, data in manifest.items():
    current_tags = data.get('tag', [])
    analysis_result = _AnalyseTradefedDockerImageTags(current_tags)
    historical_tags = []
    if analysis_result['is_historical_golden']:
      historical_tags.append(_GOLDEN_TAG)
    key = ndb.Key(
        datastore_entities.TestHarnessImageMetadata,
        _IMAGE_METADATA_KEY_TMPL.format(_DEFAULT_TRADEFED_REPO, digest))
    time_created = datetime.datetime.utcfromtimestamp(
        int(data['timeCreatedMs']) / 1000)
    entity = datastore_entities.TestHarnessImageMetadata(
        key=key,
        repo_name=_DEFAULT_TRADEFED_REPO,
        digest=digest,
        test_harness=_TRADEFED_HARNESS_NAME,
        test_harness_version=analysis_result['tradefed_version_number'],
        current_tags=current_tags,
        historical_tags=historical_tags,
        create_time=time_created,
        sync_time=time_now)
    entities_to_update.append(entity)

  ndb.put_multi(entities_to_update)

  return common.HTTP_OK


def _AnalyseTradefedDockerImageTags(tags):
  """Analyse tags of a Tradefed image.

  Args:
    tags: list of text, the tags of a image.

  Returns:
    A python dict containing the following key-value pairs:
      - tradefed_version_number, image version as text, or None if not found.
      - is_historical_golden, bool, whether the image was ever labeled golden.
  """
  result = {
      'tradefed_version_number': None,
      'is_historical_golden': False,
  }
  for tag in tags:
    if _VERSION_NUMBER_PATTERN.match(tag):
      result['tradefed_version_number'] = tag
      continue
    if _HISTORICAL_GOLDEN_PATTERN.match(tag):
      result['is_historical_golden'] = True
  return result
