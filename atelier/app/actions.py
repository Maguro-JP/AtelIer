"""メニュー・道具の帯・右クリックで共に使う操作。

同じ働きの物は 1 つの QAction を出す所ごとに足す。別々に作ると、片方だけキーや働きが変わる。
"""
from __future__ import annotations

from PySide6.QtGui import QAction

from atelier.ui.icons import icon


def build_shared_actions(w) -> dict[str, QAction]:
    """窓 w の操作を作る。行は（鍵, アイコン, 名前, 働き, キー, 説明）"""
    c = w.canvas
    rows = (
        ("new", "new", "新規キャンバス", lambda: c.new_canvas(), "Ctrl+N", "白い新しいキャンバスにします（元に戻すで戻せます）"),
        ("open", "open", "開く…", w.open_image, "Ctrl+O", "作業ファイルか絵を開きます"),
        ("save", "save", "保存", w.save_project, "Ctrl+S", "作業ファイルに保存します"),
        ("undo", "undo", "元に戻す", c.undo, "Ctrl+Z", ""),
        ("redo", "redo", "やり直す", c.redo, "Ctrl+Y", ""),
        ("select_all", "select", "すべてを選択", c.select_all, "Ctrl+A", ""),
        ("deselect", "", "選択を解除", lambda: c.set_selection(None), "Ctrl+D", ""),
        ("sel_clear", "eraser", "選択範囲の中を消す", w.selection_clear, "",
         "選んだレイヤーの、選択範囲の中を消します（絵の上で Delete でも消せます。元に戻すで戻せます）"),
        ("sel_fill", "fill", "選択範囲を塗る", w.selection_fill, "Alt+Backspace", "選択範囲の中を描く色で塗ります"),
        ("copy", "", "コピー", w.selection_copy, "Ctrl+C", "選択範囲の中をコピーします。選択が無いときは見えている絵全体をコピーします"),
        ("cut", "", "切り取り", w.selection_cut, "Ctrl+X", "選択範囲の中をコピーして消します"),
        ("paste", "", "貼り付け", w.paste_clipboard, "Ctrl+V", "コピーした絵を一番上の新しいレイヤーに貼ります"),
        ("paste_in_place", "", "同じ位置に貼り付け", w.paste_in_place, "Ctrl+Shift+V",
         "コピーした絵を、コピーした所と同じ位置の新しいレイヤーに貼ります"),
        ("copy_merged", "", "結合してコピー", w.copy_merged, "Ctrl+Shift+C",
         "見えているレイヤーを重ねた絵の、選択範囲の中をコピーします（選択が無いときは全体）"),
        ("fit", "fit", "全体を表示", c.fit, "Ctrl+0", ""),
        ("actual", "zoom", "100%", c.actual, "Ctrl+1", "等倍で表示"),
        ("zoom_in", "zoom", "拡大", lambda: c.set_zoom(c.zoom() * 1.25), "Ctrl+=", ""),
        ("zoom_out", "", "縮小", lambda: c.set_zoom(c.zoom() / 1.25), "Ctrl+-", ""),
        ("zoom_ask", "", "拡大率を指定…", w.ask_zoom, "", "拡大率を % の数字で決めます"),
        ("rotate_left", "", "左に回す", lambda: c.rotate_view(-15), "Ctrl+[", ""),
        ("rotate_right", "rotate", "右に回す", lambda: c.rotate_view(15), "Ctrl+]", ""),
        ("rotate_dial", "rotate", "角度を指定…", w.ask_angle, "", "表示の角度を数字で決めます（R を押しながらドラッグでも回せます）"),
        ("rotate_reset", "", "回転を戻す", c.reset_rotation, "Ctrl+\\", "表示の角度を 0 度に戻します"),
        ("flip_view", "", "左右反転で表示", lambda: c.flip_view(), "Shift+H",
         "絵を左右反転して見ます（絵は変えません）。崩れを見つけやすくなります"),
        ("view_reset", "fit", "表示をリセット", c.reset_view, "Ctrl+Alt+0",
         "回転・左右反転・拡大・位置を初めに戻し、絵の全体を出します（絵は変えません）"),
        ("grid", "", "グリッド", lambda: c.set_grid(not c.grid), "Ctrl+'", "絵の上に方眼を出します（保存する絵には入りません）"),
        ("add_layer", "layers", "新しいレイヤー", c.add_layer, "Ctrl+Shift+N", ""),
        ("delete_layer", "", "レイヤーを消す", c.delete_layer, "", "選んでいるレイヤーを消します（元に戻すで戻せます）"),
        ("dup_layer", "", "レイヤーを複製", c.duplicate_layer, "", "選んでいるレイヤーを、すぐ上に同じ絵で複製します"),
        ("clear_layer", "", "レイヤーの中を消す", c.clear_layer, "", "選んでいるレイヤーの絵を全部消します（レイヤーは残ります）"),
        ("layer_copy", "", "レイヤーをコピー", w.layer_copy, "Ctrl+Alt+C", "選んでいるレイヤーを、名前と不透明度ごとコピーします"),
        ("layer_cut", "", "レイヤーを切り取り", w.layer_cut, "Ctrl+Alt+X", "選んでいるレイヤーをコピーしてから消します"),
        ("layer_paste", "", "レイヤーを貼り付け", w.layer_paste, "Ctrl+Alt+V",
         "コピーしたレイヤーを、選んでいるレイヤーのすぐ上に新しいレイヤーとして貼ります"),
        ("via_copy", "", "選択範囲をコピーして新しいレイヤーへ", lambda: c.layer_via(False), "Ctrl+J",
         "選択範囲の中を同じ位置の新しいレイヤーに写します。選択が無いときはレイヤーを複製します"),
        ("via_cut", "", "選択範囲を切り取って新しいレイヤーへ", lambda: c.layer_via(True), "Ctrl+Shift+J",
         "選択範囲の中を元のレイヤーから切り取り、同じ位置の新しいレイヤーに移します"),
        ("merge_down", "", "下のレイヤーと結合", c.merge_down, "", "選んでいるレイヤーを、すぐ下のレイヤーに結合します"),
        ("merge_visible", "", "見えているレイヤーを結合", c.merge_visible, "Ctrl+Shift+E", ""),
        ("flip_layer_h", "", "レイヤーを左右反転", lambda: c.flip_layer(True), "", "選んでいるレイヤーの絵そのものを左右に反転します"),
        ("flip_layer_v", "", "レイヤーを上下反転", lambda: c.flip_layer(False), "", "選んでいるレイヤーの絵そのものを上下に反転します"),
    )
    shared: dict[str, QAction] = {}
    for key, icon_key, label, fn, shortcut, tip in rows:
        a = QAction(label, w)
        if icon_key:
            a.setIcon(icon(icon_key))
        if shortcut:
            a.setShortcut(shortcut)
        a.triggered.connect(lambda _=False, fn=fn: fn())
        a.setToolTip((tip or label) + (f"（{shortcut}）" if shortcut else ""))
        shared[key] = a
    for k in ("flip_view", "grid"):
        shared[k].setCheckable(True)
    c.view_changed.connect(lambda: (shared["flip_view"].setChecked(c.flipped), shared["grid"].setChecked(c.grid)))
    return shared
