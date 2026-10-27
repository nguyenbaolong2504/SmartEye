"""Small PyMongo repository; each write is an atomic MongoDB operation.

Records track changed fields so a video progress update cannot overwrite a
concurrent cancellation. No SQL engine, embedded SQLite or mock in production.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pymongo import MongoClient, ReturnDocument, ASCENDING, DESCENDING
from pymongo.errors import CollectionInvalid
from .config import MONGODB_URI, MONGODB_DB

_client = None


def now():
    return datetime.now(timezone.utc)


def stamp():
    return now().isoformat()


def get_client():
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000,
                             connectTimeoutMS=5000, socketTimeoutMS=20000,
                             appname='SmartEye', tz_aware=True)
    return _client


def get_database():
    return get_client()[MONGODB_DB]


def _query(model, value):
    if isinstance(value, list):
        return [_query(model,item) for item in value]
    if not isinstance(value,dict):
        return value
    return {('_id' if key == model.primary else key):_query(model,item)
            for key,item in value.items()}


def initialize_database():
    from .models import ALL_MODELS, LoginSession, ResetToken
    from .mongo_schema import SCHEMAS
    database = get_database()
    database.command('ping')
    existing = set(database.list_collection_names())
    for name in [m.collection for m in ALL_MODELS] + ['counters']:
        if name not in existing:
            try: database.create_collection(name,**({'validator':SCHEMAS[name]} if name in SCHEMAS else {}))
            except CollectionInvalid: pass
    database.users.create_index('email', unique=True, name='unique_email')
    database.observations.create_index('job_id', unique=True,
        partialFilterExpression={'job_id':{'$type':'string'}}, name='one_publication_per_video')
    database.observations.create_index([('segment_id',ASCENDING),('observed_at',DESCENDING)], name='latest_segment_observation')
    database.observations.create_index('observed_at')
    database.observations.create_index([('camera_id',1),('observed_at',-1)])
    database.alert_rules.create_index([('user_id',1),('segment_id',1),('density',1)], unique=True, name='unique_user_alert')
    database.video_jobs.create_index([('user_id',1),('created_at',-1)])
    database.video_jobs.create_index('status')
    database.favorites.create_index('user_id')
    database.notifications.create_index([('user_id',1),('created_at',-1)])
    database.traffic_samples.create_index('sample_key', unique=True, name='unique_traffic_sample')
    database.traffic_samples.create_index([('segment_id',1),('observed_at',1)])
    database.traffic_samples.create_index([('camera_id',1),('observed_at',-1)])
    database.traffic_samples.create_index('observation_id')
    database.traffic_samples.create_index([('observed_at',-1),('_id',-1)])
    for model in (LoginSession,ResetToken):
        database[model.collection].create_index('expires_on',expireAfterSeconds=0,name='expire_tokens')
    # Synchronize counters after a Compass JSON import. Never move a counter back.
    for model in ALL_MODELS:
        if model.primary != 'id' or model.collection == 'video_jobs': continue
        largest = database[model.collection].find_one({'_id':{'$type':'number'}},sort=[('_id',-1)])
        database.counters.update_one({'_id':model.collection},{'$max':{'seq':largest['_id'] if largest else 0}},upsert=True)


class MongoSession:
    def __init__(self,database=None):
        self.database = database if database is not None else get_database()
        self._tracked = {}
        self._new = []

    def __enter__(self): return self

    def __exit__(self,*_):
        self._tracked.clear()
        self._new.clear()

    def _attach(self,model,document):
        if document is None: return None
        row = model.from_mongo(document)
        self._tracked[(model,document['_id'])] = (row,row.values())
        return row

    def get(self,model,ident):
        return self._attach(model,self.database[model.collection].find_one({'_id':ident}))

    def find(self,model,filters=None,*,sort=None,limit=0,exclude=None):
        projection = {name:0 for name in exclude} if exclude else None
        cursor = self.database[model.collection].find(_query(model,filters or {}),projection)
        if sort: cursor = cursor.sort([('_id' if key == model.primary else key,direction) for key,direction in sort])
        if limit: cursor = cursor.limit(limit)
        return [self._attach(model,document) for document in cursor]

    def find_one(self,model,filters=None):
        return self._attach(model,self.database[model.collection].find_one(_query(model,filters or {})))

    def count(self,model,filters=None):
        return self.database[model.collection].count_documents(_query(model,filters or {}))

    def add(self,row):
        model = type(row)
        if getattr(row,model.primary) is None:
            counter = self.database.counters.find_one_and_update({'_id':model.collection},
                {'$inc':{'seq':1}},upsert=True,return_document=ReturnDocument.AFTER)
            setattr(row,model.primary,counter['seq'])
        self._new.append(row)

    def _stored(self,row):
        document = row.values()
        document['_id'] = document.pop(row.primary)
        if 'expires_at' in document:
            document['expires_on'] = datetime.fromisoformat(document['expires_at'])
        return document

    def commit(self):
        while self._new:
            row = self._new[0]
            self.database[row.collection].insert_one(self._stored(row))
            self._new.pop(0)
            self._tracked[(type(row),getattr(row,row.primary))] = (row,row.values())
        for (model,ident),(row,original) in list(self._tracked.items()):
            values = row.values()
            changed = {key:value for key,value in values.items()
                       if key != model.primary and value != original.get(key)}
            if changed:
                if 'expires_at' in changed:
                    changed['expires_on'] = datetime.fromisoformat(changed['expires_at'])
                self.database[model.collection].update_one({'_id':ident},{'$set':changed})
                self._tracked[(model,ident)] = (row,deepcopy(values))

    def flush(self): self.commit()

    def rollback(self):
        self._new.clear()
        self._tracked.clear()

    def delete(self,row):
        self.database[row.collection].delete_one({'_id':getattr(row,row.primary)})
        self._tracked.pop((type(row),getattr(row,row.primary)),None)

    def delete_many(self,model,filters):
        result = self.database[model.collection].delete_many(_query(model,filters))
        # Pending unchanged copies must not be saved again after revocation.
        self._tracked = {key:value for key,value in self._tracked.items() if key[0] is not model}
        return result.deleted_count

    def update(self,model,ident,values,*,condition=None,increment=None):
        query = {'_id':ident,**_query(model,condition or {})}
        operation = {'$set':values} if values else {}
        if increment: operation['$inc'] = increment
        document = self.database[model.collection].find_one_and_update(query,operation,return_document=ReturnDocument.AFTER)
        return self._attach(model,document)

    def pop(self,model,filters):
        return self._attach(model,self.database[model.collection].find_one_and_delete(_query(model,filters)))


SessionLocal = MongoSession


def get_db():
    with MongoSession() as db:
        yield db
