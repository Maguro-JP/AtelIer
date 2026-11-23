"""一緒に開発するデザイナー（AtelIer の拡張）の一覧。名前・リポジトリ・置き場の名前・インストーラーで取るかを 1 か所で持つ。

インストーラーの選べる部品（packaging/extension_sections.py が NSIS の節にする）と、CharacterDesigner からの引き継ぎ
（atelier/app/migrate.py）は、ここから名前を取る。名前を何か所にも書くと、デザイナーを足すたびに直し漏れが出るため。

起動のときに読むのは、拡張の置き場に extension.json がある物だけ（atelier/extensions.py の load_dropins）。
この一覧に載っていても、置き場に無いデザイナーには何も出さない（中身の無い入口を作らない）。
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass

# AtelIer を使う人は、デザイナーを拡張だけで入れる（拡張の置き場 C:\ProgramData\AtelIer\extensions に入る）。
# デザイナーの Release には Python ごと入った単体の Setup.exe（80 MiB ほど）もあるので、名前に Extension と Setup の
# 両方を含む .exe だけを拡張だけの Setup とみなす。単体の Setup を AtelIer から入れると、アプリが 2 つ入ってしまうため。
# packaging/get-extension.ps1 も同じ形（-like）で選ぶ
EXTENSION_SETUP_PATTERN = "*Extension*Setup*.exe"


def is_extension_setup(asset_name: str) -> bool:
    """Release の添付の名前が、拡張だけの Setup か（大文字と小文字は区別しない。PowerShell の -like と同じ）"""
    return fnmatch.fnmatch(asset_name.lower(), EXTENSION_SETUP_PATTERN.lower())


@dataclass(frozen=True)
class Designer:
    key: str        # 一覧の中の呼び名
    name: str       # アプリの名前（インストーラーと窓に出す）
    repo: str       # GitHub のリポジトリ（owner/name）。インストーラーは、ここの最新の Release から拡張だけの Setup を取る
    dropin: str     # 拡張の置き場の下のフォルダーの名前（C:\ProgramData\AtelIer\extensions\<dropin>\）
    installer: bool  # Release に拡張だけの Setup（EXTENSION_SETUP_PATTERN）がある物だけ True にする。
    #                  True の物だけを、AtelIer の Setup.exe の選べる部品と、タイルの画面の「入れる」に出す


DESIGNERS: tuple[Designer, ...] = (
    Designer("character", "CharacterDesigner", "Maguro-JP/CharacterDesigner", "character_designer", True),
    Designer("fashion", "FashionDesigner", "Maguro-JP/FashionDesigner", "fashion_designer", False),
    Designer("logo", "LogoDesigner", "Maguro-JP/LogoDesigner", "logo_designer", False),
    Designer("emblem", "EmblemDesigner", "Maguro-JP/EmblemDesigner", "emblem_designer", False),
    # Python の名前は数字で始められないので、置き場の名前は three_d_designer にする
    Designer("3d", "3DDesigner", "Maguro-JP/3DDesigner", "three_d_designer", False),
    Designer("virtual", "VirtualDesigner", "Maguro-JP/VirtualDesigner", "virtual_designer", False),
)


def by_key(key: str) -> Designer:
    for d in DESIGNERS:
        if d.key == key:
            return d
    raise KeyError(key)


def for_installer() -> tuple[Designer, ...]:
    """AtelIer の Setup.exe に選べる部品として出す物。拡張だけの Setup の無いリポジトリは出さない（押しても取れないため）"""
    return tuple(d for d in DESIGNERS if d.installer)
