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

"""Plugins for Python 2 GAE."""

import cloudstorage

from google.appengine.api import mail
from google.appengine.api import taskqueue

from tradefed_cluster.plugins import base


def _ToFileInfo(stat):
  """Converts a cloudstorage.GCSFileStat to base.FileInfo."""
  return base.FileInfo(
      filename=stat.filename,
      is_dir=stat.is_dir,
      size=stat.st_size,
      content_type=stat.content_type)


class FileStorage(object):
  """Interface for file storage plugins."""

  def ListFiles(self, path):
    """List directory/files under a given path.

    Args:
      path: a directory path.
    Returns:
      A FileInfo iterator.
    """
    it = cloudstorage.listbucket(path)
    return map(it, _ToFileInfo)

  def OpenFile(self, path, mode, content_type, content_encoding):
    """Opens a file for reading or writing.

    Args:
      path: a file path.
      mode: 'r' for reading or 'w' for writing
      content_type: a content type (optional).
      content_encoding: a content encoding (optional).
    Returns:
      A file-like object.
    """
    try:
      options = {}
      if content_encoding:
        options['content-encoding'] = content_encoding
      return cloudstorage.open(
          filename=path, mode=mode, content_type=content_type, options=options)
    except cloudstorage.NotFoundError:
      raise base.ObjectNotFoundError()


class Mailer(base.Mailer):
  """A GAE mailer. Only work with Titanoboa."""

  def SendMail(self, sender, to, subject, html, reply_to, cc, bcc):
    message = mail.EmailMessage(
        sender=sender,
        to=to,
        subject=subject,
        html=html,
        reply_to=reply_to,
        cc=cc,
        bcc=bcc)
    message.send()


class TaskScheduler(base.TaskScheduler):
  """A GAE task scheduler. Only work with Titanoboa."""

  def AddTask(self, queue_name, payload, target, task_name, eta):
    return taskqueue.add(
        queue_name=queue_name,
        payload=payload,
        target=target,
        name=task_name,
        eta=eta)

  def DeleteTask(self, queue_name, task_name):
    taskqueue.Queue(queue_name).delete_tasks_by_name(task_name=task_name)
