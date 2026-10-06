import json
from pathlib import Path
import tempfile
import unittest

from external_context.build_context import ROOT, encode, sha256
from external_context.ocr_customs import checked_completed, write_once


class OCRProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / ".tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "page.json"
        self.source_sha = "a" * 64
        self.config_sha = "b" * 64
        self.data = {"artifact_sha256": self.source_sha, "ocr_config_sha256": self.config_sha,
                     "pdf_page": 2, "outputs": {"ocr.txt": sha256(b"reviewable text")}}
        (self.root / "ocr.txt").write_bytes(b"reviewable text")
        self.path.write_bytes(encode(self.data))

    def test_verified_resume(self):
        self.assertEqual(checked_completed(self.path, self.source_sha, self.config_sha, 2), self.data)

    def test_wrong_pdf_rejected(self):
        with self.assertRaisesRegex(ValueError, "input/config"):
            checked_completed(self.path, "c" * 64, self.config_sha, 2)

    def test_changed_ocr_settings_rejected(self):
        with self.assertRaisesRegex(ValueError, "input/config"):
            checked_completed(self.path, self.source_sha, "c" * 64, 2)

    def test_wrong_page_rejected(self):
        with self.assertRaisesRegex(ValueError, "page mismatch"):
            checked_completed(self.path, self.source_sha, self.config_sha, 3)

    def test_tampered_text_rejected(self):
        (self.root / "ocr.txt").write_bytes(b"edited numbers")
        with self.assertRaisesRegex(ValueError, "hash/path"):
            checked_completed(self.path, self.source_sha, self.config_sha, 2)

    def test_path_escape_rejected(self):
        self.data["outputs"] = {"../outside.txt": "c" * 64}
        self.path.write_bytes(encode(self.data))
        with self.assertRaisesRegex(ValueError, "hash/path"):
            checked_completed(self.path, self.source_sha, self.config_sha, 2)

    def test_write_once_preserves_prior_result(self):
        target = self.root / "new.txt"
        write_once(target, b"original")
        write_once(target, b"original")
        with self.assertRaises(FileExistsError):
            write_once(target, b"replacement")
        self.assertEqual(target.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
