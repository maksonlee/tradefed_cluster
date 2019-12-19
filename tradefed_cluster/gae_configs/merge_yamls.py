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

"""A utility to merge yaml files."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from absl import app
import six
import yaml


def _MergeDicts(a, b):
  """Shallow merge two dicts.

  If both dicts have values for a same key and both are lists, it concats them.

  Args:
    a: a dict object. This will be updated with merged items.
    b: a dict object.

  Returns:
    a merged dict object.
  """
  for key, value in six.iteritems(b):
    if key not in a:
      a[key] = value
      continue
    value_a = a[key]
    if not isinstance(value_a, list) or not isinstance(value, list):
      raise ValueError(
          'values for key %s are not lists: value1 = %s, value2 = %s' %
          (key, value_a, value))
    a[key] += value
  return a


def main(argv):
  o = {}
  for name in argv[1:]:
    with open(name) as f:
      _MergeDicts(o, yaml.safe_load(f.read()))
  print((yaml.safe_dump(o, default_flow_style=False)))


if __name__ == '__main__':
  app.run(main)
