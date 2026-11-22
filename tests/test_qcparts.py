"""検品の部品の目録が、読む側（検品のコード）と同じ模型の名前を指しているか。名前がずれると、取った物を読む側が見つけられない"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def const(path, name):
    m = re.search(rf'^{name}\s*=\s*"([^"]+)"', (ROOT / path).read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


class NamesTest(unittest.TestCase):
    def test_names_match_readers(self):
        src = (ROOT / "atelier" / "qc" / "parts.py").read_text(encoding="utf-8")
        for name, path, var in (("SEG", "tools/gen/edit.py", "SEG_MODEL"), ("PERSON", "atelier/qc/sanity.py", "PERSON_MODEL"),
                                ("TAGGER", "atelier/qc/request_check.py", "REPO"), ("POSE", "atelier/ai/two_stage.py", "POSE")):
            ours = re.search(rf'^{name}\s*=\s*"([^"]+)"', src, re.M).group(1)
            self.assertEqual(ours, const(path, var), f"{name} と {path} の {var}")


if __name__ == "__main__":
    unittest.main()
