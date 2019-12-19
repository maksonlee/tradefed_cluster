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

"""Module to render and send email."""

import logging

import jinja2

from google.appengine.api import mail


# Default date format
DATE_FORMAT = '%Y-%m-%d %H:%M'


def FormatDatetime(date, fmt=DATE_FORMAT):
  """Date formatter for a jinja environment.

  Args:
    date: datetime object to format
    fmt: string format
  Returns:
    Formatted date
  """
  return date.strftime(fmt)


def Render(template_dir, template_name, **kwargs):
  """Render a template.

  Args:
    template_dir: path to the template directory
    template_name: the template's name
    **kwargs: args for the template
  Returns:
    the rendered template string
  Raises:
    TemplateNotFound: can not find the template
    TemplateError: rendering the template failed
  """
  jinja_env = jinja2.Environment(
      loader=jinja2.FileSystemLoader(template_dir),
      extensions=['jinja2.ext.autoescape'],
      autoescape=True,
      variable_start_string='[[',
      variable_end_string=']]'
  )
  jinja_env.filters['datetime'] = FormatDatetime
  try:
    template = jinja_env.get_template(template_name)
    return template.render(**kwargs)
  except jinja2.TemplateError:
    logging.exception('Render template %s failed.', template_name)
    raise


def SendEmail(sender, recipient, subject, html_body, reply_to=None):
  """Send an email.

  Args:
    sender: email sender
    recipient: send the email to
    subject: the email's subject
    html_body: a html body
    reply_to: a reply to address
  """
  logging.info(
      'Sending email from %s to %s with subject: %s',
      sender, recipient, subject)
  if not reply_to:
    reply_to = sender
  message = mail.EmailMessage(
      sender=sender,
      to=recipient,
      subject=subject,
      html=html_body,
      reply_to=reply_to)
  message.send()
