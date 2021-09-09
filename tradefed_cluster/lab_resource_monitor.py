"""Monitor lab resource pubsub and update lab resource to datastore."""
import base64
import datetime
import json
import logging

import flask
import six

from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import env_config
from tradefed_cluster.util import pubsub_client as pubsub_client_lib

BATCH_SIZE = 300
PUBSUB_SUBSCRIPTION = ('projects/%s/subscriptions/lab_resource'
                       % env_config.CONFIG.app_id)
POLL_TIMEOUT_MINS = 5  # Cron jobs have a 10m deadline

APP = flask.Flask(__name__)


def _ProcessMessage(message):
  """Process lab resource message."""
  host = message.get('host')
  if not host:
    return
  entity = datastore_entities.HostResource.FromJson(host)
  old_entity = entity.key.get()
  if not old_entity:
    entity.put()
    return
  if not old_entity.event_timestamp:
    entity.put()
    return
  if not entity.event_timestamp:
    logging.debug('No timestamp in message, ignore.')
    return
  if old_entity.event_timestamp > entity.event_timestamp:
    return
  entity.put()


def _Pull(topic):
  """Pull messages from lab resource pubsub topic."""

  pubsub_client = pubsub_client_lib.PubSubClient()
  pubsub_client.CreateSubscription(PUBSUB_SUBSCRIPTION, topic)
  message_count = 0

  end_time = common.Now() + datetime.timedelta(minutes=POLL_TIMEOUT_MINS)
  while common.Now() < end_time:
    messages = pubsub_client.PullMessages(PUBSUB_SUBSCRIPTION, BATCH_SIZE)
    if not messages:
      break
    ack_ids = []
    try:
      for message in messages:
        try:
          pubsub_message = message.get('message')
          data = json.loads(base64.b64decode(
              six.ensure_str(pubsub_message.get('data'))))
          _ProcessMessage(data)
          message_count += 1
          ack_ids.append(message.get('ackId'))
        except Exception:            logging.exception('error processing message: %s', message)
    finally:
      if ack_ids:
        pubsub_client.AcknowledgeMessages(PUBSUB_SUBSCRIPTION, ack_ids)
  logging.info('Processed %d pubsub messages', message_count)


@APP.route('/cron/monitor/lab_resource')
def PullLabResource():
  """Task to pull lab resource from pubsub topic."""
  if env_config.CONFIG.lab_resource_pubsub_topic:
    logging.debug(
        'Get lab resource from %s.',
        env_config.CONFIG.lab_resource_pubsub_topic)
    _Pull(env_config.CONFIG.lab_resource_pubsub_topic)
  else:
    logging.debug('Lab resource pubsub topic is not configured. Skip polling.')
  return common.HTTP_OK
