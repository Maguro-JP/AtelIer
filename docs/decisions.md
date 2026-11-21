# 決めたこと

1 行 1 決定。古くなった決定は消さずに「置き換え済み」と印を付け、新しい行を足す。日付は JST。

| 日付 | 決めたこと | 理由 | 触る場所 | 選ばなかった案 |
|---|---|---|---|---|
| 2026-11-21 | Python + PySide6 のデスクトップアプリにする | 流用元（CharacterDesigner の chatdraw）が PySide6 で、作画の部品をそのまま使える | `pyproject.toml`、`atelier/` 全体 | Web（Next.js）で作り直す。作画の部品を書き直すことになる |
| 2026-11-21 | パッケージ名は `atelier`、層は `ui` / `files` → `paint` → `panels` → `app` | 作画の中核を窓や AI から切り離し、AI が無くても描けることを保つ | `atelier/`、`tests/test_identity.py`（層の向きの試験） | 流用元と同じく 1 つのディレクトリに平らに並べる。120 ファイルが並び、役目が読めなかった |
| 2026-11-21 | （置き換え済み）流用元の `app.py`（約 7,800 行）は持ってこず、窓を新しく組む | 窓が AI・モデル・キャラクターデザインと絡んでいて、作画だけを切り出せない | `atelier/app/main_window.py` | 丸ごと持ってきて削る。削り残しが構成を崩す |
| 2026-11-21 | （置き換え済み）今回持ってくるのは作画の中核（キャンバス・ブラシ・描く補助・色とレイヤーの欄・テーマ・作業ファイル）だけ | まず AI 無しで動く土台を作り、試験で守る。AI の部品は依存が深く、段階に分ける | `docs/STRUCTURE.md` の対応表と「これから持ってくる物」 | 描くモデルまで一度に持ってくる。約 40 ファイルが芋づるで付いてくる |
| 2026-11-21 | （置き換え済み）赤ペンと自動選択は、コードは残すが道具の帯には出さない | どちらも AI が要る。直す先が無い印だけを付けられる状態を作らない | `atelier/app/tools.py` の `TOOLS` | 帯に出して「まだ使えません」と知らせる |
| 2026-11-21 | 作業ファイルの拡張子は `.atelier`。流用元の `.cdproj` は読めるが、上書き保存はしない | 中身の形が同じなので読める。別のアプリのファイルを書き換えない | `atelier/files/project_file.py` の `SUFFIX`、`LEGACY_SUFFIXES` | `.cdproj` のまま使う。どちらのアプリのファイルか分からなくなる |
| 2026-11-21 | アプリのデータの置き場は環境変数 `ATELIER_HOME` > Windows の ProgramData\AtelIer > 開発中の `.cache` | 流用元と置き場を分け、互いの設定を壊さない | `atelier/files/paths.py` | 流用元と同じ置き場を使う |
| 2026-11-21 | 設定（欄の配置・テーマ）は QSettings の `AtelIer` / `atelier` に持つ | 流用元の設定と混ざらない | `atelier/app/main_window.py` の `ORGANIZATION`、`APPLICATION` | - |
| 2026-11-21 | ロゴは文字の「AtelIer」。A と I を差し色、ほかの字は地の色。差し色はテーマの差し色 1（初めはオレンジ） | AI を大文字と色で強調する指定。テーマを替えても読めるよう、色はテーマから取る | `atelier/ui/logo.py`、`atelier/assets/logo.svg`、`atelier/assets/icon.svg` | 画像のロゴだけにする。テーマの色に合わせられない |
| 2026-11-21 | （置き換え済み）保存と読み込みは画面の糸でそのまま行う（裏の糸を使わない） | 仕組みを小さく保つ。流用元は裏の糸で書いていた | `atelier/app/file_commands.py` | 流用元の `run_io`（裏の糸の列）を持ってくる。レイヤーが多い絵で保存が重くなったら入れる |
| 2026-11-21 | （置き換え済み）知らせは下の帯、失敗だけ窓で出す | 流用元の知らせの札（notice.py）は動きの部品が要る。まず小さく | `atelier/app/main_window.py` の `notify`、`notify_error` | 知らせの札を持ってくる |
| 2026-11-21 | （置き換え済み）道具の帯は 2 列 | 1 列だと窓の高さ 900 で下の道具がはみ出して押せなかった（画面を撮って確かめた） | `atelier/app/main_window.py` の `TOOL_COLUMNS` | アイコンを小さくする |
| 2026-11-21 | （置き換え済み）CI（GitHub Actions）は置かない | 非公開のリポジトリで実行時間の枠を使う。試験は手元で 10 秒ほどで終わる | 置くなら `.github/workflows/` | pull_request で試験を流す。配る物を作る段になったら見直す |
| 2026-11-21 | 試験は unittest（追加の依存なし）。窓を開いてマウスで操作する形を流用元から引き継ぐ | 流用元の試験をそのまま生かせる | `tests/` | pytest に替える |
| 2026-11-21 | キャラクターデザイン以外は全部 AtelIer に置く。CharacterDesigner はキャラクターデザインだけを持つ（利用者の指示） | 道具の開発と、キャラクターデザインの開発を分ける | `docs/STRUCTURE.md` の対応表 | 作画の中核だけを持ってくる（上の置き換え済みの行） |
| 2026-11-21 | 流用元の窓をそのまま持ってきて、あとで役目ごとに分ける。先に組んだ小さい窓は捨てる | ほぼ流用してよいとの指示。小さい窓は別の目の検証で不具合が 7 件出た | `atelier/app/main_window.py` | 小さい窓を育てる |
| 2026-11-21 | 言語と枠組みは Python + PySide6 のまま（替えてよいと言われたうえで） | AI の部品が Python 前提。約 4 万行と試験 85 ファイルが動いている。直すべきは構造で、言語ではない | `pyproject.toml` | Web（TypeScript）や Rust + Tauri で書き直す。試験ごと失い、AI の部品との橋渡しが要る |
| 2026-11-21 | 2 つのリポジトリの連携は「AtelIer が本体、CharacterDesigner が拡張」。AtelIer に拡張の登録口を置き、CharacterDesigner はそこにメニュー・モード・ファイルの種類を足す | 道具の側がキャラクターデザインを知らずに済む。逆向きの依存を作らない | `atelier/extensions.py`（これから） | CharacterDesigner が AtelIer の窓を継承する。窓の中身に強く結び付く |
| 2026-11-21 | 設定とデータの置き場は CharacterDesigner と分け、古い設定は勝手に移さない。モデルの置き場（C:\LLM）は共有のまま | 互いの設定を壊さない。モデルは数 GB あり、2 つ持たない | `atelier/files/paths.py` | CharacterDesigner の設定を起動時に写す |
| 2026-11-21 | 移動の確かめは、流用元と移行後の試験をファイルごとに流して結果を比べる。モデルの部品（torch など）は入れずに流す | 入れると試験が本物のモデルを取りに行き、時間と通信を使いすぎた | 手元の手順（`.worklog/`） | モデルを入れて流す |
| 2026-11-21 | 公開になったので、試験を流す CI を pull_request にだけ置く（Linux、試験が安定してから） | 公開リポジトリは標準ランナーが無料。手元だけだと他の環境での退行に気付けない | `.github/workflows/`（これから） | 置かない（非公開のときの決定。上の置き換え済みの行） |
| 2026-11-21 | 検品の精度を測るテスト（test_qcbench）と台本（tools/gen/qcbench.py）は持ってこない | CharacterDesigner の絵の資料（library/）を正解として読むため、資料のある側に置く | 持ってくるなら資料ごと `tests/fixtures/` へ | 資料を全部写す（数百 MB） |
| 2026-11-21 | テストが読む見本の絵は `tests/fixtures/` に置く | 流用元は絵の資料の置き場（library/）を直に読んでいた。AtelIer に資料の置き場は作らない | `tests/fixtures/` | library/ を同じ形で持つ |
| 2026-11-21 | 拡張は `name` と `attach(window)` を持つ物。窓のメソッドは拡張が窓の物に結び付け、窓のクラスには足さない | 外した拡張のメソッドがクラスに残らない。前からの呼び方（`w.chara_design` など）はそのまま使える | `atelier/extensions.py`、`atelier/chara/extension.py`、`atelier/chara/window_part.py` | 窓のクラスに mixin で足す。本体が拡張を読むことになる |
| 2026-11-21 | 同梱の拡張は `atelier/extensions.py` の `BUNDLED` に文字で 1 行だけ持ち、`ATELIER_NO_BUNDLED_EXTENSIONS=1` で読まない | 切り離すまでの間も、前と同じ画面で起動する。本体だけで動くことをテストで確かめられる | `atelier/extensions.py`、`tests/test_extensions.py` | 起動の関数で直に import する。テストの窓に付かず、本体が拡張を読む行が増える |
| 2026-11-21 | 一時停止の記録の読み込み（pickle）は検査の例外にする | 読むのはアプリが自分のデータの置き場に書いたファイルだけで、中身がモデルの途中の状態（テンソル）なので JSON にできない | `atelier/files/pause_keep.py` の `state` | safetensors に書き直す（状態の形を全部決め直すことになる） |
| 2026-11-21 | コミットメッセージに ID・URL・メールを入れない | 出す前の検査（precheck）が止める。公開のリポジトリの履歴に残さない | コミットの書き方 | - |
| 2026-11-21 | Release は流用元と同じ形で出す。main に入ると Actions が Setup.exe を組み、`v<VERSION>` の Release に置く。作業ブランチでは artifact に置く | 流用元で動いていた出し方を引き継ぐ。組むのは Actions で行い、手元で組まない | `.github/workflows/atelier-setup.yml`、`packaging/`、`VERSION` | 手でタグと Release を作る |
| 2026-11-21 | 版は 0.1.0 から数え直す。更新の確かめ先は AtelIer の Release にする | 流用元の版（0.5.38）と確かめ先のままだと、AtelIer が CharacterDesigner の Setup.exe を入れてしまう | `VERSION`、`atelier/app/updater.py` の `REPO` | 流用元の版を引き継ぐ |
