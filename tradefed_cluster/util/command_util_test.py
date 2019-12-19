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

"""Unit tests for command_util."""

import unittest

from tradefed_cluster.util import command_util


class CommandUtilTest(unittest.TestCase):

  def testGetOption(self):
    command = command_util.CommandLine(
        "command --option1 value1 --option2 value2 --option3 --option4 value4"
    )

    self.assertEqual("value1", command.GetOption("--option1"))
    self.assertEqual("value2", command.GetOption("--option2"))
    self.assertEqual(None, command.GetOption("--option3"))
    self.assertEqual("value4", command.GetOption("--option4"))
    self.assertEqual(None, command.GetOption("--option5"))

  def testGetOption_withDefault(self):
    command = command_util.CommandLine(
        "command --option1 value1 --option2 value2 --option3 --option4 value4"
    )

    self.assertEqual("value1", command.GetOption("--option1", "default1"))
    self.assertEqual("value2", command.GetOption("--option2", "default2"))
    self.assertEqual("default3", command.GetOption("--option3", "default3"))
    self.assertEqual("value4", command.GetOption("--option4", "default4"))
    self.assertEqual("default5", command.GetOption("--option5", "default5"))
    self.assertEqual(None, command.GetOption("--option5", None))

  def testGetOption_MultiValue(self):
    command = command_util.CommandLine(
        "command --option1 key1 value1 --option2 value2 "
        "--option3 --option4 key4 value4"
    )
    self.assertEqual("key1 value1", command.GetOption("--option1"))
    self.assertEqual("value2", command.GetOption("--option2"))
    self.assertEqual(None, command.GetOption("--option3"))
    self.assertEqual("key4 value4", command.GetOption("--option4"))
    self.assertEqual(None, command.GetOption("--option5"))

  def testExtractKey(self):
    command = command_util.CommandLine("command --option1 '-k1 v1' -o")
    self.assertEqual(
        "option1", command_util._ExtractKey(command[1]))  # --option1
    self.assertIsNone(command_util._ExtractKey(command[2]))  # '-k1 v1'
    self.assertEqual("o", command_util._ExtractKey(command[3]))  # -o

  def testGetOptionsDicts(self):
    command = command_util.CommandLine(
        "command --option1 key1 value1 --option2 value2 "
        "--option3 --option4 key4 value4"
    )
    expected = [
        {"key": "option1", "values": ["key1", "value1"]},
        {"key": "option2", "values": ["value2"]},
        {"key": "option3", "values": []},
        {"key": "option4", "values": ["key4", "value4"]}
    ]
    self.assertEqual(expected, command.GetOptionsDicts())

  def testGetOptionsDicts_quotedValue(self):
    command = command_util.CommandLine(
        "command --option1 '-k1 v1' --option2")
    expected = [
        {"key": "option1", "values": ["-k1 v1"]},
        {"key": "option2", "values": []},
    ]
    self.assertEqual(expected, command.GetOptionsDicts())

  def testGetOptionsDicts_noOptions(self):
    command = command_util.CommandLine("command")
    expected = []
    self.assertEqual(expected, command.GetOptionsDicts())

  def testGetOptionsDicts_repeatedOption(self):
    command = command_util.CommandLine(
        "command --option1 value1 --option1 value2 "
    )
    expected = [
        {"key": "option1", "values": ["value1"]},
        {"key": "option1", "values": ["value2"]}
    ]
    self.assertEqual(expected, command.GetOptionsDicts())

  def testExpandContext(self):
    command = command_util.CommandLine(
        "command --cts-build-flavor {extra_builds[0].build_target} "
        "--cts-build-id {extra_builds[0].build_id} "
        "--foo {bar}"
    )
    context = {
        "extra_builds": [{"build_target": "bt", "build_id": "123"}],
        "foo": "unused",
        "bar": "foobar"
    }
    expected = command_util.CommandLine(
        "command --cts-build-flavor bt --cts-build-id 123 --foo foobar"
    )
    self.assertEqual(expected, command.ExpandContext(context))

  def testExpandContext_missingVariable_ignoreInvalid(self):
    command = command_util.CommandLine(
        "command --cts-build-flavor {extra_builds[0].build_target} "
        "--cts-build-id {extra_builds[0].build_id} "
        "--foo {bar}"
    )
    context = {
        "extra_builds": [{"build_target": "bt", "build_id": "123"}]
    }
    expected = command_util.CommandLine(
        "command --cts-build-flavor bt --cts-build-id 123"
    )
    self.assertEqual(expected, command.ExpandContext(context, True))

  def testExpandContext_missingVariable_considerInvalid(self):
    command = command_util.CommandLine(
        "command --cts-build-flavor {extra_builds[0].build_target} "
        "--cts-build-id {extra_builds[0].build_id} "
        "--foo {bar}"
    )
    context = {
        "extra_builds": [{"build_target": "bt", "build_id": "123"}]
    }
    expected = command_util.CommandLine(
        "command --cts-build-flavor bt --cts-build-id 123 --foo {bar}"
    )
    self.assertEqual(expected, command.ExpandContext(context, False))

  def testAddOption(self):
    command = command_util.CommandLine(
        "command --option1 value1 --option2"
    )

    command.AddOption("--option3", "value3")
    command.AddOption("--option4")

    self.assertEqual("value3", command.GetOption("--option3"))
    self.assertEqual(None, command.GetOption("--option4"))
    self.assertEqual(7, len(command))

  def testRemoveOptions(self):
    command = command_util.CommandLine(
        "command --option1 value1 --option2 value2 --option3 --option4 value4"
    )
    self.assertEqual("value1", command.GetOption("--option1"))
    self.assertEqual("value4", command.GetOption("--option4"))

    command.RemoveOptions(["--option1", "--option4"])

    self.assertEqual(None, command.GetOption("--option1"))
    self.assertEqual(None, command.GetOption("--option4"))
    self.assertEqual(4, len(command))

  def testRemoveOptions_nonExistingOptions(self):
    command = command_util.CommandLine(
        "command --option1 value1 --option2 value2"
    )
    self.assertEqual(5, len(command))

    command.RemoveOptions(["--option3", "--option4"])

    self.assertEqual(5, len(command))

  def testRemoveOptions_MultiValue(self):
    command = command_util.CommandLine(
        "command --option1 key1 value1 --option2 value2"
    )
    self.assertEqual(6, len(command))
    command.RemoveOptions(["--option1", "--option4"])
    self.assertEqual(3, len(command))

  def testGetOption_differentOptionsformat(self):
    command = command_util.CommandLine(
        "command --option1 value1 -option2 value2 -option3 --option4 value4"
    )

    self.assertEqual("value1", command.GetOption("--option1"))
    self.assertEqual("value2", command.GetOption("-option2"))
    self.assertEqual(None, command.GetOption("--option3"))
    self.assertEqual("value4", command.GetOption("--option4"))
    self.assertEqual(None, command.GetOption("--option5"))

  def testToString(self):
    command = command_util.CommandLine(
        ["command", "spa ce", "\"quote\"", "back\\slashes"]
    )

    self.assertEqual(command, command_util.CommandLine(str(command)))

  def testToTFString(self):
    command = command_util.CommandLine(
        ["command", "spa ce", "\"quote\"", "back\\slashes"]
    )

    self.assertEqual(
        "command \"spa ce\" \\\"quote\\\" back\\slashes", command.ToTFString())

  def testFromOptions(self):
    options = [
        {"key": "option1", "values": ["value1"]},
        {"key": "option1", "values": ["value2"]},
        {"key": "option2", "values": None}
    ]
    self.assertEqual(
        command_util.CommandLine(
            "command --option1 value1 --option1 value2 --option2"),
        command_util.CommandLine.FromOptions("command", options))


if __name__ == "__main__":
  unittest.main()
