import json
import sys
import types
import unittest

upstash_redis_module = types.ModuleType("upstash_redis")
upstash_redis_module.Redis = object
sys.modules.setdefault("upstash_redis", upstash_redis_module)

upstash_vector_module = types.ModuleType("upstash_vector")
upstash_vector_module.Index = object
sys.modules.setdefault("upstash_vector", upstash_vector_module)

upstash_vector_errors_module = types.ModuleType("upstash_vector.errors")
upstash_vector_errors_module.UpstashError = Exception
sys.modules.setdefault("upstash_vector.errors", upstash_vector_errors_module)

from backend.services.database import DatabaseService


class FakePipeline:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.operations = []

    def delete(self, key):
        self.operations.append(("delete", key))
        return self

    def rpush(self, key, *values):
        self.operations.append(("rpush", key, values))
        return self

    def expire(self, key, ttl):
        self.operations.append(("expire", key, ttl))
        return self

    def exec(self):
        for operation in self.operations:
            command = operation[0]
            if command == "delete":
                _, key = operation
                self.redis.storage.pop(key, None)
            elif command == "rpush":
                _, key, values = operation
                self.redis.storage.setdefault(key, []).extend(values)
            elif command == "expire":
                _, key, ttl = operation
                self.redis.expiry[key] = ttl

        self.redis.executed_pipelines.append(list(self.operations))
        return True


class FakeRedis:
    def __init__(self):
        self.storage = {}
        self.expiry = {}
        self.executed_pipelines = []

    def pipeline(self):
        return FakePipeline(self)

    def lrange(self, key, start, end):
        values = list(self.storage.get(key, []))
        if end == -1:
            end = len(values) - 1
        return values[start : end + 1]

    def set(self, key, value):
        self.storage[key] = value

    def get(self, key):
        return self.storage.get(key)


class FakeVectorIndex:
    def query(self, **kwargs):
        return []


class FakeEmbeddingProvider:
    def embed(self, text):
        return [0.0]


class DatabaseServiceHistoryTests(unittest.TestCase):
    def create_service(self):
        return DatabaseService(
            redis_client=FakeRedis(),
            vector_index=FakeVectorIndex(),
            embedding_provider=FakeEmbeddingProvider(),
        )

    def test_store_chat_message_appends_without_rewriting_history(self):
        service = self.create_service()
        first_message = {"turn_number": 1, "message": "first"}
        second_message = {"turn_number": 2, "message": "second"}

        service.store_chat_message("session-1", first_message)
        service.store_chat_message("session-1", second_message)

        pipeline_operations = service.redis.executed_pipelines
        self.assertEqual(len(pipeline_operations), 2)
        self.assertEqual([operation[0] for operation in pipeline_operations[0]], ["rpush", "expire"])
        self.assertEqual([operation[0] for operation in pipeline_operations[1]], ["rpush", "expire"])
        self.assertEqual(service.get_chat_history("session-1"), [first_message, second_message])

    def test_append_chat_message_preserves_existing_return_shape(self):
        service = self.create_service()
        message = {"turn_number": 1, "message": "only"}

        history = service.append_chat_message("session-2", message)

        self.assertEqual(history, [message])
        stored_payload = service.redis.storage[service._history_key("session-2")]
        self.assertEqual(json.loads(stored_payload[0]), message)

    def test_get_recent_chat_history_reads_only_requested_window(self):
        service = self.create_service()
        messages = [
            {"turn_number": 3, "message": "third"},
            {"turn_number": 1, "message": "first"},
            {"turn_number": 2, "message": "second"},
        ]

        for message in messages:
            service.store_chat_message("session-3", message)

        recent_history = service.get_recent_chat_history("session-3", 2)

        self.assertEqual(recent_history, [
            {"turn_number": 1, "message": "first"},
            {"turn_number": 2, "message": "second"},
        ])

    def test_get_recent_chat_history_returns_empty_for_non_positive_limit(self):
        service = self.create_service()

        self.assertEqual(service.get_recent_chat_history("session-4", 0), [])

    def test_get_recent_chat_history_for_topic_filters_cross_topic_entries(self):
        service = self.create_service()
        messages = [
            {"turn_number": 1, "topic": "Democracy", "message": "first democracy"},
            {"turn_number": 2, "topic": "Tyrany", "message": "first tyranny"},
            {"turn_number": 3, "topic": "Democracy", "message": "second democracy"},
            {"turn_number": 4, "topic": "Tyrany", "message": "second tyranny"},
            {"turn_number": 5, "topic": "Democracy", "message": "third democracy"},
        ]

        for message in messages:
            service.store_chat_message("session-5", message)

        recent_history = service.get_recent_chat_history_for_topic("session-5", "Tyrany", 2)

        self.assertEqual(
            recent_history,
            [
                {"turn_number": 2, "topic": "Tyrany", "message": "first tyranny"},
                {"turn_number": 4, "topic": "Tyrany", "message": "second tyranny"},
            ],
        )


if __name__ == "__main__":
    unittest.main()