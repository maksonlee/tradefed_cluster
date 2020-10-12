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

"""Unit tests for mailer module."""

from absl.testing import absltest
import mock

from tradefed_cluster import env_config
from tradefed_cluster.plugins import base as plugins_base
from tradefed_cluster.services import mailer


class MailerTest(absltest.TestCase):

  def setUp(self):
    super(MailerTest, self).setUp()
    self.mock_mailer = mock.MagicMock(spec=plugins_base.Mailer)
    env_config.CONFIG.mailer = self.mock_mailer

  def testSendMail(self):
    mailer.SendMail(
        sender='sender',
        to='to',
        subject='subject',
        html='html',
        reply_to='reply_to',
        cc='cc',
        bcc='bcc')

    self.mock_mailer.SendMail.assert_called_once_with(
        sender='sender',
        to='to',
        subject='subject',
        html='html',
        reply_to='reply_to',
        cc='cc',
        bcc='bcc')

if __name__ == '__main__':
  absltest.main()
