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

"""Unit tests for appengine module."""

from absl.testing import absltest
import cloudstorage

from google.appengine.ext import testbed

from tradefed_cluster.plugins import appengine


class MailerTest(absltest.TestCase):
  """Unit tests for Appengine mailer."""

  def setUp(self):
    super(MailerTest, self).setUp()
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_all_stubs()
    self.mail_stub = self.testbed.get_stub(testbed.MAIL_SERVICE_NAME)
    self.addCleanup(self.testbed.deactivate)

    self.mailer = appengine.Mailer()

  def testSendMail(self):
    self.mailer.SendMail(
        sender='send',
        to='recipient',
        subject='hello',
        html='bye',
        reply_to=None,
        cc=None,
        bcc=None)

    messages = self.mail_stub.get_sent_messages()
    self.assertLen(messages, 1)
    message = messages[0]
    self.assertEqual('send', message.sender)
    self.assertEqual('recipient', message.to)
    self.assertEqual('hello', message.subject)
    self.assertEqual('bye', message.html.decode())
    self.assertFalse(hasattr(message, 'reply_to'))
    self.assertFalse(hasattr(message, 'cc'))
    self.assertFalse(hasattr(message, 'bcc'))

  def testSendMail_withCCandBCC(self):
    self.mailer.SendMail(
        sender='send',
        to='recipient',
        subject='hello',
        html='bye',
        reply_to='reply_to',
        cc='cc',
        bcc='bcc')

    messages = self.mail_stub.get_sent_messages()
    self.assertLen(messages, 1)
    message = messages[0]
    self.assertEqual('send', message.sender)
    self.assertEqual('recipient', message.to)
    self.assertEqual('hello', message.subject)
    self.assertEqual('bye', message.html.decode())
    self.assertEqual('reply_to', message.reply_to)
    self.assertEqual('cc', message.cc)
    self.assertEqual('bcc', message.bcc)


class FileStorageTest(absltest.TestCase):
  """Unit tests for Appengine file storage."""

  def setUp(self):
    super(FileStorageTest, self).setUp()
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.testbed.init_all_stubs()
    self.addCleanup(self.testbed.deactivate)

    self.file_storage = appengine.FileStorage()

  def testOpenFile(self):
    with cloudstorage.open('/path/to/file', mode='w') as f:
      f.write(b'hello')

    with self.file_storage.OpenFile(
        '/path/to/file',
        mode='r',
        content_type=None,
        content_encoding=None) as f:
      self.assertEqual(b'hello', f.read())

if __name__ == '__main__':
  absltest.main()
