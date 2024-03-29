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

  def UpsertDoc(self, index_name, doc_id, document):
    """Insert or update a document.

    Args:
      index_name: the index
      doc_id: Unique id
      document: an entity
    """
    self._GetEsClient().index(index_name, id=doc_id, body=document)

  def Search(self, index_name, query):
    """Fetches a page of results based on the provided query.

    Args:
      index_name: the index
      query: query to apply

    Returns:
     tuple(list of elements).
    """
    results = self._GetEsClient().search(index=index_name, body=query)
    return [hit['_source'] for hit in results['hits']['hits']]
