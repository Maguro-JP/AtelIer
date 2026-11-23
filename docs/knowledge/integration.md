# AtelIer ↔ CharacterDesigner ↔ FashionDesigner の連携

AtelIer は道具（ペイントソフト）の本体で、キャラクターデザインは CharacterDesigner と、服飾は FashionDesigner と一緒に開発する。
道具の側は、キャラクターデザインと服飾の中身を知らない形を保つ。

## 役目

| リポジトリ | 持つ物 | AtelIer との関係 |
|---|---|---|
| AtelIer | 描く・直す・加工する道具、AI で描く仕組み、作業ファイル、配布（Setup.exe） | 本体 |
| CharacterDesigner | 設定資料、三面図、表情差分、キャラクターファイル（.chara）。拡張のパッケージ `character_designer` | AtelIer の拡張として載る（entry points の `atelier.extensions`） |
| FashionDesigner | 服の輪郭の抽出、型紙の図面（SVG・JSON・OBJ）、服の画像生成の窓口 | 当面はファイルで受け渡す。あとで拡張として載せる |

## AtelIer が今できること（コードで確かめた物）

- 開ける形: PNG、JPEG、WebP、作業ファイル（`.atelier`、CharacterDesigner の `.cdproj`）。`atelier/files/project_file.py`
- 書き出せる形: PNG（重ねた 1 枚）、PSD（レイヤーごと）、作業ファイル。`atelier/app/main_window.py` の `save_as`、`export_psd`
- 外から開く: `python -m atelier --open <ファイル>`（起動して、そのファイルを開く）。`atelier/app/main_window.py` の `main`
- 拡張の登録口: `atelier/extensions.py`。拡張は `name` と `attach(window)` を持ち、`register()` か entry points（`atelier.extensions`）で足す。窓の口は `docs/STRUCTURE.md` に書いた
- 人の筆と同じ経路で線を引く入口: `Canvas.draw_stroke`（`atelier/paint/canvas.py`）

SVG・JSON・OBJ（FashionDesigner の出力）は、まだ開けない。

## 進め方

1. CharacterDesigner: 拡張は CharacterDesigner の `character_designer/` にあり、AtelIer を依存として読む。AtelIer を入れてから CharacterDesigner を入れ（`pip install -e .`）、`python -m atelier` で起動すると「キャラクターデザイン」のメニューが出る。AtelIer の側はキャラクターデザインの中身を持たない
2. FashionDesigner: PNG を受け渡す（AtelIer で描いた絵を FashionDesigner で開き、輪郭を取る）。次に、FashionDesigner の SVG の輪郭を AtelIer のレイヤーとして開けるようにする
3. 3 つで同じ作業ファイルを読めるようにする形（FashionDesigner の `fashiondesigner.project.v1` の案と、AtelIer の `.atelier`）は、それぞれの開発者で合わせて決める

## 服飾の資料の置き場

CharacterDesigner から移した服飾の資料（`casts/fashion*.json`、`casts/fashion-zukan/`、`docs/knowledge/` の服の資料、`library/feedback/fashion/`、`tools/gen/` の服の台本、`tests/test_fashion.py`、`tests/test_zukan.py`）は、FashionDesigner と相談して置き場を決めるまで AtelIer に置いておく。

## インストーラーどうしの連携

### AtelIer の入っている場所を見つける

AtelIer の Setup.exe は `HKLM\Software\AtelIer` の `InstallDir` に入れた場所（既定は `C:\Program Files\AtelIer`）を書く。
アンインストールの情報は `HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\AtelIer`（`DisplayVersion` に版）。
データの置き場は `C:\ProgramData\AtelIer`（`%ProgramData%\AtelIer`。開発中は `ATELIER_HOME` で替えられる）。

### 拡張の置き場

AtelIer の Python は Setup.exe の中にあるので、ほかのアプリのインストーラーは pip で拡張を入れられない。
そのかわり、次の形で置けば、AtelIer が起動のときに読む（`atelier/extensions.py` の `load_dropins`）。

```
C:\ProgramData\AtelIer\extensions\<名前>\extension.json
C:\ProgramData\AtelIer\extensions\<名前>\<パッケージ>\__init__.py ...
```

`extension.json` の形（`version` などほかの鍵は読まずに置いておける）:

```json
{"module": "character_designer.extension", "attr": "EXTENSION", "path": "."}
```

- `path` は sys.path に足す所で、`<名前>\` からの道（既定は `.`）。AtelIer はそこを sys.path の後ろに足し（AtelIer と同じ名前の物は AtelIer の物が先に読まれる。CharacterDesigner の `tools/gen` は AtelIer の `tools/gen` と同じ名前の台本が多いので、拡張の中からは `character_designer` の下の道で読む）、`module` を import して `attr` を取る
- `attr` は `name` と `attach(window)` を持つ物か、そのクラス（引数なしで作る）。既定は `EXTENSION`
- 読めない拡張は stderr に理由を出して飛ばし、本体とほかの拡張は動く
- 消すときは `<名前>\` を丸ごと消す。CharacterDesigner のアンインストーラーは自分の置いた `<名前>\` だけを消す
- 拡張の依存は `<名前>\` の中に一緒に置く（AtelIer の Python に無い物は読めない）

CharacterDesigner の Setup.exe は、AtelIer の `InstallDir` が見つかったときに、この置き場へ自分の拡張を置く。

### AtelIer の Setup.exe から CharacterDesigner を入れる

コンポーネントのページに「CharacterDesigner も入れる（ネットから取る）」がある（既定で選ぶ。外せば入れない）。
選ぶと、`Maguro-JP/CharacterDesigner` の最新の Release から名前に `Setup` を含む `.exe` を取り、`/S` で静かに入れる
（`packaging/get-characterdesigner.ps1`）。AtelIer を入れたあとに動くので、CharacterDesigner の Setup.exe は AtelIer を見つけられる。
Release に Setup.exe が無いとき・取れないときは知らせて先へ進む。

### データの引き継ぎ

インストーラーは引き継がない。AtelIer の初めての起動で CharacterDesigner の置き場（`%ProgramData%\CharacterDesigner`）が
見つかったときだけ「CharacterDesigner から引き継ぐ」窓を出し、利用者が選んだ組だけを写す（`atelier/app/migrate.py`）。

拡張だけの Setup が Release にある拡張は、AtelIer のインストーラーで既定で入れる（外すこともできる）。静かに入れるとき（/S）も既定どおり入れ、取れないときは理由を出して飛ばし、AtelIer の入れ方は止めない。
