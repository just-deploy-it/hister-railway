# ---
# author: Just Deploy It
# project: Hister on Railway
# purpose: Prove the updater advances from its current pin rather than replacing one original value
# used_by: local verification and GitHub Actions
# status: active
# verified: 2026-08-27
# ---
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.update_hister import apply_update
from scripts.verify import verify

PINS = (
    ("v0.16.0", "sha256:98ba061692aeb36616574defdad9938aba94dbf142463915f596693acd4f5ef4"),
    ("v0.17.0", "sha256:2894138653cc11fde955cd9e53c51385fbaa14d236730bbefff2b64b841d7395"),
    ("v0.18.0", "sha256:55ca3b00da9d3245cc689a7f4455be5f4a3931c29d3450d6d1f46f8c931cce35"),
)


class UpdaterTest(unittest.TestCase):
    def test_same_pin_is_a_verified_noop(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("Dockerfile", "upstream.json", "railway-template.json"):
                shutil.copy2(source / name, root / name)
            current = json.loads((root / "upstream.json").read_text())
            result = apply_update(root, current["version"], current["digest"])
            self.assertFalse(result["changed"])
            self.assertEqual(verify(root)["digest"], current["digest"])

    def test_two_consecutive_pin_advances_keep_every_file_consistent(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("Dockerfile", "upstream.json", "railway-template.json"):
                shutil.copy2(source / name, root / name)
            apply_update(root, *PINS[0])
            first = apply_update(root, *PINS[1])
            self.assertEqual(first["from"]["version"], "v0.16.0")
            self.assertEqual(verify(root)["digest"], PINS[1][1])
            second = apply_update(root, *PINS[2])
            self.assertEqual(second["from"]["version"], "v0.17.0")
            self.assertEqual(verify(root)["digest"], PINS[2][1])

    def test_rejects_invalid_or_partial_candidate_pins(self):
        source = Path(__file__).resolve().parents[1]
        with self.assertRaises(ValueError):
            apply_update(source, "rolling", PINS[2][1])
        with self.assertRaises(ValueError):
            apply_update(source, "v0.18.0", "sha256:bad")


if __name__ == "__main__":
    unittest.main()
