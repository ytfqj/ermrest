
import unittest
import common

_Sd = "AclDefault"
_Se = "AclExplicit"

def setUpModule():
    r = common.primary_session.get('schema/%s' % _Sd)
    if r.status_code == 404:
        # idempotent because unittest can re-enter module several times...
        common.primary_session.post('schema', json=_defs).raise_for_status()

catalog_acls = dict(common.catalog_acls)
catalog_acls['owner'] = [common.primary_client_id]

def add_acl_tests(klass):
    for acl in klass.expected_acls:
        def pickle(method, acl):
            return lambda self: method(self, acl)

        for name, method in [
                ('1_check', klass._check),
                ('3_override', klass._override),
                ('5_remove', klass._remove),
                ('7_restore', klass._restore)
        ]:
            setattr(
                klass,
                'test_%s_%s' % (name, acl),
                pickle(method, acl)
            )

    if not hasattr(klass, 'test_disown') and 'owner' in klass.expected_acls:
        # an empty owner is allowed because primary_client_id inherits ownership from catalog...
        setattr(
            klass,
            'test_disown',
            lambda self: self.assertHttp(self.session.put(self._url('owner'), json=[]), 200)
        )

    if 'owner' not in klass.expected_acls:
        # owner ACL is not supported on parts of tables
        setattr(
            klass,
            'test_owner_noset',
            lambda self: self._unsupported('owner')
        )

    setattr(
        klass,
        'test_invalid_acl',
        lambda self: self._unsupported('INVALID')
    )

    if common.secondary_session:
        setattr(
            klass,
            'test_nonowner_forbidden',
            lambda self: self._nonowner(common.secondary_session)
        )

    return klass

class Acls (common.ErmrestTest):
    expected_acls = {}
    override_value = ['foo', 'bar', common.primary_client_id]

    def _base(self):
        return '%s/acl' % self.resource
    
    def _url(self, aclname=None):
        base = self._base()
        if aclname is not None:
            return '%s/%s' % (base, aclname)
        else:
            return base
    
    def _check(self, acl):
        if acl in self.expected_acls:
            self._checkval(acl, self.expected_acls[acl])

    def test_2_check_all(self):
        if self.expected_acls:
            self._checkvals(lambda acl: self.expected_acls[acl])

    def _override(self, acl):
        if acl in self.expected_acls:
            self._setval(acl, self.override_value)

    def test_4_check_all(self):
        if self.expected_acls:
            self._checkvals(lambda acl: self.override_value)

    def _remove(self, acl):
        if acl in self.expected_acls and acl != 'owner':
            self._delete(acl)
            self._setval(acl, None)

    def test_6_check_all(self):
        if self.expected_acls:
            self._checkvals(lambda acl: self.override_value if acl == 'owner' else None)

    def _restore(self, acl):
        if acl in self.expected_acls:
            self._setval(acl, self.expected_acls[acl])

    def test_8_check_all(self):
        if self.expected_acls:
            self._checkvals(lambda acl: self.expected_acls[acl])

    def _checkvals(self, lookup):
        r = self.session.get(self._url())
        self.assertHttp(r, 200, 'application/json')
        for acl in self.expected_acls.keys():
            expected = lookup(acl)
            self.assertEqual(r.json().get(acl), expected, 'Expected %s for %s in %s' % (expected, acl, r.json()))
            
    def _checkval(self, acl, value):
        r = self.session.get(self._url(acl))
        self.assertHttp(r, 200, 'application/json')
        self.assertEqual(r.json(), value, "ACL %s got %s when expecting %s" % (acl, r.json(), value))

    def _setval(self, acl, value):
        self.assertHttp(self.session.put(self._url(acl), json=value), 200)
        self._checkval(acl, value)

    def _delete(self, acl):
        self.assertHttp(self.session.delete(self._url(acl)), 200)
        self._checkval(acl, None)

    def _unsupported(self, acl):
        self.assertHttp(self.session.get(self._url(acl)), 404)
        self.assertHttp(self.session.put(self._url(acl), json=['foobar']), 409)
        self.assertHttp(self.session.delete(self._url(acl)), 404)

    def _nonowner(self, session):
        for acl in set([None, 'owner', 'INVALID'] + list(self.expected_acls)):
            self.assertHttp(session.get(self._url(acl)), 403)
            self.assertHttp(session.put(self._url(acl), json=[common.primary_client_id, common.secondary_client_id]), 403)
            self.assertHttp(session.delete(self._url(acl)), 403)

@add_acl_tests
class AclsCatalog (Acls):
    expected_acls = catalog_acls

    def _base(self):
        return 'acl'

    def test_disown(self):
        # primary_client_id cannot disown the whole catalog
        self.assertHttp(self.session.put(self._url('owner'), json=[]), 403)

@add_acl_tests
class AclsDefaultSchema (Acls):
    resource = 'schema/%s' % _Sd
    expected_acls = {
        "owner": None,
        "write": None,
        "create": None,
        "insert": None,
        "update": None,
        "delete": None,
        "select": None,
        "enumerate": None
    }

@add_acl_tests
class AclsT1 (Acls):
    resource = 'schema/%s/table/T1' % _Sd
    expected_acls = {
        "owner": None,
        "write": None,
        "insert": None,
        "update": None,
        "delete": None,
        "select": None,
        "enumerate": None
    }
 
@add_acl_tests
class AclsT1Col (Acls):
    resource = 'schema/%s/table/T1/column/id' % _Sd
    expected_acls = {
        "write": None,
        "insert": None,
        "update": None,
        "delete": None,
        "select": None,
        "enumerate": None
    }

@add_acl_tests
class AclsOverrideSchema (Acls):
    resource = 'schema/%s' % _Se
    expected_acls = {
        "owner": [common.primary_client_id, " NOT-A-MATCH ", "*"],
        "write": [],
        "create": None,
        "insert": None,
        "update": None,
        "delete": None,
        "select": ["foo", "*"],
        "enumerate": ["bar", "*"]
    }
    
@add_acl_tests
class AclsT3 (Acls):
    resource = 'schema/%s/table/T3' % _Se
    expected_acls = {
        "owner": [common.primary_client_id, " NOT-A-MATCH ", "*"],
        "write": [],
        "insert": None,
        "update": None,
        "delete": None,
        "select": ["foo", "*"],
        "enumerate": ["bar", "*"]
    }

@add_acl_tests
class AclsT3Col (Acls):
    resource = 'schema/%s/table/T3/column/id' % _Se
    expected_acls = {
        "write": [],
        "insert": None,
        "update": None,
        "select": ["foo", "*"],
        "enumerate": ["bar", "*"]
    }
    
_defs = {
    "schemas": {
        _Sd: {
            "tables": {
                "T1": {
                    "column_definitions": [
                        {
                            "name": "id", 
                            "type": {"typename": "int8"},
                            "nullok": False
                        },
                        {
                            "name": "name",
                            "type": {"typename": "text"},
                            "nullok": False
                        },
                        {
                            "name": "value",
                            "type": {"typename": "text"}
                        }
                    ],
                    "keys": [
                        {"unique_columns": ["id"]},
                        {"unique_columns": ["name"]}
                    ]
                },
                "T2": {
                    "column_definitions": [
                        {
                            "name": "id", 
                            "type": {"typename": "int8"},
                            "nullok": False
                        },
                        {
                            "name": "name",
                            "type": {"typename": "text"},
                            "nullok": False
                        },
                        {
                            "name": "value",
                            "type": {"typename": "text"}
                        },
                        {
                            "name": "t1id",
                            "type": {"typename": "int8"}
                        }
                    ],
                    "keys": [
                        {"unique_columns": ["id"]},
                        {"unique_columns": ["name"]}
                    ],
                    "foreign_keys": [
                        {
                            "foreign_key_columns": [{"schema_name": _Sd, "table_name": "T2", "column_name": "t1id"}],
                            "referenced_columns": [{"schema_name": _Sd, "table_name": "T1", "column_name": "id"}]
                        }
                    ]
                }
            }
        },
        _Se: {
            "acls": AclsOverrideSchema.expected_acls,
            "tables": {
                "T3": {
                    "acls": AclsT3.expected_acls,
                    "column_definitions": [
                        {
                            "acls": AclsT3Col.expected_acls,
                            "name": "id", 
                            "type": {"typename": "int8"},
                            "nullok": False
                        },
                        {
                            "name": "name",
                            "type": {"typename": "text"},
                            "nullok": False
                        },
                        {
                            "name": "value",
                            "type": {"typename": "text"}
                        },
                        {
                            "name": "t1id",
                            "type": {"typename": "int8"}
                        }
                    ],
                    "keys": [
                        {"unique_columns": ["id"]},
                        {"unique_columns": ["name"]}
                    ],
                    "foreign_keys": [
                        {
                            "foreign_key_columns": [{"schema_name": _Se, "table_name": "T3", "column_name": "t1id"}],
                            "referenced_columns": [{"schema_name": _Sd, "table_name": "T1", "column_name": "id"}]
                        }
                    ]
                }
            }
        }
    }
}


if __name__ == '__main__':
    unittest.main(verbosity=2)
