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

"""A task scheduler service.

This module is developed to replace the legacy usage of GAE Taskqueue.
"""
import logging
import pickle
import types
import uuid

import flask


from tradefed_cluster import common
from tradefed_cluster import env_config
from tradefed_cluster.plugins import base as plugins_base
from tradefed_cluster.util import ndb_shim as ndb

# This number is based on Cloud Tasks spec:
# https://cloud.google.com/tasks/docs/quotas
MAX_TASK_SIZE_BYTES = 100 * 1024
DEFAULT_CALLABLE_TASK_QUEUE = "default"

APP = flask.Flask(__name__)

Task = plugins_base.Task


class Error(Exception):
  """A task scheduler error."""
  pass


class TaskTooLargeError(Error):
  """Task payload is too large."""
  pass


class TaskExecutionError(Error):
  """A retriable task execution error."""
  pass


class NonRetriableTaskExecutionError(Error):
  """A non-retriable task execution error."""
  pass


class _CallableTaskEntity(ndb.Model):
  """Datastore representation of a callable task.

  This is used in cases when the deferred task is too big to be included as
  payload with the task queue entry.
  """
  data = ndb.BlobProperty(required=True)


def _GetTaskScheduler():
  if not env_config.CONFIG.task_scheduler:
    raise ValueError("No task scheduler is configured")
  return env_config.CONFIG.task_scheduler


def _AddTask(
    queue_name, payload, target=None, name=None, eta=None, transactional=False):
  """Add a task using a selected task scheduler implementation.

  Args:
    queue_name: a queue name.
    payload: a task payload.
    target: a target module name.
    name: a task name.
    eta: a ETA for task execution.
    transactional: a flag to indicate whether this task should be tied to
        datastore transaction.
  Returns:
    A Task object.
  Raises:
    TaskTooLargeError: if a task is too large.
  """
  if MAX_TASK_SIZE_BYTES < len(payload):
    raise TaskTooLargeError(
        "Task %s-%s is larger than %s bytes" % (
            queue_name, name, MAX_TASK_SIZE_BYTES))
  if transactional and not name:
    name = str(uuid.uuid1())

  def Callback():
    """A callback function to add a task."""
    try:
      return _GetTaskScheduler().AddTask(
          queue_name=queue_name,
          payload=payload,
          target=target,
          task_name=name,
          eta=eta)
    except Exception as e:
      logging.info("Failed to add task", exc_info=True)
      raise Error(e)

  if transactional:
    ndb.get_context().call_on_commit(Callback)
    return plugins_base.Task(name=name, payload=payload, eta=eta)
  return Callback()


def AddTask(
    queue_name, payload, target=None, name=None, eta=None, transactional=False):
  """Schedule a task.

  Args:
    queue_name: a queue name.
    payload: a task payload.
    target: a target module name (optional).
    name: a task name (optional).
    eta: a ETA for task execution (optional).
    transactional: a flag to indicate whether this task should be tied to
        datastore transaction.
  Returns:
    a Task object.
  """
  return _AddTask(
      queue_name=queue_name,
      payload=payload,
      target=target,
      name=name,
      eta=eta,
      transactional=transactional)


def DeleteTask(queue_name, task_name):
  """Delete a scheduled task.

  Args:
    queue_name: a queue name.
    task_name: a task name.
  """
  try:
    _GetTaskScheduler().DeleteTask(queue_name=queue_name, task_name=task_name)
  except Exception as e:
    raise Error(e)


def AddCallableTask(obj, *args, **kwargs):
  """Schedules a task to execute a callable.

  Callable tasks queue URLs (e.g. /_ah/queue/default) must be routed to
  TaskHandler so that tasks can be properly executed.

  Args:
    obj: The callable to execute. See module docstring for restrictions.
    *args: Positional arguments to call the callable with.
    **kwargs: Any other keyword arguments are passed through to the callable.
        Special parameters like _queue, _target, _transactional are passed to
        task scheduler.
  Returns:
    A Task object.
  Raises:
    Error: if a task cannot be added.
  """
  queue = kwargs.pop("_queue", DEFAULT_CALLABLE_TASK_QUEUE)
  target = kwargs.pop("_target", None)
  transactional = kwargs.pop("_transactional", False)
  eta = kwargs.pop("_eta", None)
  pickled = _Serialize(obj, *args, **kwargs)
  try:
    return _AddTask(
        queue_name=queue,
        payload=pickled,
        name=None,
        target=target,
        eta=eta,
        transactional=transactional)
  except TaskTooLargeError:
    # Task is too big - store it to the datastore
    pass
  if not transactional and ndb.in_transaction():
    logging.warning("Adding large callable task transactionally")
    transactional = True  # Ensure callback is executed after task is committed
  entity_key = _CallableTaskEntity(data=pickled).put()
  pickled = _Serialize(_RunCallableTaskFromDatastore, entity_key)
  return _AddTask(
      queue_name=queue,
      payload=pickled,
      name=None,
      target=target,
      eta=eta,
      transactional=transactional)


def RunCallableTask(data):
  """Unpickles and executes a callable task.

  Args:
    data: A pickled tuple of (function, args, kwargs) to execute.
  Returns:
    The return value of the function invocation.
  """
  try:
    func, args, kwds = pickle.loads(data)
  except Exception as e:
    raise NonRetriableTaskExecutionError(e)
  else:
    return func(*args, **kwds)


def _RunCallableTaskFromDatastore(key):
  """Retrieves a callable task from the datastore and executes it.

  Args:
    key: The datastore key of a _CallableTaskEntity storing the task.
  Returns:
    The return value of the function invocation.
  Raises:
    NonRetriableTaskExecutionError: if a task cannot be read from datastore.
  """
  entity = key.get()
  if not entity:
    # If the entity is missing, no number of retries will help.
    raise NonRetriableTaskExecutionError()
  try:
    RunCallableTask(entity.data)
    key.delete()
  except NonRetriableTaskExecutionError:
    key.delete()
    raise


def _InvokeMember(obj, membername, *args, **kwargs):
  """Retrieves a member of an object, then calls it with the provided arguments.

  Args:
    obj: The object to operate on.
    membername: The name of the member to retrieve from ojb.
    *args: Positional arguments to pass to the method.
    **kwargs: Keyword arguments to pass to the method.
  Returns:
    The return value of the method invocation.
  """
  return getattr(obj, membername)(*args, **kwargs)


def _PackCallable(obj, *args, **kwargs):
  """Takes a callable and arguments and returns a tuple.

  The returned tuple consists of (callable, args, kwargs), and can be pickled
  and unpickled safely.

  Args:
    obj: The callable to curry. See the module docstring for restrictions.
    *args: Positional arguments to call the callable with.
    **kwargs: Keyword arguments to call the callable with.
  Returns:
    A tuple consisting of (callable, args, kwargs) that can be evaluated by
    run() with equivalent effect of executing the function directly.
  Raises:
    ValueError: If the passed in object is not of a valid callable type.
  """
  if isinstance(obj, types.MethodType):
    return (_InvokeMember, (obj.__self__, obj.__func__.__name__) + args, kwargs)
  elif isinstance(obj, types.BuiltinMethodType):
    if not obj.__self__:
      # Some built in functions are identified as methods (eg, operator.add)
      return (obj, args, kwargs)
    else:
      return (_InvokeMember, (obj.__self__, obj.__name__) + args, kwargs)
  elif isinstance(obj, object) and hasattr(obj, "__call__"):
    return (obj, args, kwargs)
  elif isinstance(obj, (types.FunctionType, types.BuiltinFunctionType,
                        type, types.MethodType)):
    return (obj, args, kwargs)
  else:
    raise ValueError("obj must be callable")


def _Serialize(obj, *args, **kwargs):
  """Serializes a callable into a format recognized by the deferred executor.

  Args:
    obj: The callable to serialize. See module docstring for restrictions.
    *args: Positional arguments to call the callable with.
    **kwargs: Keyword arguments to call the callable with.
  Returns:
    A serialized representation of the callable.
  """
  pack = _PackCallable(obj, *args, **kwargs)
  return pickle.dumps(pack, protocol=pickle.HIGHEST_PROTOCOL)


@APP.route("/", methods=["POST"])
# This matchs all path start with "/".
@APP.route("/<path:fake>", methods=["POST"])
def HandleCallableTask(fake=None):
  """Process callable tasks."""
  del fake
  try:
    RunCallableTask(flask.request.get_data())
  except TaskExecutionError:
    # Catch a TaskExecutionError. Intended for users to be able to force a
    # task retry without causing an error.
    logging.debug("Fail to execute a task, task retry forced")
    status_code = flask.Response(status=408)
    return status_code
  except NonRetriableTaskExecutionError:
    # Catch this so we return a 200 and don't retry the task.
    logging.exception("Non-retriable error raised while executing a task")
  return common.HTTP_OK
