# Lint as: python2, python3
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

"""Tests for email_sender."""
import datetime
import os
import unittest

import jinja2

from google.appengine.ext import testbed

from tradefed_cluster import testbed_dependent_test
from tradefed_cluster.util import email_sender

TEMPLATE_FILE = 'sample_email_template.html'


class EmailSenderTest(testbed_dependent_test.TestbedDependentTest):

  def setUp(self):
    super(EmailSenderTest, self).setUp()
    self.testdata_src_root = os.path.join(
        os.path.dirname(__file__), 'testdata')
    self.mail_stub = self.testbed.get_stub(testbed.MAIL_SERVICE_NAME)

  def testRender(self):
    # Test rendring when the template successfully
    expected = '<b>Variable x:</b> value'
    actual = email_sender.Render(
        self.testdata_src_root, TEMPLATE_FILE, x='value')
    self.assertEqual(expected, actual)

  def testRender_noTemplate(self):
    # Test rendering when the template is missing a parameter
    with self.assertRaises(jinja2.TemplateNotFound):
      email_sender.Render(self.testdata_src_root, 'fake_template.html')

  def testSendEmail(self):
    # Test SendEmail
    email_sender.SendEmail(
        sender='send', recipient='recipient', subject='hello', html_body='bye')
    messages = self.mail_stub.get_sent_messages()
    self.assertEqual(1, len(messages))
    message = messages[0]
    self.assertEqual('send', message.sender)
    self.assertEqual('recipient', message.to)
    self.assertEqual('send', message.reply_to)
    self.assertEqual('hello', message.subject)
    self.assertEqual('bye', message.html.decode())

  def testSendEmail_customReplyTo(self):
    # Test SendEmail with reply_to set
    email_sender.SendEmail(
        sender='send', recipient='recipient', subject='hello', html_body='bye',
        reply_to='reply')
    messages = self.mail_stub.get_sent_messages()
    self.assertEqual(1, len(messages))
    message = messages[0]
    self.assertEqual('send', message.sender)
    self.assertEqual('recipient', message.to)
    self.assertEqual('reply', message.reply_to)
    self.assertEqual('hello', message.subject)
    self.assertEqual('bye', message.html.decode())

  def testFormatDatetime(self):
    # Test FormatDatetime
    date = datetime.datetime(2016, 8, 31)
    self.assertEqual('2016-08-31 00:00', email_sender.FormatDatetime(date))

  def testFormatDatetime_givenFormat(self):
    # Test FormatDatetime with a given format
    date = datetime.datetime(2016, 8, 31)
    fmt = '%Y-%m-%d'
    self.assertEqual('2016-08-31', email_sender.FormatDatetime(date, fmt))


if __name__ == '__main__':
  unittest.main()
