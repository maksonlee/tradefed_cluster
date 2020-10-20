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

# Lint as: python2, python3
"""A utility module for command line manipulation."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import logging
import pipes
import re
import shlex

import munch
import six


class CommandLine(list):
  """A utility class for manipulating a command line."""

  def __init__(self, command_line):
    """Constructor.

    Args:
      command_line: a CommandLine object or a command line string.
    """
    # TODO: Consider storing a command line as a dictionary of lists to
    # make option lookup and update more efficient.
    if isinstance(command_line, six.string_types):
      command_line = shlex.split(command_line)
    super(CommandLine, self).__init__(command_line)

  def GetOption(self, name, default_value=None):
    """Gets the value of an option.

    Args:
      name: the name of an option.
      default_value: a default value if the desired option was not found.
    Returns:
      the option value.
    """
    index = 0
    expect_value = False
    value = []
    while index < len(self):
      if six.ensure_str(self[index], "utf-8").find("-") == 0:
        expect_value = False
      if name == self[index]:
        expect_value = True
      elif expect_value:
        value.append(self[index])
      index += 1
    return " ".join(value) or default_value

  def GetOptionsDicts(self):
    """Gets a list of dictionaries with the command options.

    The output format is the one expected by ATP's testruns.new()

    Example output:
    options = [{"key": "key0", "values": ["value0", "value1"]},
               {"key": "key1", "values": ["value2", "value3"]}]

    Returns:
      a list of dictionaries.
    """
    result = []
    args = None
    index = 1  # The first element should never be part of options
    while index < len(self):
      key = _ExtractKey(self[index])
      if key:
        if args:
          result.append(args)
        args = {"key": key, "values": []}
      elif args:
        args["values"].append(self[index])
      index += 1
    if args:
      result.append(args)
    return result

  def ExpandContext(self, context, ignore_invalid_options=True):
    """Expands context variables into this command.

    TODO: Refactor shared logic with atp.manager.test_kicker

    Args:
      context: a dictionary of test run context variables
      ignore_invalid_options: boolean flag to ignore missing keys
    Returns:
      A new command with the expanded context variables
    """
    context_obj = munch.Munch.fromDict(context)
    old_options = self.GetOptionsDicts()
    new_options = []
    for option in old_options:
      new_option = {"key": option["key"]}
      if "values" in option:
        new_option["values"] = []
        for value in option["values"]:
          try:
            new_option["values"].append(value.format(**context_obj))
          except KeyError as e:
            if ignore_invalid_options:
              new_option = None
            else:
              new_option = option
            logging.warning(
                "Missing test run context key: %s. If this is a remote test, "
                "it may be resolved at runtime.", e)
      if new_option:
        new_options.append(new_option)
    return self.FromOptions(self[0], new_options)

  def AddOption(self, name, value=None):
    """Adds an option with the given name and/or value.

    TODO: This should be smarter and allow replacing options if they
    already exist.

    Args:
      name: the name of an option
      value: value for the option
    """
    self.append(name)
    if value:
      self.append(value)

  def RemoveOptions(self, names):
    """Removes options with the given names.

    Args:
      names: a list of option names to remove.
    """
    index = 0
    expect_value = False
    while index < len(self):
      if six.ensure_str(self[index], "utf-8").find("-") == 0:
        expect_value = False
      if self[index] in names or expect_value:
        del self[index]
        expect_value = True
        continue
      index += 1

  def __str__(self):
    tokens = []
    for token in self:
      tokens.append(pipes.quote(token))
    return u" ".join(tokens)

  def ToTFString(self):
    """Returns a TF-compatible command string.

    Returns:
      a command string.
    """

    tokens = []
    for token in self:
      # We cannot pipes.quote() here because it is not compatible with TF's
      # command parsing which only understands quoting with double quotes.
      token = six.ensure_text(token)
      # Escape double quotes with backslash escaping
      token = re.sub(r"(\")", r"\\\1", token)
      if not token or u" " in token:
        tokens.append("\"%s\"" % token)
      else:
        tokens.append(token)
    return u" ".join(tokens)

  @classmethod
  def FromOptions(cls, test_type, options):
    """Create a CommandLine object from a test type and its options.

    Args:
      test_type: command test type, ie: the command without any options
      options: list of dictionaries for the command options
    Returns:
      A command line for the given test type and options
    """
    args = [test_type]
    for option in options:
      args.append("--" + six.ensure_str(option.get("key"), "utf-8"))
      args.extend(option.get("values") or [])
    return cls(args)


def _ExtractKey(option):
  """Helper to extract a key for an option dictionary."""
  if " " in option:
    # The option was quoted so it is a value.
    return None
  if six.ensure_str(option, "utf-8").startswith("--"):
    return option[2:]
  elif six.ensure_str(option, "utf-8").startswith("-"):
    return option[1:]
  return None
