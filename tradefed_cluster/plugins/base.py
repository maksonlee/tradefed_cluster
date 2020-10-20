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

"""A module to define base classes for Tradefed Cluster plugins.

A plugin is a python class that gets instantiated and called start and finished.
Also a test hook can populate parameters so that they can be used in test args.
"""

import collections

import six


class Error(Exception):
  """A base class for plugin errors."""
  pass


class ObjectNotFoundError(Error):
  """Cannot find an object."""
  pass


class PluginMetaClass(type):
  """A meta class to register all test hook classes to the test hook map."""

  def __init__(cls, name, bases, attrs):
    if not hasattr(cls, 'name'):
      cls._registry = {}
    else:
      if cls.name in cls._registry:
        raise ValueError('name %s is already taken by %s.' % (
            cls.name, cls._registry[cls.name]))
      cls._registry[cls.name] = cls
    super(PluginMetaClass, cls).__init__(name, bases, attrs)

  def GetClass(cls, name):
    return cls._registry.get(name)


CommandInfo = collections.namedtuple('CommandInfo', [
    'command_id',
    'command_line',
    'run_count',
    'shard_count',
    'shard_index',
])


class Plugin(six.with_metaclass(PluginMetaClass, object)):
  """A base class for Plugin."""

  def OnCommandTasksLease(self, command_tasks):
    """A callback function to be executed before a plugin executed.

    Args:
      command_tasks: the list of datastore_entities.CommandTask.
    """
    pass

  def OnCreateCommands(
      self, command_infos, request_plugin_data, command_plugin_data_map):
    """A callback function to be executed before a plugin executed.

    Args:
      command_infos: a list of CommandInfo objects.
      request_plugin_data: the request plguin data.
      command_plugin_data_map: the command plugin data for each command id.
    """
    pass

  def OnProcessCommandEvent(self, command, attempt):
    """A callback function to be executed before a plugin executed.

    Args:
      command: a datastore_entities.Command.
      attempt: a datastore_entities.CommandAttempt.
    """
    pass


FileInfo = collections.namedtuple(
    'FileInfo', ['filename', 'is_dir', 'size', 'content_type'])


class FileStorage(object):
  """Interface for file storage plugins."""

  def ListFiles(self, path):
    """List directory/files under a given path.

    Args:
      path: a directory path.
    Returns:
      A FileInfo iterator.
    """
    raise NotImplementedError()

  def OpenFile(self, path, mode, content_type, content_encoding):
    """Opens a file for reading or writing.

    Args:
      path: a file path.
      mode: 'r' for reading or 'w' for writing
      content_type: a content type.
      content_encoding: a content encoding.
    Returns:
      A file-like object.
    """
    raise NotImplementedError()


class Mailer(object):
  """A mailer plugin interface."""

  def SendMail(self, sender, to, subject, html, reply_to, cc, bcc):
    raise NotImplementedError()

Task = collections.namedtuple('Task', ['name', 'payload', 'eta'])
Task.__new__.__defaults__ = (None, None)


class TaskScheduler(object):
  """Interface for task scheduler plugins."""

  def AddTask(self, queue_name, payload, target, task_name, eta):
    """Add a task using a selected task scheduler implementation.

    Args:
      queue_name: a queue name.
      payload: a task payload.
      target: a target module name.
      task_name: a task name.
      eta: a ETA for task execution.
    Returns:
      A Task object.
    """
    raise NotImplementedError()

  def DeleteTask(self, queue_name, task_name):
    """Deletes a task.

    Args:
      queue_name: a queue name.
      task_name: a task name.
    """
    raise NotImplementedError()
