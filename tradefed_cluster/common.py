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

"""A module for common constants and functions."""
import base64
import datetime
import logging
import os

from protorpc import messages
import pytz
import retry
import six

# List APIs defaults
DEFAULT_PAGE_OFFSET = 0
DEFAULT_ROW_COUNT = 200

# Task queue constants
# Polling interval in seconds."
POLL_INTERVAL = 10
# The max number of request to process in batch.
BATCH_SIZE = 100
# The lease time for requests in seconds.
LEASE_SECS = 300

# Default timezone
DEFAULT_TZ = pytz.timezone("US/Pacific")

# Default date format
DATE_FORMAT = "%Y-%m-%d %H:%M"

NAMESPACE = "tfc-v2"

OBJECT_EVENT_QUEUE = "request-state-notification-queue"

HTTP_OK = ("", 200)


class TooMuchContentionError(Exception):
  """Exception identifier used for retrying too much contention errors."""
  pass


# TODO: Remove retry once TFC runs in firestore mode.
def RetryNdbContentionErrors(f):
  """If is a too much contention error it should be retried."""
  @retry.retry(exceptions=TooMuchContentionError,
               tries=3, delay=2, backoff=2, logger=logging)
  def Wrapper(*args, **kwargs):
    try:
      f(*args, **kwargs)
    except Exception as e:        exception_message = str(e)
      if "too much contention" in exception_message:
        raise TooMuchContentionError(exception_message)
      # If not matched by the parser will be raised.
      raise
  return Wrapper


class ClassProperty(object):
  """Class property decorator."""

  def __init__(self, f):
    self.f = f

  def __get__(self, obj, owner):
    return self.f(owner)


class CommandState(messages.Enum):
  """Command states."""
  UNKNOWN = 0
  QUEUED = 1
  RUNNING = 2
  CANCELED = 3
  COMPLETED = 4
  ERROR = 5
  FATAL = 6


def IsFinalCommandState(state):
  """Return True if this state is final."""
  return state in FINAL_COMMAND_STATES


FINAL_COMMAND_STATES = (
    CommandState.CANCELED,
    CommandState.COMPLETED,
    CommandState.ERROR,
    CommandState.FATAL,
)


class RequestState(messages.Enum):
  """Request states."""
  UNKNOWN = 0
  QUEUED = 1
  RUNNING = 2
  CANCELED = 3
  COMPLETED = 4
  ERROR = 5


def IsFinalRequestState(state):
  """Return True if this state is final."""
  return state in FINAL_REQUEST_STATES


FINAL_REQUEST_STATES = (
    RequestState.CANCELED,
    RequestState.COMPLETED,
    RequestState.ERROR,
)


class CommandErrorType(messages.Enum):
  """Command error type codes."""
  UNKNOWN = 0
  INFRA = 1
  TEST = 2


class DeviceState(object):
  """Device state."""
  ALLOCATED = "Allocated"
  AVAILABLE = "Available"
  CHECKING = "Checking_Availability"
  FASTBOOT = "Fastboot"
  GONE = "Gone"
  IGNORED = "Ignored"
  UNAVAILABLE = "Unavailable"
  UNKNOWN = "Unknown"
  # MH device state
  INIT = "Init"
  DYING = "Dying"
  MISSING = "Missing"
  PREPPING = "Prepping"
  DIRTY = "Dirty"
  LAMEDUCK = "Lameduck"

DEVICE_ALL_STATES = (
    DeviceState.ALLOCATED,
    DeviceState.AVAILABLE,
    DeviceState.CHECKING,
    DeviceState.FASTBOOT,
    DeviceState.GONE,
    DeviceState.IGNORED,
    DeviceState.UNAVAILABLE,
    DeviceState.UNKNOWN,
    DeviceState.INIT,
    DeviceState.DYING,
    DeviceState.MISSING,
    DeviceState.PREPPING,
    DeviceState.DIRTY,
    DeviceState.LAMEDUCK,
)

DEVICE_ONLINE_STATES = (
    DeviceState.ALLOCATED,
    DeviceState.AVAILABLE,
    DeviceState.CHECKING
)


DEVICE_OFFLINE_STATES = (
    DeviceState.FASTBOOT,
    DeviceState.GONE,
    DeviceState.IGNORED,
    DeviceState.UNAVAILABLE,
    DeviceState.UNKNOWN
)


class TestHarness(object):
  """Test harness."""
  UNKNOWN = "UNKNOWN"
  TRADEFED = "tradefed"
  MH = "MH"
  GOATS = "GOATS"



class CancelReason(messages.Enum):
  """Enum for cancel reasons."""
  UNKNOWN = 0
  QUEUE_TIMEOUT = 1
  REQUEST_API = 2
  COMMAND_ALREADY_CANCELED = 3
  REQUEST_ALREADY_CANCELED = 4
  COMMAND_NOT_EXECUTABLE = 5
  INVALID_REQUEST = 6




class ErrorReason(messages.Enum):
  """Enum for error reasons."""
  UNKNOWN = 0
  TOO_MANY_LOST_DEVICES = 1


# Invocation event types
class InvocationEventType(object):
  """Invocation event types."""
  ALLOCATION_FAILED = "AllocationFailed"
  CONFIGURATION_ERROR = "ConfigurationError"
  FETCH_FAILED = "FetchFailed"
  EXECUTE_FAILED = "ExecuteFailed"
  INVOCATION_INITIATED = "InvocationInitiated"
  INVOCATION_STARTED = "InvocationStarted"
  TEST_RUN_IN_PROGRESS = "TestRunInProgress"
  INVOCATION_COMPLETED = "InvocationCompleted"
  INVOCATION_ENDED = "InvocationEnded"


class ObjectEventType(object):
  REQUEST_STATE_CHANGED = "RequestStateChanged"
  COMMAND_ATTEMPT_STATE_CHANGED = "CommandAttemptStateChanged"


class LogLevel(messages.Enum):
  """Log levels."""
  UNKNOWN = 0
  VERBOSE = 1
  DEBUG = 2
  INFO = 3
  WARNING = 4
  ERROR = 5


class NoteType(messages.Enum):
  """The types of notes."""
  UNKNOWN = 0
  CLUSTER_NOTE = 1
  HOST_NOTE = 2
  DEVICE_NOTE = 3


class PredefinedMessageType(messages.Enum):
  """The types of predefined messages."""
  DEVICE_OFFLINE_REASON = 1
  DEVICE_RECOVERY_ACTION = 2
  HOST_OFFLINE_REASON = 3
  HOST_RECOVERY_ACTION = 4


def Now():
  """Returns the current time in UTC."""
  return datetime.datetime.utcnow()


class PublishEventType(messages.Enum):
  """Event types for publishing message to pubsub."""
  DEVICE_NOTE_EVENT = 0
  HOST_NOTE_EVENT = 1


class FilterHintType(messages.Enum):
  """Which type of filter hint will be retuened on the api."""
  POOL = 0
  LAB = 1
  RUN_TARGET = 2
  HOST = 3
  TEST_HARNESS = 4
  TEST_HARNESS_VERSION = 5
  DEVICE_STATE = 6
  HOST_STATE = 7
  HOST_GROUP = 8


class Operator(messages.Enum):
  """The types of operators."""
  UNKNOWN = 0
  EQUAL = 1
  LESS_THAN = 2
  LESS_THAN_OR_EQUAL = 3
  GREATER_THAN = 4
  GREATER_THAN_OR_EQUAL = 5


class RecoveryState(object):
  """Host and device recovery state."""
  UNKNOWN = "UNKNOWN"
  ASSIGNED = "ASSIGNED"
  FIXED = "FIXED"
  VERIFIED = "VERIFIED"


def UrlSafeB64Encode(message):
  """wrapper of base64.urlsafe_b64encode.

  Helper method to avoid calling six multiple times for preparing b64 strings.

  Args:
    message: string or binary to encode
  Returns:
    encoded data in string format.
  """
  data = base64.urlsafe_b64encode(six.ensure_binary(message))
  return six.ensure_str(data)


def UrlSafeB64Decode(message):
  """wrapper of base64.urlsafe_b64decode.

  Helper method to avoid calling six multiple times for preparing b64 strings.

  Args:
    message: string or binary to decode
  Returns:
    decoded data in string format.
  """
  data = base64.urlsafe_b64decode(six.ensure_binary(message))
  return six.ensure_str(data)


def GetServiceName():
  """Returns a GAE service name."""
  return os.environ.get("GAE_SERVICE")


def GetServiceVersion():
  """Returns a GAE service version."""
  return os.environ.get("GAE_VERSION")


class TestBenchKey(object):
  """Json keys for test bench."""
  HOST = "host"
  GROUPS = "groups"
  RUN_TARGETS = "run_targets"
  RUN_TARGET_NAME = "name"
  DEVICE_ATTRIBUTES = "device_attributes"
  ATTRIBUTE_NAME = "name"
  ATTRIBUET_VALUE = "value"
