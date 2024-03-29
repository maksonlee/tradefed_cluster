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

"""A shim for gradually migrating out of GAE NDB into Google Cloud NDB."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import functools
from six.moves import map


from google import auth
from google.cloud import ndb
from google.cloud.ndb import context as context_module

# All methods/classes used by tradefed_cluster are defined below
Expando = ndb.Expando
Key = ndb.Key
Model = ndb.Model

BooleanProperty = ndb.BooleanProperty
BlobProperty = ndb.BlobProperty
ComputedProperty = ndb.ComputedProperty
DateTimeProperty = ndb.DateTimeProperty
FloatProperty = ndb.FloatProperty
IntegerProperty = ndb.IntegerProperty
JsonProperty = ndb.JsonProperty
KeyProperty = ndb.KeyProperty
LocalStructuredProperty = ndb.LocalStructuredProperty
StringProperty = ndb.StringProperty
StructuredProperty = ndb.StructuredProperty
TextProperty = ndb.TextProperty

Cursor = ndb.Cursor
Query = ndb.Query

delete_multi = ndb.delete_multi
get_context = ndb.get_context
get_multi = ndb.get_multi
put_multi = ndb.put_multi
put_multi_async = ndb.put_multi_async

QueryOptions = ndb.QueryOptions
toplevel = ndb.toplevel
transaction = ndb.transaction
in_transaction = ndb.in_transaction

exceptions = ndb.exceptions

UnprojectedPropertyError = ndb.UnprojectedPropertyError

Client = ndb.Client


def transactional(*targs, **tkwargs):
  """A ndb transactional decorator with ALLOWED propagation mode."""
  def decorator(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
      if ndb.in_transaction():
        return func(*args, **kwargs)
      return ndb.transaction(lambda: func(*args, **kwargs), *targs, **tkwargs)
    return wrapper
  return decorator


# Enum Property hasn't been implemented by google.cloud ndb yet.
# We will continue to use our own implementation until google.cloud ndb has one.
# TODO: Check if EnumProperty is still needed.
class EnumProperty(IntegerProperty):
  """Enums are represented in Cloud Datastore as integers.

  While this is less user-friendly in the Datastore viewer, it matches
  the representation of enums in the protobuf serialization (although
  not in JSON), and it allows renaming enum values without requiring
  changes to values already stored in the Datastore.
  """

  _enum_type = None

  def __init__(self,
               enum_type,
               name=None,
               default=None,
               choices=None,
               **kwargs):
    """Constructor.

    Args:
      enum_type: A subclass of protorpc.messages.Enum.
      name: Optional datastore name (defaults to the property name).
      default: Default enum value
      choices: Universe of enum options available
      **kwargs: Additional keywords arguments specify the same options as
                supported by IntegerProperty.
    """
    self._enum_type = enum_type
    if default is not None:
      self._validate(default)
    if choices is not None:
      list(map(self._validate, choices))
    super(EnumProperty, self).__init__(name, default=default,
                                       choices=choices, **kwargs)

  def _validate(self, value):
    """Validate an Enum value.

    Args:
      value: The value of property to be validated
    Raises:
      TypeError if the value is not an instance of self._enum_type.
    """
    if not isinstance(value, self._enum_type):
      raise TypeError('Expected a %s instance, got %r instead' %
                      (self._enum_type.__name__, value))

  def _to_base_type(self, enum):
    """Convert an Enum value to a base type (integer) value."""
    return enum.number

  def _from_base_type(self, val):
    """Convert a base type (integer) value to an Enum value."""
    return self._enum_type(val)


def with_ndb_context(method):
  """Decorator to wrap individual endpoints in NDB Context."""

  @functools.wraps(method)
  def wrap_endpoint(*args, **kwargs):
    """Wraps the endpoint method in a NDB Context."""
    context = context_module.get_context(raise_context_error=False)
    if not context:
      creds, project = auth.default()
      with ndb.Client(project=project, credentials=creds).context(
          legacy_data=False):
        return method(*args, **kwargs)
    # If endpoint is inside a NDB context don't create a new context.
    return method(*args, **kwargs)

  return wrap_endpoint
