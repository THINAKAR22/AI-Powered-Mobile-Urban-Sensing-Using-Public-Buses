"""MongoDB persistence helpers used by the FastAPI routes."""

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import DESCENDING, MongoClient, ReturnDocument

load_dotenv(Path(__file__).parent / "backend" / ".env")


class Predicate:
    def __init__(self, check): self.check = check
    def __call__(self, document): return self.check(document)


class Field:
    def __init__(self, name, default=None): self.name, self.default = name, default
    def __get__(self, instance, owner): return self if instance is None else instance.__dict__.get(self.name, self.default_value())
    def __set__(self, instance, value): instance.__dict__[self.name] = value
    def default_value(self): return self.default() if callable(self.default) else self.default
    def __eq__(self, value): return Predicate(lambda document: document.get(self.name) == value)
    def desc(self): return (self.name, DESCENDING)


class LowerValue:
    def __init__(self, value): self.value = value
    def resolve(self, document):
        value = document.get(self.value.name) if isinstance(self.value, Field) else self.value
        return value.lower() if isinstance(value, str) else value
    def __eq__(self, other): return Predicate(lambda document: self.resolve(document) == (other.resolve(document) if isinstance(other, LowerValue) else other))


class Functions:
    @staticmethod
    def lower(value): return LowerValue(value)


func = Functions()


def _database():
    uri = os.getenv("MONGODB_URI")
    if not uri: raise RuntimeError("MONGODB_URI is not configured")
    return MongoClient(uri, serverSelectionTimeoutMS=10_000)[os.getenv("MONGODB_DB_NAME", "urban_sensing")]


def init_db():
    """Verify MongoDB connectivity and create indexes used by the API."""
    database = _database()
    database.command("ping")
    database.buses.create_index("id", unique=True)
    database.buses.create_index("bus_number", unique=True)
    database.incidents.create_index("id", unique=True)
    database.detections.create_index("id", unique=True)


class Query:
    def __init__(self, database, model): self.database, self.model, self.predicates, self.sort = database, model, [], None
    def filter(self, predicate): self.predicates.append(predicate); return self
    def order_by(self, sort): self.sort = sort; return self
    def _documents(self):
        cursor = self.database[self.model.collection].find({})
        if self.sort: cursor = cursor.sort(*self.sort)
        return [item for item in cursor if all(predicate(item) for predicate in self.predicates)]
    def all(self): return [self.model.from_document(item) for item in self._documents()]
    def first(self):
        documents = self._documents()
        return self.model.from_document(documents[0]) if documents else None
    def count(self): return len(self._documents())


class MongoSession:
    def __init__(self): self.database, self.pending, self.deleted = _database(), [], []
    def add(self, instance):
        if instance not in self.pending: self.pending.append(instance)
    def delete(self, instance): self.deleted.append(instance)
    def query(self, model): return Query(self.database, model)
    def commit(self):
        for instance in self.pending:
            collection = self.database[instance.collection]
            if instance.id is None:
                counter = self.database.counters.find_one_and_update({"_id": instance.collection}, {"$inc": {"value": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
                instance.id = counter["value"]
                collection.insert_one(instance.to_document())
            else: collection.replace_one({"id": instance.id}, instance.to_document(), upsert=True)
        for instance in self.deleted: self.database[instance.collection].delete_one({"id": instance.id})
        self.pending.clear(); self.deleted.clear()
    def refresh(self, instance):
        document = self.database[instance.collection].find_one({"id": instance.id})
        if document: instance.load_document(document)
    def rollback(self): self.pending.clear(); self.deleted.clear()
    def close(self): pass


def get_db():
    database = MongoSession()
    try: yield database
    finally: database.close()


def utc_now(): return datetime.now(timezone.utc)
