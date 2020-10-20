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

"""A module for parsing TF command files.

This module is a python port of TF CommandFileParser.
"""

import logging
import os.path
import re
import shlex

# A regex to match macros in command lines.
_MACRO_PATTERN = re.compile(r"([a-z][a-z0-9_-]*)\(\)", re.I)


def _ShouldParseLine(line):
  """Checks whether a line should be parsed."""
  if not line or line.startswith("#"):
    return False
  return True


def _IsMacro(command):
  """Checks whether a command is a macro."""
  if len(command) >= 4 and command[0] == "MACRO" and command[2] == "=":
    return True
  return False


def _IsLongMacro(command):
  """Checks whether a command is a long macro."""
  if len(command) == 3 and command[0] == "LONG" and command[1] == "MACRO":
    return True
  return False


def _IsIncludeDirective(command):
  """Checke where a command is an include directive."""
  if len(command) == 2 and command[0] == "INCLUDE":
    return True
  return False


class Parser(object):
  """A class for parsing command files."""

  def __init__(self):
    self._filenames = []
    self._commands = []
    self._macros = {}
    self._long_macros = {}

  def Parse(self, filename):
    """Reads and parses a command file.

    Args:
      filename: the name of a command file including necessary path.
    """
    self._ScanFile(filename)
    self._ExpandMacros()

  def _ScanFile(self, filename):
    """Scans a file and parse lines."""
    logging.info("Scanning %s", filename)
    if filename in self._filenames:
      return
    self._filenames.append(filename)

    with open(filename, "r") as f:
      while True:
        line = f.readline()
        if not line:
          break

        line = line.strip()
        if not _ShouldParseLine(line):
          continue
        command = shlex.split(line)
        if _IsMacro(command):
          name = command[1]
          macro = command[3:]
          if name in self._macros:
            logging.warning(
                "Overwrote short macro '%s' while parsing file %s",
                name,
                filename
            )
            logging.warning(
                "value '%s' replaced previous value '%s'",
                self._macros[name],
                macro
            )
          self._macros[name] = macro
        elif _IsLongMacro(command):
          name = command[2]
          macro = []
          while True:
            line = f.readline()
            if not line:
              break

            line = line.strip()
            if not _ShouldParseLine(line):
              continue
            if line == "END MACRO":
              break
            command = shlex.split(line)
            macro.append(command)
          if name in self._long_macros:
            logging.warning(
                "Overwrote long macro '%s' while parsing file %s",
                name,
                filename
            )
            logging.warning(
                "%d-line definition replaced previous %d-line definition",
                len(self._long_macros[name]),
                len(macro)
            )
          self._long_macros[name] = macro
        elif _IsIncludeDirective(command):
          include_filename = command[1]
          if not os.path.isabs(include_filename):
            include_filename = os.path.normpath(
                os.path.join(os.path.dirname(filename), include_filename))
          logging.debug("Including %s", include_filename)
          self._ScanFile(include_filename)
        else:
          self._commands.append(command)

  def _ExpandMacros(self):
    """Expands macros in commands."""
    has_macro = True
    iteration = 0
    while has_macro:
      logging.debug("Macro expansion iteration %d", iteration)
      has_macro = False
      index = 0
      while index < len(self._commands):
        command = self._commands[index]
        if self._ExpandShortMacro(command):
          has_macro = True
        new_commands = self._ExpandLongMacro(command, not has_macro)
        if new_commands:
          has_macro = True
          del self._commands[index]
          for new_command in new_commands:
            self._commands.insert(index, new_command)
            index += 1
        else:
          index += 1
      iteration += 1

  def _ExpandShortMacro(self, command):
    """Expands short macros in a command."""
    has_macro = False
    index = 0
    while index < len(command):
      token = command[index]
      match = _MACRO_PATTERN.match(token)
      if match and match.group(1) in self._macros:
        has_macro = True
        name = match.group(1)
        del command[index]
        for macro_token in self._macros[name]:
          command.insert(index, macro_token)
          index += 1
      else:
        index += 1
    return has_macro

  def _ExpandLongMacro(self, command, check_unknown_macro):
    """Expands the first long macro in a command."""
    index = 0
    while index < len(command):
      token = command[index]
      match = _MACRO_PATTERN.match(token)
      if match:
        name = match.group(1)
        if name not in self._long_macros:
          if check_unknown_macro:
            raise Exception(
                "Macro call '%s' does not match any macro definitions" % name
            )
          else:
            return []

        new_commands = []
        prefix = command[0:index]
        suffix = command[index:]
        del suffix[0]
        for macro_line in self._long_macros[name]:
          new_command = []
          new_command.extend(prefix)
          new_command.extend(macro_line)
          new_command.extend(suffix)
          new_commands.append(new_command)
        return new_commands
      index += 1
    return []

  def GetCommands(self):
    """Returns parsed commands.

    Returns:
      a list of commands.
    """
    return self._commands
