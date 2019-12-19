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

from six import with_metaclass


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


class Plugin(with_metaclass(PluginMetaClass, object)):
  """A base class for Plugin."""

  def OnCommandTasksLease(self, command_tasks):
    """A callback function to be executed before a plugin executed.

    Args:
      command_tasks: the list of datastore_entities.CommandTask.
    """
    pass

  def OnCreateCommands(self,
                       command_ids,
                       request_plugin_data,
                       command_plugin_data_map):
    """A callback function to be executed before a plugin executed.

    Args:
      command_ids: a list of command id.
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
