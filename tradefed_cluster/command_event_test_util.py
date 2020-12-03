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

from tradefed_cluster.util import ndb_shim as ndb

TIMESTAMP_INT = 1489010400
TIMESTAMP = datetime.datetime.utcfromtimestamp(TIMESTAMP_INT)
TASK_ID = "task_id"


def CreateTestCommandEventJson(request_id,
                               command_id,
                               attempt_id,
                               type_,
                               error=None,
                               data=None,
                               device_serials=None,
                               invocation_status=None,
                               task=None,
                               time=TIMESTAMP_INT,
                               device_lost_detected=0):
  """Create command event json for unit test."""
  event = {
      "task_id": "%s-%s-0" % (request_id, command_id),
      "attempt_id": attempt_id,
      "type": type_,
      "time": time,
      "hostname": "hostname",
      "device_serial": "0123456789ABCDEF",
      "data": {}
  }
  if task:
    event["task_id"] = task.task_id
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
        "device_lost_detected": device_lost_detected,
    }
    if error:
      event["data"]["error"] = error
  if data:
    event["data"].update(data)
  return event


def CreateTestCommandEvent(*args, **kwargs):
  """Create CommandEvent for test."""
  event = CreateTestCommandEventJson(*args, **kwargs)
  return command_event.CommandEvent(**event)


def CreateCommandAttempt(
    command, attempt_id, state,
    start_time=None, end_time=None, update_time=None, task=None):
  """Helper to create a command attempt."""
  command_attempt = datastore_entities.CommandAttempt(
      key=ndb.Key(
          datastore_entities.CommandAttempt,
          attempt_id,
          parent=command.key,
          namespace=common.NAMESPACE),
      attempt_id=attempt_id,
      command_id=command.key.id(),
      task_id=task.task_id if task else TASK_ID,
      state=state,
      start_time=start_time,
      end_time=end_time,
      update_time=update_time,
      attempt_index=task.attempt_index if task else None,
      run_index=task.run_index if task else None)
  command_attempt.put()
  return command_attempt
