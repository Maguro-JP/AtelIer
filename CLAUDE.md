# AtelIer（アトリエ）

応答は日本語、です・ます調。太字記法は使わない。一度読んだファイルは読み直さない。

## 作業の前に必ず読む

1. `docs/decisions.md`（決めたことと理由）
2. `docs/STRUCTURE.md`（構成と、CharacterDesigner からの対応表）
3. `.worklog/` の最新の日付のファイル（手元の経緯。無ければ飛ばす）

決めたことは、その場で `docs/decisions.md` に 1 行足す。試行錯誤は `.worklog/<日付>.md` に書く（git に入れない）。

## これは何か

人が使う、AI が使う、AI を使うペイントソフト。Python + PySide6 のデスクトップアプリ。
作画の部品は CharacterDesigner（`Maguro-JP/CharacterDesigner` の `chatdraw/`）から流用している。

## 用語

| 呼び方 | 意味 |
|---|---|
| AtelIer | 製品名。読みはアトリエ。A と I だけを大文字の差し色にする（`atelier/ui/logo.py`） |
| 欄 | ドッキングできるパネル（カラー、ブラシ、レイヤーなど） |
| 帯 | ツールバーとステータスバー |
| 作業ファイル | レイヤーごと保存する `.atelier`（`atelier/files/project_file.py`） |
| 赤ペン | AI に直してほしい所を囲む印（`atelier/paint/redpen.py`） |
| 流用元 | CharacterDesigner の `chatdraw/` |

## 構成の決まり

- 層は `ui` / `files` → `paint` → `panels` → `app` の順。下の層は上の層を import しない（`tests/test_identity.py` が見る）
- `atelier/paint` は AI（`atelier/ai`、`atelier/agent`）を import しない。AI が無くても描けることを保つ
- 1 ファイル 1 役目。役目が 2 つになったら分ける。ファイル名は省略しない（`brush_preview.py`、`project_file.py`）
- 流用元の名前（chatdraw、CD_ で始まる環境変数）を `atelier/` に残さない（同じ試験が見る）
- 流用元から部品を足すときは、`docs/STRUCTURE.md` の対応表に行を足す
- メニュー・帯・右クリックで同じ働きの操作は、`atelier/app/actions.py` の 1 つの QAction を使う
- 失敗は `notify_error`（窓）で、成功や案内は `notify`（下の帯）で知らせる

## 確かめ方

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t .   # 試験
python3 -m pyflakes atelier tests                                      # 静的な検査
python3 -m atelier                                                     # 起動
```

- 画面を変えたら `docs/images/main-window.png` を撮り直す（ダミーの絵で撮る）
- 見た目の不具合は、画面を撮って測ってから直す
- 直したバグは試験に足す。試験は窓を開き、マウスの押す・動かす・離すで確かめる（`tests/helpers.py`）

## git

- 枝で作業し、Draft の PR を出す。open の PR がある間は新しい PR を出さない
- CI（GitHub Actions）は置いていない。試験と検査は手元で流す
- コミットをまとめてから push する。コードに触れない変更は `[skip ci]` を付ける
- 記録物に機密・個人情報・モデル名やツール名の署名を書かない
