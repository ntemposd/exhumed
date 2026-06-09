import json
import sys
import types
import unittest
from types import SimpleNamespace

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

    def ltrim(self, key, start, end):
        self.operations.append(("ltrim", key, start, end))
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
            elif command == "ltrim":
                _, key, start, end = operation
                values = list(self.redis.storage.get(key, []))
                length = len(values)
                if length > 0:
                    norm_start = max(length + start, 0) if start < 0 else start
                    norm_end = (length + end) if end < 0 else min(end, length - 1)
                    self.redis.storage[key] = values[norm_start:norm_end + 1] if norm_start <= norm_end else []

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
    def __init__(self):
        self.fetch_payloads = {}

    def query(self, **kwargs):
        return []

    def fetch(self, ids):
        return [self.fetch_payloads[vector_id] for vector_id in ids if vector_id in self.fetch_payloads]


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
        self.assertEqual([operation[0] for operation in pipeline_operations[0]], ["rpush", "ltrim", "expire"])
        self.assertEqual([operation[0] for operation in pipeline_operations[1]], ["rpush", "ltrim", "expire"])
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

    def test_get_agent_context_enriches_matches_with_neighbor_chunks(self):
        vector_index = FakeVectorIndex()
        vector_index.query = lambda **kwargs: [
            SimpleNamespace(
                id="agt_003:art_of_war:0002",
                score=0.91,
                metadata={
                    "agent_id": "agt_003",
                    "source_slug": "art_of_war",
                    "chunk_index": 2,
                    "source_title": "The Art of War",
                },
                data="Current strategic passage.",
            )
        ]
        vector_index.fetch_payloads = {
            "agt_003:art_of_war:0001": {
                "id": "agt_003:art_of_war:0001",
                "metadata": {"agent_id": "agt_003", "source_slug": "art_of_war", "chunk_index": 1},
                "data": "Previous context.",
            },
            "agt_003:art_of_war:0002": {
                "id": "agt_003:art_of_war:0002",
                "metadata": {"agent_id": "agt_003", "source_slug": "art_of_war", "chunk_index": 2},
                "data": "Current strategic passage.",
            },
            "agt_003:art_of_war:0003": {
                "id": "agt_003:art_of_war:0003",
                "metadata": {"agent_id": "agt_003", "source_slug": "art_of_war", "chunk_index": 3},
                "data": "Following context.",
            },
        }

        service = DatabaseService(
            redis_client=FakeRedis(),
            vector_index=vector_index,
            embedding_provider=FakeEmbeddingProvider(),
        )

        matches = service.get_agent_context("strategy", "agt_003", top_k=1, neighbor_window=1)

        self.assertEqual(len(matches), 1)
        self.assertEqual(
            matches[0]["data"],
            "Previous context.\n\nCurrent strategic passage.\n\nFollowing context.",
        )
        self.assertEqual(
            matches[0]["metadata"]["neighbor_chunk_ids"],
            [
                "agt_003:art_of_war:0001",
                "agt_003:art_of_war:0002",
                "agt_003:art_of_war:0003",
            ],
        )

    def test_get_agent_context_falls_back_to_id_parsing_for_older_metadata(self):
        vector_index = FakeVectorIndex()
        vector_index.query = lambda **kwargs: [
            SimpleNamespace(
                id="agt_013:my_inventions:0007",
                score=0.77,
                metadata={"agent_id": "agt_013", "source_title": "My Inventions"},
                data="Central Tesla passage.",
            )
        ]
        vector_index.fetch_payloads = {
            "agt_013:my_inventions:0006": {
                "id": "agt_013:my_inventions:0006",
                "metadata": {"agent_id": "agt_013", "source_slug": "my_inventions", "chunk_index": 6},
                "data": "Prior section.",
            },
            "agt_013:my_inventions:0008": {
                "id": "agt_013:my_inventions:0008",
                "metadata": {"agent_id": "agt_013", "source_slug": "my_inventions", "chunk_index": 8},
                "data": "Next section.",
            },
        }

        service = DatabaseService(
            redis_client=FakeRedis(),
            vector_index=vector_index,
            embedding_provider=FakeEmbeddingProvider(),
        )

        matches = service.get_agent_context("inventor", "agt_013", top_k=1, neighbor_window=1)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["metadata"]["source_slug"], "my_inventions")
        self.assertEqual(matches[0]["metadata"]["chunk_index"], 7)
        self.assertIn("Prior section.", matches[0]["data"])
        self.assertIn("Central Tesla passage.", matches[0]["data"])
        self.assertIn("Next section.", matches[0]["data"])

    def test_get_agent_context_filters_out_low_score_matches_before_neighbor_enrichment(self):
        vector_index = FakeVectorIndex()
        vector_index.query = lambda **kwargs: [
            SimpleNamespace(
                id="agt_001:apology:0001",
                score=0.59,
                metadata={"agent_id": "agt_001", "source_slug": "apology", "chunk_index": 1},
                data="Weak match.",
            )
        ]

        service = DatabaseService(
            redis_client=FakeRedis(),
            vector_index=vector_index,
            embedding_provider=FakeEmbeddingProvider(),
        )

        matches = service.get_agent_context("virtue", "agt_001", top_k=1)

        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()