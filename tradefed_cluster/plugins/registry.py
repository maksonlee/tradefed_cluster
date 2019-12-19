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

"""A module to import plugin."""

from tradefed_cluster.plugins import base
from tradefed_cluster.plugins import noop_plugin  

def GetPlugin(name, **kwargs):
  """Returns a plugin instance registered with the given name.

  Args:
    name: a test plugin.
    **kwargs: **kwargs.
  Returns:
    a instance of base.Plugin class's child class.
  """
  cls = base.Plugin.GetClass(name)
  if not cls:
    raise ValueError('Plugin "%s" does not exist' % name)
  return cls(**kwargs)


def GetNoOpPlugin():
  return GetPlugin('noop')
