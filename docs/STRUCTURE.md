# 構成

## 3 つの柱と置き場

| 柱 | 意味 | 置き場 |
|---|---|---|
| 人が使う | 人がペンやマウスで描く | `atelier/paint`、`atelier/panels`、`atelier/ui`、`atelier/app` |
| AI を使う | 絵のモデルで描く・直す・選ぶ | `atelier/ai`、`atelier/models`、`atelier/words`、`atelier/qc` |
| AI が使う | AI がこのソフトを道具として操作する | `atelier/agent`。入口は `Canvas.draw_stroke`（人の筆と同じ経路で描く）と `atelier/agent/commands.py`（言葉での操作） |

## ディレクトリ

| 場所 | 役割 |
|---|---|
| `atelier/app/` | 窓と起動。設定、キーの割り当て、モード、更新、落ちたときの記録 |
| `atelier/app/window/` | 窓（`main_window.py` の `Window`）を役目ごとに分けた mixin と部品。ファイルの開閉と保存（`files.py`）、AI の描画（`ai_drawing.py`）と結果（`ai_results.py`）、チャット（`chat.py`）、描く言葉（`prompts.py`）、赤ペン（`redpen.py`）、キャンバスの右クリック（`canvas_menu.py`）、レイヤーと選択（`layers_and_selection.py`）、画像の加工（`image_editing.py`）、模型（`models.py`）、履歴（`history.py`）、モードとロゴ（`modes_and_logos.py`）、設定とデバッグ（`settings_and_debug.py`）、結果の置き方と進み（`results_and_progress.py`）、欄と帯の配置（`layout.py`）、ツアー（`tour.py`）。補助は `jobs.py`、`widgets.py`、`image_convert.py`、`process_check.py`、`constants.py`。`main_window.py` には起動の準備、`Window.__init__`、`main` が残り、前の名前を再輸出する |
| `atelier/paint/` | 作画の中核。キャンバス、ブラシ、描く補助、赤ペンの印、タイムラプス |
| `atelier/panels/` | 欄。カラー、ブラシの見本、レイヤー、AI、チャット、ライブラリー、進みと履歴 |
| `atelier/ui/` | 見た目と操作の土台。テーマ、アイコン、ロゴ、言語、欄の配置、メニューの編集、知らせ、ツアー、ヘルプ |
| `atelier/files/` | 置き場とファイル。作業ファイル、ごみ箱、ライブラリー、取得、一時停止の記録 |
| `atelier/ai/` | AI を使う。絵のモデルで描く・直す・加工する・拡大する・画風を替える・自動選択 |
| `atelier/models/` | モデルの一覧と管理。目録、初回の取得、お気に入り、評価 |
| `atelier/words/` | 頼みの言葉。日本語の語の表、単語辞書、学び |
| `atelier/qc/` | 検品。手・体・左右・頼んだ物・数字の検品 |
| `atelier/agent/` | AI が使う。チャット、言葉での操作、予約、音声 |
| `atelier/bench/` | モデルを動かして確かめる台本（Actions から流す） |
| `atelier/extensions.py` | 拡張の登録口。外の部品が、窓にメニュー・モード・欄・ファイルの種類を足す入口 |
| `atelier/assets/` | ロゴとアイコン（SVG） |
| `tools/gen/`、`tools/engine/` | アプリが読む道具の台本（仕上げ、検品の測り方、3D）。置き場を `sys.path` に足して読む |
| `styles/`、`casts/`、`config/` | 道具が読む基準と設定 |
| `packaging/` | Windows の Setup.exe の組み方（CharacterDesigner のまま。AtelIer 用にはまだ直していない） |
| `tests/` | テスト。見本の絵は `tests/fixtures/` |
| `scripts/run_tests.py` | テストをファイルごとに別の処理で流す |
| `scripts/unmerged_fixes.py`、`scripts/validate.sh` | 作業ブランチで直した不具合のうち main に無い物を注意に出す（precheck と Actions の unmerged-fixes が呼ぶ） |
| `docs/` | 決めたこと（knowledge/decisions.md）、この地図、モデルの一覧（models.md）、画像 |

## CharacterDesigner との分け方

- AtelIer は道具の本体で、キャラクターデザインを知らない形にする
- CharacterDesigner はキャラクターデザイン（設定資料、三面図、表情差分、キャラクターファイル）だけを持ち、AtelIer の上に載る
- 本体はキャラクターデザインのパッケージを読まない。読んでいないことは `tests/test_extensions.py` が見張る
- キャラクターデザインは CharacterDesigner のリポジトリの `character_designer` パッケージにあり、拡張として窓に付く。CharacterDesigner の `pyproject.toml` が entry points の `atelier.extensions` の組に `character_designer.extension:EXTENSION` を書き、起動のときに `atelier/extensions.py` の `load_entry_points` が読む
- 同梱の拡張（`BUNDLED`）はいまは無い。CharacterDesigner を入れていなければ、本体だけの形で起動する
- キャラクターデザインの資料（`bible/`、`designs/`、`templates/`）とキャラクターデザインのテストも CharacterDesigner にある

### 拡張が使う窓の口

| 口 | 何を足すか |
|---|---|
| `menuBar()`、`logo_menu` など | メニュー。`insertMenu` で位置を決める |
| `file_menu`、`file_extension_anchor` | ファイルのメニューの項目。保存と書き出しの間の区切り（anchor）の前に足す |
| `add_mode(key)` と `modes.register(key, spec, after=)` | モード。`modes.MODES` の順に「表示」の「モード」へ入る |
| `studio_hooks` | 描く仕組み（Studio）を作り直すたびに呼ぶ関数 |
| `expression_sources` | 表情差分の絵を返す関数（ロゴ・スタンプの「表情差分をまとめてスタンプにする」が使う） |
| `library_panel.tabs`、`library_panel.refresh_hooks` | ライブラリーの欄のタブと、並べ直しのときに呼ぶ関数 |

拡張を付けるのは `Window.__init__` の、メニューと欄を作り終えたあとで、メニューの言葉の引き換え・欄の並びを戻す・キーの割り当て・メニューの編集より前。

## まだ直していない所

- `tools/gen/` は置き場に頼って読む平らな台本のまま。キャラクターデザイン専用の台本（bible、charsheet、design など）も、ほかの台本と服飾の資料が読むので残している
- `characters/`（ドット絵のキャラクターの部品）は `tools/build.py`・`tools/body.py`・`tools/faces.py` と `tests/test_build.py` が読むので残している
- `atelier/app/migrate.py` は CharacterDesigner からの引き継ぎと、前の版が写した物の片付けの中身。窓は `atelier/app/migrate_dialog.py`
- モデルの部品（torch、diffusers）を入れた環境では、テストを流していない（`tests/needs_models.txt`）

## CharacterDesigner からの対応表

流用元は `Maguro-JP/CharacterDesigner` の `chatdraw/`（2026-11-21 時点の main、コミット 4a9e809）。
中身は、import の先と、製品名・設定の置き場・環境変数（`CD_*` を `ATELIER_*` に）を替えただけで移している。

| 流用元（chatdraw/） | AtelIer（atelier/） |
|---|---|
| `app.py` | `app/main_window.py`（起動と `Window.__init__`）と `app/window/`（役目ごとの mixin と部品） |
| `settings.py` | `app/settings.py` |
| `keys.py` | `app/key_bindings.py` |
| `modes.py` | `app/modes.py` |
| `crashlog.py` | `app/crash_log.py` |
| `debuglog.py` | `app/debug_log.py` |
| `updater.py` | `app/updater.py` |
| `migrate.py` | `app/migrate.py` |
| `canvas.py` | `paint/canvas.py` |
| `brush.py` | `paint/brush.py` |
| `assist.py` | `paint/drawing_assist.py` |
| `redpen.py` | `paint/redpen.py` |
| `timelapse.py` | `paint/timelapse.py` |
| `colorpanel.py` | `panels/color_panel.py` |
| `layerpanel.py` | `panels/layer_panel.py` |
| `brushpreview.py` | `panels/brush_preview.py` |
| `activity.py` | `panels/activity_panel.py` |
| `aipanel.py` | `panels/ai_panel.py` |
| `chatpanel.py` | `panels/chat_panel.py` |
| `librarypanel.py` | `panels/library_panel.py` |
| `wordpanel.py` | `panels/word_panel.py` |
| `favpanel.py` | `panels/favorite_models_panel.py` |
| `civitaipanel.py` | `panels/civitai_panel.py` |
| `presetdialog.py` | `panels/preset_dialog.py` |
| `userstats.py` | `panels/user_stats.py` |
| `loradialog.py` | `panels/lora_dialog.py` |
| `themes.py` | `ui/themes.py` |
| `themeedit.py` | `ui/theme_editor.py` |
| `icons.py` | `ui/icons.py` |
| `i18n.py` | `ui/i18n.py` |
| `fit.py` | `ui/window_fit.py` |
| `wheelguard.py` | `ui/wheel_guard.py` |
| `typeguard.py` | `ui/type_guard.py` |
| `flowlayout.py` | `ui/flow_layout.py` |
| `popup.py` | `ui/popup.py` |
| `motion.py` | `ui/motion.py` |
| `notice.py` | `ui/notice.py` |
| `ribbon.py` | `ui/ribbon.py` |
| `backdrop.py` | `ui/backdrop.py` |
| `look.py` | `ui/look.py` |
| `menuedit.py` | `ui/menu_editor.py` |
| `tabdock.py` | `ui/tab_dock.py` |
| `layouts.py` | `ui/layouts.py` |
| `confirm.py` | `ui/confirm.py` |
| `tour.py` | `ui/tour.py` |
| `tours.py` | `ui/tours.py` |
| `helpview.py` | `ui/help_view.py` |
| `share.py` | `ui/share.py` |
| `paths.py` | `files/paths.py` |
| `project.py` | `files/project_file.py` |
| `workkeep.py` | `files/work_keep.py` |
| `trash.py` | `files/trash.py` |
| `folders.py` | `files/folders.py` |
| `library.py` | `files/library.py` |
| `fetchfile.py` | `files/fetch_file.py` |
| `sent.py` | `files/sent.py` |
| `pausekeep.py` | `files/pause_keep.py` |
| `redpenclean.py` | `files/redpen_clean.py` |
| `engine.py` | `ai/engine.py` |
| `membudget.py` | `ai/memory_budget.py` |
| `twostage.py` | `ai/two_stage.py` |
| `phases.py` | `ai/phases.py` |
| `phasetools.py` | `ai/phase_tools.py` |
| `omakase.py` | `ai/omakase.py` |
| `choose.py` | `ai/choose.py` |
| `composition.py` | `ai/composition.py` |
| `director.py` | `ai/director.py` |
| `variety.py` | `ai/variety.py` |
| `lora.py` | `ai/lora.py` |
| `refs.py` | `ai/references.py` |
| `restyle.py` | `ai/restyle.py` |
| `upscale.py` | `ai/upscale.py` |
| `postfx.py` | `ai/post_effects.py` |
| `seamfix.py` | `ai/seam_fix.py` |
| `finishers.py` | `ai/finishers.py` |
| `edittools.py` | `ai/edit_tools.py` |
| `autosel.py` | `ai/auto_select.py` |
| `facefeat.py` | `ai/face_features.py` |
| `fixmenu.py` | `ai/fix_menu.py` |
| `fixrequests.py` | `ai/fix_requests.py` |
| `shortcuts.py` | `ai/shortcuts.py` |
| `ownstyle.py` | `ai/own_style.py` |
| `to3d.py` | `ai/to_3d.py` |
| `logo.py` | `ai/logo_maker.py` |
| `batch.py` | `ai/batch.py` |
| `models.py` | `models/catalog.py` |
| `setup.py` | `models/first_setup.py` |
| `manager.py` | `models/manager.py` |
| `hfadd.py` | `models/hugging_face_add.py` |
| `civitai.py` | `models/civitai.py` |
| `favmodels.py` | `models/favorites.py` |
| `ratings.py` | `models/ratings.py` |
| `popular.py` | `models/popular.py` |
| `modeldoc.py` | `models/model_doc.py` |
| `jaterms.py` | `words/japanese_terms.py` |
| `worddict.py` | `words/dictionary.py` |
| `wordlearn.py` | `words/learning.py` |
| `chatwords.py` | `words/chat_words.py` |
| `childsafe.py` | `words/child_safety.py` |
| `body.py` | `words/body_words.py` |
| `handcheck.py` | `qc/hand_check.py` |
| `bodycheck.py` | `qc/body_check.py` |
| `mirrorcheck.py` | `qc/mirror_check.py` |
| `origqc.py` | `qc/original_qc.py` |
| `sanity.py` | `qc/sanity.py` |
| `requestcheck.py` | `qc/request_check.py` |
| `qcmanual.py` | `qc/manual_check.py` |
| `qcparts.py` | `qc/parts.py` |
| `assistant.py` | `agent/assistant.py` |
| `chatplan.py` | `agent/chat_plan.py` |
| `commands.py` | `agent/commands.py` |
| `scheduler.py` | `agent/scheduler.py` |
| `intent.py` | `agent/intent.py` |
| `voice.py` | `agent/voice.py` |
| `adherebench.py` | `bench/adherence_bench.py` |
| `autoselbench.py` | `bench/auto_select_bench.py` |
| `bench_finish.py` | `bench/finish_bench.py` |
| `perfbench.py` | `bench/performance_bench.py` |
| `phasebench.py` | `bench/phase_bench.py` |
| `verify_models.py` | `bench/verify_models.py` |
| `fix_verify.py` | `bench/fix_verify.py` |
| `restyle_verify.py` | `bench/restyle_verify.py` |
| `e2e.py` | `bench/end_to_end.py` |
| `windraw.py` | `bench/windows_draw.py` |
| `draw_one.py` | `bench/draw_one.py` |
| `charadesign.py`、`charafile.py`、`app.py` のキャラクターデザインの操作、`batch.py` の `chara_jobs` と `run_charas`、`logo.py` の `expressions`、`library_panel.py` のキャラクターのタブ、`modes.py` の designer | AtelIer には無い。CharacterDesigner の `character_designer/`（`chara_design.py`、`chara_file.py`、`window_part.py`、`chara_batch.py`、`extension.py`） |
| `catalog.json` | `models/catalog.json` |
| `fixrequests.json` | `ai/fixrequests.json` |
| `help` | `ui/help` |
| `icon` | `ai/icon` |
| `styleprev` | `app/styleprev` |
| `tests/` | `tests/`（ファイル名は同じ） |
