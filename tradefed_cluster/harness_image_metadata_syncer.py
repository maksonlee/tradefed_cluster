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
from tradefed_cluster import datastore_util
from tradefed_cluster import env_config
from tradefed_cluster.util import auth
from tradefed_cluster.util import ndb_shim as ndb

APP = flask.Flask(__name__)

# The URL base to read image version metadata from GCP Artifact Registry
_LIST_VERSION_URL_BASE = (
    'https://artifactregistry.googleapis.com/v1/projects/dockerized-tradefed/'
    'locations/us/repositories/gcr.io/packages/tradefed/versions'
    '?view=FULL&page_size=100&page_token=')
# Format to parse datetime
_TIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
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
# Template to create image url with SHA
_IMAGE_WITH_SHA_TMPL = '{}@{}'
# Delete image metadata older than the period
_STALE_METADATA_MAX_AGE = datetime.timedelta(days=180)


@APP.route(r'/cron/syncer/sync_harness_image_metadata')
def SyncHarnessImageMetadata():
  """The job to read image manifest from GCR and write to NDB."""
  if not env_config.CONFIG.should_sync_harness_image:
    return common.HTTP_OK
  logging.debug('"should_sync_harness_image" is enabled.')

  creds = auth.GetComputeEngineCredentials()
  versions = []
  page_token = ''
  try:
    while True:
      url = _LIST_VERSION_URL_BASE + page_token
      response = requests.get(
          url=url,
          headers={'Authorization': _AUTHORIZATION_TMPL.format(creds.token)})
      response_json = response.json()
      batch_versions = response_json.get('versions', [])
      logging.info('Fetched %d image versions with page token %s.',
                   len(batch_versions), page_token)
      versions.extend(batch_versions)
      page_token = response_json.get('nextPageToken')
      if not page_token:
        break
  except requests.exceptions.HTTPError as http_error:
    logging.exception('Error in http request to get image manifest from GCR.')
    raise http_error

  time_now = datetime.datetime.utcnow()

  entities_to_update = []
  for version in versions:
    digest = 'sha256:' + version.get('name', '').split('sha256:')[-1]
    current_tags = []
    for tag_obj in version.get('relatedTags', []):
      tag = tag_obj.get('name', '').split('tags/')[-1]
      current_tags.append(tag)
    analysis_result = _AnalyseTradefedDockerImageTags(current_tags)
    historical_tags = []
    if analysis_result['is_historical_golden']:
      historical_tags.append(_GOLDEN_TAG)
    key = ndb.Key(
        datastore_entities.TestHarnessImageMetadata,
        _IMAGE_METADATA_KEY_TMPL.format(_DEFAULT_TRADEFED_REPO, digest))
    time_created = datetime.datetime.strptime(
        version.get('createTime'), _TIME_FORMAT)
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

  # Delete stale image metadata
  datastore_util.DeleteEntitiesUpdatedEarlyThanSomeTimeAgo(
      datastore_entities.TestHarnessImageMetadata,
      datastore_entities.TestHarnessImageMetadata.sync_time,
      _STALE_METADATA_MAX_AGE)

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


def _GetTestHarnessImageMetadata(repo_name, image_tag):
  """Get a TestHarnessImageMetadata entity.

  Args:
    repo_name: string, repo name.
    image_tag: string, image tag.

  Returns:
    A entity of TestHarnessImageMetadata, or None.
  """
  result = None
  response = list(datastore_entities.TestHarnessImageMetadata.query().filter(
      datastore_entities.TestHarnessImageMetadata.repo_name ==
      repo_name).filter(datastore_entities.TestHarnessImageMetadata.current_tags
                        == image_tag).fetch(1))
  if response:
    result = response[0]
  return result


def _SplitImageUrlIntoRepoAndTag(image_url):
  """Split image url to tuple of repo_name and image_tag.

  Args:
    image_url: string, image url.

  Returns:
    string, repo name.
    string, image tag name.
  """
  delimiter = ':'
  default_tag = 'latest'
  if delimiter in image_url:
    repo_name, image_tag = image_url.split(delimiter, 1)
  else:
    repo_name = image_url
    image_tag = default_tag
  return repo_name, image_tag


def AreHarnessImagesEqual(image_url_a, image_url_b):
  """Helper function to check whether the images behind urls equal.

  Args:
    image_url_a: string, url to image A.
    image_url_b: string, url to image B.

  Returns:
    bool, whether two images urls links to the same image digest.
  """

  if image_url_a == image_url_b:
    return True
  if not image_url_a or not image_url_b:
    return False

  repo_a, tag_a = _SplitImageUrlIntoRepoAndTag(image_url_a)
  repo_b, tag_b = _SplitImageUrlIntoRepoAndTag(image_url_b)
  image_a = _GetTestHarnessImageMetadata(repo_a, tag_a)
  image_b = _GetTestHarnessImageMetadata(repo_b, tag_b)
  if image_a and image_b and image_a.digest == image_b.digest:
    return True
  return False


def GetHarnessVersionFromImageUrl(image_url):
  """Helper function to get test harness version number from image url.

  Args:
    image_url: string, url to the image.

  Returns:
    A string, representing the version number in text.
  """
  repo, tag = _SplitImageUrlIntoRepoAndTag(image_url)
  image_metadata = _GetTestHarnessImageMetadata(repo, tag)
  version = common.UNKNOWN_TEST_HARNESS_VERSION
  if image_metadata and image_metadata.test_harness_version:
    version = image_metadata.test_harness_version
  return version


def GetHarnessImageWithShaFromImageUrlWithTag(image_url):
  """Helpler funtion to get <image>@<sha> from <image>:<tag>.

  Args:
    image_url: string, url to the image with tag name.

  Returns:
    A optional string, the url to image with SHA; None, if SHA is not found.
  """
  repo, tag = _SplitImageUrlIntoRepoAndTag(image_url)
  image_metadata = _GetTestHarnessImageMetadata(repo, tag)
  if image_metadata and image_metadata.digest:
    return _IMAGE_WITH_SHA_TMPL.format(repo, image_metadata.digest)
  return None
