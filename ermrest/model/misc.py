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

from .. import exception
from ..util import sql_identifier, sql_literal, table_exists, udecode
from .. import ermpath
from .type import _default_config
from .name import Name

import json
import web
import hashlib
import base64

def frozendict (d):
    """Convert a dictionary to a canonical and immutable form."""
    items = d.items()
    items.sort() # sort by key, value pair
    return tuple(items)
        
def _get_ermrest_config():
    """Helper method to return the ERMrest config.
    """ 
    if web.ctx and 'ermrest_config' in web.ctx:
        return web.ctx['ermrest_config']
    else:
        return _default_config

def enforce_63byte_id(s, prefix="Identifier"):
    s = udecode(s)
    if type(s) is not unicode:
        raise exception.BadData(u'%s "%s" "%s" is unsupported and should be unicode.' % (prefix, s, type(s)))
    if len(s.encode('utf8')) > 63:
        raise exception.BadData(u'%s "%s" exceeded 63-byte limit when encoded as UTF-8.' % (prefix, s))

def truncated_identifier(parts, threshold=4):
    """Build a 63 byte (or less) postgres identifier out of sequentially concatenated parts.
    """
    parts = [ udecode(p).encode('utf8') for p in parts ]
    len_static = len(''.join([ p for p in parts if len(p) <= threshold ]))
    assert len_static < 20
    num_components = len([ p for p in parts if len(p) > threshold ])
    max_component_len = (63 - len_static) / (num_components or 1)

    def convert(p):
        if len(p) <= max_component_len:
            return p
        # return a truncated hash using base64 chars
        h = hashlib.md5()
        h.update(p)
        return base64.b64encode(h.digest())[0:max_component_len]

    result = ''.join([ convert(p) for p in parts ])
    assert len(result) <= 63
    result = udecode(result)
    return result

sufficient_rights = {
    "owner": set(),
    "create": {"owner"},
    "write": {"owner"},
    "insert": {"owner", "write"},
    "update": {"owner", "write"},
    "delete": {"owner", "write"},
    "select": {"owner", "write", "update", "delete"},
    "enumerate": {"owner", "create", "write", "insert", "update", "delete", "select"},
}

class AltDict (dict):
    """Alternative dict that raises custom errors."""
    def __init__(self, keyerror, validator=lambda k, v: (k, v)):
        dict.__init__(self)
        self._keyerror = keyerror
        self._validator = validator

    def __getitem__(self, k):
        try:
            result = dict.__getitem__(self, k)
            return result
        except KeyError:
            raise self._keyerror(k)

    def __setitem__(self, k, v):
        self._validator(k, v)
        return dict.__setitem__(self, k, v)

    def get_enumerable(self, k):
        result = self[k]
        if not result.has_right('enumerate'):
            raise self._keyerror(k)
        return result

class AclDict (dict):
    """Alternative dict that validates keys and returns default."""
    def __init__(self, subject):
        dict.__init__(self)
        self._subject = subject

    def __getitem__(self, k):
        if k not in self._subject._acls_supported:
            raise exception.NotFound('ACL %s on %s' % (k, self._subject))
        try:
            return dict.__getitem__(self, k)
        except KeyError, e:
            return None

class AclBasePredicate (object):
    def validate(self, epath, allow_star=False):
        pass

    def sql_where(self, epath, elem, prefix=None):
        assert prefix
        key = None
        for unique in elem.table.uniques.values():
            nullok = False
            for col in unique.columns:
                if col.nullok:
                    nullok = True
                    break
            if nullok:
                continue
            else:
                key = unique
                break
        assert key
        clauses = [
            '%s.%s = %st0.%s' % (
                prefix,
                col.sql_name(),
                prefix,
                col.sql_name()
            )
            for col in key.columns
        ]
        return ' AND '.join(['(%s)' % clause for clause in clauses ])

class AclBinding (AltDict):
    """Represents one acl binding."""
    def __init__(self, model, resource, binding_name, doc):
        def keyerror(k):
            return KeyError(k)
        def validator(k, v):
            if k == 'types':
                if type(v) is not list or len(v) == 0:
                    raise exception.BadData('Field "types" in ACL binding "%s" must be a non-empty list of type names.' % binding_name)
                for t in v:
                    if t not in resource.dynacl_types_supported:
                        raise exception.BadData('ACL binding type %r is not supported on this resource.' % t)
            elif k == 'projection':
                pass
            elif k == 'projection_type':
                if v not in ['acl', 'nonnull']:
                    raise exception.BadData('ACL binding projection-type %r is not supported.' % (v,))
            elif k == 'comment':
                if type(v) not in [str, unicode]:
                    raise exception.BadData('ACL binding comment must be of string type.')
            else:
                raise exception.BadData('Field "%s" in ACL binding "%s" not recognized.' % (k, binding_name))
        AltDict.__init__(self, keyerror, validator)
        self.model = model
        self.resource = resource
        self.binding_name = binding_name

        # let AltDict validator behavior check each field above for simple stuff...
        for k, v in doc.items():
            self[k] = v

        # now check overall constraints...
        for k in ['types', 'projection']:
            if k not in self:
                raise exception.BadData('Field "%s" is required for ACL bindings.' % k)

        # validate the projection against the model
        aclpath, col, ctype = self._compile_projection()

        # set default
        if 'projection_type' not in self:
            self['projection_type'] = 'acl' if ctype.name == 'text' else 'nonnull'

    def _compile_projection(self):
        proj = self['projection']

        if type(proj) in [str, unicode]:
            # expand syntactic sugar for bare column name projection
            proj = [proj]

        epath = ermpath.EntityPath(self.model)

        if hasattr(self.resource, 'unique'):
            epath.set_base_entity(self.resource.unique.table, 'base')
        elif hasattr(self.resource, 'table'):
            epath.set_base_entity(self.resource.table, 'base')
        else:
            epath.set_base_entity(self.resource, 'base')

        epath.add_filter(AclBasePredicate())

        def compile_join(elem):
            # HACK: this repeats some of the path resolution logic that is tangled in the URL parser/AST code...
            lalias = elem.get('context')
            if lalias is not None:
                if type(lalias) not in [str, unicode]:
                    raise exception.BadData('Context %r in ACL binding %s must be a string literal alias name.' % (lalias, self.binding_name))
                epath.set_context(elem['context'])

            ltable = epath.current_entity_table()
            ralias = elem.get('alias')
            if ralias is not None:
                if type(ralias) not in [str, unicode]:
                    raise exception.BadData('Alias %r in ACL binding %s must be a string literal alias name.' % (lalias, self.binding_name))
            fkeyname = elem.get('inbound', elem.get('outbound'))
            if (type(fkeyname) is not list \
                or len(fkeyname) != 2 \
                or type(fkeyname[0]) not in [str, unicode] \
                or type(fkeyname[1]) not in [str, unicode]
            ):
                raise exception.BadData('Foreign key name %r in ACL binding %s not valid.' % (fkeyname, self.binding_name))
            fkeyname = tuple(fkeyname)

            def find_fkeyref(sources, fkeyname):
                for source in sources.values():
                    for fkeyrefset in source.table_references.values():
                        for constr in fkeyrefset:
                            if constr.constraint_name == fkeyname:
                                return constr
                raise exception.ConflictModel('No foreign key %r found connected to table %s in ACL binding %s' % (
                    fkeyname, ltable, self.binding_name
                ))

            if elem.get('inbound') is not None:
                fkeyref = find_fkeyref(ltable.uniques, fkeyname)
                refop = '@='
            else:
                fkeyref = find_fkeyref(ltable.fkeys, fkeyname)
                refop = '=@'
            epath.add_link(fkeyref, refop, ralias=ralias)

        def compile_filter(elem):
            if 'and' in elem:
                filt = ast.data.predicate.Conjunction([ compile_filter(e) for e in elem['and'] ])
            elif 'or' in elem:
                filt = ast.data.predicate.Disjunction([ compile_filter(e) for e in elem['or'] ])
            elif 'filter' in elem:
                lname = elem['filter']
                if type(lname) in [str, unicode]:
                    # expand syntactic sugar for bare column name filter
                    lname = [ lname ]
                if (type(lname) is not list \
                    or len(lname) != 2 \
                    or type(lname[0]) not in [str, unicode] \
                    or type(lname[1]) not in [str, unicode]
                ):
                    raise exception.BadData('Invalid filter column name %r in ACL binding %s.' % (lname, self.binding_name))
                lname = ast.name(lname)
                operator = elem.get('operator', '=')
                try:
                    klass = ast.data.predicatecls(operator)
                except KeyError:
                    raise exception.BadData('Unknown operator %r in ACL binding %s.' % (operator, self.binding_name))
                if operator == 'null':
                    filt = klass(lname)
                else:
                    operand = ast.Value(elem.get('operand', ''))
                    filt = klass(lname, operand)
            else:
                raise exception.BadData('Filter element %r of ACL binding %s is malformed.' % (elem, self.binding_name))
            if elem.get('negate', False):
                filt = ast.data.predicate.Negation(filt)
            return filt

        # extend path with each element left to right
        for elem in proj[0:-1]:
            if type(elem) is not dict:
                raise exception.BadData('Projection element %s of ACL binding %s must be an object.' % (elem, self.binding_name))
            if 'inbound' in elem or 'outbound' in elem:
                compile_join(elem)
            else:
                filt = compile_filter(elem)
                filt.validate(epath)
                epath.add_filter(filt)

        # apply final projection
        if type(proj[-1]) not in [str, unicode]:
            raise exception.BadData('Projection for ACL binding %s must conclude with a string literal column name.' % self.binding_name)

        col = epath.current_entity_table().columns[proj[-1]]
        aclpath = ermpath.AttributePath(epath, [ (Name([proj[-1]]), col, epath) ])
        ctype = col.type
        while ctype.is_array or ctype.is_domain:
            ctype = ctype.base_type

        if self.get('projection_type') == 'acl' and ctype.name != 'text':
            raise exception.ConflictModel('ACL binding projection type %r not allowed for column %s in ACL binding %s.' % (
                self['projection_type'], col, self.binding_name
            ))

        return (aclpath, col, ctype)

class AclPredicate (object):
    def __init__(self, binding, column):
        self.binding = binding
        self.left_col = column
        self.left_elem = None

    def validate(self, epath, allow_star=False):
        self.left_elem = epath._path[epath.current_entity_position()]

    def sql_where(self, epath, elem, prefix=''):
        lname = '%st%d.%s' % (prefix, self.left_elem.pos, self.left_col.sql_name())
        if binding['projection_type'] == 'acl':
            attrs = 'ARRAY[%s]::text[]' % ','.join([ sql_literal(a['id']) for a in web.ctx.webauthn2_context.attributes ])
            if self.left_col.type.is_array:
                return '%s && %s' % (lname, attrs)
            else:
                return '%s = ANY (%s)' % (lname, attrs)
        else:
            return '%s NOT NULL' % (lname,)

def commentable(orig_class):
    """Decorator to add comment storage access interface to model classes.
    """
    def set_comment(self, conn, cur, comment):
        """Set SQL comment."""
        self.enforce_right('owner')
        resources = self.sql_comment_resource()
        if not isinstance(resources, set):
            # backwards compatibility
            resources = set([resources])
        for resource in resources:
            cur.execute("""
COMMENT ON %s IS %s;
SELECT _ermrest.model_change_event();
""" % (resource, sql_literal(comment))
            )
            self.comment = comment

    setattr(orig_class, 'set_comment', set_comment)
    return orig_class
        
annotatable_classes = []

def keying(restype, keying):
    """Decorator to configure resource type and keying for model classes.

       restype: the string name for the resource type, used to name auxilliary storage

       keying: dictionary of column names mapped to (psql_type, function) pairs
         which define the Postgres storage type and compute 
         literals for those columns to key the individual annotations.

    """
    def helper(orig_class):
        setattr(orig_class, '_model_restype', restype)
        setattr(orig_class, '_model_keying', keying)
        return orig_class
    return helper

def _create_storage_table(orig_class, cur, suffix, extra_keys, extra_cols):
    tname = 'model_%s_%s' % (orig_class._model_restype, suffix)
    if table_exists(cur, '_ermrest', tname):
        return
    cur.execute("""
CREATE TABLE _ermrest.%(tname)s (%(cols)s);
""" % dict(
    tname=tname,
    cols=', '.join(
        [
            '%s %s NOT NULL' % (sql_identifier(colname), coltype)
            for colname, coltype in [
                (k, v[0]) for k, v in orig_class._model_keying.items()
            ]
            + extra_keys.items()
            + extra_cols.items()
        ] + [
            'UNIQUE(%s)' % ', '.join([
                sql_identifier(k)
                for k in (orig_class._model_keying.keys() + extra_keys.keys())
            ])
        ]
    )
)
    )

def _introspect_helper(orig_class, cur, model, suffix, extra_keys, extra_cols, func):
    tname = 'model_%s_%s' % (orig_class._model_restype, suffix)
    cols = orig_class._model_keying.keys() + extra_keys.keys() + extra_cols.keys()
    cur.execute("""
SELECT %(cols)s FROM _ermrest.%(tname)s;
""" % dict(
    tname=tname,
    cols=', '.join([sql_identifier(c) for c in cols])
)
    )
    for row in cur:
        kwargs0 = {
            cols[i]: row[i]
            for i in range(
                    len(orig_class._model_keying.keys())
            )
        }
        kwargs0['model'] = model

        kwargs1 = {
            cols[i]: row[i]
            for i in range(
                    len(orig_class._model_keying.keys()),
                    len(orig_class._model_keying.keys()) + len(extra_keys.keys()) + len(extra_cols.keys())
            )
        }

        try:
            kwargs1['resource'] = orig_class.keyed_resource(**kwargs0)
            func(**kwargs1)
        except exception.ConflictModel:
            # TODO: prune orphaned auxilliary storage?
            pass

def annotatable(orig_class):
    """Decorator to add annotation storage access interface to model classes.

       The keying() decorator MUST be applied before this one.
    """
    def _interp_annotation(self, key, sql_wrap=True):
        if sql_wrap:
            sql_wrap = sql_literal
        else:
            sql_wrap = lambda v: v
        return dict([
            (k, sql_wrap(v[1](self))) for k, v in orig_class._model_keying.items()
        ] + [
            ('annotation_uri', sql_wrap(key))
        ])
        
    def set_annotation(self, conn, cur, key, value):
        """Set annotation on %s, returning previous value for updates or None.""" % orig_class._model_restype
        assert key is not None
        self.enforce_right('owner')
        interp = self._interp_annotation(key)
        where = ' AND '.join([
            "new.%(col)s = old.%(col)s AND new.%(col)s = %(val)s" % dict(col=sql_identifier(k), val=v)
            for k, v in interp.items()
        ])
        cur.execute("""
SELECT _ermrest.model_change_event();
UPDATE _ermrest.model_%(restype)s_annotation new
SET annotation_value = %(newval)s
FROM _ermrest.model_%(restype)s_annotation old
WHERE %(where)s
RETURNING old.annotation_value;
""" % dict(
    restype=orig_class._model_restype,
    newval=sql_literal(json.dumps(value)),
    where=where
)
        )
        for oldvalue in cur:
            # happens zero or one time
            return oldvalue

        # only run this if update returned empty set
        columns = ', '.join([sql_identifier(k) for k in interp.keys()] + ['annotation_value'])
        values = ', '.join([interp[k] for k in interp.keys()] + [sql_literal(json.dumps(value))])
        cur.execute("""
INSERT INTO _ermrest.model_%s_annotation (%s) VALUES (%s);
""" % (orig_class._model_restype, columns, values)
        )
        return None

    def delete_annotation(self, conn, cur, key):
        """Delete annotation on %s.""" % orig_class._model_restype
        self.enforce_right('owner')
        interp = self._interp_annotation(key)
        if key is None:
            del interp['annotation_uri']
        keys = interp.keys()
        where = ' AND '.join([
            "%s = %s" % (sql_identifier(k), interp[k])
            for k in keys
        ])
        cur.execute("""
SELECT _ermrest.model_change_event();
DELETE FROM _ermrest.model_%s_annotation WHERE %s;
""" % (orig_class._model_restype, where)
        )

    @classmethod
    def create_storage_table(orig_class, cur):
        _create_storage_table(orig_class, cur, 'annotation', {'annotation_uri': 'text'}, {'annotation_value': 'json'})

    @classmethod
    def introspect_helper(orig_class, cur, model):
        def helper(resource=None, annotation_uri=None, annotation_value=None):
            resource.annotations[annotation_uri] = annotation_value
        _introspect_helper(orig_class, cur, model, 'annotation', {'annotation_uri': 'text'}, {'annotation_value': 'json'}, helper)

    setattr(orig_class, '_interp_annotation', _interp_annotation)
    setattr(orig_class, 'set_annotation', set_annotation)
    setattr(orig_class, 'delete_annotation', delete_annotation)
    if hasattr(orig_class, 'keyed_resource'):
        setattr(orig_class, 'introspect_helper', introspect_helper)
    setattr(orig_class, 'create_storage_table', create_storage_table)
    annotatable_classes.append(orig_class)
    return orig_class

hasacls_classes = []

def hasacls(acls_supported, rights_supported, getparent):
    """Decorator to add ACL storage access interface to model classes.

       acls_supported: { aclname, ... }

       rights_supported: { aclname, ... }

       getparent: getparent_func

       The keying() decorator MUST be applied first.
    """
    def _interp_acl(self, aclname):
        interp = {
            k: sql_literal(v[1](self))
            for k, v in self._model_keying.items()
        }
        interp['acl'] = sql_literal(aclname)
        return interp

    @classmethod
    def create_acl_storage_table(orig_class, cur):
        _create_storage_table(orig_class, cur, 'acl', {'acl': 'text'}, {'members': 'text[]'})

    @classmethod
    def introspect_acl_helper(orig_class, cur, model):
        def helper(resource=None, acl=None, members=None):
            resource.acls[acl] = members
        _introspect_helper(orig_class, cur, model, 'acl', {'acl': 'text'}, {'members': 'text[]'}, helper)

    def set_acl(self, cur, aclname, members):
        """Set annotation on %s, returning previous value for updates or None.""" % self._model_restype
        assert aclname is not None

        if members is None:
            return self.delete_acl(cur, aclname)

        self.enforce_right('owner') # pre-flight authz
        if aclname not in self._acls_supported:
            raise exception.ConflictData('ACL name %s not supported on %s.' % (aclname, self))

        self.acls[aclname] = members
        self.enforce_right('owner') # integrity check using Python data...

        interp = self._interp_acl(aclname)
        keys = interp.keys()
        where = ' AND '.join([
            'new.%(col)s = old.%(col)s AND new.%(col)s = %(val)s' % dict(col=sql_identifier(k), val=interp[k])
            for k in keys
        ])
        cur.execute("""
SELECT _ermrest.model_change_event();
UPDATE _ermrest.model_%(restype)s_acl new
SET members = %(members)s::text[]
FROM _ermrest.model_%(restype)s_acl old
WHERE %(where)s
RETURNING old.members;
""" % dict(
    restype=self._model_restype,
    members=sql_literal(list(members)),
    where=where
)
        )
        for oldvalue in cur:
            return oldvalue

        cur.execute("""
INSERT INTO _ermrest.model_%(restype)s_acl (%(columns)s, members) VALUES (%(values)s, %(members)s::text[]);
""" % dict(
    restype=self._model_restype,
    columns=', '.join([sql_identifier(k) for k in keys]),
    values=', '.join([interp[k] for k in keys]),
    members=sql_literal(members)
)
        )
        return None

    def delete_acl(self, cur, aclname, purging=False):
        interp = self._interp_acl(aclname)

        self.enforce_right('owner') # pre-flight authz

        if aclname is not None and aclname not in self._acls_supported:
            raise exception.NotFound('ACL %s on %s' % (aclname, self))

        if aclname is None:
            del interp['acl']
            self.acls.clear()
        elif aclname in self.acls:
            del self.acls[aclname]

        if not purging:
            self.enforce_right('owner') # integrity check... can't disown except when purging

        keys = interp.keys()
        where = ' AND '.join([
            '%s = %s' % (sql_identifier(k), interp[k])
            for k in keys
        ])
        cur.execute("""
SELECT _ermrest.model_change_event();
DELETE FROM _ermrest.model_%(restype)s_acl WHERE %(where)s;
""" % dict(
    restype=self._model_restype,
    where=where
    )
        )

    def has_right(self, aclname, roles=None):
        """Return access decision True, False, None.

           aclname: the symbolic name for the access mode

           roles: the client roles for whom to make a decision

        """
        if roles is None:
            roles = set([
                r['id'] if type(r) is dict else r
                for r in web.ctx.webauthn2_context.attributes
            ])
            roles.add('*')

        if getparent is not None:
            parentres = getparent(self)
        else:
            parentres = None

        if aclname in self.acls:
            acl = self.acls[aclname]
        else:
            acl = None

        if parentres is not None:
            if parentres.has_right('owner', roles):
                # have right implicitly due to parent resource ownership rule
                return True
            elif acl is None and parentres.has_right(aclname, roles):
                # have right due to inherited parent ACL
                return True

        for aclname2 in sufficient_rights[aclname]:
            if self.has_right(aclname2, roles):
                # have right implicitly due to another sufficient right
                return True

        if acl is not None:
            if not set(acl).isdisjoint(roles):
                # have right explicitly due to ACL intersection
                return True

        if hasattr(self, 'dynacls'):
            for binding in self.dynacls.values():
                if not set(binding['types']).isdisjoint(sufficient_rights[aclname]):
                    # dynamic rights are possible on this resource...
                    return None

        if parentres is not None:
            if parentres.has_right(aclname, roles) is None:
                # dynamic rights are possible on parent resource...
                return None

        # finally, static deny decision
        return False

    def enforce_right(self, aclname):
        """Policy enforcement for named right."""
        decision = self.has_right(aclname)
        if decision is False:
            # we can't stop now if decision is True or None...
            raise exception.Forbidden('%s access on %s' % (aclname, web.ctx.env['REQUEST_URI']))

    def rights(self):
        return {
            aclname: self.has_right(aclname)
            for aclname in self._acls_rights
        }

    def helper(orig_class):
        setattr(orig_class, '_acl_getparent', lambda self: getparent(self))
        setattr(orig_class, '_acls_supported', set(acls_supported))
        setattr(orig_class, '_acls_rights', set(rights_supported))
        setattr(orig_class, '_interp_acl', _interp_acl)
        setattr(orig_class, 'rights', rights)
        if not hasattr(orig_class, 'has_right'):
            setattr(orig_class, 'has_right', has_right)
        else:
            setattr(orig_class, '_has_right', has_right)
        if not hasattr(orig_class, 'enforce_right'):
            setattr(orig_class, 'enforce_right', enforce_right)
        else:
            setattr(orig_class, '_enforce_right', enforce_right)
        setattr(orig_class, 'set_acl', set_acl)
        setattr(orig_class, 'delete_acl', delete_acl)
        if hasattr(orig_class, 'keyed_resource'):
            setattr(orig_class, 'introspect_acl_helper', introspect_acl_helper)
        setattr(orig_class, 'create_acl_storage_table', create_acl_storage_table)
        hasacls_classes.append(orig_class)
        return orig_class

    return helper

hasdynacls_classes = []

def hasdynacls(dynacl_types_supported):
    """Decorator to add dynamic ACL storage access to model classes.

       The keying() decorator MUST be applied first.
    """
    @classmethod
    def create_dynacl_storage_table(orig_class, cur):
        _create_storage_table(orig_class, cur, 'dynacl', {'binding_name': 'text'}, {'binding': 'jsonb'})

    @classmethod
    def introspect_dynacl_helper(orig_class, cur, model):
        def helper(resource=None, binding_name=None, binding=None):
            resource.dynacls[binding_name] = AclBinding(model, resource, binding_name, binding)
        _introspect_helper(orig_class, cur, model, 'dynacl', {'binding_name': 'text'}, {'binding': 'jsonb'}, helper)

    def _interp_dynacl(self, name):
        interp = {
            k: sql_literal(v[1](self))
            for k, v in self._model_keying.items()
        }
        interp['binding_name'] = sql_literal(name)
        return interp

    def set_dynacl(self, cur, name, binding):
        assert name is not None

        if binding is None:
            return self.delete_dynacl(cur, name)

        self.enforce_right('owner') # pre-flight authz
        self.dynacls[name] = AclBinding(web.ctx.ermrest_catalog_model, self, name, binding)

        interp = self._interp_dynacl(name)
        keys = interp.keys()
        where = ' AND '.join([
            'new.%(col)s = old.%(col)s AND new.%(col)s = %(val)s' % dict(col=sql_identifier(k), val=interp[k])
            for k in keys
        ])
        cur.execute("""
SELECT _ermrest.model_change_event();
UPDATE _ermrest.model_%(restype)s_dynacl new
SET binding = %(binding)s::jsonb
FROM _ermrest.model_%(restype)s_dynacl old
WHERE %(where)s
RETURNING old.binding;
""" % dict(
    restype=self._model_restype,
    binding=sql_literal(json.dumps(binding)),
    where=where
)
        )
        for oldvalue in cur:
            return oldvalue

        cur.execute("""
INSERT INTO _ermrest.model_%(restype)s_dynacl (%(columns)s, binding) VALUES (%(values)s, %(binding)s::jsonb);
""" % dict(
    restype=self._model_restype,
    columns=', '.join([sql_identifier(k) for k in keys]),
    values=', '.join([interp[k] for k in keys]),
    binding=sql_literal(json.dumps(binding))
)
        )
        return None

    def delete_dynacl(self, cur, name):
        interp = self._interp_dynacl(name)

        self.enforce_right('owner') # pre-flight authz

        if name is None:
            del interp['binding_name']
            self.dynacls.clear()
        elif name in self.dynacls:
            del self.dynacls[name]

        keys = interp.keys()
        where = ' AND '.join([
            '%s = %s' % (sql_identifier(k), interp[k])
            for k in keys
        ])
        cur.execute("""
SELECT _ermrest.model_change_event();
DELETE FROM _ermrest.model_%(restype)s_dynacl WHERE %(where)s;
""" % dict(
    restype=self._model_restype,
    where=where
    )
        )

    def helper(orig_class):
        setattr(orig_class, '_interp_dynacl', _interp_dynacl)
        setattr(orig_class, 'set_dynacl', set_dynacl)
        setattr(orig_class, 'delete_dynacl', delete_dynacl)
        setattr(orig_class, 'dynacl_types_supported', dynacl_types_supported)
        if hasattr(orig_class, 'keyed_resource'):
            setattr(orig_class, 'introspect_dynacl_helper', introspect_dynacl_helper)
        setattr(orig_class, 'create_dynacl_storage_table', create_dynacl_storage_table)
        hasdynacls_classes.append(orig_class)
        return orig_class

    return helper
