"""右クリックのメニューを開く。"""
from __future__ import annotations


def exec_once(menu, pos):
    """右クリックのたびに作るメニューを開き、閉じたら捨てる。窓を親にして作るので、捨てないと右クリックのたびに
    メニューが窓に溜まり続ける。押した項目の処理は exec の中で済んでいるので、閉じたあとに捨ててよい"""
    try:
        return menu.exec(pos)
    finally:
        menu.deleteLater()
