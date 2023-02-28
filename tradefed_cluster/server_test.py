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

"""Tests for server."""
import unittest
import werkzeug


from tradefed_cluster import server
from tradefed_cluster import testbed_dependent_test


def CreateMockApp(status_code=200):
  """Create a mock WSGI app that always returns the same status code."""
  return werkzeug.wrappers.Request.application(
      lambda _: werkzeug.wrappers.Response(status=status_code))


class RegexDispatcherTest(testbed_dependent_test.TestbedDependentTest):

  def testDispatch(self):
    """Tests that requests can be dispatched."""
    dispatcher = server.RegexDispatcher([
        (r'/test', CreateMockApp(status_code=200)),
        (r'/(hello|world)(/.*)?', CreateMockApp(status_code=201)),
    ])
    client = werkzeug.test.Client(dispatcher, werkzeug.wrappers.BaseResponse)

    # Exact match
    self.assertEqual(client.get('/test').status_code, 200)
    self.assertEqual(client.get('/test/unknown').status_code, 404)
    # Matched by regex
    self.assertEqual(client.get('/hello').status_code, 201)
    self.assertEqual(client.get('/world').status_code, 201)
    self.assertEqual(client.get('/world/more').status_code, 201)
    # Unmatched
    self.assertEqual(client.get('/unknown').status_code, 404)


if __name__ == '__main__':
  unittest.main()
