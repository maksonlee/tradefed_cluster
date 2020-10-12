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

"""A mailer service."""

from tradefed_cluster import env_config


def _GetMailer():
  if not env_config.CONFIG.mailer:
    raise ValueError("No mailer is configured")
  return env_config.CONFIG.mailer


def SendMail(sender, to, subject, html, reply_to=None, cc=None, bcc=None):
  """Sends an email.

  Args:
    sender: a sender address.
    to: a receiver address. Can be a list.
    subject: a subject.
    html: a HTML body.
    reply_to: an optional reply-to address.
    cc: an optional cc address. Can be a list.
    bcc: an optional  bcc address. Can be a list.
  """
  _GetMailer().SendMail(
      sender=sender,
      to=to,
      subject=subject,
      html=html,
      cc=cc,
      bcc=bcc,
      reply_to=reply_to)
