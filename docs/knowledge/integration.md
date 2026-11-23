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

- タイルの画面（`atelier/app/title_screen.py`）に出す見せ方は、任意の鍵 `"title"`（名前）、`"image"`（`<名前>\` からの絵の道）、`"tagline"`（一言）で書く。無いときは拡張の `name` と、名前の頭文字で作った絵を出す
- タイルを押したとき、拡張に `open(window)` があればそれを呼ぶ。無ければ、`attach` で増えたモード、欄、メニューの最初の操作の順に開く
- `path` は sys.path に足す所で、`<名前>\` からの道（既定は `.`）。AtelIer はそこを sys.path の後ろに足し（AtelIer と同じ名前の物は AtelIer の物が先に読まれる。CharacterDesigner の `tools/gen` は AtelIer の `tools/gen` と同じ名前の台本が多いので、拡張の中からは `character_designer` の下の道で読む）、`module` を import して `attr` を取る
- `attr` は `name` と `attach(window)` を持つ物か、そのクラス（引数なしで作る）。既定は `EXTENSION`
- 読めない拡張は stderr に理由を出して飛ばし、本体とほかの拡張は動く
- 消すときは `<名前>\` を丸ごと消す。CharacterDesigner のアンインストーラーは自分の置いた `<名前>\` だけを消す
- 拡張の依存は `<名前>\` の中に一緒に置く（AtelIer の Python に無い物は読めない）

CharacterDesigner の Setup.exe は、AtelIer の `InstallDir` が見つかったときに、この置き場へ自分の拡張を置く。

### デザイナーの一覧

一緒に開発するデザイナーは `atelier/extension_catalog.py` に並べる（CharacterDesigner、FashionDesigner、LogoDesigner、
EmblemDesigner、3DDesigner、VirtualDesigner）。持つのは名前・リポジトリ・拡張の置き場の名前（`<名前>`）・インストーラーで取るか。
置き場の名前は `character_designer`、`fashion_designer`、`logo_designer`、`emblem_designer`、`three_d_designer`、`virtual_designer`。

### 拡張の設計（3 つの使われ方を 1 つの中身で支える）

6 つのデザイナーは AtelIer のために設計するが、単体のアプリとしても動き、ほかの AI サービスからも使えるようにする。
使われ方ごとに中身を作り分けると、同じ処理が 3 か所に分かれて直し漏れが出るので、中身は 1 つにして入口だけを分ける。

| 層 | 中身 |
|---|---|
| 中身の処理 | UI に頼らない部品（Python の関数・クラス）。窓・メニュー・AtelIer の型を読み込まない |
| 入口 1: AtelIer の拡張 | `extension.json` とメニュー。拡張の置き場（`C:\ProgramData\AtelIer\extensions\<名前>`）に置かれ、AtelIer が読み込む |
| 入口 2: 単体のアプリ | 自分のウィンドウと Setup.exe。AtelIer が無くても起動する |
| 入口 3: ほかの AI サービスから使う口 | MCP のサーバーと、コマンドで呼べる口。中身の処理をそのまま呼ぶ |

- 置き場と設定は、どの入口から使っても同じにする。入口ごとに置き場を持つと、同じ人の設定や作った物が入口ごとに分かれるため。
- 言葉の模型は共通の置き場 `C:\LLM` に置く（shared-models）。
- AtelIer が無くても動き、AtelIer があれば拡張として載る。中身の処理は AtelIer を読み込まない。
- ほかの AI サービスから使う口を MCP のサーバー（標準入出力で話す形）にすること、コマンドの口を `python -m <パッケージ> <操作>` の形で JSON を返すものにすること、MCP のサーバーとコマンドが同じ操作の一覧を共有することは、私の推測。

### AtelIer の Setup.exe からデザイナーを入れる

コンポーネントのページに「<デザイナー> も入れる（ネットから取る）」が出る（既定は外す）。出すのは一覧で `installer` が True の物
（Release に Setup.exe がある物）だけで、`packaging/extension_sections.py` が組むたびに節を書き出す。
選ぶと、そのリポジトリの最新の Release から名前に `Setup` を含む `.exe` を取り、`/S` で静かに入れる
（`packaging/get-extension.ps1 -Repo <owner/name>`）。AtelIer を入れたあとに動くので、CharacterDesigner の Setup.exe は AtelIer を見つけられる。
Release に Setup.exe が無いとき・取れないときは知らせて先へ進む。

### データの引き継ぎ

インストーラーは引き継がない。AtelIer の初めての起動で CharacterDesigner の置き場（`%ProgramData%\CharacterDesigner`）が
見つかったときだけ「CharacterDesigner から引き継ぐ」窓を出し、利用者が選んだ組だけを写す（`atelier/app/migrate.py`）。
