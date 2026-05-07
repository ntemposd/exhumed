import sys
import types
import unittest
from pathlib import Path

dotenv_module = types.ModuleType("dotenv")
dotenv_module.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", dotenv_module)

from backend.scripts.ingest_agent_knowledge import (
    chunk_source_text,
    extract_source_documents,
    format_agent_plan,
    format_agent_plan_catalog,
    get_agent_ingest_plan,
    resolve_source_path,
)


class IngestAgentKnowledgeTests(unittest.TestCase):
    def test_resolve_source_path_defaults_to_agent_specific_file(self):
        path = resolve_source_path("agt_013", None)

        self.assertEqual(path, Path("c:/Users/ntemposd/Documents/GitHub/roundtablelegends/data/agt_013.txt"))

    def test_get_agent_ingest_plan_exposes_speaker_specific_descriptions(self):
        plan = get_agent_ingest_plan("agt_011")

        self.assertEqual(plan.speaker_name, "Leon Trotsky")
        self.assertIn("chapter boundaries", plan.chunking_summary.lower())

    def test_format_agent_plan_includes_operator_facing_details(self):
        description = format_agent_plan("agt_013")

        self.assertIn("Agent: agt_013", description)
        self.assertIn("Speaker: Nikola Tesla", description)
        self.assertIn("Default source file: agt_013.txt", description)

    def test_format_agent_plan_catalog_lists_supported_speakers(self):
        catalog = format_agent_plan_catalog()

        self.assertIn("Supported speaker ingestion plans:", catalog)
        self.assertIn("- agt_001: Socrates", catalog)
        self.assertIn("- agt_013: Nikola Tesla", catalog)

    def test_extract_source_documents_cleans_trotsky_navigation_noise(self):
        text = """Leon Trotsky
My Life
return
Last updated on: 2024-01-01
CHAPTER I
The first chapter text.
"""

        documents = extract_source_documents("agt_011", text)

        self.assertEqual(len(documents), 1)
        self.assertTrue(documents[0]["text"].startswith("CHAPTER I"))
        self.assertNotIn("Last updated on:", documents[0]["text"])

    def test_chunk_source_text_keeps_sun_tzu_sections_separate_when_needed(self):
        text = """Chapter I. LAYING PLANS
Short section one.

Chapter II. WAGING WAR
Short section two.
"""

        chunks = chunk_source_text("agt_003", text, chunk_size=45, chunk_overlap=0)

        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].startswith("Chapter I. LAYING PLANS"))
        self.assertTrue(chunks[1].startswith("Chapter II. WAGING WAR"))


if __name__ == "__main__":
    unittest.main()