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

import webapp2

from google.appengine.api import taskqueue
from google.appengine.ext import ndb

DEFAULT_CALLABLE_TASK_QUEUE = "default"


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


def AddTask(
    queue_name, payload, target=None, name=None, eta=None, transactional=False):
  """Add a task.

  This is currently a shim to GAE taskqueue.

  Args:
    queue_name: a queue name.
    payload: a task payload.
    target: a target module name (optional).
    name: a task name (optional).
    eta: a ETA for task execution (optional).
    transactional: a flag to indicate whether this task should be tied to
        datastore transaction.
  Returns:
    a taskqueue.Task object.
  """
  try:
    return taskqueue.add(
        queue_name=queue_name,
        payload=payload,
        target=target,
        name=name,
        eta=eta,
        transactional=transactional)
  except taskqueue.TaskTooLargeError as e:
    raise TaskTooLargeError(e)
  except taskqueue.Error as e:
    raise Error(e)


def DeleteTask(queue_name, task_name):
  """delete a task.

  This is currently a shim to GAE taskqueue.

  Args:
    queue_name: a queue name.
    task_name: a task name.
  """
  try:
    taskqueue.Queue(queue_name).delete_tasks_by_name(task_name=task_name)
  except taskqueue.Error as e:
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
  """
  queue = kwargs.pop("_queue", DEFAULT_CALLABLE_TASK_QUEUE)
  target = kwargs.pop("_target", None)
  transactional = kwargs.pop("_transactional", False)
  pickled = _Serialize(obj, *args, **kwargs)
  try:
    AddTask(
        queue_name=queue,
        payload=pickled,
        target=target,
        transactional=transactional)
  except TaskTooLargeError:
    # Task is too big - store it to the datastore
    key = _CallableTaskEntity(data=pickled).put()
    pickled = _Serialize(_RunCallableTaskFromDatastore, str(key))
    AddTask(
        queue_name=queue,
        payload=pickled,
        target=target,
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


class _CallableTaskEntity(ndb.Model):
  """Datastore representation of a callable task.

  This is used in cases when the deferred task is too big to be included as
  payload with the task queue entry.
  """
  data = ndb.BlobProperty(required=True)


def _RunCallableTaskFromDatastore(key):
  """Retrieves a callable task from the datastore and executes it.

  Args:
    key: The datastore key of a _DeferredTask storing the task.
  Returns:
    The return value of the function invocation.
  Raises:
    NonRetriableTaskExecutionError: if a task cannot be read from datastore.
  """
  entity = _CallableTaskEntity.get(key)
  if not entity:
    # If the entity is missing, no number of retries will help.
    raise NonRetriableTaskExecutionError()
  try:
    ret = RunCallableTask(entity.data)
    entity.delete()
  except NonRetriableTaskExecutionError:
    entity.delete()
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
    return (_InvokeMember, (obj.im_self, obj.im_func.__name__) + args, kwargs)
  elif isinstance(obj, types.BuiltinMethodType):
    if not obj.__self__:
      # Some built in functions are identified as methods (eg, operator.add)
      return (obj, args, kwargs)
    else:
      return (_InvokeMember, (obj.__self__, obj.__name__) + args, kwargs)
  elif isinstance(obj, object) and hasattr(obj, "__call__"):
    return (obj, args, kwargs)
  elif isinstance(obj, (types.FunctionType, types.BuiltinFunctionType,
                        type, types.UnboundMethodType)):
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


class CallableTaskHandler(webapp2.RequestHandler):
  """A webapp handler class that processes callable tasks."""

  def post(self):
    try:
      RunCallableTask(self.request.body)
    except TaskExecutionError:
      # Catch a TaskExecutionError. Intended for users to be able to force a
      # task retry without causing an error.
      logging.debug("Fail to execute a task, task retry forced")
      self.response.set_status(408)
      return
    except NonRetriableTaskExecutionError:
      # Catch this so we return a 200 and don't retry the task.
      logging.exception("Non-retriable error raised while executing a task")


APP = webapp2.WSGIApplication([(".*", CallableTaskHandler)])
