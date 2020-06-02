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

"""Tests for Dimension API."""

import datetime
import unittest

from protorpc import protojson

from tradefed_cluster import api_messages
from tradefed_cluster import api_test
from tradefed_cluster import datastore_test_util


class FilterHintApiTest(api_test.ApiTest):
  """Unit test for FilterHintApi."""

  TIMESTAMP = datetime.datetime.utcfromtimestamp(1431712965)

  def setUp(self):
    api_test.ApiTest.setUp(self)

  def testListClusters_keys(self):
    """Tests ListClusters' keys."""
    cluster_list = [
        datastore_test_util.CreateCluster(cluster='free'),
        datastore_test_util.CreateCluster(cluster='paid')
    ]
    api_request = {'type': 'POOL'}
    api_response = self.testapp.post_json(
        '/_ah/api/FilterHintApi.ListFilterHints', api_request)
    cluster_collection = protojson.decode_message(
        api_messages.FilterHintCollection, api_response.body)
    self.assertEqual('200 OK', api_response.status)
    clusters = list(cluster_collection.filter_hints)
    self.assertEqual(clusters[0].value, cluster_list[0].cluster)
    self.assertEqual(clusters[1].value, cluster_list[1].cluster)

if __name__ == '__main__':
  unittest.main()
