# Lint as: python2, python3
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

"""A file storage service."""

from tradefed_cluster import env_config
from tradefed_cluster.plugins import base as plugins_base

FileInfo = plugins_base.FileInfo

ObjectNotFoundError = plugins_base.ObjectNotFoundError


def _GetPlugin():
  if not env_config.CONFIG.file_storage:
    raise ValueError('No file_storage is configured')
  return env_config.CONFIG.file_storage


def ListFiles(path):
  """List directory/files under a given path.

  Args:
    path: a directory path.
  Returns:
    A FileInfo iterator.
  """
  return _GetPlugin().ListFiles(path)


def OpenFile(path, mode='r', content_type=None, content_encoding=None):
  """Opens a file for reading or writing.

  Args:
    path: a file path.
    mode: 'r' for reading or 'w' for writing (default='r').
    content_type: a content type (optional).
    content_encoding: a content encoding (optional).
  Returns:
    A file-like object.
  """
  return _GetPlugin().OpenFile(
      path=path,
      mode=mode,
      content_type=content_type,
      content_encoding=content_encoding)
