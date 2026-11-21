# AtelIer ↔ CharacterDesigner ↔ FashionDesigner の連携

AtelIer は道具（ペイントソフト）の本体で、キャラクターデザインは CharacterDesigner と、服飾は FashionDesigner と一緒に開発する。
道具の側は、キャラクターデザインと服飾の中身を知らない形を保つ。

## 役目

| リポジトリ | 持つ物 | AtelIer との関係 |
|---|---|---|
| AtelIer | 描く・直す・加工する道具、AI で描く仕組み、作業ファイル、配布（Setup.exe） | 本体 |
| CharacterDesigner | 設定資料、三面図、表情差分、キャラクターファイル（.chara） | AtelIer の拡張として載る |
| FashionDesigner | 服の輪郭の抽出、型紙の図面（SVG・JSON・OBJ）、服の画像生成の窓口 | 当面はファイルで受け渡す。あとで拡張として載せる |

## AtelIer が今できること（コードで確かめた物）

- 開ける形: PNG、JPEG、WebP、作業ファイル（`.atelier`、CharacterDesigner の `.cdproj`）。`atelier/files/project_file.py`
- 書き出せる形: PNG（重ねた 1 枚）、PSD（レイヤーごと）、作業ファイル。`atelier/app/main_window.py` の `save_as`、`export_psd`
- 外から開く: `python -m atelier --open <ファイル>`（起動して、そのファイルを開く）。`atelier/app/main_window.py` の `main`
- 拡張の登録口: `atelier/extensions.py`。拡張は `name` と `attach(window)` を持ち、`register()` か entry points（`atelier.extensions`）で足す。窓の口は `docs/STRUCTURE.md` に書いた
- 人の筆と同じ経路で線を引く入口: `Canvas.draw_stroke`（`atelier/paint/canvas.py`）

SVG・JSON・OBJ（FashionDesigner の出力）は、まだ開けない。

## 進め方

1. CharacterDesigner: いまは `atelier/chara/` に置いた拡張で動く。CharacterDesigner のリポジトリへ移し、AtelIer を依存として読む形にする
2. FashionDesigner: PNG を受け渡す（AtelIer で描いた絵を FashionDesigner で開き、輪郭を取る）。次に、FashionDesigner の SVG の輪郭を AtelIer のレイヤーとして開けるようにする
3. 3 つで同じ作業ファイルを読めるようにする形（FashionDesigner の `fashiondesigner.project.v1` の案と、AtelIer の `.atelier`）は、それぞれの開発者で合わせて決める

## 服飾の資料の置き場

CharacterDesigner から移した服飾の資料（`casts/fashion*.json`、`casts/fashion-zukan/`、`docs/knowledge/` の服の資料、`library/feedback/fashion/`、`tools/gen/` の服の台本、`tests/test_fashion.py`、`tests/test_zukan.py`）は、FashionDesigner と相談して置き場を決めるまで AtelIer に置いておく。
