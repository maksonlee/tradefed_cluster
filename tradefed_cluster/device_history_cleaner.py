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

"""Module for device history cleanup cron job."""

import datetime
import logging

import webapp2

from google.appengine.ext import db
from google.appengine.ext import ndb

from tradefed_cluster import datastore_entities

DEVICE_HISTORY_RENTENTION_DAYS = 100
BATCH_SIZE = 200
DEFAULT_DEADLINE = 60  # Query deadline in seconds
# The GAE frontend timeout is 10 minutes. So let's restart the request after
# 8 minutes.
TIMEOUT_MINUTES = 8


def RetrieveKeys(end_date):
  """Retrieve DeviceStateHistory keys that are older than a given end date.

  The keys are yielded in batches to reduce the likelyhood of timeouts.

  Args:
    end_date: date to compare against the DeviceStateHistory timestamp
  Yields:
    Lists of keys older than the given end_date.
  """
  while True:
    query = datastore_entities.DeviceStateHistory.query(
        datastore_entities.DeviceStateHistory.timestamp < end_date)
    keys = []
    # Do not use the cache as the keys are being retrieved for deletion.
    for key in query.iter(
        limit=BATCH_SIZE, keys_only=True, use_cache=False, use_memcache=False,
        deadline=DEFAULT_DEADLINE):
      keys.append(key)
    yield keys
    if len(keys) < BATCH_SIZE:
      break


def _Now():
  """Returns the current time in UTC. Added to allow mocking in our tests."""
  return datetime.datetime.utcnow()


def DeleteEntities(retention_days):
  """Delete DeviceStateHistory entities older than the retention days.

  Args:
    retention_days: Number of days to keep in datastore.
  Returns:
    Number of entities deleted.
  """
  now = _Now()
  end_date = now - datetime.timedelta(days=retention_days)
  request_end_time = now + datetime.timedelta(minutes=TIMEOUT_MINUTES)
  deleted = 0
  for keys_to_delete in RetrieveKeys(end_date):
    try:
      ndb.delete_multi(keys_to_delete)
      deleted += len(keys_to_delete)
      logging.info("Deleted: %d keys. Total: %d", len(keys_to_delete), deleted)
      if _Now() > request_end_time:
        logging.info("End the request after %r minutes.", TIMEOUT_MINUTES)
        break
    except db.Error:
      logging.exception("Datastore error while deleting device history.")
  return deleted


class DeviceHistoryCleanerHandler(webapp2.RequestHandler):
  """Request handler for cleaning up device history."""

  def get(self):
    """Start the device history cleanup."""
    logging.info("Started DeviceHistoryCleaner")
    number_deleted = DeleteEntities(DEVICE_HISTORY_RENTENTION_DAYS)
    self.response.write(str(number_deleted))
    logging.info("Finished DeviceHistoryCleaner. Deleted: %d", number_deleted)

APP = webapp2.WSGIApplication(
    [(r"/.*", DeviceHistoryCleanerHandler)], debug=True)
