"""利用者の設定（模型の ★・非表示・ブロック・点・タグ、絵の ★、模型の置き場、学んだ基準）を版をまたいで引き継ぐ試験。

前の版は、手の検品か言葉の読み取りが一度動くと ATELIER_HOME を data_home()/cd に書き換え、それ以降の読み書きが cd の下へずれた。
そのため ★ や非表示がリセットされたように見え、ずれた所に付けた印は次の起動で消えた。
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from atelier.ai import own_style as ownstyle
from atelier.files import paths
from atelier.models import ratings

ROOT = Path(__file__).resolve().parents[1]


class KeepSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"ATELIER_HOME": str(self.home)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def write(self, rel: str, data):
        p = self.home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return p

    def test_reads_previous_version_files(self):
        """v0.5.3〜v0.5.7 の形の model_prefs.json と favorites.json をそのまま読む"""
        self.write("model_prefs.json", {"a/b": {"favorite": True, "hidden": True, "rating": 77, "tags": ["アニメ"]},
                                        "c/d": {"blocked": True}})
        self.write("favorites.json", ["C:/pic/1.png"])
        self.assertTrue(ratings.is_favorite("a/b"))
        self.assertTrue(ratings.is_hidden("a/b"))
        self.assertEqual(ratings.user_rating("a/b"), 77)
        self.assertEqual(ratings.user_tags("a/b"), ["アニメ"])
        self.assertTrue(ratings.is_blocked("c/d"))
        self.assertEqual(ownstyle.favorites(), ["C:/pic/1.png"])

    def test_bom_is_read(self):
        """メモ帳で直して BOM が付いたファイルも読む"""
        (self.home / "model_prefs.json").write_text(json.dumps({"a/b": {"favorite": True}}), encoding="utf-8-sig")
        self.assertTrue(ratings.is_favorite("a/b"))

    def test_checks_do_not_move_data_home(self):
        """手の検品と言葉の読み取りの準備で、データの置き場がずれない（前の版はここで ★ が消えた）"""
        os.environ.pop("ATELIER_HOME")
        with TemporaryDirectory() as d, mock.patch.dict(os.environ, {"ProgramData": d}), \
                mock.patch.object(paths, "WINDOWS", True):
            before = paths.data_home()
            home = Path(d) / "AtelIer"
            home.mkdir()
            (home / "model_prefs.json").write_text(json.dumps({"a/b": {"favorite": True}}), encoding="utf-8")
            data_home = paths.use_tools_gen()
            self.assertNotIn("ATELIER_HOME", os.environ)
            self.assertEqual(paths.data_home(), before)
            self.assertEqual(Path(data_home.HOME), before)   # 部品の置き場もデータの置き場と同じ 1 か所
            self.assertTrue(ratings.is_favorite("a/b"))

    def test_broken_file_is_kept(self):
        """読めないファイルは消さずに控えを残し、次の保存で元の中身を失わない"""
        broken = '{"a/b": {"favorite": true}'   # 閉じ括弧が無い
        self.write("model_prefs.json", broken)
        self.assertFalse(ratings.is_favorite("a/b"))
        ratings.set_favorite("c/d", True)
        backups = list(self.home.glob("model_prefs.json.broken-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), broken)
        self.assertTrue(ratings.is_favorite("c/d"))
        self.write("favorites.json", {"not": "a list"})
        self.assertEqual(ownstyle.favorites(), [])
        self.assertEqual(len(list(self.home.glob("favorites.json.broken-*"))), 1)

    def test_installer_keeps_user_data(self):
        """アンインストールで QSettings（HKCU）を消さず、黙って消すときは ProgramData を消さず、設定のファイルを残す"""
        nsi = (ROOT / "packaging" / "installer.nsi").read_text(encoding="utf-8")
        self.assertNotIn('DeleteRegKey HKCU "Software\\${APP}"', nsi)
        self.assertNotIn("/SD IDYES", nsi)
        # 利用者の物を巻き込まないよう、インストール先・ProgramData・C:\\LLM を /r で丸ごと消さない
        for whole in ('RMDir /r "$INSTDIR"\n', 'RMDir /r "$1"', 'RMDir /r "$COMMONPROGRAMDATA\\${APP}"\n',
                      'RMDir /r "$1LLM', 'RMDir /r "$COMMONPROGRAMDATA\\${APP}\\extensions'):
            self.assertNotIn(whole, nsi)
        self.assertIn('${AndIf} ${FileExists} "$INSTDIR\\atelier\\__init__.py"', nsi)


if __name__ == "__main__":
    unittest.main()
