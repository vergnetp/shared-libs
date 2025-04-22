# This module is meant to offer a database api to the user


## Interface

The api is defined in interface.py

The database will offer:
* usual sql execution (one liner or list of sqls)
* ability to begin/commit/rollback a transaction
* the connection is done upon object creation, based on some config
* Connection and resources releases are done:
 - in an explicit call to the close function 
 - or at the end of the with statement (if relevant) 
 - or upon destruction of the object

## Factory

It is easier to create the databse using factory.py

It will generate the database based on an alias defined in config.json
Example: `get_database("mydatabase")`

## Config

It is hosted in [config.json]()

This is `{"databases": [...]}` where `...` is a list of config objects.

Those objects follow this structure: `{"alias":"mydatabase","type":"sqlite|mysql","config":{"prod": {...}}}`

Where `{...}` depends on the type:
* sqlite: `{"path":"foo|bar|mydatabase.db"}`
* mysql: `{"host":"localhost","user":"foo","password":"bar","database":"mydatabase"}`

config.py is an attempt at enforcing this but is work in progress

NB. For sqlite, if the configuration is absent or wrong, a file named `{alias}.db` will be created in `app|server|resources|files|databases|{env}`

## Example

```
with lib.database.factory.get_database('mydatabase') as db:
    try:
        db.begin_transaction()
        db.execute_sql('Create table Users2(name,email)')
        db.execute_sql("insert into Users2(name,email) values('Ken','na')")
        db.execute_sql("insert into table Users2(name,email) values('Phil','na')")
        res = db.execute_sql(sql)
        db.commit_transaction()
        return res
    except:
        db.rollback_transaction()
 ```
