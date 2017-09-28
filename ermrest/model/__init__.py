# 
# Copyright 2013-2017 University of Southern California
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#    http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
A database introspection layer.

At present, the capabilities of this module are limited to introspection of an 
existing database model. This module does not attempt to capture all of the 
details that could be found in an entity-relationship model or in the standard 
information_schema of a relational database. It represents the model as 
needed by other modules of the ermrest project.
"""

from .type import Type, text_type, tsvector_type, int8_type, jsonb_type
from .column import Column
from .table import Table
from .schema import Model, Schema
from .introspect import introspect, current_model_version, normalized_catalog_version
from . import name
from . import predicate

__all__ = ["introspect", "current_model_version", "normalized_catalog_version", "Model", "Schema", "Table", "Column", "Type", "name", "predicate"]

