# Lint as: python2, python3
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
"""Util for datastore query."""
import logging
import six

from tradefed_cluster.util import ndb_shim as ndb
# TODO: Remove gae_ndb is no longer used
from google.appengine.ext import ndb as gae_ndb


def FetchPage(query, page_size, page_cursor=None, backwards=False,
              result_filter=None):
  """Fetches a page of results based on the provided cursors.

  Args:
    query: query to apply, must be ordered
    page_size: maximum number of results to fetch
    page_cursor: marks the position to fetch from
    backwards: True to fetch the page that precedes the cursor
    result_filter (Callable[[ndb.Model], bool]): post-query predicate to apply

  Returns:
    tuple(list of elements, prev cursor, next cursor).
  """

  if isinstance(query, ndb.Query):
    return GoogleCloudFetchPage(query, page_size,
                                page_cursor=page_cursor, backwards=backwards,
                                result_filter=result_filter)
  else:
    # TODO: Clean up legacy NDB behaviour
    return AppEngineFetchPage(query, page_size,
                              page_cursor=page_cursor, backwards=backwards)


def GoogleCloudFetchPage(query, page_size, page_cursor=None, backwards=False,
                         result_filter=None):
  """Fetches a page of results based on the provided cursors.

  Args:
    query: query to apply, must be ordered
    page_size: maximum number of results to fetch
    page_cursor: marks the position to fetch from
    backwards: True to fetch the page that precedes the cursor
    result_filter (Callable[[ndb.Model], bool]): post-query predicate to apply

  Returns:
    page of results
  """
  if not page_cursor:
    # no pagination information, fetch first page in normal order
    results, cursor, more = _FetchPageWithIterator(
        query, page_size, None, result_filter)
    next_cursor = cursor.urlsafe() if more else None
    prev_cursor = None
  elif backwards:
    # fetching previous page in reverse order
    reversed_query = ndb.Query(
        ancestor=query.ancestor,
        kind=query.kind,
        filters=query.filters,
        orders=[-order for order in query.order_by])
    results, cursor, more = _FetchPageWithIterator(
        reversed_query, page_size,
        ndb.Cursor(urlsafe=six.ensure_str(page_cursor)),
        result_filter)
    if not more and len(results) < page_size:
      return FetchPage(query, page_size)
    results.reverse()
    next_cursor = page_cursor
    prev_cursor = cursor.urlsafe() if more else None
  else:
    # fetching next page in normal order
    results, cursor, more = _FetchPageWithIterator(
        query, page_size, ndb.Cursor(urlsafe=six.ensure_str(page_cursor)),
        result_filter)
    next_cursor = cursor.urlsafe() if more else None
    prev_cursor = page_cursor
  if prev_cursor:
    prev_cursor = six.ensure_str(prev_cursor)
  if next_cursor:
    next_cursor = six.ensure_text(next_cursor)
  return results, prev_cursor, next_cursor


def _FetchPageWithIterator(query, page_size, start_cursor, result_filter):
  """Iterates over query results to accumulate a page of results.

  This has the same behavior as fetch_page (which also iterates over query
  results with internal batching), but relies on has_next instead of
  probably_has_next to determine the next cursor.

  This can be slower for small page_sizes as fetch_page will limit the batch to
  min(page_size, batch_size). However, this prevents post-query filtering.

  Args:
    query: query to apply, must be ordered
    page_size: maximum number of results to fetch
    start_cursor: marks the position to fetch from
    result_filter (Callable[[ndb.Model], bool]): post-query predicate to apply
  Returns:
    results: list of entities
    next_cursor: position of the next set of results if there are more results
    more: True if there are more results
  See:
    cs/google3/third_party/py/google/cloud/ndb/query.py;l=2387
  """
  it = query.iter(start_cursor=start_cursor)
  results = []
  while len(results) < page_size and it.has_next():
    result = next(it)
    if not result_filter or result_filter(result):
      results.append(result)
  next_cursor = it.cursor_after() if results else None
  return results, next_cursor, next_cursor and it.has_next()


def AppEngineFetchPage(query, page_size, page_cursor=None, backwards=False):
  """Fetches a page of results based on the provided cursors.

  DEPRECATED: will be removed once we migrate out of GAE NDB in TFC & MTT

  Args:
    query: query to apply, must be ordered
    page_size: maximum number of results to fetch
    page_cursor: marks the position to fetch from
    backwards: True to fetch the page that precedes the cursor

  Returns:
    page of results
  """
  if not page_cursor:
    # no pagination information, fetch first page in normal order
    results, cursor, more = query.fetch_page(page_size)
    next_cursor = cursor.urlsafe() if more else None
    prev_cursor = None
  elif backwards:
    # fetching previous page in reverse order
    orders = query.orders
    if query.ancestor is not None:
      reversed_query = gae_ndb.Query(
          ancestor=query.ancestor,
          kind=query.kind,
          filters=query.filters,
          orders=orders.reversed())
    else:
      reversed_query = gae_ndb.Query(
          kind=query.kind, filters=query.filters, orders=orders.reversed())
    results, cursor, more = reversed_query.fetch_page(
        page_size, start_cursor=gae_ndb.Cursor(urlsafe=page_cursor))
    if not more and len(results) < page_size:
      return FetchPage(query, page_size)
    results.reverse()
    next_cursor = page_cursor
    prev_cursor = cursor.urlsafe() if more else None
  else:
    # fetching next page in normal order
    results, cursor, more = query.fetch_page(
        page_size, start_cursor=gae_ndb.Cursor(urlsafe=page_cursor))
    next_cursor = cursor.urlsafe() if more else None
    prev_cursor = page_cursor
  return results, prev_cursor, next_cursor


def BatchQuery(query, batch_size, keys_only=False, projection=None):
  """Query by batch.

  Args:
    query: the ndb.Query
    batch_size: batch size
    keys_only: only return keys
    projection: projection of the query

  Yields:
    entity
  """
  cursor = None
  more = True
  while more:
    params = {}
    if cursor:
      params['start_cursor'] = cursor
    if keys_only:
      params['keys_only'] = keys_only
    if projection:
      params['projection'] = projection
    logging.debug('Process batch (%s, %r).', cursor, batch_size)
    entities, cursor, more = query.fetch_page(batch_size, **params)
    for entity in entities:
      yield entity


def GetOrCreateEntity(entity_type, entity_id=None, **kwargs):
  """Get or create a datastore entity.

  Get the datastore entity by its id and type. If id is not provided, then
  create entity with type and its fields in kwargs.

  Args:
    entity_type: a class name, which is a subclass of ndb.model, for the entity
      type.
    entity_id: id of the datastore entity.
    **kwargs: the fileds to create the datastore entity, if entity_id is
      unavailable.

  Returns:
    An instance of entity_type datastore entity.
  """
  if entity_id:
    entity = ndb.Key(entity_type, entity_id).get()
    if entity:
      return entity
    logging.debug('Could not find the datastore entity by (%s, %s).',
                  entity_type, entity_id)
  return entity_type(**kwargs)
