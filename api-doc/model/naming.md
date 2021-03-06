# ERMrest Model Resource Naming

Unlike general web architecture, [ERMrest](http://github.com/informatics-isi-edu/ermrest) expects clients to understand the URL internal structure and permits (or even encourages) reflection on URL content to understand how one resource name relates to another. To support introspection and management, the data model of a catalog is exposed as a set of model-level resources. These model elements also influence the [naming of data resources](../data/naming.md).

## Catalog Names

The ERMrest model resources belong to a catalog resource:

- _service_ `/catalog/` _cid_

where the components of this root path are:

- _service_: the ERMrest service endpoint such as `https://www.example.com/ermrest`.
- _cid_: the catalog identifier for one dataset such as `42`.

The catalog resource has a representation which provides basic information about it including access control lists.

### Catalog Annotations

Each catalog annotation is reified as a model-level resource:

- _service_ `/catalog/` _cid_ `/annotation/` _annotation key_

This keyed annotation has a simple representation which is a machine-readable document in `application/json` format. The expected content and interpretation of the JSON document is externally defined and associated with the _annotation key_ which SHOULD be a URL (escaped with standard URL-encoding before embedding in this annotation name URL). The purpose of the _annotation key_ is to allow different user communities to organize their own annotation standards without ambiguity.

Additionally, a composite resource summarizes all existing annotations on one catalog for convenient discovery and bulk retrieval:

- _service_ `/catalog/` _cid_ `/annotation`
- _service_ `/catalog/` _cid_ `/annotation/`

## Schemata Names

The ERMrest model resources are named under a root collection of schemata for a particular catalog:

- _service_ `/catalog/` _cid_ `/schema/`

where the components of this root path are:

- _service_: the ERMrest service endpoint such as `https://www.example.com/ermrest`.
- _cid_: the catalog identifier for one dataset such as `42`.

This root schemata resource has a representation which summarizes the entire data model of the catalog as a single document.

## Schema Names

Each schema or namespace of tables in a particular catalog is reified as a model-level resource:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_

This named schema resource has a representation which summarizes the data model of all tables qualified by the _schema name_ namespace.

### Schema Comments

Each schema comment is reified as a model-level resource:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/comment`

This named resource has a simple representation which is just human readable text in `text/plain` format.

### Schema Annotations

Each schema annotation is reified as a model-level resource:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/annotation/` _annotation key_

This keyed annotation has a simple representation which is a machine-readable document in `application/json` format. The expected content and interpretation of the JSON document is externally defined and associated with the _annotation key_ which SHOULD be a URL (escaped with standard URL-encoding before embedding in this annotation name URL). The purpose of the _annotation key_ is to allow different user communities to organize their own annotation standards without ambiguity.

Additionally, a composite resource summarizes all existing annotations on one schema for convenient discovery and bulk retrieval:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/annotation`
- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/annotation/`

## Table Names

Each table is reified as a model-level resource:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_

This named table resource has a representation which summarizes its data model including columns, keys, and foreign keys. Within data resource names, a table may be referenced by _table name_ only if that name is unique within the catalog or by a fully qualified _schema name_ `:` _table name_. Concrete examples of such names might be `table1` or `schema1:table1`.

### Table Comments

Each table comment is reified as a model-level resource:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/comment`

This named resource has a simple representation which is just human readable text in `text/plain` format.

### Table Annotations

Each table annotation is reified as a model-level resource:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/annotation/` _annotation key_

This keyed annotation has a simple representation which is a machine-readable document in `application/json` format. The expected content and interpretation of the JSON document is externally defined and associated with the _annotation key_ which SHOULD be a URL (escaped with standard URL-encoding before embedding in this annotation name URL). The purpose of the _annotation key_ is to allow different user communities to organize their own annotation standards without ambiguity.

Additionally, a composite resource summarizes all existing annotations on one table for convenient discovery and bulk retrieval:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/annotation`
- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/annotation/`

### Column Names

Each column is reified as a model-level resource:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/column/` _column name_

This named column resource has a representation which summarizes its data model including name and type. Within data resource names, a column may be referenced by:

- _column name_ when resolving within an implicit table context;
- _table alias_ : _column name_ when resolving against a context where _table alias_ has been bound as an alias to a specific table instance;
- _table name_ : _column name_ when resolving against the model and _table name_ is unique within the catalog;
- _schema name_ : _table name_ : _column name_ when resolving against the model and _table name_ might otherwise be ambiguous.

##### Column Comments

Each column comment is reified as a model-level resource:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/column/` _column name_ `/comment`

This named resource has a simple representation which is just human readable text in `text/plain` format.

##### Column Annotations

Each column annotation is reified as a model-level resource:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/column/` _column name_ `/annotation/` _annotation key_

This keyed annotation has a simple representation which is a machine-readable document in `application/json` format. The expected content and interpretation of the JSON document is externally defined and associated with the _annotation key_ which SHOULD be a URL (escaped with standard URL-encoding before embedding in this annotation name URL). The purpose of the _annotation key_ is to allow different user communities to organize their own annotation standards without ambiguity.

Additionally, a composite resource summarizes all existing annotations on one column for convenient discovery and bulk retrieval:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/column/` _column name_ `/annotation`
- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/column/` _column name_ `/annotation/`

### Key Names

Each (composite) key constraint is reified as a model-level resource:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/key/` _column name_ `,` ...

This named constraint has a representation which summarizes its set of constituent key columns. The meaning of a key constraint is that the combination of listed columns must be a unique identifier for rows in the table, i.e. no two rows can share the same combination of values for those columns.

ERMrest also supports pseudo-keys on views, which allow the uniqueness properties of views to be asserted both for clients introspecting the catalog model and for ERMrest itself to reason about queries on the view. Psuedo-keys are chosen automatically when an authorized client creates a key constraint on a view, while real database constraints are used when the client creates a key constraint on a table.

  - *NOTE* pseudo-keys are advisory, *not enforced* in the database, and *not validated* by ERMrest. A client SHOULD NOT assert inaccurate psuedo-key constraints as it could mislead other clients who introspect the schema or lead to unexpected query results as ERMrest formulates relational queries assuming the constraints are true.
  - Future ERMrest releases MAY enforce validation on psuedo-keys so clients SHOULD NOT depend on the ability to create inaccurate psuedo-constraints.

Additionally, a composite resource summarizes all existing key constraints on one table for convenient discovery and bulk retrieval:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/key`
- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/key/`

##### Key Comments

Each key comment is reified as a model-level resource:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/key/` _column name_ `,` ... `/comment`

This named resource has a simple representation which is just human readable text in `text/plain` format.

##### Key Annotations

Each key annotation is reified as a model-level resource:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/key/` _column name_ `,` ... `/annotation/` _annotation key_

This keyed annotation has a simple representation which is a machine-readable document in `application/json` format. The expected content and interpretation of the JSON document is externally defined and associated with the _annotation key_ which SHOULD be a URL (escaped with standard URL-encoding before embedding in this annotation name URL). The purpose of the _annotation key_ is to allow different user communities to organize their own annotation standards without ambiguity.

Additionally, a composite resource summarizes all existing annotations on one key for convenient discovery and bulk retrieval:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/key/` _column name_ `,` ... `/annotation`
- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/key/` _column name_ `,` ... `/annotation/`

### Foreign Key Names

Each (composite) foreign key constraint is reified as a model-level resource:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/foreignkey/` _column name_ `,` ... `/reference/` _table reference_ `/` _key column_ `,` ...

This named constraint has a representation which summarizes its set of constituent foreign key columns, another referenced table, and the set of key columns that form the composite key being referenced in that other table, including the mapping of each foreign key _column name_ to each composite key _key column_. The _table reference_ can be a qualified table name, e.g. `schema1:table1` or an unqualified table name, e.g. `table1`.  The meaning of this constraint is that each combination of non-NULL values in _schema name_:_table name_ MUST reference an existing combination of values forming a composite key for a row in _table reference_.

ERMrest also supports pseudo-foreign keys on views, which allow the reference links of views to be asserted both for clients introspecting the catalog model and for ERMrest itself to reason about queries on the view. Psuedo-foreign keys are chosen automatically when an authorized client creates a foreign key constraint on a view or referencing a view, while real database constraints are used when the client creates a foreign key constraint on a table referencing another table.

  - *NOTE* pseudo-foreign keys are advisory, *not enforced* in the database, and *not validated* by ERMrest. A client SHOULD NOT assert inaccurate psuedo-foreign key constraints as it could mislead other clients who introspect the schema or lead to unexpected query results as ERMrest formulates relational queries assuming the constraints are true.
  - Future ERMrest releases MAY enforce validation on psuedo-foreign keys so clients SHOULD NOT depend on the ability to create inaccurate psuedo-constraints.

Additionally, a composite resource summarizes all foreign key constraints on one table for discovery and bulk retrieval purposes:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/foreignkey`
- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/foreignkey/`

Additionally, a composite resource summarizes all foreign key constraints involving one composite foreign key _column name_ list:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/foreignkey/` _column name_ `,` ...
- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/foreignkey/` _column name_ `,` ... `/reference`
- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/foreignkey/` _column name_ `,` ... `/reference/`

Finally, a composite resource summarizes all foreign key constraints involving one composite foreign key _column name_ list and one _table reference_:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/foreignkey/` _column name_ `,` ... `/reference/` _table reference_

(While highly unusual, it is possible to express more than one foreign key constraint from the same composite foreign key _column name_ list to different composite key _key column_ lists in the same or different _table reference_ tables.)

##### Foreign Key Comments

Each foreign-key comment is reified as a model-level resource:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/foreignkey/` _column name_ `,` ... `/reference/` _table reference_ `/` _key column_ `,` ... `/comment`

This named resource has a simple representation which is just human readable text in `text/plain` format.

#### Foreign Key Annotations

Each foreign-key annotation is reified as a model-level resource:

-  _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/foreignkey/` _column name_ `,` ... `/reference/` _table reference_ `/` _key column_ `,` ... `/annotation/` _annotation key_

This keyed annotation has a simple representation which is a machine-readable document in `application/json` format. The expected content and interpretation of the JSON document is externally defined and associated with the _annotation key_ which SHOULD be a URL (escaped with standard URL-encoding before embedding in this annotation name URL). The purpose of the _annotation key_ is to allow different user communities to organize their own annotation standards without ambiguity.

Additionally, a composite resource summarizes all existing annotations on one foreign-key for convenient discovery and bulk retrieval:

- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/foreignkey/` _column name_ `,` ... `/reference/` _table reference_ `/` _key column_ `,` ... `/annotation`
- _service_ `/catalog/` _cid_ `/schema/` _schema name_ `/table/` _table name_ `/foreignkey/` _column name_ `,` ... `/reference/` _table reference_ `/` _key column_ `,` ... `/annotation/`
