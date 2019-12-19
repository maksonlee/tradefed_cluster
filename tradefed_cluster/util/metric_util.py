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

"""Utilities for metric collection."""

from tradefed_cluster.plugins import metric_client

# A metric value unit.
Units = metric_client.Units

# A metric type.
MetricType = metric_client.MetricType

# A metric descriptor.
MetricDescriptor = metric_client.MetricDescriptor


class MetricBatch(object):
  """A class for batching metric emitting.

  A MetricBatch object can be created and passed to Metric methods to batching
  metric emissions for performance optimization.
  """

  def __init__(self):
    self._client = None
    self._actions = []

  def Emit(self):
    """Emit batched metrics."""
    if not self._client or not self._actions:
      return
    self._client.Emit(self._actions)

  def Add(self, client, action):
    """Add a metric action.

    Args:
      client: a metric_client.MetricClient object.
      action: a metric_client.MetricAction tuple.
    """
    if self._client and self._client != client:
      raise ValueError('Cannot add metrics for different clients')
    self._client = client
    self._actions.append(action)


class Metric(object):
  """A metric. Used to collect system metrics."""

  def __init__(self, name, descriptor, client):
    """Constructor.

    Args:
      name: a metric name.
      descriptor: a MetricDescriptor object.
      client: a metric_client.MetricClient object.
    """
    self._name = name
    self._descriptor = descriptor
    self._client = client
    self._client.Register(name, descriptor)

  @property
  def name(self):
    return self._name

  def _Emit(self, action, batch):
    if batch:
      batch.Add(self._client, action)
      return
    self._client.Emit([action])

  def Set(self, value, field_values, batch=None):
    """Sets a metric value with field values.

    Args:
      value: a metric value.
      field_values: a dict containing field values.
      batch: an optional MetricBatch object.
    """
    action = metric_client.MetricAction(
        self.name, metric_client.MetricActionType.SET, value, field_values)
    self._Emit(action, batch)

  def Record(self, value, field_values, batch=None):
    """Records a metric value with field values.

    Args:
      value: a metric value.
      field_values: a dict containing field values.
      batch: an optional MetricBatch object.
    """
    action = metric_client.MetricAction(
        self.name, metric_client.MetricActionType.RECORD, value, field_values)
    self._Emit(action, batch)

  def Increment(self, field_values, batch=None):
    """Increments a metric with field values.

    Args:
      field_values: a dict containing field values.
      batch: an optional MetricBatch object.
    """
    action = metric_client.MetricAction(
        self.name, metric_client.MetricActionType.INCREMENT, None, field_values)
    self._Emit(action, batch)
