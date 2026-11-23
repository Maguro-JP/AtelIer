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

### 拡張の設計（AtelIer が統括し、拡張だけを入れる）

AtelIer が 6 つのデザイナーを統括する。開発はデザイナーごとのリポジトリで分担するが、AtelIer のための開発をする
（AtelIer で使われない作り込みは、AtelIer を使う人に届かないため）。AtelIer を使う人は拡張だけを入れ、使う物は AtelIer のタイトルの画面で選ぶ。
デザイナーごとに Python と PySide6 を持つと、容量がかさみ、同じ物が重なって入るため。
拡張は単体でも動き、ほかの AI サービスからも使える。使われ方ごとに中身を作り分けると直し漏れが出るので、中身は 1 つにして入口だけを分ける。

| 層 | 中身 |
|---|---|
| 中身の処理 | UI に頼らない部品（Python の関数・クラス）。窓・メニュー・AtelIer の型を読み込まない |
| 入口 1: AtelIer の拡張 | `extension.json` とメニュー。拡張の置き場（`C:\ProgramData\AtelIer\extensions\<名前>`）に置かれ、AtelIer が読み込む |
| 入口 2: 単体のアプリ | 自分のウィンドウ。AtelIer が無くても起動する |
| 入口 3: ほかの AI サービスから使う口 | MCP のサーバーと、コマンドで呼べる口。中身の処理をそのまま呼ぶ |

配る物は 2 つで、拡張だけの Setup が先、単体の Setup は後に作る。

| 配る物 | 中身 | 誰向け |
|---|---|---|
| 拡張だけの Setup | 拡張のコードと、AtelIer の Python に無い依存だけ。AtelIer の Python と PySide6 で動く。小さい | AtelIer を使う人。AtelIer のインストーラーで選べる部品はこちらを入れる |
| 単体の Setup | 自分の Python と PySide6 を持つ | AtelIer を使わない人 |

- AtelIer のタイトルの画面に出す名前・絵・一言は、拡張の `extension.json` に持たせる（欄の名前はデザイナーの側の `docs/atelier-extension.md`。私の推測）。
- 置き場と設定は、どの入口から使っても同じにする。入口ごとに置き場を持つと、同じ人の設定や作った物が入口ごとに分かれるため。
- 言葉の模型は共通の置き場 `C:\LLM` に置く（shared-models）。
- ほかの AI サービスから使う口を MCP のサーバー（標準入出力で話す形）にすること、コマンドの口を `python -m <パッケージ> <操作>` の形で JSON を返すものにすることは、私の推測。

#### 今の CharacterDesigner の Setup.exe は Python ごとの物

`gh release view -R Maguro-JP/CharacterDesigner` で見た最新の Release（v0.5.38、2026-11-20）の資産は `CharacterDesigner-Setup.exe` の 1 つで、
大きさは 84,670,803 バイト（約 81 MiB）。Release のコミットの `packaging/chatdraw/build.sh` は、python.org の埋め込み版の Python、PySide6-Essentials 6.9.3、
numpy、Pillow、huggingface_hub を同梱して組む。拡張だけの物ではなく、単体の Setup（Python ごと）にあたる。
AtelIer のインストーラーの `packaging/get-extension.ps1` は名前に `Setup` を含む最初の `.exe` を取るので、今はこの Python ごとの物を入れる。

直し方（私の推測。まだ直していない）:

1. CharacterDesigner の `packaging/character_designer/`（ブランチ `claude/FIX-atelier-extension-20261121`。拡張だけを置き場へ入れる形）で組んだ物を、
   `CharacterDesigner-Extension-Setup.exe` の名前で Release に足す。単体の物（`CharacterDesigner-Setup.exe`）と同じ名前にすると取り違えるため。
2. `get-extension.ps1` は `*Extension*Setup*.exe` を先に探し、無いデザイナーは選べる部品に出さない（Python ごとの物を代わりに入れない）。
3. `atelier/extension_catalog.py` の `installer` は、拡張だけの Setup が Release にあるときだけ True にする。

### 採用し合う物

AtelIer と 6 つのデザイナーは、互いの良い所・使える所（部品、画面、検品、手順、試験、配る仕組み）を採用し合い、同じ物を二度作らない。
共通に使える部品は AtelIer の側に置いてデザイナーが使い、デザイナーで出来た良い物は AtelIer に取り込む。開発の工数を減らすため。

いま同じ役目を別々に持っている物を、コードを読んで並べた（動かして比べてはいない。CharacterDesigner は `claude/FIX-atelier-extension-20261121`
と、Release の元の `chatdraw/`、FashionDesigner は `claude/FIX-atelier-extension-20261121`）。推奨はどれも私の推測で、コードはまだ変えていない。

| 役目 | AtelIer | CharacterDesigner | FashionDesigner | 推奨 |
|---|---|---|---|---|
| 絵の模型の置き場と一覧 | `atelier/models/`（`catalog.py`、`manager.py`、`ratings.py`、`civitai.py`） | `tools/gen/models.py`（リポジトリの `models/` に置く）、流用元の `chatdraw/manager.py` | 無い（`FD_IMAGE_API_URL` の外の窓口に頼む） | AtelIer を採る。評価と推奨の並びまである。デザイナーは `atelier.models` を呼び、`models/` を自分で持たない |
| 絵を描く窓口 | `atelier/ai/engine.py` | 拡張は `atelier.ai.engine` を呼ぶ。`tools/gen/` に開発用の描き方が別にある | `server.py` の `/api/generate`（OpenAI 互換の画像の窓口へ渡す） | AtelIer を採る。FashionDesigner の外の窓口へ渡す口は、AtelIer の engine の選べる描き手の 1 つとして取り込む |
| 言葉の模型 | `atelier/ai/engine.py`、`atelier/agent/voice.py`（`C:\LLM`） | `tools/gen/local_llm.py`（OpenAI 互換の窓口で Ollama・LM Studio・llama.cpp を同じに扱う） | 無い | 置き場は AtelIer の `C:\LLM` を採る。窓口を道具に頼らない形にする所は CharacterDesigner の `local_llm.py` の考え方を AtelIer に取り込む |
| 検品 | `atelier/qc/`（`hand_check.py`、`body_check.py`、`request_check.py`、`sanity.py` など） | 拡張は `atelier.qc` を呼ぶ。`tools/gen/qc.py`、`qcbench.py`、`facecheck.py`、`legcount.py` が開発用に別にある | 無い | AtelIer を採る。CharacterDesigner の `facecheck.py`・`legcount.py` のうち AtelIer に無い見方は `atelier/qc/` に取り込む |
| データの置き場と道 | `atelier/files/paths.py` | 拡張は `atelier.files.paths` を呼ぶ。流用元は `chatdraw/paths.py`、`tools/gen/cdhome.py` | リポジトリの `library/` | AtelIer を採る。デザイナーの作った物も AtelIer の置き場の下に置く |
| 設定の保存 | `QSettings("AtelIer", ...)`（`atelier/ai/references.py` など） | 拡張は AtelIer の物を使う | 画面の `localStorage`（`*.html`） | AtelIer の `QSettings` を採る。FashionDesigner の画面を AtelIer の窓に載せるとき、`localStorage` の値を AtelIer の設定へ移す |
| 作業ファイル | `atelier/files/project_file.py` | `character_designer/chara_file.py` が AtelIer の作業ファイルを使う | 無い | AtelIer を採る |
| インストーラー | `packaging/build.sh`・`installer.nsi`（Python ごと）、`get-extension.ps1`、`extension_sections.py` | `packaging/character_designer/`（拡張だけ）と、Release の元の `packaging/chatdraw/`（Python ごと） | 無い | 拡張だけの Setup は CharacterDesigner の `packaging/character_designer/` を見本として 6 つで同じ形にする。Python ごとの組み方は AtelIer の `packaging/` を採り、単体の Setup もそれを使う |
| 試験の台本 | `tests/`（unittest、`QT_QPA_PLATFORM=offscreen`）と `atelier/bench/`、Actions の `*-bench.yml` | `tests/atelier_helpers.py`（AtelIer の窓と描き手の代わり）、Actions に同じ名前の `*-bench.yml` | `tests/test_atelier_extension.py`（AtelIer の窓に付けて確かめる） | 拡張を AtelIer の窓に付けて確かめる下ごしらえは、CharacterDesigner の `atelier_helpers.py` を AtelIer の側に移して 6 つが使う。測る台と Actions は AtelIer の物を採り、デザイナーの側の同じ名前の物は消す |
| 子どもを描く頼みの止め | `atelier/words/child_safety.py` | 流用元の `chatdraw/childsafe.py` | 無い | AtelIer を採る（止めるのはこの 1 か所という決まりがあるため）。FashionDesigner の外の窓口へ渡す頼みも、ここを通す |
| 服の型紙の画面 | 無い | 無い | `image-to-pattern.html`、`studio.html` | FashionDesigner で出来た物として、AtelIer の窓に載せる（今の `FashionExtension` が `QWebEngineView` で開く形） |

### AtelIer の Setup.exe からデザイナーを入れる

コンポーネントのページに「<デザイナー> も入れる（ネットから取る）」が出る（既定で選ぶ。外せば入れない）。出すのは一覧で `installer` が True の物
（Release に Setup.exe がある物）だけで、`packaging/extension_sections.py` が組むたびに節を書き出す。
選ぶと、そのリポジトリの最新の Release から名前に `Setup` を含む `.exe` を取り、`/S` で静かに入れる
（`packaging/get-extension.ps1 -Repo <owner/name>`）。AtelIer を入れたあとに動くので、CharacterDesigner の Setup.exe は AtelIer を見つけられる。
Release に Setup.exe が無いとき・取れないときは知らせて先へ進む。

### データの引き継ぎ

インストーラーは引き継がない。AtelIer の初めての起動で CharacterDesigner の置き場（`%ProgramData%\CharacterDesigner`）が
見つかったときだけ「CharacterDesigner から引き継ぐ」窓を出し、利用者が選んだ組だけを写す（`atelier/app/migrate.py`）。

拡張だけの Setup が Release にある拡張は、AtelIer のインストーラーで既定で入れる（外すこともできる）。静かに入れるとき（/S）も既定どおり入れ、取れないときは理由を出して飛ばし、AtelIer の入れ方は止めない。
