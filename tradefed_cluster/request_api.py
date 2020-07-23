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

"""API module to serve request service calls."""
import logging

import endpoints
from protorpc import message_types
from protorpc import messages
from protorpc import remote

from tradefed_cluster.util import ndb_shim as ndb

from tradefed_cluster import api_common
from tradefed_cluster import api_messages
from tradefed_cluster import command_manager
from tradefed_cluster import command_monitor
from tradefed_cluster import common
from tradefed_cluster import datastore_entities
from tradefed_cluster import request_manager


@api_common.tradefed_cluster_api.api_class(
    resource_name="requests", path="requests")
class RequestApi(remote.Service):
  """A class for request API service."""

  def _CheckAuth(self):
    """Check whether a request is authorized or not.

    Raises:
      endpoints.UnauthorizedException if a request is not authorized
    """
    user = endpoints.get_current_user()
    if not user:
      raise endpoints.UnauthorizedException("A request is not authenticated.")

    logging.info("request from user %s", user)
    # TODO: Add additional authorization logic here.

  @endpoints.method(
      api_messages.NewRequestMessage,
      api_messages.RequestMessage,
      path="/requests",
      http_method="POST",
      name="new"
  )
  def NewRequest(self, request):
    """Create a new request.

    Args:
      request: a request to create.
    Returns:
      a new request object with a valid ID.
    """
    # TODO: figure a better way for auth.
    # self._CheckAuth()
    logging.info("Request API new request start: %s", request.user)
    if not request.user:
      raise endpoints.BadRequestException("user cannot be null.")
    if not request.command_line:
      raise endpoints.BadRequestException("command_line cannot be null.")

    prev_test_context_obj = None
    if request.prev_test_context:
      prev_test_context_obj = datastore_entities.TestContext.FromMessage(
          request.prev_test_context)

    plugin_data_ = api_messages.KeyValuePairMessagesToMap(request.plugin_data)

    logging.info("Request API new request before create request: %s",
                 request.user)

    new_request = request_manager.CreateRequest(
        request.user,
        request.command_line,
        priority=request.priority,
        queue_timeout_seconds=request.queue_timeout_seconds,
        type_=request.type,
        cluster=request.cluster,
        run_target=request.run_target,
        run_count=request.run_count,
        shard_count=request.shard_count,
        plugin_data=plugin_data_,
        max_retry_on_test_failures=request.max_retry_on_test_failures,
        prev_test_context=prev_test_context_obj)
    logging.info("Request API new request after create request: %s %s",
                 new_request.key.id(), request.user)
    if request.test_environment:
      request_manager.SetTestEnvironment(
          new_request.key.id(),
          datastore_entities.TestEnvironment.FromMessage(
              request.test_environment))
    logging.info("Request API new request after setting test environment %s %s",
                 new_request.key.id(), request.user)
    for res in request.test_resources or []:
      request_manager.AddTestResource(
          request_id=new_request.key.id(), name=res.name, url=res.url)
    logging.info("Request API new request after adding test resources %s %s",
                 new_request.key.id(), request.user)
    request_manager.AddToQueue(new_request)
    logging.info("Request API new request after adding request to queue %s %s",
                 new_request.key.id(), request.user)
    return api_messages.RequestMessage(
        id=new_request.key.id(),
        api_module_version=common.NAMESPACE)

  REQUEST_LIST_FILTER_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      user=messages.StringField(1, variant=messages.Variant.STRING),
      state=messages.EnumField(common.RequestState, 2),
      offset=messages.IntegerField(3, variant=messages.Variant.INT32),
      count=messages.IntegerField(4, variant=messages.Variant.INT32)
  )

  @endpoints.method(
      REQUEST_LIST_FILTER_RESOURCE,
      api_messages.RequestMessageCollection,
      path="/requests",
      http_method="GET",
      name="list"
  )
  def ListRequest(self, api_request):
    """Get requests satisfy the condition.

    This API does not populate Request.command_attempts field.

    Args:
      api_request: api request contains test request id
    Returns:
      collection of all request
    """
    cur_requests = request_manager.GetRequests(
        user=api_request.user,
        state=api_request.state,
        offset=api_request.offset,
        count=api_request.count)
    res_request_list = [
        datastore_entities.ToMessage(request) for request in cur_requests]
    return api_messages.RequestMessageCollection(requests=res_request_list)

  REQUEST_ID_RESOURCE = endpoints.ResourceContainer(
      message_types.VoidMessage,
      request_id=messages.IntegerField(1, variant=messages.Variant.INT32)
  )

  @endpoints.method(
      REQUEST_ID_RESOURCE,
      api_messages.RequestMessage,
      path="{request_id}",
      http_method="GET",
      name="get"
  )
  def GetRequest(self, api_request):
    """Get a specific test request by id.

    This API populates Request.command_attempts field.

    Args:
      api_request: api request contains test request id
    Returns:
      the test request
    """
    request_id = str(api_request.request_id)
    request = request_manager.GetRequest(request_id)
    if not request:
      raise endpoints.NotFoundException()
    command_attempts = request_manager.GetCommandAttempts(request_id)
    commands = command_manager.GetCommands(request_id)
    message = datastore_entities.ToMessage(
        request,
        command_attempts=command_attempts,
        commands=commands)
    return message

  @endpoints.method(
      REQUEST_ID_RESOURCE,
      api_messages.RequestMessage,
      path="{request_id}/cancel",
      http_method="GET",
      name="cancel"
  )
  def CancelRequest(self, api_request):
    """Cancel a specific test request by id.

    Args:
      api_request: api request contains the test request id
    Returns:
      the test request
    """
    # TODO: figure a better auth check.
    # self._CheckAuth()
    request_id = str(api_request.request_id)
    cur_request = request_manager.GetRequest(request_id)
    if not cur_request:
      raise endpoints.NotFoundException()

    # This should ideally go inside request_manager.CancelRequest.
    # However, it will cause a circular dependency between
    # command_manager and request_manager.
    logging.debug(
        "Cancel request [%s] from API.", api_request.request_id)
    command_manager.CancelCommands(
        request_id=request_id,
        cancel_reason=common.CancelReason.REQUEST_API)

    return datastore_entities.ToMessage(cur_request)

  @endpoints.method(
      REQUEST_ID_RESOURCE,
      api_messages.RequestMessage,
      path="{request_id}",
      http_method="POST",
      name="poke"
  )
  def PokeRequest(self, request):
    """Pokes a request to notify its state via Cloud Pub/Sub.

    This API is for testing the state change notification.

    Args:
      request: an API request.
    Returns:
      a request object.
    """
    request_id = str(request.request_id)
    req = request_manager.GetRequest(request_id)
    if not req:
      raise endpoints.NotFoundException()

    _SyncCommands(request_id)
    request_manager.Poke(request_id)
    return datastore_entities.ToMessage(req)

  @endpoints.method(
      endpoints.ResourceContainer(
          message_types.VoidMessage,
          request_ids=messages.IntegerField(1, repeated=True),
          final_only=messages.BooleanField(2, default=False),
      ),
      message_types.VoidMessage,
      path="poke",
      http_method="POST",
      name="batchPoke"
  )
  def PokeRequests(self, request):
    """Pokes a list of requests to notify their state via Cloud Pub/Sub.

    Args:
      request: an API request.
    Returns:
      a request object.
    """
    logging.info("PokeRequests request: %s", request)
    for request_id in request.request_ids:
      request_id = str(request_id)
      req = request_manager.GetRequest(request_id)
      if not req:
        logging.warning("No request found for id: %r", request_id)
        continue
      _SyncCommands(request_id)
      state = common.RequestState(req.state)
      if request.final_only and state not in common.FINAL_REQUEST_STATES:
        logging.info(
            "Not poking request %s as it is in state %s",
            req.key, state.name)
        continue
      request_manager.Poke(request_id)
    return message_types.VoidMessage()

  @endpoints.method(
      REQUEST_ID_RESOURCE,
      api_messages.TestEnvironment,
      path="{request_id}/test_environment",
      http_method="GET",
      name="testEnvironment.get")
  def GetTestEnvironment(self, request):
    """Returns a test environment for a request.

    Args:
      request: an API request.
    Returns:
      a api_messages.TestEnvironment.
    """
    request_id = str(request.request_id)
    entity = request_manager.GetTestEnvironment(request_id)
    if not entity:
      return api_messages.TestEnvironment()
    return datastore_entities.ToMessage(entity)

  @endpoints.method(
      REQUEST_ID_RESOURCE,
      api_messages.TestResourceCollection,
      path="{request_id}/test_resources",
      http_method="GET",
      name="testResource.list")
  def ListTestResources(self, request):
    """Lists test resources for a request.

    Args:
      request: an API request.
    Returns:
      a api_messages.TestResourceCollection.
    """
    request_id = str(request.request_id)
    request_entities = request_manager.GetTestResources(request_id)
    test_resources = []
    for entity in request_entities:
      test_resources.append(api_messages.TestResource(
          url=entity.url, name=entity.name))
    return api_messages.TestResourceCollection(test_resources=test_resources)

  @endpoints.method(
      REQUEST_ID_RESOURCE,
      api_messages.InvocationStatus,
      path="{request_id}/invocation_status",
      http_method="GET",
      name="invocationStatus.get")
  def GetInvocationStatus(self, request):
    """Returns invocation status for a request.

    Args:
      request: an API request.
    Returns:
      a api_messages.InvocationStatus.
    """
    invocation_status = datastore_entities.InvocationStatus()
    request_id = str(request.request_id)
    commands = command_manager.GetCommands(request_id=request_id)
    for command in commands:
      attempts = command_manager.GetCommandAttempts(
          request_id=request_id, command_id=command.key.id())
      run_count = command.run_count
      for attempt in reversed(attempts):
        # TODO: consider ignoring errored attempts.
        if not attempt.invocation_status:
          continue
        invocation_status.Merge(attempt.invocation_status)
        run_count -= 1
        if run_count <= 0:
          break
    return datastore_entities.ToMessage(invocation_status)

  @endpoints.method(
      endpoints.ResourceContainer(
          message_types.VoidMessage,
          request_id=messages.IntegerField(1, required=True),
          command_id=messages.StringField(2, required=True)),
      api_messages.TestContext,
      path="{request_id}/commands/{command_id}/test_context",
      http_method="GET",
      name="testContext.get")
  def GetTestContext(self, request):
    """Returns a test context for a command.

    Args:
      request: an API request.
    Returns:
      a api_messages.TestContext object.
    """
    command_key = ndb.Key(
        datastore_entities.Request, str(request.request_id),
        datastore_entities.Command, request.command_id,
        namespace=common.NAMESPACE)
    test_context = datastore_entities.TestContext.query(
        ancestor=command_key).get()
    if not test_context:
      test_context = datastore_entities.TestContext(env_vars={})

    # Populate attempt number attribute to let a new attempt to know its
    # position within a series of attempts.

    # Note: the attempt number can collide if there are concurrent attempts
    # started at the same time (e.g. run_count > 1).
    query = datastore_entities.CommandAttempt.query(ancestor=command_key)
    attempt_number = query.count() + 1
    test_context.env_vars["TFC_ATTEMPT_NUMBER"] = str(attempt_number)

    return datastore_entities.ToMessage(test_context)

  @endpoints.method(
      endpoints.ResourceContainer(
          api_messages.TestContext,
          request_id=messages.IntegerField(1, required=True),
          command_id=messages.StringField(2, required=True)),
      message_types.VoidMessage,
      path="{request_id}/commands/{command_id}/test_context",
      http_method="POST",
      name="testContext.update")
  def UpdateTestContext(self, request):
    """Updates a test context for a command.

    Args:
      request: an API request.
    Returns:
      a api_messages.TestResourceCollection.
    """
    test_context = datastore_entities.TestContext(
        command_line=request.command_line,
        env_vars={p.key: p.value for p in request.env_vars},
        test_resources=[
            datastore_entities.TestResource(name=r.name, url=r.url, path=r.path)
            for r in request.test_resources
        ])
    command_manager.UpdateTestContext(
        request_id=request.request_id,
        command_id=request.command_id,
        test_context=test_context)
    return message_types.VoidMessage()

  @endpoints.method(
      endpoints.ResourceContainer(
          message_types.VoidMessage,
          request_id=messages.StringField(1, required=True),
          command_id=messages.StringField(2, required=True)),
      api_messages.CommandMessage,
      path="{request_id}/commands/{command_id}",
      http_method="GET",
      name="command"
  )
  def GetCommand(self, request):
    command = command_manager.GetCommand(request.request_id, request.command_id)
    if not command:
      raise endpoints.NotFoundException(
          "Command {0} {1} not found.".format(
              request.request_id, request.command_id))
    return datastore_entities.ToMessage(command)


def _SyncCommands(request_id):
  """Sync a request's commands."""
  for command in request_manager.GetCommands(request_id):
    command_monitor.SyncCommand(
        request_id, command.key.id(), add_to_sync_queue=False)
