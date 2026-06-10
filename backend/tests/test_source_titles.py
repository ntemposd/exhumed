import unittest



from backend.utils.source_titles import (

    citation_from_metadata,

    compose_source_citation,

    format_source_citation,

    format_source_title,

    normalize_stored_citation_field,

)





class SourceTitleTests(unittest.TestCase):

    def test_normalize_stored_field_strips_trailing_period(self):

        self.assertEqual(normalize_stored_citation_field("The Lost Interview 1995."), "The Lost Interview 1995")



    def test_normalize_stored_field_removes_ellipsis(self):

        self.assertEqual(

            normalize_stored_citation_field("Memoirs of the life..."),

            "Memoirs of the life",

        )



    def test_compose_source_citation_joins_parts(self):

        composed = compose_source_citation(

            "Memoirs of the life, exile, and conversations of the Emperor Napoleon",

            volume="Vol. II",

        )

        self.assertEqual(

            composed,

            "Memoirs of the life, exile, and conversations of the Emperor Napoleon - Vol. II",

        )



    def test_format_source_citation_truncates_long_composed_title(self):

        formatted = format_source_citation(

            "Autobiographical Notes",

            chapter="Discovery and Old Shed Years",

        )



        self.assertLessEqual(len(formatted), 48)

        self.assertTrue(formatted.endswith("Discovery and Old Shed Years"))

        self.assertIn("...", formatted)



    def test_format_source_citation_preserves_volume_after_title_truncation(self):

        formatted = format_source_citation(

            "Memoirs of the life, exile, and conversations of the Emperor Napoleon",

            volume="Vol. II",

        )



        self.assertLessEqual(len(formatted), 48)

        self.assertTrue(formatted.endswith("Vol. II"))

        self.assertIn("...", formatted)



    def test_format_source_title_keeps_short_title_unchanged(self):

        self.assertEqual(format_source_title("Crito"), "Crito")



    def test_format_source_title_keeps_legacy_trailing_ellipsis(self):

        self.assertEqual(format_source_title("Memoirs of the life..."), "Memoirs of the life...")



    def test_citation_from_metadata_reads_volume_and_chapter(self):

        citation = citation_from_metadata(

            {

                "source_title": "Meditations",

                "source_volume": "",

                "source_chapter": "Second Book",

            }

        )

        self.assertEqual(citation["title"], "Meditations")

        self.assertIsNone(citation["volume"])

        self.assertEqual(citation["chapter"], "Second Book")





if __name__ == "__main__":

    unittest.main()

