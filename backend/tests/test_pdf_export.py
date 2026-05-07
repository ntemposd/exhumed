import os
import unittest
from uuid import uuid4

from backend.utils.pdf_export import export_session_pdf


class PdfExportTests(unittest.TestCase):
    def test_export_session_pdf_writes_pdf_file(self):
        session_id = uuid4()
        pdf_path = export_session_pdf(
            [
                {
                    "topic": "AI governance",
                    "display_name": "Socrates",
                    "turn_number": 1,
                    "created_at": "2026-05-07T00:00:00Z",
                    "message": "What is justice in a machine age?",
                }
            ],
            session_id,
        )

        self.assertTrue(os.path.exists(pdf_path))
        self.assertGreater(os.path.getsize(pdf_path), 0)


if __name__ == "__main__":
    unittest.main()