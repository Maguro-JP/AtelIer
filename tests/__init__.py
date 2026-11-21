"""AtelIer の試験。

試験が開く窓は、閉じるときに欄の配置やテーマを QSettings に書く。利用者の設定と同じ場所に書くと、
前の試験の配置が次の窓に残って順番によって結果が変わるので、試験の間は設定とデータの置き場を一時の場所に替える。
"""
import atexit
import os
import shutil
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_CONFIG = tempfile.mkdtemp(prefix="atelier-test-config-")
_DATA = tempfile.mkdtemp(prefix="atelier-test-data-")
os.environ["XDG_CONFIG_HOME"] = _CONFIG
os.environ["ATELIER_HOME"] = _DATA
atexit.register(shutil.rmtree, _CONFIG, True)
atexit.register(shutil.rmtree, _DATA, True)
