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
"""API module for test harness image metadata."""
import endpoints
from protorpc import messages
from protorpc import remote

from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import datastore_entities
from tradefed_cluster import datastore_util

# Default count of image metadata in the list response.
_DEFAULT_LIST_IMAGES_COUNT = 60


@api_common.tradefed_cluster_api.api_class(
    resource_name="test_harness_images", path="test_harness_images")
class TestHarnessImageApi(remote.Service):
  """A class for harness image API service."""

  TEST_HARNESS_IMAGE_LIST_RESOURCE = endpoints.ResourceContainer(
      count=messages.IntegerField(1, default=_DEFAULT_LIST_IMAGES_COUNT),
      cursor=messages.StringField(2),
      tag_prefix=messages.StringField(3))

  @api_common.method(
      TEST_HARNESS_IMAGE_LIST_RESOURCE,
      api_messages.TestHarnessImageMetadataCollection,
      path="/test_harness_images",
      http_method="GET",
      name="list")
  def ListTestHarnessImages(self, request):
    """List test harness image metadata.

    Args:
      request: an API request.

    Returns:
      An api_messages.TestHarnessImageMetadataCollection object.
    """
    query = datastore_entities.TestHarnessImageMetadata.query()

    if request.tag_prefix:
      query = (
          query.filter(datastore_entities.TestHarnessImageMetadata.current_tags
                       >= request.tag_prefix).filter(
                           datastore_entities.TestHarnessImageMetadata
                           .current_tags < request.tag_prefix + u"\ufffd")
          .order(-datastore_entities.TestHarnessImageMetadata.current_tags))

    query = query.order(
        -datastore_entities.TestHarnessImageMetadata.create_time)

    entities, _, next_cursor = datastore_util.FetchPage(query, request.count,
                                                        request.cursor)

    image_msgs = [datastore_entities.ToMessage(entity) for entity in entities]

    return api_messages.TestHarnessImageMetadataCollection(
        images=image_msgs, next_cursor=next_cursor)
