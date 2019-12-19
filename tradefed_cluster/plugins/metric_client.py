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

"""A metric client interface."""

import collections
import logging


class Units(object):
  """Metric units."""
  SECONDS = 1
  MILLISECONDS = 2
  MICROSECONDS = 3
  NANOSECONDS = 4


class MetricType(object):
  """Metric types."""
  VALUE = 1
  COUNTER = 2
  EVENT = 3

# A metric descriptor.
MetricDescriptor = collections.namedtuple(
    'MetricDescriptor', ['type_', 'value_type', 'desc', 'fields', 'units'])
MetricDescriptor.__new__.__defaults__ = (None, None, [], None)


class MetricActionType(object):
  """Metric action types."""
  SET = 1
  RECORD = 2
  INCREMENT = 3

# A metric action.
MetricAction = collections.namedtuple(
    'MetricAction', ['name', 'type_', 'value', 'field_values'])


class MetricClient(object):
  """Interface for metric client plugins."""

  def Register(self, name, descriptor):
    """Called when a new metric is registered.

    Args:
      name: a metric name.
      descriptor: a MetricDescriptor object.
    """
    logging.debug('metric registered: name=%s, descriptor=%s', name, descriptor)

  def Emit(self, actions):
    """Emit metric(s).

    Args:
      actions: a list of MetricAction tuples.
    """
    logging.debug('metric emit: %s', actions)
