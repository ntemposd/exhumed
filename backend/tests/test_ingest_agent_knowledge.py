import sys
import types
import unittest
from pathlib import Path

dotenv_module = types.ModuleType("dotenv")
dotenv_module.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", dotenv_module)

from backend.scripts.ingest_agent_knowledge import (
    NAPOLEON_MEMOIR_SERIES_TITLE,
    build_chunk_payloads,
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

        expected_path = Path(__file__).resolve().parents[2] / "data" / "agt_013.txt"

        self.assertEqual(path, expected_path)

    def test_get_agent_ingest_plan_exposes_speaker_specific_descriptions(self):
        plan = get_agent_ingest_plan("agt_011")

        self.assertEqual(plan.speaker_name, "Leon Trotsky")
        self.assertIn("chapter boundaries", plan.chunking_summary.lower())
        self.assertEqual(plan.chunking_policy.target_chunk_size, 1000)

    def test_format_agent_plan_includes_operator_facing_details(self):
        description = format_agent_plan("agt_013")

        self.assertIn("Agent: agt_013", description)
        self.assertIn("Speaker: Nikola Tesla", description)
        self.assertIn("Default source file: agt_013.txt", description)
        self.assertIn("Chunking policy:", description)

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

    def test_extract_source_documents_keeps_only_cleopatra_arc(self):
        text = """Earlier Roman material that should be excluded.

Such being his temper, the last and crowning mischief that could befall him came in the love of Cleopatra, to awaken and kindle to fury passions that as yet lay still and dormant in his nature.

She received several letters, both from Antony and from his friends, to summon her, but she took no account of these orders; and at last, as if in mockery of them, she came sailing up the river Cydnus.

They had a sort of company, to which they gave a particular name, calling it that of the Inimitable Livers.

But the fortune of the day was still undecided, and the battle equal, when on a sudden Cleopatra's sixty ships were seen hoisting sail and making out to sea in full flight.

Some relate that an asp was brought in amongst those figs and covered with the leaves, and that Cleopatra had arranged that it might settle on her before she knew.

Antony left by his three wives seven children, of whom only Antyllus, the eldest, was put to death by Caesar.

Later imperial genealogy that should be excluded.
"""

        documents = extract_source_documents("agt_006", text)

        self.assertEqual(len(documents), 1)
        self.assertTrue(documents[0]["text"].startswith("Such being his temper"))
        self.assertIn("river Cydnus", documents[0]["text"])
        self.assertIn("Inimitable Livers", documents[0]["text"])
        self.assertIn("Cleopatra's sixty ships", documents[0]["text"])
        self.assertIn("asp was brought in amongst those figs", documents[0]["text"])
        self.assertNotIn("Antony left by his three wives seven children", documents[0]["text"])
        self.assertNotIn("Earlier Roman material", documents[0]["text"])
        self.assertEqual(documents[0]["source_slug"], "life_of_antony_cleopatra_arc")

    def test_extract_source_documents_builds_napoleon_anchor_windows(self):
        text = """*** START OF THE PROJECT GUTENBERG EBOOK MEMOIRS OF THE LIFE, EXILE, AND CONVERSATIONS OF THE EMPEROR NAPOLEON. (VOL. I) ***

The Burning of Moscow 164
The Battle of Waterloo 233
Legion of Honour 301

Paragraph 0.

Paragraph 1.

Paragraph 2.

AUSTERLITZ.

Paragraph 4.

WATERLOO.

Paragraph 6.

Paragraph 7.

Paragraph 8.

Paragraph 9.

Paragraph 10.

*** END OF THE PROJECT GUTENBERG EBOOK MEMOIRS OF THE LIFE, EXILE, AND CONVERSATIONS OF THE EMPEROR NAPOLEON. (VOL. I) ***

*** START OF THE PROJECT GUTENBERG EBOOK MEMOIRS OF THE LIFE, EXILE, AND CONVERSATIONS OF THE EMPEROR NAPOLEON. (VOL. II) ***

Lead 0.

Lead 1.

Lead 2.

My code alone, from its simplicity, has been more beneficial to France.

Lead 4.

Lead 5.

Lead 6.

Lead 7.

Lead 8.

Lead 9.

*** END OF THE PROJECT GUTENBERG EBOOK MEMOIRS OF THE LIFE, EXILE, AND CONVERSATIONS OF THE EMPEROR NAPOLEON. (VOL. II) ***

*** START OF THE PROJECT GUTENBERG EBOOK MEMOIRS OF THE LIFE, EXILE, AND CONVERSATIONS OF THE EMPEROR NAPOLEON. (VOL. III) ***

Alpha 0.

Alpha 1.

Alpha 2.

European association! All these young Princes would have grown up together.

Alpha 4.

Alpha 5.

Alpha 6.

Alpha 7.

Alpha 8.

Alpha 9.

*** END OF THE PROJECT GUTENBERG EBOOK MEMOIRS OF THE LIFE, EXILE, AND CONVERSATIONS OF THE EMPEROR NAPOLEON. (VOL. III) ***

*** START OF THE PROJECT GUTENBERG EBOOK MEMOIRS OF THE LIFE, EXILE, AND CONVERSATIONS OF THE EMPEROR NAPOLEON. (VOL. IV) ***

Tail 0.

Tail 1.

Tail 2.

This paragraph mentions Waterlooville only and should not match.

Tail 4.

*** END OF THE PROJECT GUTENBERG EBOOK MEMOIRS OF THE LIFE, EXILE, AND CONVERSATIONS OF THE EMPEROR NAPOLEON. (VOL. IV) ***
"""

        documents = extract_source_documents("agt_004", text)

        self.assertEqual(len(documents), 3)
        self.assertEqual(documents[0]["source_title"], NAPOLEON_MEMOIR_SERIES_TITLE)
        self.assertEqual(documents[0]["source_volume"], "Vol. I")
        self.assertEqual(documents[0]["source_chapter"], "")
        self.assertNotIn("The Burning of Moscow 164", documents[0]["text"])
        self.assertIn("Paragraph 0.", documents[0]["text"])
        self.assertIn("Paragraph 10.", documents[0]["text"])
        self.assertEqual(documents[1]["source_slug"], "memoirs_of_the_life_vol_2_civil_code_0001")
        self.assertIn("My code alone", documents[1]["text"])
        self.assertEqual(documents[2]["source_slug"], "memoirs_of_the_life_vol_3_united_states_of_europe_0001")
        self.assertIn("European association", documents[2]["text"])
        self.assertTrue(all("Waterlooville" not in document["text"] for document in documents))

    def test_extract_source_documents_keeps_only_requested_lovelace_notes(self):
        text = """*** START OF THE PROJECT GUTENBERG EBOOK SKETCH OF THE ANALYTICAL ENGINE INVENTED BY CHARLES BABBAGE, ESQ. ***

NOTE A.—Page 9.

The Analytical Engine may be described as the material expression of any indefinite function.

Delta^7 u_z=0

Supposing, for instance, that the fundamental relations of pitched sounds were susceptible of such expression, the engine might compose elaborate and scientific pieces of music.

NOTE B.—Page 11.

Intermediate note material.

NOTE G.—Page 24.

The Analytical Engine has no pretensions whatever to originate any thing. It can do whatever we know how to order it to perform.

It can follow analysis; but it has no power of anticipating any analytical relations or truths.

x/e^x-1=1/1-x/2+x^2/2.3+x^3/2.34+&c

We append to this Note a Diagram and Table, containing the details of the computation for B_7, (B_1, B_3, B_5 being supposed given).

The diagram[30] represents the columns of the engine when just prepared for computing B_7.

Diagram for the computation by the Engine of the Numbers of Bernoulli.

*** END OF THE PROJECT GUTENBERG EBOOK SKETCH OF THE ANALYTICAL ENGINE INVENTED BY CHARLES BABBAGE, ESQ. ***
"""

        documents = extract_source_documents("agt_008", text)
        plan = get_agent_ingest_plan("agt_008")

        self.assertEqual(len(documents), 2)
        self.assertEqual(plan.chunking_policy.target_chunk_size, 900)
        self.assertEqual(plan.chunking_policy.overlap_percent, 12)
        self.assertEqual(plan.chunking_policy.boundary_patterns, (r"^NOTE [A-G]",))
        self.assertEqual(documents[0]["source_slug"], "note_a_analytical_engine_scope")
        self.assertIn("material expression of any indefinite function", documents[0]["text"])
        self.assertIn("$$", documents[0]["text"])
        self.assertIn("might compose elaborate and scientific pieces of music", documents[0]["text"])
        self.assertEqual(documents[1]["source_slug"], "note_g_engine_limits_bernoulli_method")
        self.assertIn("has no pretensions whatever to originate any thing", documents[1]["text"])
        self.assertIn("$$", documents[1]["text"])
        self.assertIn("### Engine Workflow Summary", documents[1]["text"])
        self.assertNotIn("The diagram[30] represents the columns of the engine", documents[1]["text"])

    def test_extract_source_documents_keeps_only_requested_curie_sections(self):
        text = """*** START OF THE PROJECT GUTENBERG EBOOK PIERRE CURIE ***

PIERRE CURIE

Preface material.

CHAPTER V

The Dream Become a Reality. The Discovery of Radium

We became able to recognize in pitchblende the presence of at least two new radioactive elements: polonium and radium.

CHAPTER VI

Material that should not be included from the Pierre Curie biography.

AUTOBIOGRAPHICAL NOTES
MARIE CURIE

CHAPTER I

Earlier autobiographical material that should be excluded.

CHAPTER II

Yet it was in this miserable old shed that we passed the best and happiest years of our life.

In July, 1898, we announced the existence of this new substance, to which I gave the name of polonium.

CHAPTER III

I had to make the change, during these difficult war years, of my laboratory into the new building of the Institute of Radium.

CHAPTER IV

A visit to America and later material that should be excluded.

*** END OF THE PROJECT GUTENBERG EBOOK PIERRE CURIE ***
"""

        documents = extract_source_documents("agt_009", text)

        self.assertEqual(len(documents), 3)
        self.assertEqual(documents[0]["source_slug"], "pierre_curie_discovery_of_radium")
        self.assertIn("polonium and radium", documents[0]["text"])
        self.assertNotIn("Material that should not be included", documents[0]["text"])
        self.assertEqual(documents[1]["source_slug"], "autobiographical_notes_discovery_old_shed_years")
        self.assertIn("miserable old shed", documents[1]["text"])
        self.assertIn("name of polonium", documents[1]["text"])
        self.assertNotIn("Earlier autobiographical material", documents[1]["text"])
        self.assertEqual(documents[2]["source_slug"], "autobiographical_notes_war_years")
        self.assertIn("difficult war years", documents[2]["text"])
        self.assertNotIn("A visit to America", documents[2]["text"])

    def test_extract_source_documents_builds_marie_antoinette_hybrid_set(self):
        text = """PRIMARY SOURCE DOCUMENT 1: MARIE ANTOINETTE TO HER MOTHER (MARIA THERESA)
Versailles, This 14th of June, 1773.
Madame, my dear mother,—I cannot express how much I am moved by your goodness.

HISTORICAL RECORD 2: THE AMBASSADOR'S REPORT ON EXTRAVAGANCE (COUNT MERCY-ARGENTEAU, 1776)
The Queen has developed an unfortunate passion for high-stakes card games.

HISTORICAL RECORD 3: MEMOIRS OF THE COURT OF MARIE ANTOINETTE (BY MADAME CAMPAN)
The Queen's love for simple country life at the Petit Trianon was entirely misunderstood by the public.

HISTORICAL RECORD 4: THE OFFICIAL INDICTMENT AND TRIAL ACCUSATIONS (OCTOBER 1793)
The Revolutionary Tribunal accuses Marie Antoinette, widow of Louis Capet, of high treason.

PRIMARY SOURCE DOCUMENT 5: THE LAST LETTER OF MARIE ANTOINETTE TO MADAME ÉLISABETH
Conciergerie Prison, October 16th, 1793, 4:30 AM.
It is to you, my sister, that I write for the last time.

The Project Gutenberg eBook of Memoirs of the Court of Marie Antoinette, Queen of France, Complete

*** START OF THE PROJECT GUTENBERG EBOOK MEMOIRS OF THE COURT OF MARIE ANTOINETTE, QUEEN OF FRANCE, COMPLETE ***

LIST OF ILLUSTRATIONS
Marie Antoinette on the way to the Guillotine

PREFACE BY THE AUTHOR.

Louis XVI. meant to write his own memoirs.

HISTORIC COURT MEMOIRS.

MARIE ANTOINETTE.

MEMOIR OF MADAME CAMPAN.

Madame Campan served near Marie Antoinette and recorded court scenes.

*** END OF THE PROJECT GUTENBERG EBOOK MEMOIRS OF THE COURT OF MARIE ANTOINETTE, QUEEN OF FRANCE, COMPLETE ***
"""

        documents = extract_source_documents("agt_014", text)
        plan = get_agent_ingest_plan("agt_014")

        self.assertEqual(len(documents), 6)
        self.assertEqual(plan.chunking_policy.target_chunk_size, 950)
        self.assertEqual(plan.chunking_policy.overlap_percent, 12)
        self.assertEqual(plan.chunking_policy.min_chunk_chars, 60)
        self.assertEqual(documents[0]["source_slug"], "letter_to_maria_theresa_1773")
        self.assertIn("my dear mother", documents[0]["text"])
        self.assertEqual(documents[4]["source_slug"], "last_letter_to_madame_elisabeth_1793")
        self.assertIn("write for the last time", documents[4]["text"])
        self.assertEqual(documents[5]["source_slug"], "memoirs_of_the_court_of_marie_antoinette")
        self.assertIn("PREFACE BY THE AUTHOR.", documents[5]["text"])
        self.assertIn("MEMOIR OF MADAME CAMPAN.", documents[5]["text"])
        self.assertNotIn("LIST OF ILLUSTRATIONS", documents[5]["text"])
        self.assertNotIn("Marie Antoinette on the way to the Guillotine", documents[5]["text"])

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

    def test_chunk_source_text_merges_heading_only_fragments_after_rebalancing(self):
        text = """CHAPTER I

This is the first long paragraph that should remain attached to the heading and not survive as a dangling title fragment. It has enough detail to exceed the minimum chunk threshold.
"""

        chunks = chunk_source_text("agt_011", text, chunk_size=180, overlap_percent=0)

        self.assertEqual(len(chunks), 1)
        self.assertTrue(chunks[0].startswith("CHAPTER I"))
        self.assertIn("first long paragraph", chunks[0])

    def test_build_chunk_payloads_includes_neighbor_retrieval_metadata(self):
        payloads = build_chunk_payloads(
            agent_id="agt_002",
            source_path=Path("agt_002.txt"),
            source_document={
                "speaker_name": "Steve Jobs",
                "source_title": "Stanford Commencement Address",
                "source_volume": "",
                "source_chapter": "",
                "author": "Steve Jobs",
                "translator": "",
                "source_type": "speech",
                "voice_type": "primary",
                "section": "speech_body",
                "source_slug": "stanford_commencement",
            },
            chunks=["Stay hungry. Stay foolish."],
        )

        self.assertEqual(payloads[0]["id"], "agt_002:stanford_commencement:0001")
        self.assertEqual(payloads[0]["metadata"]["agent_id"], "agt_002")
        self.assertEqual(payloads[0]["metadata"]["source_slug"], "stanford_commencement")
        self.assertEqual(payloads[0]["metadata"]["source_volume"], "")
        self.assertEqual(payloads[0]["metadata"]["source_chapter"], "")
        self.assertEqual(payloads[0]["metadata"]["chunk_index"], 1)


if __name__ == "__main__":
    unittest.main()