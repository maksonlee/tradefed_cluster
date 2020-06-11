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

# TODO: Remove after Python 3 migration
"""Allows third_party/py/google modules to be imported into py_appengine_*."""
import sys
import google

# Prepends the 'third_party/py/google' location to the search path for 'google'.
third_party_path = next(p for p in sys.path if p.endswith('third_party/py'))
google.__path__ = [third_party_path + '/google'] + google.__path__
