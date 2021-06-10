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
"""Util for elasticsearch query."""

import elasticsearch


class ElasticsearchClient(object):
  """A wrapper class for Elasticsearch API client."""

  def _GetEsClient(self, host='127.0.0.1', port=9200):
    return elasticsearch.Elasticsearch([{'host': host, 'port': port}])

  def GetDoc(self, index_name, doc_id):
    """Fetches the document for a given document id.

    Args:
      index_name: the name of an index.
      doc_id: Unique id

    Returns:
      a document object.
    """
    return self._GetEsClient().get(index=index_name, id=doc_id)['_source']
