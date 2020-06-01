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

"""Util for creating command event for tests."""

import datetime


from tradefed_cluster import command_event
from tradefed_cluster import common
from tradefed_cluster import datastore_entities

from google.appengine.ext import ndb

TIMESTAMP_INT = 1489010400
TIMESTAMP = datetime.datetime.utcfromtimestamp(TIMESTAMP_INT)
TASK_ID = "task_id"


def CreateTestCommandEventJson(
    request_id, command_id, attempt_id, type_, run_index=0,
    error=None, data=None, device_serials=None, invocation_status=None,
    time=TIMESTAMP_INT):
  """Create command event json for unit test."""
  event = {
      "task_id": "%s-%s-%d" % (request_id, command_id, run_index),
      "attempt_id": attempt_id,
      "type": type_,
      "time": time,
      "hostname": "hostname",
      "device_serial": "0123456789ABCDEF",
      "data": {}
  }
  if device_serials:
    event["device_serials"] = device_serials
  if invocation_status:
    event["invocation_status"] = invocation_status
  if type_ == "InvocationCompleted":
    event["data"] = {
        "summary": "summary",
        "total_test_count": 1000,
        "failed_test_count": 100,
        "passed_test_count": 900,
        "failed_test_run_count": 10,
        "device_lost_detected": 1,
    }
    if error:
      event["data"]["error"] = error
  if data:
    event.get("data").update(data)
  return event


def CreateTestCommandEvent(*args, **kwargs):
  """Create CommandEvent for test."""
  event = CreateTestCommandEventJson(*args, **kwargs)
  return command_event.CommandEvent(**event)


def CreateCommandAttempt(command,
                         attempt_id,
                         state,
                         start_time=None,
                         end_time=None,
                         update_time=None,
                         task_id=TASK_ID):
  """Helper to create a command attempt."""
  command_attempt = datastore_entities.CommandAttempt(
      key=ndb.Key(
          datastore_entities.CommandAttempt,
          attempt_id,
          parent=command.key,
          namespace=common.NAMESPACE),
      attempt_id=attempt_id,
      command_id=command.key.id(),
      task_id=task_id,
      state=state,
      start_time=start_time,
      end_time=end_time,
      update_time=update_time)
  command_attempt.put()
  return command_attempt
