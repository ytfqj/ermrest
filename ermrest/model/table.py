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

from .. import exception, ermpath
from ..util import sql_identifier, sql_literal, udecode
from .misc import AltDict, AclDict, DynaclDict, keying, annotatable, commentable, cache_rights, hasacls, hasdynacls, enforce_63byte_id, sufficient_rights, get_dynacl_clauses
from .column import Column, FreetextColumn
from .key import Unique, ForeignKey, KeyReference

import urllib
import json
import web

@commentable
@annotatable
@hasdynacls(
    { "owner", "update", "delete", "select" }
)
@hasacls(
    { "owner", "enumerate", "write", "insert", "update", "delete", "select" },
    { "owner", "insert", "update", "delete", "select" },
    lambda self: self.schema
)
@keying(
    'table',
    {
        "schema_name": ('text', lambda self: unicode(self.schema.name)),
        "table_name": ('text', lambda self: unicode(self.name))
    }
)
class Table (object):
    """Represents a database table.
    
    At present, this has a 'name' and a collection of table 'columns'. It
    also has a reference to its 'schema'.
    """
    
    def __init__(self, schema, name, columns, kind, comment=None, annotations={}, acls={}, dynacls={}):
        self.schema = schema
        self.name = name
        self.kind = kind
        self.comment = comment
        self.columns = AltDict(
            lambda k: exception.ConflictModel(u"Requested column %s does not exist in table %s." % (k, self.name)),
            lambda k, v: enforce_63byte_id(k, "Column")
        )
        self.uniques = AltDict(
            lambda k: exception.ConflictModel(u"Requested key %s does not exist in table %s." % (
                ",".join([unicode(c.name) for c in k]), self.name)
            )
        )
        self.fkeys = AltDict(
            lambda k: exception.ConflictModel(
                u"Requested foreign-key %s does not exist in table %s." % (
                    ",".join([unicode(c.name) for c in k]), self)
            )
        )
        self.annotations = AltDict(
            lambda k: exception.NotFound(u'annotation "%s" on table %s' % (k, self))
        )
        self.annotations.update(annotations)
        self.acls = AclDict(self)
        self.acls.update(acls)
        self.dynacls = DynaclDict(self)
        self.dynacls.update(dynacls)

        for c in columns:
            self.columns[c.name] = c
            c.table = self

        if name not in self.schema.tables:
            self.schema.tables[name] = self

    @staticmethod
    def keyed_resource(model=None, schema_name=None, table_name=None):
        return model.schemas[schema_name].tables[table_name]

    def __str__(self):
        return ':%s:%s' % (
            urllib.quote(unicode(self.schema.name).encode('utf8')),
            urllib.quote(unicode(self.name).encode('utf8'))
            )

    def __repr__(self):
        return '<ermrest.model.Table %s>' % str(self)

    @cache_rights
    def has_right(self, aclname, roles=None):
        # we need parent enumeration too
        if not self.schema.has_right('enumerate', roles):
            return False
        return self._has_right(aclname, roles)

    def columns_in_order(self):
        cols = [ c for c in self.columns.values() if c.has_right('enumerate') ]
        cols.sort(key=lambda c: c.position)
        return cols

    def has_primary_key(self):
        for k in self.uniques.values():
            if k.is_primary_key():
                return True
        return False

    def check_primary_keys(self, require):
        if not self.has_primary_key():
            if require:
                raise exception.rest.RuntimeError('Table %s lacks primary key. Contact ERMrest administrator.' % self)
            else:
                web.debug('WARNING: Table %s lacks primary key.' % self)

    def writable_kind(self):
        """Return true if table is writable in SQL.

           TODO: handle writable views some day?
        """
        if self.kind == 'r':
            return True
        return False

    def verbose(self):
        return json.dumps(self.prejson(), indent=2)

    @staticmethod
    def create_fromjson(conn, cur, schema, tabledoc, ermrest_config):
        sname = tabledoc.get('schema_name', unicode(schema.name))
        if sname != unicode(schema.name):
            raise exception.ConflictModel('JSON schema name %s does not match URL schema name %s' % (sname, schema.name))

        if 'table_name' not in tabledoc:
            raise exception.BadData('Table representation requires table_name field.')
        
        tname = tabledoc.get('table_name')

        if tname in schema.tables:
            raise exception.ConflictModel('Table %s already exists in schema %s.' % (tname, sname))

        kind = tabledoc.get('kind', 'table')
        if kind != 'table':
            raise exception.ConflictData('Kind "%s" not supported in table creation' % kind)

        schema.enforce_right('create')

        acls = tabledoc.get('acls', {})
        dynacls = tabledoc.get('acl_bindings', {})
        annotations = tabledoc.get('annotations', {})
        columns = Column.fromjson(tabledoc.get('column_definitions',[]), ermrest_config)
        comment = tabledoc.get('comment')
        table = Table(schema, tname, columns, 'r', comment, annotations)
        if not schema.has_right('owner'):
            table.acls['owner'] = [web.ctx.webauthn2_context.client] # so enforcement won't deny next step...
            table.set_acl(cur, 'owner', [web.ctx.webauthn2_context.client])

        clauses = []
        for column in columns:
            clauses.append(column.sql_def())
            
        cur.execute("""
CREATE TABLE %(sname)s.%(tname)s (
   %(clauses)s
);
COMMENT ON TABLE %(sname)s.%(tname)s IS %(comment)s;
SELECT _ermrest.model_change_event();
SELECT _ermrest.data_change_event(%(snamestr)s, %(tnamestr)s);
""" % dict(sname=sql_identifier(sname),
           tname=sql_identifier(tname),
           snamestr=sql_literal(sname),
           tnamestr=sql_literal(tname),
           clauses=',\n'.join(clauses),
           comment=sql_literal(comment),
           )
                    )

        for keydoc in tabledoc.get('keys', []):
            for key in table.add_unique(conn, cur, keydoc):
                # need to drain this generating function
                pass
        
        for fkeydoc in tabledoc.get('foreign_keys', []):
            for fkr in table.add_fkeyref(conn, cur, fkeydoc):
                # need to drain this generating function
                pass

        if ermrest_config.get('require_primary_keys', True):
            if not table.has_primary_key():
                raise exception.BadData('Table definitions require at least one not-null key constraint.')

        for k, v in annotations.items():
            table.set_annotation(conn, cur, k, v)

        for k, v in acls.items():
            table.set_acl(cur, k, v)

        for k, v in dynacls.items():
            table.set_dynacl(cur, k, v)

        def execute_if(sql):
            if sql:
                try:
                    cur.execute(sql)
                except:
                    web.debug('Got error executing SQL: %s' % sql)
                    raise

        for column in columns:
            if column.comment is not None:
                column.set_comment(conn, cur, column.comment)
            for k, v in column.annotations.items():
                column.set_annotation(conn, cur, k, v)
            for k, v in column.acls.items():
                column.set_acl(cur, k, v)
            for k, v in column.dynacls.items():
                column.set_dynacl(cur, k, v)
            try:
                execute_if(column.btree_index_sql())
                execute_if(column.pg_trgm_index_sql())
            except Exception, e:
                web.debug(table, column, e)
                raise
                
        return table

    def delete(self, conn, cur):
        self.enforce_right('owner')
        self.pre_delete(conn, cur)
        cur.execute("""
DROP %(kind)s %(sname)s.%(tname)s ;
SELECT _ermrest.model_change_event();
SELECT _ermrest.data_change_event(%(snamestr)s, %(tnamestr)s);
""" % dict(
    kind={'r': 'TABLE', 'v': 'VIEW', 'f': 'FOREIGN TABLE'}[self.kind],
    sname=sql_identifier(self.schema.name), 
    tname=sql_identifier(self.name),
    snamestr=sql_literal(self.schema.name), 
    tnamestr=sql_literal(self.name)
)
        )

    def pre_delete(self, conn, cur):
        """Do any maintenance before table is deleted."""
        for fkey in self.fkeys.values():
            fkey.pre_delete(conn, cur)
        for unique in self.uniques.values():
            unique.pre_delete(conn, cur)
        for column in self.columns.values():
            column.pre_delete(conn, cur)
        self.delete_annotation(conn, cur, None)
        self.delete_acl(cur, None, purging=True)

    def alter_table(self, conn, cur, alterclause):
        """Generic ALTER TABLE ... wrapper"""
        self.enforce_right('owner')
        cur.execute("""
ALTER TABLE %(sname)s.%(tname)s  %(alter)s ;
SELECT _ermrest.model_change_event();
SELECT _ermrest.data_change_event(%(snamestr)s, %(tnamestr)s);
""" % dict(sname=sql_identifier(self.schema.name), 
           tname=sql_identifier(self.name),
           snamestr=sql_literal(self.schema.name), 
           tnamestr=sql_literal(self.name),
           alter=alterclause
       )
                    )

    def sql_comment_resource(self):
        return "TABLE %s.%s" % (
            sql_identifier(unicode(self.schema.name)),
            sql_identifier(unicode(self.name))
        )

    def add_column(self, conn, cur, columndoc, ermrest_config):
        """Add column to table."""
        self.enforce_right('owner')
        # new column always goes on rightmost position
        position = len(self.columns)
        column = Column.fromjson_single(columndoc, position, ermrest_config)
        if column.name in self.columns:
            raise exception.ConflictModel('Column %s already exists in table %s:%s.' % (column.name, self.schema.name, self.name))
        column.table = self
        self.alter_table(conn, cur, 'ADD COLUMN %s' % column.sql_def())
        column.set_comment(conn, cur, column.comment)
        self.columns[column.name] = column
        column.table = self
        for k, v in column.annotations.items():
            column.set_annotation(conn, cur, k, v)
        for k, v in column.acls.items():
            column.set_acl(cur, k, v)
        return column

    def delete_column(self, conn, cur, cname):
        """Delete column from table."""
        self.enforce_right('owner')
        column = self.columns[cname]
        for unique in self.uniques.values():
            if column in unique.columns:
                unique.pre_delete(conn, cur)
        for fkey in self.fkeys.values():
            if column in fkey.columns:
                fkey.pre_delete(conn, cur)
        column.pre_delete(conn, cur)
        self.alter_table(conn, cur, 'DROP COLUMN %s' % sql_identifier(cname))
        del self.columns[cname]
                    
    def add_unique(self, conn, cur, udoc):
        """Add a unique constraint to table."""
        self.enforce_right('owner')
        for key in Unique.fromjson_single(self, udoc):
            key.add(conn, cur)
            yield key

    def add_fkeyref(self, conn, cur, fkrdoc):
        """Add foreign-key reference constraint to table."""
        self.enforce_right('owner')
        for fkr in KeyReference.fromjson(self.schema.model, fkrdoc, None, self, None, None, None):
            # new foreign key constraint must be added to table
            fkr.add(conn, cur)
            for k, v in fkr.annotations.items():
                fkr.set_annotation(conn, cur, k, v)
            for k, v in fkr.acls.items():
                fkr.set_acl(cur, k, v, anon_mutation_ok=True)
            for k, v in fkr.dynacls.items():
                fkr.set_dynacl(cur, k, v)
            yield fkr

    def prejson(self):
        doc = {
            "schema_name": self.schema.name,
            "table_name": self.name,
            "rights": self.rights(),
            "column_definitions": [
                c.prejson() for c in self.columns_in_order()
            ],
            "keys": [
                u.prejson() for u in self.uniques.values() if u.has_right('enumerate')
            ],
            "foreign_keys": [
                fkr.prejson()
                for fk in self.fkeys.values() for fkr in fk.references.values() if fkr.has_right('enumerate')
            ],
            "kind": {
                'r':'table', 
                'f':'foreign_table',
                'v':'view'
            }.get(self.kind, 'unknown'),
            "comment": self.comment,
            "annotations": self.annotations
        }
        if self.has_right('owner'):
            doc['acls'] = self.acls
            doc['acl_bindings'] = self.dynacls
        return doc

    def sql_name(self, dynauthz=None, access_type='select', alias=None, dynauthz_testcol=None, dynauthz_testfkr=None):
        """Generate SQL representing this entity for use as a FROM clause.

           dynauthz: dynamic authorization mode to compile
               None: do not compile dynamic ACLs
               True: compile positive ACL... match rows client is authorized to access
               False: compile negative ACL... match rows client is NOT authorized to access

           access_type: the access type to be enforced for dynauthz

           dynauthz_testcol:
               None: normal mode
               col: match rows where client is NOT authorized to access column

           dynauthz_testfkr:
               None: normal mode
               fkr: compile using dynamic ACLs from fkr instead of from this table

           The result is a schema-qualified table name for dynauthz=None, else a subquery.
        """
        tsql = '.'.join([
            sql_identifier(self.schema.name),
            sql_identifier(self.name)
        ])

        talias = alias if alias else 's'

        if dynauthz is not None:
            assert alias is not None
            assert dynauthz_testcol is None
            if dynauthz_testfkr is not None:
                assert dynauthz_testfkr.unique.table == self

            clauses = get_dynacl_clauses(self if dynauthz_testfkr is None else dynauthz_testfkr, access_type, alias)

            if dynauthz:
                tsql = "(SELECT %s FROM %s %s WHERE (%s))" % (
                    ', '.join([ c.sql_name_dynauthz(talias, dynauthz=True, access_type=access_type) for c in self.columns_in_order()]),
                    tsql,
                    talias,
                    ' OR '.join(["(%s)" % clause for clause in clauses ]),
                )
            else:
                tsql = "(SELECT * FROM %s %s WHERE (%s))" % (
                    tsql,
                    talias,
                    ' AND '.join(["COALESCE(NOT (%s), True)" % clause for clause in clauses ])
                )
        elif dynauthz_testcol is not None:
            assert alias is not None
            tsql = "(SELECT * FROM %s %s WHERE (%s))" % (
                tsql,
                talias,
                dynauthz_testcol.sql_name_dynauthz(talias, dynauthz=False, access_type=access_type)
            )

        if alias is not None:
            tsql = "%s AS %s" % (tsql, sql_identifier(alias))

        return tsql

    def freetext_column(self):
        return FreetextColumn(self)

