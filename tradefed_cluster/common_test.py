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

"""Tests for google3.wireless.android.test_tools.tradefed_cluster.common."""
import datetime
import unittest
import six

from tradefed_cluster import common


# GPyLint does not recognize the ClassProperty in the common module.

class TestIntState(int):

  def __new__(cls, value):
    return int.__new__(cls, int(value))

  @common.ClassProperty
  def StateZero(cls):
    return cls(0)

  @common.ClassProperty
  def StateOne(cls):
    return cls(1)


class CommonTest(unittest.TestCase):

  def testClassProperty(self):
    """Tests that class properties can be accessed."""
    self.assertEqual(0, TestIntState.StateZero)
    self.assertEqual(1, TestIntState.StateOne)

  def testUrlSafeB64EncodeAndDecode(self):
    string_message = str("{message}")
    bytes_message = bytes(b"{message}")
    string_result = common.UrlSafeB64Encode(string_message)
    bytes_result = common.UrlSafeB64Encode(bytes_message)
    # Validate result are equal even if type is different
    decoded_string_message = common.UrlSafeB64Decode(string_result)
    decoded_bytes_message = common.UrlSafeB64Decode(bytes_result)
    self.assertEqual(decoded_bytes_message, decoded_string_message)
    # Output will be turn to str
    self.assertEqual(six.ensure_str(bytes_message), decoded_bytes_message)
    self.assertEqual(string_message, decoded_string_message)

  def testParseFloat(self):
    self.assertEqual(60, common.ParseFloat("60"))
    self.assertEqual(1.2, common.ParseFloat("1.2"))
    self.assertIsNone(common.ParseFloat("P1234"))
    self.assertIsNone(common.ParseFloat(None))

  def testDatetimeToTimestampProperty(self):
    self.assertEqual(
        "1622793723000",
        common.DatetimeToAntsTimestampProperty(
            datetime.datetime(2021, 6, 4, 1, 2, 3)))


if __name__ == "__main__":
  unittest.main()
