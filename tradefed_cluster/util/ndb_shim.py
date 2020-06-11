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

from google.appengine.ext import ndb as legacy_ndb
from google.appengine.ext.ndb import msgprop

import tradefed_cluster.util.google_import_fixer  from google.cloud import ndb  
# All methods/classes used by tradefed_cluster are defined below
Expando = legacy_ndb.Expando
Key = legacy_ndb.Key
Model = legacy_ndb.Model

BooleanProperty = legacy_ndb.BooleanProperty
ComputedProperty = legacy_ndb.ComputedProperty
DateTimeProperty = legacy_ndb.DateTimeProperty
EnumProperty = msgprop.EnumProperty
IntegerProperty = legacy_ndb.IntegerProperty
JsonProperty = legacy_ndb.JsonProperty
LocalStructuredProperty = legacy_ndb.LocalStructuredProperty
StringProperty = legacy_ndb.StringProperty
StructuredProperty = legacy_ndb.StructuredProperty
TextProperty = legacy_ndb.TextProperty

Cursor = legacy_ndb.Cursor
EVENTUAL_CONSISTENCY = legacy_ndb.EVENTUAL_CONSISTENCY
Query = legacy_ndb.Query
QueryOptions = legacy_ndb.QueryOptions

delete_multi = legacy_ndb.delete_multi
get_context = legacy_ndb.get_context
get_multi = legacy_ndb.get_multi
put_multi = legacy_ndb.put_multi
put_multi_async = legacy_ndb.put_multi_async

toplevel = legacy_ndb.toplevel
transactional = legacy_ndb.transactional

