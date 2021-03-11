"""Monitor requests until they reach a final state."""

import datetime
import json
import logging

import flask

from tradefed_cluster import command_event
from tradefed_cluster import command_manager
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import request_manager
from tradefed_cluster.services import task_scheduler
from tradefed_cluster.util import ndb_shim as ndb

REQUEST_SYNC_QUEUE = 'request-sync-queue'
REQUEST_ID_KEY = 'request_id'

# Wait 1 second if there were events.
SHORT_SYNC_COUNTDOWN_SECS = 1

# Wait 10 seconds before checking again if there are no events
LONG_SYNC_COUNTDOWN_SECS = 10

# Force a check for events at least once every minute
FORCE_REQUEST_SYNC_SECS = 60

APP = flask.Flask(__name__)


class RequestSyncStatusNotFoundError(Exception):
  """Unable to find the Request sync status."""
  pass


def _AddRequestToQueue(request_id, countdown_secs=LONG_SYNC_COUNTDOWN_SECS):
  """Add a request to the sync queue."""
  payload = json.dumps({
      REQUEST_ID_KEY: request_id,
  })

  next_sync = common.Now() + datetime.timedelta(seconds=countdown_secs)
  logging.info('Queueing request %s to be synced at %s', request_id, next_sync)
  task = task_scheduler.AddTask(
      queue_name=REQUEST_SYNC_QUEUE, payload=payload, eta=next_sync)
  logging.info('Queued task: %s', task)


def GetRequestSyncStatusKey(request_id):
  """Generate the key for a RequestSyncStatusEntity."""
  return ndb.Key(
      datastore_entities.RequestSyncStatus,
      request_id,
      namespace=common.NAMESPACE)


def Monitor(request_id):
  """Monitor the given request ID."""
  logging.info('Monitoring request: %s', request_id)

  _AddRequestToQueue(request_id)

  key = GetRequestSyncStatusKey(request_id)
  if key.get():
    logging.warning('Sync status already exists for %s', request_id)
    return

  sync_status = datastore_entities.RequestSyncStatus(
      key=key, request_id=request_id)
  sync_status.put()


@ndb.transactional()
def _UpdateSyncStatus(request_id):
  """Update the RequestSyncStatus in a transaction.

  Args:
    request_id: The request ID as a string

  Returns:
    True if the request should be synced. False otherwise.

  Raises:
    RequestSyncStatusNotFoundError: the a RequestSyncStatus is not found for the
      given request.
  """
  sync_status_key = GetRequestSyncStatusKey(request_id)
  sync_status = sync_status_key.get()

  if not sync_status:
    # This should not happen. If it does, that would mean that put() operation
    # in Monitor() failed after adding the request which would have caused
    # CreateRequest to also fail.
    raise RequestSyncStatusNotFoundError('No RequestSyncStatus found for: %s' %
                                         request_id)

  should_sync = False
  if sync_status.has_new_command_events:
    logging.info('Request %s has new command events.', request_id)
    sync_status.has_new_command_events = False
    should_sync = True
  elif not sync_status.last_sync_time:
    logging.info('Request %s does not have a last sync time.', request_id)
    should_sync = True
  elif (datetime.timedelta(seconds=FORCE_REQUEST_SYNC_SECS) <
        (common.Now() - sync_status.last_sync_time)):
    logging.info('Request %s was last synced on %s.', request_id,
                 sync_status.last_sync_time)
    should_sync = True

  if should_sync:
    sync_status.last_sync_time = common.Now()

  sync_status.put()
  return should_sync


def StoreCommandEvent(event):
  """Stores the command event to be processed later.

  Args:
    event: a CommandEvent
  """
  _SetNewCommandEvents(event.request_id)
  raw_event = datastore_entities.RawCommandEvent(
      request_id=event.request_id,
      command_id=event.command_id,
      attempt_id=event.attempt_id,
      event_timestamp=event.time,
      payload=event.event_dict,
      namespace=common.NAMESPACE)
  raw_event.put()


def _ProcessCommandEvents(request_id):
  """Process all raw command events for the given request.

  Args:
    request_id: ID of the request to process all its events for.
  """
  raw_events = datastore_entities.RawCommandEvent.query(
      datastore_entities.RawCommandEvent.request_id == request_id,
      namespace=common.NAMESPACE).order(
          datastore_entities.RawCommandEvent.event_timestamp)

  raw_events_keys_to_delete = []
  for raw_event in raw_events:
    event = command_event.CommandEvent(**raw_event.payload)
    command_manager.ProcessCommandEvent(event)
    raw_events_keys_to_delete.append(raw_event.key)

  logging.info('Processed %d events for request %s',
               len(raw_events_keys_to_delete), request_id)
  if raw_events_keys_to_delete:
    ndb.delete_multi(raw_events_keys_to_delete)


def _SetNewCommandEvents(request_id):
  """Set the has_new_command_events=True for the given request."""
  sync_status_key = GetRequestSyncStatusKey(request_id)
  sync_status = sync_status_key.get()

  if not sync_status:
    logging.error(
        'Unable find sync status for %s. This can happen when events '
        'arrived after the request is final.', request_id)
    return

  if not sync_status.has_new_command_events:
    sync_status.has_new_command_events = True
    sync_status.put()


def SyncRequest(request_id):
  """Sync the request for the given ID.

  Check for pending command events for the given request and process them in
  order of their timestamps until the request reaches a final state.

  If command events aren't available or the request isn't final, add the request
  back to the sync queue.

  Args:
    request_id: The request ID as a string
  """
  should_sync = _UpdateSyncStatus(request_id)
  if not should_sync:
    logging.info('Not syncing request %s', request_id)
    _AddRequestToQueue(request_id)
    return

  request = request_manager.GetRequest(request_id)
  if not request:
    # This should not happen. Requires further debugging.
    logging.error('No request found with ID: %s', request_id)
    key = GetRequestSyncStatusKey(request_id)
    key.delete()
    return

  if common.IsFinalRequestState(request.state):
    # TODO: Process or delete leftover RawCommandEvents
    logging.info('Request %s is final and will no longer be synced', request_id)
    key = GetRequestSyncStatusKey(request_id)
    key.delete()
    return

  logging.info('Syncing request %s', request_id)
  try:
    _ProcessCommandEvents(request_id)
  except:
    logging.exception('Failed to process events for %s', request_id)
    _SetNewCommandEvents(request_id)
    raise

  _AddRequestToQueue(request_id, countdown_secs=SHORT_SYNC_COUNTDOWN_SECS)


@APP.route('/_ah/queue/%s' % REQUEST_SYNC_QUEUE, methods=['POST'])
def HandleRequestTask():
  """Request sync queue handler."""
  payload = flask.request.get_data()
  request_info = json.loads(payload)
  logging.debug('RequestTaskHandler syncing %s', request_info)
  try:
    SyncRequest(request_info[REQUEST_ID_KEY])
  except RequestSyncStatusNotFoundError:
    # Do not retry missing RequestSyncStatus
    logging.warning('Missing request sync status for %s', request_info)

  return common.HTTP_OK
