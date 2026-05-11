import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

dotenv_module = types.ModuleType("dotenv")
dotenv_module.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", dotenv_module)

from backend.scripts.render_provider_prompt_example import PromptExample, build_provider_payload, load_latest_captured_example, render_markdown, resolve_output_path


class RenderProviderPromptExampleTests(unittest.TestCase):
    def test_build_provider_payload_marks_stream_options_only_for_streaming(self):
        payload = build_provider_payload(
            provider_url="https://api.example.com/v1",
            model_id="demo-model",
            prompt="Prompt body",
            max_tokens=256,
            temperature=0.7,
            stream=True,
        )

        self.assertEqual(payload["request_url"], "https://api.example.com/v1/chat/completions")
        self.assertTrue(payload["body"]["stream"])
        self.assertEqual(payload["body"]["messages"][0]["content"], "Prompt body")
        self.assertEqual(payload["body"]["stream_options"], {"include_usage": True})

        non_stream_payload = build_provider_payload(
            provider_url="https://api.example.com/v1",
            model_id="demo-model",
            prompt="Prompt body",
            max_tokens=256,
            temperature=0.7,
            stream=False,
        )

        self.assertFalse(non_stream_payload["body"]["stream"])
        self.assertNotIn("stream_options", non_stream_payload["body"])

    def test_render_markdown_states_json_transport_and_prompt_location(self):
        example = PromptExample(
            source="capture",
            debate_date="2026-05-09",
            session_id="123e4567-e89b-12d3-a456-426614174000",
            agent_id="agt_007",
            display_name="Friedrich Nietzsche",
            topic="Should AI replace teachers?",
            mode="compare",
            provider_url="https://api.example.com/v1",
            model_id="demo-model",
            temperature=0.7,
            max_tokens=512,
            context_turns=2,
            vector_matches=3,
            context_messages=[{"turn_number": 1, "display_name": "Socrates", "message": "What is teaching?"}],
            vector_context=[
                {
                    "id": "chunk-1",
                    "score": 0.991,
                    "source_title": "Notebook Fragment",
                    "data": "Education often breeds obedience.",
                }
            ],
            prompt="Full prompt text",
            payloads={
                "stream": {"body": {"messages": [{"role": "user", "content": "Full prompt text"}], "stream": True}, "request_url": "https://api.example.com/v1/chat/completions"},
                "non-stream": {"body": {"messages": [{"role": "user", "content": "Full prompt text"}], "stream": False}, "request_url": "https://api.example.com/v1/chat/completions"},
            },
        )

        markdown = render_markdown(example)

        self.assertIn("# Provider Prompt Example", markdown)
        self.assertIn("The provider request is JSON over HTTP.", markdown)
        self.assertIn("body.messages[0].content", markdown)
        self.assertIn("## Retrieved Vector Context", markdown)
        self.assertIn("## Raw Stored Context Messages", markdown)
        self.assertIn("Notebook Fragment", markdown)
        self.assertIn("````text", markdown)
        self.assertIn("Full prompt text", markdown)
        self.assertIn("````json", markdown)
        self.assertIn("### Stream Payload", markdown)
        self.assertIn("### Non-Stream Payload", markdown)

    def test_load_latest_captured_example_reads_real_capture_file(self):
        with TemporaryDirectory() as tmp_dir:
            capture_path = Path(tmp_dir) / "prompt-captures.jsonl"
            capture_path.write_text(
                "\n".join(
                    [
                        '{"agent_id": "agt_001", "display_name": "Socrates", "topic": "Old", "prompt": "old prompt", "provider_url": "https://api.example.com/v1", "model_id": "demo-model", "temperature": 0.6, "max_tokens": 200, "context_messages": [], "vector_context": [], "provider_request": {"request_url": "https://api.example.com/v1/chat/completions", "body": {"model": "demo-model", "messages": [{"role": "user", "content": "old prompt"}], "temperature": 0.6, "max_tokens": 200, "top_p": 0.95, "stream": false}}}',
                        '{"agent_id": "agt_001", "display_name": "Socrates", "topic": "Should AI replace teachers?", "prompt": "new prompt", "provider_url": "https://api.example.com/v1", "model_id": "demo-model", "temperature": 0.7, "max_tokens": 256, "context_messages": [{"turn_number": 1}], "vector_context": [{"id": "chunk-1"}], "provider_request": {"request_url": "https://api.example.com/v1/chat/completions", "body": {"model": "demo-model", "messages": [{"role": "user", "content": "new prompt"}], "temperature": 0.7, "max_tokens": 256, "top_p": 0.95, "stream": true, "stream_options": {"include_usage": true}}}}',
                    ]
                ),
                encoding="utf-8",
            )

            args = SimpleNamespace(
                capture_file=str(capture_path),
                agent_id="agt_001",
                session_id=None,
                topic="replace teachers",
                mode="compare",
            )
            example = load_latest_captured_example(args)

            self.assertEqual(example.source, "capture")
            self.assertEqual(example.prompt, "new prompt")
            self.assertEqual(example.context_turns, 1)
            self.assertEqual(example.vector_matches, 1)
            self.assertEqual(example.debate_date, "2026-05-09")
            self.assertIn("stream", example.payloads)
            self.assertIn("non-stream", example.payloads)

    def test_resolve_output_path_uses_date_and_topic_when_output_omitted(self):
        args = SimpleNamespace(output=None)
        example = PromptExample(
            source="capture",
            debate_date="2026-05-09",
            session_id=None,
            agent_id="agt_003",
            display_name="Sun Tzu",
            topic="What do you think of Democracy?",
            mode="compare",
            provider_url="https://api.example.com/v1",
            model_id="demo-model",
            temperature=0.0,
            max_tokens=512,
            context_turns=5,
            vector_matches=4,
            context_messages=[],
            vector_context=[],
            prompt="prompt",
            payloads={"stream": {}, "non-stream": {}},
        )

        output_path = resolve_output_path(args, example)

        self.assertEqual(output_path.name, "2026-05-09_what-do-you-think-of-democracy_capture.md")


if __name__ == "__main__":
    unittest.main()