"""移したときに、ファイルの置き場からの道（Path(__file__) と with_name）がずれて、データが読めなくなるのを止める"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRITTEN = {"compose-rounds.json"}   # 描いたあとに書く物（読む前に在ることを求めない）


class ModulePathsTest(unittest.TestCase):
    def test_paths_from_module_exist(self):
        missing = []
        pat = re.compile(r'Path\(__file__\)(?:\.resolve\(\))?((?:\.parent)+|\.parents\[(\d)\])((?:\s*/\s*["\'][^"\']+["\'])*)')
        for p in sorted((ROOT / "atelier").rglob("*.py")):
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                for m in pat.finditer(line):
                    up = int(m.group(2)) + 1 if m.group(2) else m.group(1).count(".parent")
                    base = p.resolve().parents[up - 1]
                    parts = re.findall(r'["\']([^"\']+)["\']', m.group(3))
                    if parts == ["fonts"]:
                        continue   # 自由に配れるフォントを置いたときだけ使う置き場（無ければ使わない）
                    if parts and not base.joinpath(*parts).exists():
                        missing.append(f"{p.relative_to(ROOT)}:{i}")
                for m in re.finditer(r'with_name\(["\']([^"\']+)["\']\)', line):
                    if "__file__" in line and m.group(1) not in WRITTEN and not (p.parent / m.group(1)).exists():
                        missing.append(f"{p.relative_to(ROOT)}:{i}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
