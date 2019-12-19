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

"""Util for datastore query."""
import logging

from google.appengine.ext import ndb


def FetchPage(query, page_size, page_cursor=None, backwards=False):
  """Fetches a page of results based on the provided cursors.

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
    reversed_query = ndb.Query(
        kind=query.kind, filters=query.filters, orders=orders.reversed())
    results, cursor, more = reversed_query.fetch_page(
        page_size, start_cursor=ndb.Cursor(urlsafe=page_cursor))
    if not more and len(results) < page_size:
      return FetchPage(query, page_size)
    results.reverse()
    next_cursor = page_cursor
    prev_cursor = cursor.urlsafe() if more else None
  else:
    # fetching next page in normal order
    results, cursor, more = query.fetch_page(
        page_size, start_cursor=ndb.Cursor(urlsafe=page_cursor))
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
