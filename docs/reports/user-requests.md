# 利用者の依頼の一覧（CharacterDesigner のアプリ）

依頼を受けたら、まずこの表に 1 行足し、直したら状態を書き換える。会話の記録は要約で落ちるので、指示はここで管理する。

2026-11-14 に、origin/main（9af2c00e、0.5.28）のコードと試験に照らして全部の行を見直した。
集めた所: `git log --all` の全コミットのメッセージ（マージした PR の題と本文を含む）、CLAUDE.md の「ユーザーの決めたこと」、docs/knowledge/decisions.md、docs/reports/requests-20261113.md、docs/reports/deliverables.md、CHANGELOG.md、.claude/skills/lessons/LESSONS.md、origin の各ブランチにある前の版のこの表。

状態の意味:

- 済み: origin/main のコードと試験に根拠がある（ファイル:行と試験のファイルを書く）
- 一部: コードの一部だけがある、または試験が無い・実機で確かめていない
- 消えた: 前の版にあったのに今の main に無い（消えた版を書く）
- 未着手: コードに根拠が無い
- 作業中: 未マージのブランチがある（ブランチ名。origin に無い手元だけのブランチは「手元のみ」と書く）

見方の限り: 根拠はファイルと語の検索で確かめた。試験は流していない。Windows の実機と GPU では何も確かめていない。

## 数

2026-11-22 に、消えた 29 行と一部の一部を AtelIer の窓（offscreen、小さな模型）で押して見直した。消えた 29 行のうち 11 行は窓で動いた（済み）、1 行は戻した（A14）、1 行は CharacterDesigner の分、残りは一部（描く・直すを最後まで流すと共有の機械のメモリ不足で落ち、見ていない所がある）。前の数は 済み 35・一部 81・消えた 29・未着手 15。

| 状態 | 数 |
|---|---|
| 済み | 48 |
| 一部 | 96 |
| 消えた | 0 |
| CharacterDesigner の分 | 1 |
| 未着手 | 15 |
| 作業中 | 0（未マージのブランチは、消えた・未着手・一部の行の根拠の欄に書いた。消えた 29 件のうち、origin のブランチで戻す物は 6 件、手元だけのブランチの物は 12 件） |
| 合計 | 160 |

消えた 29 件のうち 23 件は 0.5.23（#409、fca48949）で消えた。0.5.23 は描けなくなった不具合を直すために chatdraw を 0.5.18 に戻し、0.5.19〜0.5.22 で入れた機能のファイル 46 本（autosel.py、lora.py、charafile.py、modes.py、director.py、typeguard.py、batch.py、debuglog.py、persist.py、refs.py、seamfix.py など）と試験をまとめて外した。11-07〜11-08 の依頼（C・B・A の行）のほとんどは、このとき消えた。
戻す作業は origin/claude/FIX-backui-20261114 と、それを取り込んだ origin/claude/FIX-rel529-20261114（0.5.29、未マージ）にある。LoRA・モード・担当編集者・加工の直し・自動選択・チャットと描くワードの分け方を戻すコミットは、手元のブランチ claude/FIX-backchara-20261114 と claude/FIX-backredpen-20261114 にだけあり、origin に push されていない。

なぜ完成しないか（記録から分かること）: 0.5.19〜0.5.22 で一度に多くを足して描けなくなり、0.5.23 で全部を外した。外すときにこの表と照らさなかったので、済んだ依頼が黙って消えた。0.5.24〜0.5.28 は 11-13 の順番の 1〜11 を進めたが、消えた物を戻す作業は未マージのまま残っている。

## 作業の順番（消えた・未着手の物）

壊れていて使えない物を先、頼まれた回数の多い物を先に並べた。回数は、この表・前の版の表・コミットに出た回数（私の数え方）。

| 順 | # | 依頼 | 状態 | 回数 | 理由 |
|---|---|---|---|---|---|
| 1 | A11 | 文字入力中にショートカットに取られない（アプリ全体） | 消えた（0.5.23） | 3 | 急ぎ。打った文字が消える。rel529 にある |
| 2 | N2 | 描くボタンで落ちない（閉じた窓の裏の糸） | 消えた（0.5.23） | 2 | 落ちる。rel529 にある |
| 3 | A12 | 落とさない。メモリの使い方を選ばせる | 消えた（0.5.23） | 3 | 落ちる。rel529 にある |
| 4 | 36 | 進捗のポップアップが出なくなる | 未着手 | 1 | 進みが見えない |
| 5 | 9 | フリーズする言葉がある | 未着手 | 1 | 固まる |
| 6 | 29 | 追加ダウンロードが要る模型が動かない | 未着手 | 1 | 使えない。origin/claude/FIX-partsmodels-20261114 が検品の部品を初回に取る |
| 7 | A1 | 枚数と種をまとめない | 消えた（0.5.23） | 4 | 72・A1・0.5.18・0.5.21 で 4 回。rel529 にある |
| 8 | B5 | マウスの戻る・進む | 消えた（0.5.23） | 2 | rel529 にある |
| 9 | B3 | ライブラリーの右クリックから「一覧から外す」を除く | 消えた（0.5.23） | 1 | 1 行の直し |
| 10 | C1 | AI の自動選択（選択と赤ペン） | 消えた（0.5.23） | 3 | 手元の backredpen のみ |
| 11 | C4 | チャットと描くワードを分ける | 消えた（0.5.23） | 3 | CLAUDE.md の決まりにもある。手元の backredpen のみ |
| 12 | A2〜A5 | ディテール追加・画風を加工のメニューに・拡大の文言・奇麗にする | 消えた（0.5.23） | 2 | 手元の backchara のみ |
| 13 | A13 | LoRA（Civitai・Hugging Face）とキャラクターシート・学習セット | 消えた（0.5.23） | 2 | 手元の backchara のみ |
| 14 | N1 | デバッグモード | 消えた（0.5.23） | 1 | 描けない理由を見るのに要る。rel529 にある |
| 15 | N3 | 模型に本当に渡した言葉をツールチップに出す | 消えた（0.5.23） | 1 | 頼んだ通りに描かない原因を見るのに要る。rel529 にある |
| 16 | A14 | 工程ごとの秒・並べて比べる（Ctrl+Shift+K）・操作を探す（Ctrl+K） | 消えた（0.5.23） | 1 | |
| 17 | B4 | 技能（加工・仕上げ・組み合わせ）が全部効く | 消えた（0.5.23） | 2 | 359 件押した試験（test_function_check）ごと消えた |
| 18 | A7 | プリセットを精査する | 消えた（0.5.23） | 2 | 手元の backchara のみ |
| 19 | C2 | 自動選択の印にも境目の確かめ、加工のあと全体を確かめる | 消えた（0.5.23） | 2 | 手元の backredpen のみ |
| 20 | K5 | 赤ペンの指示の欄の確定のボタン、印の右クリックから囲みの中だけ加工 | 消えた（0.5.23） | 2 | 手元の backredpen のみ |
| 21 | 88 | 参考画像を探させる、参考先を保存 | 消えた（0.5.23、refs.py） | 2 | |
| 22 | K3 | キャラデザモード（設定資料集・三面図・表情差分がそろうまで場面の絵を描かない） | 消えた（0.5.23、charafile.py・modes.py） | 2 | 手元の backchara のみ |
| 23 | 86 | チャットで繰り返し・予定の依頼、アップロードの自動化 | 未着手 | 1 | |
| 24 | 87 | ワードではなく文で依頼・修正・加工 | 未着手 | 2 | 11-14 の fixprompt が直しの訳を作る |
| 25 | 2・13 | 描けるまで描き直す・何回も回す | 消えた（0.5.25） | 4 | 11-13 の順 5（繋げて無限ループにしない）で外した。CLAUDE.md の「工程の数や回数に上限を決めない」と食い違うので、どちらにするか利用者に聞く |
| 26 | 33 | 好みの絵を学習した模型のように使う | 未着手 | 1 | いずれ |
| 27 | 93 | アプリ版とウェブサービス版の準備 | 未着手 | 1 | 後で |

残りの未着手（65・92・K-行の 3 件など）は表の中に書いた。

## 2026-11-14 の決まり（未マージのブランチ）

| # | 依頼 | 状態 | 根拠 |
|---|---|---|---|
| D1 | 基本は性能向上（確認・精査・改善）。機能の追加は指示があったときだけ | 未着手 | origin/claude/FIX-rule-20261114（CLAUDE.md の 1 行。未マージ） |
| D2 | 絵は工程（構図・線画・塗り・仕上げ）に分けて描き、工程ごとに検品して 1 回だけ直す | 未着手 | origin/claude/FIX-flow-20261114（決まり）、origin/claude/FIX-phases-20261114（比べの台）。main のコードに工程分けは無い |
| D3 | 直しの指示（赤ペン・加工）を模型に確実に届ける。訳せない語は黙って描かずに出す | 一部 | main: engine.py の untranslated の知らせ（「模型に伝わらない言葉があります」）。直しの訳は origin/claude/FIX-fixprompt-20261114 |
| D4 | 依頼を受けたらこの表に 1 行足し、直す前に消える機能が無いか照らす | 未着手 | origin/claude/FIX-flow-20261114。0.5.23 はこれをしなかった |
| D5 | 修正依頼の一覧と、模型を使わない整える・揃える・消す | 未着手 | origin/claude/FIX-fixrequests-20261114 |
| D6 | 画風の加工が本物の模型で変わらなかった 7 つを直し、画風を足す | 未着手 | origin/claude/FIX-restyle-20261114 |

## 2026-11-13 の依頼と順番（requests-20261113.md）

| # | 依頼 | 状態 | 根拠 |
|---|---|---|---|
| R1 | 頼みを正確に伝える（勝手に変えない・消さない・足さない） | 一部 | atelier/ai/engine.py:1455（vary_background は頼みをそのまま返す、0.5.24）。試験: tests/test_variety.py。adhere-bench（atelier/bench/adherence_bench.py）で前の版と比べた数字は記録に無い。origin/claude/FIX-noextra-20261114 が 2 段の構図の足し言葉を外す（未マージ） |
| R2 | 直しをまともに（赤ペン修正のバグ、赤ペンのレイヤーを履歴に載せない） | 一部 | atelier/panels/layer_panel.py:124-235（印ごとの行、消す・全部消す）、atelier/paint/redpen.py:98（元に戻す）。試験: test_redpenfix.py、test_redpeninput.py。履歴に載せない・消したら何も残さない（0.5.22）は 0.5.23 で消え、手元の backredpen のみ |
| R3 | 加工をまともに | 一部 | atelier/ai/finishers.py。試験: test_finish_quality.py、test_nobreak.py。0.5.22 の直し（A2〜A5）は消えた |
| R4 | 「描けませんでした」と出さない | 一部 | engine.py:105（メモリ不足で 1 回だけ設定を下げてやり直す）。0.5.22 の段を下げて描き続ける形は消えた |
| R5 | 検品と直しを個別に動かす（繋げて無限ループにしない） | 済み | atelier/ai/engine.py:1793（REDRAW_TRIES = 1）、engine.py:1583-1585 の注。0.5.25。試験: test_qcmanual.py |
| R6 | 検品単体の精度を上げる | 一部 | tests/test_qcbench.py、0.5.28（人の判定 103 枚で取りこぼし無しの割合 93.2% → 95.1%）。origin/claude/FIX-qcaccuracy2-20261114 が台を直す（未マージ） |
| R7 | 検品の手動実施（右クリック、人が描いた絵にも、結果を赤ペンで） | 済み | atelier/qc/manual_check.py、0.5.25。試験: tests/test_qcmanual.py |
| R8 | 赤ペンで指示が無いときは範囲を検品して直す | 済み | atelier/app/main_window.py:2284。試験: test_qcmanual.py |
| R9 | 正確な図形のアシスタント、AI 補正、線対称・点対称 | 済み | atelier/paint/canvas.py:28（対称）、commands.py:111（正多角形）、0.5.26・0.5.27。試験: test_layertools.py、test_shapeassist.py、test_brushtools.py。「AI 補正」は形を整える補正（模型は使わない） |
| R10 | レイヤーのコピー・切り取りなど | 済み | atelier/paint/canvas.py:441（copy_layer）、0.5.26。試験: test_layertools.py |
| R11 | 芸術の知識を調べてアルゴリズムに（迫力なら遠近法など） | 一部 | atelier/ai/composition.py、engine.py:1546。試験: test_composition.py。構図の言葉を足すだけで、ほかの知識は無い |
| R12 | 急ぎ、加工と直しが出来る版を Release | 一部 | 0.5.24〜0.5.28 を CHANGELOG.md に書いた。Release が出たかは GitHub で見ていない |

## CLAUDE.md「ユーザーの決めたこと」のうち、アプリの機能になる物

作業の進め方の決まり（PR の前に聞く、散らかさない、日本時間で書く など）はコードでは測れないので、この表には入れていない。フックがあるもの（pr_gate.py、reread_check.py、precheck.py、docs_check.py、measure_hooks.py）は .claude/skills/ の下にある。

| # | 依頼 | 状態 | 根拠 |
|---|---|---|---|
| K1 | AI の欄の「指示」のタブを、模型・描くワード・登録・禁止ワード・登録の順に詰めて並べ、登録のボタンは折り返す | 済み | 2026-11-22 窓で見た。指示のタブの見出しは上から 絵の模型・描くワード（登録の札が折り返して並ぶ）・禁止ワードの順（/tmp/claude-0/-home-user/e19cd56b-00c0-5c61-a043-c8cddeecb792/scratchpad/use/req/C1-autosel.png、A1-aipanel.png） |
| K2 | 赤ペンの印をレイヤーの欄に「赤ペン」として出し、隠す・全部消す・1 つずつ消す・元に戻す・やり直す | 一部 | 2026-11-22 窓で、赤ペンの行がレイヤーの欄に「赤ペン 1: 笑顔に」と出て、全部消すで行が消えた。隠す・1 つずつ消す・元に戻す・やり直すは押していない |
| K3 | キャラデザモードで設計し、そろうまで場面の絵を描かない | CharacterDesigner の分 | キャラデザモード（設定資料集・三面図・表情差分）はキャラクターデザインの機能なので CharacterDesigner で扱う |
| K4 | AI の結果は一番上の新しいレイヤーに置いて選ぶ | 済み | atelier/app/main_window.py:5180、finishers.py:184。試験: tests/test_toplayer.py |
| K5 | 赤ペンの指示の欄に確定のボタン、印の右クリックから囲みの中だけ加工 | 済み | 2026-11-22 窓で確かめた。赤ペンで囲んで指示の欄に「笑顔に」と打ち「確定」を押すと欄が閉じ、レイヤーの欄に「赤ペン 1: 笑顔に」が出た。印の右クリックに「赤ペン 1 の中だけ加工」（綺麗にする・ディテール・質感など 13 項目）が出た（/tmp/claude-0/-home-user/e19cd56b-00c0-5c61-a043-c8cddeecb792/scratchpad/use/req/K5-note.png、K5-after.png）。中だけ加工を押して外が変わらないかは見ていない |
| K6 | 赤ペンのレイヤーを消したら、絵・履歴・ライブラリー・作業の保存に何も残さない | 一部 | 2026-11-22 窓で、赤ペンの印を全部消すと印は 0 になり、レイヤーの欄から赤ペンの行が消えた。直した結果のレイヤーを消したあと履歴・ライブラリー・作業の保存に残らないかは見ていない（描くのがメモリ不足で落ちた） |
| K7 | 描く前に止めるのは子どもを性的に描く頼みだけ（childsafe.py の 1 か所） | 一部 | atelier/words/child_safety.py、engine.py:381。専用の試験 test_childsafe.py は 0.5.23 で消えた |
| K8 | 日本語の頼みを、そのまま絵の模型に渡さない | 一部 | atelier/words/japanese_terms.py、engine.py の untranslated の知らせ。試験: test_words.py、test_chatplan.py。全部の経路は確かめていない |
| K9 | 新しく描いた絵はキャンバスを置き換え、頼んだ言葉を履歴に残す | 一部 | atelier/app/main_window.py:3457（履歴から頼みを戻す）。試験: test_chatdraw.py。置き換えの試験は見つけていない |
| K10 | 描くのも直すのも、工程の数や回数に上限を決めない | 一部 | 精度優先（主軸）は直しの回数に上限を置かない（phases.py:17）。AI モードは REDRAW_TRIES = 1（engine.py:2318）のまま。engine.py は別の作業の担当なので触っていない |
| K11 | 模型の評価は数値 1 つ、推奨は点の順、タグで探す、点の届いた物だけ推奨、削除は管理画面で選んだときだけ | 済み | atelier/models/manager.py:7-8、313、atelier/models/ratings.py。試験: test_folders_ratings.py、test_modelblock.py |
| K12 | 全部の機能の精度を数字で測って上げ続け、前と後の数字を docs/knowledge/ に残す | 一部 | 検品だけ（test_qcbench.py、docs/knowledge/accuracy.md）。自動選択は消えた。ほかの機能の台は無い |
| K13 | 描く言葉・打ち消し・既定・検品に触る変更は adhere-bench で前の版と比べる | 一部 | atelier/bench/adherence_bench.py。0.5.24〜0.5.28 で比べた数字は CHANGELOG と docs/knowledge に見つけていない |
| K14 | 入れた機能はアプリから押して最後まで動くか確かめてから出す | 一部 | 2026-11-22 窓で加工のメニュー 40 項目を順に押す台本を流し、9 項目は落ちずに結果のレイヤーを置いた（/tmp/claude-0/-home-user/e19cd56b-00c0-5c61-a043-c8cddeecb792/scratchpad/use/req/kako.out）。10 項目目から先は共有の機械のメモリが足りず止めた。359 件の押す試験は戻していない（試験は足さない指示） |
| K15 | 実在の道具は調べてから描く | 未着手 | 描く仕組みに調べる工程は無い（docs/knowledge の記録だけ） |

## 0.5.23 で消え、前の版の表にあった行

| # | 依頼 | 状態 | 根拠 |
|---|---|---|---|
| N1 | デバッグモード（記録の欄、例外の全文、制限を外す項目） | 済み | 2026-11-22 窓で確かめた。設定のデバッグモードをオンにして当てると、下に「記録」の欄が出た（/tmp/claude-0/-home-user/e19cd56b-00c0-5c61-a043-c8cddeecb792/scratchpad/use/req/N1-debug.png、window/settings_and_debug.py:114、app/debug_log.py） |
| N2 | 描くボタンで落ちない（閉じた窓の裏の糸、アプリ全体のキー） | 一部 | アプリ全体のキーを閉じた窓から外す所はある（window/layout.py:700）。描くボタンを押して最後まで描くのは、共有の機械のメモリ不足（oom-kill）で 2 回落ちて見ていない |
| N3 | 模型に本当に渡した言葉を、頼みの欄とチャットの欄のツールチップに出す | 済み | 2026-11-22 窓で確かめた。描くときの記録（files/sent.py）を入れたあと、頼みの欄とチャットの欄のツールチップに「模型に渡した言葉（描く）: 1girl, red hat / 打ち消し: lowres」が出た |

## 11-07〜11-08 の依頼

| # | 依頼 | 状態 | 根拠・担当 |
|---|---|---|---|
| D1 | 模型に本当に渡した言葉を、頼みの欄とチャットの欄のツールチップに出す（0.5.20 で入れ、0.5.18 に戻したときに消えた） | 作業中 | claude/FIX-backui-20261114: atelier/files/sent.py（記録するだけで言葉は足さない）、test_sent |
| D2 | デバッグモード（記録の欄と記録のファイル、例外の全文、描けなかった理由の窓、制限を外す項目）（0.5.20 で入れ、0.5.18 に戻したときに消えた） | 作業中 | claude/FIX-backui-20261114: atelier/app/debug_log.py。外せる制限は今の main で効く 2 つ（メモリの予算による止め、工程の上限）だけにした（test_backui.DebugModeTest） |
| D3 | 描くボタンで落ちない。閉じた窓の裏の糸とアプリ全体のキーを外す（0.5.20 で直し、0.5.18 に戻したときに消えた） | 作業中 | claude/FIX-backui-20261114: 今の main の send は引数を取らないので描くボタンでは落ちない（試験で押して確かめる）。閉じるときに緊急停止のキーと保存の糸を外す（test_backui.CloseTest） |
| D1 | 起動時にモードを選ぶ（イラストレーター、キャラクターデザイナー、ロゴ・エンブレム・スタンプ）。モードごとのメニュー | 作業中 | claude/FIX-backchara-20261114: atelier/app/modes.py、test_modes.ModeTest |
| D2 | キャラクターデザインのメニュー（一括生成、キャラクターシートの PSD、追加資料、使う人物） | 作業中 | claude/FIX-backchara-20261114: atelier/ai/batch.py・charadesign.py、test_modes |
| D3 | キャラクターファイル（.chara）とキャラデザを作る流れ | 作業中 | claude/FIX-backchara-20261114: chatdraw/charafile.py、test_charafile |
| D4 | 担当編集者（サボりの検品と工程の記録）。描き直しには繋げず、記録と知らせだけ | 作業中 | claude/FIX-backchara-20261114: atelier/ai/director.py、test_director |
| D5 | プリセットを編集・作成できるようにし、設定できる項目を増やし、描くワードなどお気に入りの指示をプリセットに固定する | 作業中 | claude/FIX-backchara-20261114: atelier/panels/preset_dialog.py、test_menuaudit.PresetEditTest |
| D6 | おまかせがおまかせになっていない（毎回同じ模型になる） | 作業中 | claude/FIX-backchara-20261114: choose.choose_image の種での選び直し、test_omakase.ReselectTest。作風のおまかせは言葉を足さない決まりのため選び直していない |
| C1 | AI の自動選択（選択と赤ペン）。丸・四角・全選択・自動選択の赤ペン | 作業中 | claude/FIX-autosel-20261108 |
| C2 | 自動選択の印にも境目の確かめを通し、加工のあとは全体を確かめる | 作業中 | claude/FIX-autosel-20261108 |
| C1 | AI の自動選択（選択と赤ペン）。丸・四角・全選択・自動選択の赤ペン | 作業中 | claude/FIX-backredpen-20261114: 0.5.23 で消えた物を戻した（atelier/ai/auto_select.py、帯の「囲み方」、test_autosel） |
| C2 | 自動選択の印にも境目の確かめを通し、加工のあとは全体を確かめる | 作業中 | claude/FIX-backredpen-20261114: seamfix.settle で境目を合わせ、seamfix.whole_check で全体を 1 回だけ測って知らせる（繰り返しに繋げない） |
| C3 | 自動選択を含め、全部の機能の精度を上げ続ける | 決まり | CLAUDE.md「ユーザーの決めたこと」 |
| C4 | チャットは言語の模型への指示、描くワードは描画の模型への設定として分ける | 作業中 | claude/FIX-backredpen-20261114: atelier/words/chat_words.py、send の once（test_autosel.test_chat_*） |
| C6 | 赤ペンの直しのレイヤーを消したら、絵・画面・履歴・ライブラリー・作業の保存に何も残さない。前の版の直しの絵はごみ箱へ | 作業中 | claude/FIX-backredpen-20261114: atelier/files/redpen_clean.py、Library._drop_redpen_results（test_redpen3） |
| C7 | 赤ペンの指示の欄に確定のボタン | 作業中 | claude/FIX-backredpen-20261114: note_ok（test_redpen3.test_confirm_button） |
| C8 | 赤ペンの印の右クリックから、その囲みの中だけに加工を掛ける。登録した言葉の指示を並べ、その印だけを直す | 作業中 | claude/FIX-backredpen-20261114: _mark_menu、MARK_OK、fix_with_text(mark=)（test_redpen3） |
| C5 | 描く前に止めるのは子どもを性的に描く頼みだけ。ほかの制限を足さない | 済み（未 Release） | atelier/words/child_safety.py、claude/FIX-integ5-20261108 |
| B1 | 前の版より絵の質が下がった。好みは質にだけ効かせ、構図や色を引っ張らない | 作業中 | claude/FIX-quality2-20261108 |
| B2 | 効いていないフィルターを直すか外す | 作業中 | claude/FIX-quality2-20261108 |
| B3 | ライブラリーの右クリックから「一覧から外す」を除く（履歴にはあってよい） | 作業中 | claude/FIX-integ5-20261108: librarypanel._menu |
| B4 | 技能（加工・仕上げ・組み合わせ）が全部効くようにする。効かない物は出さない | 作業中 | claude/FIX-qc3-20261108 |
| B5 | マウスの戻る・進むボタンを使えるようにする | 作業中 | claude/FIX-backui-20261114: 0.5.18 に戻したときに消えたのを v0.5.22 から戻した。戻るで元に戻す、進むでやり直す、打っている欄ではその欄の元に戻す（test_typeguard.MouseSideButtonTest） |
| B6 | 絵に矛盾が無いように、まともに効く検品を入れる | 作業中 | claude/FIX-qc3-20261108 |
| A1 | 枚数と種をまとめない。枚数の入力欄を用意する | 作業中 | claude/FIX-backui-20261114: v0.5.22 から戻した。描くボタンの左に「枚数」の欄（幅 0 に潰れない）、詳しい設定に枚数を置かない、見出しは「絵の模型」、一括生成はファイルのメニュー、複数枚の 1 枚が失敗しても残りを描く（test_backui） |
| A2 | ディテール追加が効かない | 作業中 | claude/FIX-finish2-20261108 |
| A3 | 画風を加工のメニューに入れる | 作業中 | claude/FIX-finish2-20261108 |
| A4 | 拡大の文言を直す | 作業中 | claude/FIX-finish2-20261108 |
| A5 | 奇麗にするを直す（崩さない・速く） | 作業中 | claude/FIX-finish2-20261108 |
| A6 | 右クリックメニューを編集できるようにする・充実させる・精査する | 作業中 | claude/FIX-menus-20261108 |
| A7 | プリセットを精査する | 作業中 | claude/FIX-menus-20261108 |
| A8 | チャットを有効活用する（チャットで描く・直す・加工する・設定を変える） | 作業中 | claude/FIX-obey-20261108 |
| A9 | 訳の分からない制限で「描けませんでした」にしない | 作業中 | claude/FIX-obey-20261108 |
| A10 | 頼んだ指示を模型が無視しない | 作業中 | claude/FIX-obey-20261108、前の版の claude/FIX-adhere-20261108 |
| A11 | 文字入力中にショートカットに取られない（急ぎ） | 作業中 | claude/FIX-backui-20261114: v0.5.22 から戻した。atelier/ui/type_guard.py（アプリ全体）、test_typeguard.TypeGuardTest・WindowFieldsTest |
| A12 | 落とさない。メモリの使い方を選ばせる（自動が既定、優先して動かす、控えめに動かす） | 作業中 | claude/FIX-backui-20261114: v0.5.22 から戻した。membudget.MODES、設定の「メモリの使い方」、見張りのメモリの解放は 30 秒に 1 回まで（test_membudget.MemModeTest・WatchTest、test_backui.MemModeWindowTest）。読み込みの見積もりの倍率は 0.5.18 の 1.1 のまま |
| A13 | キャラクターシートと LoRA を入れる。模型ごとの参考画像・学習セット、外部共有サイト（Civitai・Hugging Face）から取る | 作業中 | claude/FIX-lora-20261108 |
| A1 | 枚数と種をまとめない。枚数の入力欄を用意する | 作業中 | claude/FIX-integ5-20261108: 詳しい設定で「枚数」と「種」の見出しを分け、描くボタンの左の欄に「枚数」の名前を付けた（test_typeguard.CountFieldTest） |
| A2 | ディテール追加が効かない | 作業中 | claude/FIX-backchara-20261114（0.5.22 から今の main に戻した） |
| A3 | 画風を加工のメニューに入れる | 作業中 | claude/FIX-backchara-20261114（0.5.22 から今の main に戻した） |
| A4 | 拡大の文言を直す | 作業中 | claude/FIX-backchara-20261114（0.5.22 から今の main に戻した） |
| A5 | 奇麗にするを直す（崩さない・速く） | 作業中 | claude/FIX-backchara-20261114（0.5.22 から今の main に戻した） |
| A6 | 右クリックメニューを編集できるようにする・充実させる・精査する | 作業中 | claude/FIX-backchara-20261114（0.5.22 から今の main に戻した） |
| A7 | プリセットを精査する | 作業中 | claude/FIX-backchara-20261114（0.5.22 から今の main に戻した） |
| A8 | チャットを有効活用する（チャットで描く・直す・加工する・設定を変える） | 作業中 | claude/FIX-obey-20261108 |
| A9 | 訳の分からない制限で「描けませんでした」にしない | 作業中 | claude/FIX-obey-20261108 |
| A10 | 頼んだ指示を模型が無視しない | 作業中 | claude/FIX-obey-20261108、前の版の claude/FIX-adhere-20261108 |
| A11 | 文字入力中にショートカットに取られない（急ぎ） | 作業中 | claude/FIX-integ5-20261108: atelier/ui/type_guard.py（アプリ全体）、test_typeguard |
| A12 | 落とさない。メモリの使い方を選ばせる（自動が既定、優先して動かす、控えめに動かす） | 作業中 | claude/FIX-integ5-20261108: membudget.MODES、設定の「メモリの使い方」、test_membudget.MemModeTest |
| A13 | キャラクターシートと LoRA を入れる。模型ごとの参考画像・学習セット、外部共有サイト（Civitai・Hugging Face）から取る | 作業中 | claude/FIX-backchara-20261114（0.5.22 から今の main に戻した） |
| A14 | ComfyUI を参考に、インテュイティブで見やすい画面にする | 作業中 | claude/FIX-comfyui-20261108（工程ごとの秒、並べて比べる、操作を探す）を integ5 に統合 |
| A15 | 作画監督を早く完成させる | 作業中 | claude/FIX-qc2-20261108 を integ5 に統合 |
| A16 | 機能が足されたら Release、急ぎの直しは急いで Release | 決まり | CLAUDE.md「ユーザーの決めたこと」 |
| C1 | AI の自動選択（選択と赤ペン）。丸・四角・全選択・自動選択の赤ペン | 済み | 2026-11-22 窓で確かめた。自動選択で服の所を押すと「自動選択: 46,921 画素を選びました」と出て、服の四角（230×200）を選んだ（/tmp/claude-0/-home-user/e19cd56b-00c0-5c61-a043-c8cddeecb792/scratchpad/use/req/C1-autosel.png）。赤ペンの自動選択は右クリック「ここを自動選択で印にする」にある（canvas_menu.py） |
| C2 | 自動選択の印にも境目の確かめを通し、加工のあとは全体を確かめる | 一部 | コードはある（engine.py:2509 seam_fix.settle、2516 whole_check、finishers.py:1259）。窓で直しを流すのは、共有の機械のメモリ不足（oom-kill）で 2 回落ちて見ていない |
| C3 | 自動選択を含め、全部の機能の精度を上げ続ける | 一部 | K12 と同じ |
| C4 | チャットは言語の模型への指示、描くワードは描画の模型への設定として分ける | 一部 | 2026-11-22 窓で、チャットに「こんにちは」と送っても描くワードは空のままだった（/tmp/claude-0/-home-user/e19cd56b-00c0-5c61-a043-c8cddeecb792/scratchpad/use/req/C4-chat.png）。「描くワードを〜にして」と頼んだときに変わるかは、言葉の模型の答えが遅く見ていない（chat.py:170 chat_words.parse） |
| C5 | 描く前に止めるのは子どもを性的に描く頼みだけ | 一部 | K7 と同じ |
| B1 | 前の版より絵の質が下がった。好みは質にだけ効かせる | 一部 | 0.5.24 で足す言葉を止めた（engine.py:1455）。好みの効かせ方の 0.5.22 の直しは消えた。origin/claude/FIX-noextra-20261114（未マージ） |
| B2 | 効いていないフィルターを直すか外す | 一部 | docs/knowledge/filter-audit.md。0.5.24 で決まり文句と打ち消しを外した。試験は見つけていない |
| B3 | ライブラリーの右クリックから「一覧から外す」を除く | 済み | 2026-11-22 窓で確かめた。ライブラリーの絵の右クリックは 13 項目で「一覧から外す」は無く、消すは「消す（ごみ箱へ）…」の 1 つ。ファイルが見つからない絵だけ「一覧から外す」と「場所を探す…」を出す（library_panel.py:230。ごみ箱へ移せないため） |
| B4 | 技能（加工・仕上げ・組み合わせ）が全部効くようにする | 一部 | K14 と同じ。押した 9 項目は効いた（綺麗にする 4、まとめて 2、ディテール追加、整える）。画風・質感・広げるなどは押していない |
| B5 | マウスの戻る・進むボタン | 済み | 2026-11-22 窓で確かめた。レイヤーを足して 2→3、マウスの戻るで 2、進むで 3 に戻った（type_guard.py:43、window/redpen.py:246） |
| B6 | 絵に矛盾が無いように、まともに効く検品 | 一部 | atelier/qc/manual_check.py、test_qcmanual.py、test_qcbench.py。0.5.22 の矛盾の検品（test_qc3.py）は消えた |
| A1 | 枚数と種をまとめない。枚数の入力欄 | 済み | 2026-11-22 窓で確かめた。描くボタンの左に「枚数」の欄、詳しい設定に「種」の見出しが別にある（/tmp/claude-0/-home-user/e19cd56b-00c0-5c61-a043-c8cddeecb792/scratchpad/use/req/A1-aipanel.png、ai_panel.py:212） |
| A2 | ディテール追加が効かない | 一部 | 2026-11-22 窓で加工 › ディテール › ディテール追加を押すと 16.8 秒で新しいレイヤーに置いた。ダミーの平らな絵では変わりの平均が 0.04 で、0.5.22 の 1.84 と同じ台では測っていない（/tmp/claude-0/-home-user/e19cd56b-00c0-5c61-a043-c8cddeecb792/scratchpad/use/req/kako-09-*.png） |
| A3 | 画風を加工のメニューに入れる | 済み | 2026-11-22 窓で確かめた。メニューバーの「加工」に「画風の変更」（アニメの塗り〜ドット絵の 13）がある（/tmp/claude-0/-home-user/e19cd56b-00c0-5c61-a043-c8cddeecb792/scratchpad/use/req/menus.txt）。画風を掛けて描き替わるかは見ていない（模型を取る前にメモリ不足で止めた） |
| A4 | 拡大の文言を直す | 一部 | 2026-11-22 窓で見た。加工 › 拡大 に「1 枚にして 2 倍に拡大（アニメ向け）」「レイヤーのまま 2 倍に拡大」がある。0.5.22 の文言と同じかは比べていない。押して拡大されるかは見ていない |
| A5 | 奇麗にするを直す（崩さない・速く） | 一部 | 2026-11-22 窓で加工 › 綺麗にするの 5 つを押した。線と塗りを整える 29.3 秒、塗りのざらつきを抑える 34.8 秒（初回の模型の読み込みを含む）、ほかは 1〜2 秒で新しいレイヤーに置いた。「指定した箇所の周辺を整える」は囲みが無いと「囲んでから選んでください」と出た。崩さないかは本物の絵で見ていない |
| A6 | 右クリックメニューを編集できるようにする | 一部 | 右クリックのメニューの並べ替えと隠す（menu_editor.py:23、128 の「右クリック: 」）と、右クリックに出す加工を選ぶ窓（canvas_menu.py:314）はある。窓で並べ替えて開き直すのは見ていない |
| A7 | プリセットを精査する | 一部 | 2026-11-22 窓で見た。プリセットは標準・キャラデザ・ラフを清書・ラフから自由に・イラスト・アイコン・背景美術・モノクロ・ロゴ・スタンプの 10 と、まとめた 5（ai_panel.py:34、49）。各プリセットで描いて精査はしていない |
| A8 | チャットを有効活用する（チャットで描く・直す・加工・設定を変える） | 一部 | atelier/agent/chat_plan.py、app.py:2082（枚数を読む）。試験: test_chatplan.py |
| A9 | 訳の分からない制限で「描けませんでした」にしない | 一部 | R4 と同じ。止めるのは childsafe.py だけ |
| A10 | 頼んだ指示を模型が無視しない | 一部 | R1 と同じ |
| A11 | 文字入力中にショートカットに取られない | 済み | 2026-11-22 窓で確かめた。禁止ワードの欄に b・e・x を打つと欄に「bex」が入り、道具は手のひらのまま（atelier/ui/type_guard.py、main_window.py:130） |
| A12 | 落とさない。メモリの使い方を選ばせる | 済み | 2026-11-22 窓で確かめた。設定の「描き方」に「メモリの使い方」（自動・優先して動かす・控えめに動かす）がある（settings.py:52、memory_budget.py:92）。実機で落ちないかは見ていない |
| A13 | キャラクターシートと LoRA、学習セット、Civitai・Hugging Face から取る | 一部 | 2026-11-22 窓で見た。LoRA の窓（取る・ファイルから足す・消す）と AI › Civitai から探す、ライブラリーの右クリック「学習用に集める」がある。Hugging Face から LoRA を取るのとキャラクターシートは CharacterDesigner の分 |
| A14 | ComfyUI を参考に見やすい画面（工程ごとの秒、並べて比べる、操作を探す） | 済み | 2026-11-22 戻した（流用元 6f12af8 の palette.py を atelier/ui/command_palette.py へ）。窓で Ctrl+K の「操作を探す」を開いて「保存」と打つと 11 件並んだ（/tmp/claude-0/-home-user/e19cd56b-00c0-5c61-a043-c8cddeecb792/scratchpad/use/req/A14-palette.png）。「描いた絵を並べて比べる」は表示のメニューと Ctrl+Shift+K。履歴が 2 枚未満では「比べる絵が 2 枚以上ありません」と出た。2 枚以上で並べるのは窓で見ていない（描くのが共有の機械のメモリ不足で落ちた）。工程ごとの秒は ai_results.py:116 |
| A15 | 作画監督を早く完成させる | 一部 | R6 と同じ |
| A16 | 機能が足されたら Release、急ぎの直しは急いで Release | 一部 | R12 と同じ。0.5.29 は未マージ |

## 描く（10-25〜10-31）

| # | 依頼 | 状態 | 根拠 |
|---|---|---|---|
| 1 | 頼んだ通りの絵を描かせる | 一部 | engine.py:1455、1461（emphasize）。R1 と同じ。実際の模型で効くかは確かめていない |
| 2 | 手足・目など細かい所をきちんと描く。描けるまで描き直す | 一部 | K10 と同じ。精度優先は検品を通るまで直しを足す（phases.py:17）。AI モードは 1 回 |
| 3 | 質が先。時間をかけてよいので奇麗で正しい絵 | 一部 | atelier/ai/two_stage.py。工程分け（D2）は未マージ |
| 4 | 頼んでいない物を描かせない | 一部 | engine.py:1567-1572（頼んでいない物を描かない物に足す）。描き直しが 1 回になったので次の回が無い。試験: test_variety.py |
| 5 | 標準的な体型で描く | 一部 | atelier/words/body_words.py、bodycheck.py。試験名は確かめていない |
| 6 | 背景がワンパターンで魅力が無い | 一部 | vary_background は頼みをそのまま返す（engine.py:1790）。頼んでいない背景を足さない決まり（R1）に従った形で、背景の魅力を上げる別の手は無い |
| 7 | 日本語の頼みをそのまま絵の模型に渡さない | 一部 | K8 と同じ |
| 8 | 3D のキャラデザも出来るようにする | 一部 | atelier/ai/to_3d.py（入口だけ）。試験: test_features.py |
| 9 | フリーズする言葉がある | 未着手 | 原因の言葉の記録が無い |

## 検品

| # | 依頼 | 状態 | 根拠 |
|---|---|---|---|
| 10 | 手・足の指の数を数える | 一部 | tools/gen/hands.py の count_fingers。小さな絵ではほとんど数えられない |
| 11 | 検品で崩れを逃がさない。読めない絵は崩れとして扱う | 一部 | 0.5.28 で片目の隠れを足した（test_qcbench.py）。0.5.22 の「検品できなかった物も崩れ」は消えた |
| 12 | AI の不出来な絵を AI 自身が直す | 一部 | 赤ペンの直しと app.py:2284（指示の空の囲みを検品して 1 回直す）。自動では直さない（0.5.25） |
| 13 | 模型とのやり取りを 1 回で終えず何回も回す | 一部 | K10 と同じ |
| 14 | モデルの外の処理を引き続き開発する | 一部 | 0.5.26〜0.5.28 |

## 模型

| # | 依頼 | 状態 | 根拠 |
|---|---|---|---|
| 15 | 優秀な絵画モデルを早急に用意 | 一部 | atelier/models/catalog.json。目録の見直しは origin/claude/FIX-partsmodels-20261114（未マージ） |
| 16 | 動かせるモデルをまとめて GitHub に載せる | 済み | atelier/ui/help/install.md、atelier/models/model_doc.py。試験: test_modeldoc.py |
| 17 | 模型のダウンロード先と導入方法 | 済み | atelier/ui/help/install.md。試験: test_modeldoc.py |
| 18 | 模型を精査し、選択肢を増やす | 一部 | atelier/models/manager.py、hfadd.py。実際に動かした点が足りない |
| 19 | 評価は数値 1 つ、都度見直し、推奨をソート | 済み | atelier/models/ratings.py、manager.py:7。試験: test_folders_ratings.py |
| 20 | タグで管理 | 済み | atelier/models/manager.py、ratings.py。試験: test_folders_ratings.py |
| 21 | 評価の低い模型を推奨に出さない | 済み | atelier/models/catalog.py。試験: test_chatdraw.py |
| 22 | 取得済みの模型は表示する | 済み | atelier/models/manager.py:8、237。試験: test_modelmgr.py |
| 23 | 取得済みを一覧の上に | 済み | atelier/models/manager.py:8（手元にある模型はどの絞り込みでも先頭）。試験: test_modelmgr.py（前の版では未着手） |
| 24 | ★でお気に入りの模型 | 済み | atelier/models/manager.py:8（その中で ★ を先に）、paths.py:133（favorites.json）。試験: test_modelmgr.py |
| 25 | 使いたくない模型を非表示 | 済み | atelier/models/manager.py:311-329（set_hidden）。試験: test_modelblock.py |
| 26 | メニューの AI に使える模型が更新される | 済み | atelier/app/main_window.py（開くたびに作り直す）。試験: test_chatdraw.py |
| 27 | おまかせが機能していない | 一部 | atelier/ai/omakase.py、choose.py。試験: test_omakase.py。「機能していない」原因は記録に無い |
| 28 | 世間の評価の高い模型を優先して評価試験 | 一部 | atelier/models/popular.py（config/verify-models.txt を人気順に書く）。試験: test_chatdraw.py。Actions が使っているかは確かめていない |
| 29 | 追加ダウンロードが要る模型が動かない | 未着手 | main に根拠無し。origin/claude/FIX-partsmodels-20261114 |
| 30 | 大容量の模型も動くように | 一部 | atelier/ai/memory_budget.py:34（置き方 4 つ）。実機で確かめていない |
| 31 | 模型によって絵が描けなくなる | 一部 | 0.5.23 で 0.5.18 に戻した。GPU で確かめていない |
| 32 | 高性能な言語模型の方が時間がかかる | 一部 | engine.py:443（同じ模型は読み直さない） |
| 33 | 好みの絵をオリジナルの学習モデルのように使う | 未着手 | ownstyle.py は ★ の絵を集める入口だけ。学習は無い |

## UI

| # | 依頼 | 状態 | 根拠 |
|---|---|---|---|
| 34 | 全体的に使いやすく。優れた UI を学ぶ | 一部 | docs/knowledge/ui-design.md、atelier/ui/layouts.py |
| 35 | 進みはポップアップに | 済み | atelier/ui/notice.py。試験: test_chatdraw.py、test_confirm.py |
| 36 | 進捗のポップアップが出なくなる不具合 | 未着手 | 再現と直しの記録が無い |
| 37 | ボタンの説明はツールチップに。AI タブは枠を取りすぎない | 済み | atelier/panels/ai_panel.py（setToolTip 21 か所）。試験: test_aiui.py |
| 38 | 右ボタンでつかんで動かす。右クリックの機能を充実 | 済み | atelier/paint/canvas.py。試験: test_chatdraw.py（RightButton） |
| 39 | カーソルが邪魔にならない | 一部 | atelier/ui/layouts.py、canvas.py。試験名は確かめていない |
| 40 | 描いたあと新しい絵が出ない。表示の選択・固定・解除 | 一部 | atelier/app/main_window.py。試験名は確かめていない |
| 41 | 完成した絵が表示されない | 一部 | 試験: test_uifix.py。本物の模型で確かめていない |
| 42 | デフォルトのプリセット、リセット | 一部 | atelier/panels/ai_panel.py。試験: test_presetui.py。リセットの試験は確かめていない |
| 43 | スクロールでシード値などが変わる | 済み | atelier/ui/wheel_guard.py、app.py:576。試験: test_presetui.py |
| 44 | ツアーなどでフリーズする | 一部 | atelier/ui/tour.py、tours.py:112（5 枚まで）。試験: test_freeze.py。Windows で確かめていない |
| 45 | フリーズのあと 1 度正しく閉じないと戻らない | 済み | atelier/app/main_window.py:254（crashed_before）。試験: test_chatdraw.py |
| 46 | 全体表示のタブに表示領域、動かせる | 済み | atelier/app/main_window.py:355（view_rect）。試験: test_presetui.py |
| 47 | 模型の管理が開けない | 一部 | 試験: test_modelmgr.py。CUDA 版の Windows では確かめていない |
| 48 | 関係するディレクトリを開くボタン | 一部 | atelier/files/folders.py:27、app.py:829。試験: test_folders_ratings.py にあるかは確かめていない |
| 49 | 増えた機能はプルダウンで整理 | 一部 | atelier/panels/layer_panel.py、aipanel.py |
| 50 | 音声入力 | 一部 | atelier/agent/voice.py。試験: test_voicechat.py。本物のマイクでは確かめていない |

## チャット

| # | 依頼 | 状態 | 根拠 |
|---|---|---|---|
| 51 | チャットの下に頼んだ言葉の履歴 | 済み | atelier/app/main_window.py。試験: test_chatdraw.py |
| 52 | お気に入りの言葉・指示を固定・保存 | 済み | atelier/app/main_window.py:698、721。試験: test_keepsettings.py |
| 53 | チャットとして使えるよう設計 | 一部 | atelier/panels/chat_panel.py。試験: test_uifix.py |
| 54 | 描く言葉の指示を AI タブに統合、禁止ワードの欄 | 済み | atelier/panels/ai_panel.py:147-149、283。試験: test_aitabs.py |

## レイヤー

| # | 依頼 | 状態 | 根拠 |
|---|---|---|---|
| 55 | 真ん中の画像が重なる | 済み | atelier/app/main_window.py:5180（一番上の新しいレイヤーに置く）。試験: test_toplayer.py |
| 56 | レイヤーの使い方が意図した動きでない | 一部 | atelier/panels/layer_panel.py、canvas.py。試験: test_layertools.py、test_layercrash.py。利用者が使って確かめていない |

## ライブラリ

| # | 依頼 | 状態 | 根拠 |
|---|---|---|---|
| 57 | ライブラリが開けなくなった | 済み | 試験: test_uifix.py |
| 58 | 履歴から SNS 連携 | 一部 | atelier/ui/share.py。試験: test_features.py。Windows で確かめていない |
| 59 | タイムラプス、録画・GIF | 一部 | atelier/paint/timelapse.py。試験: test_works.py、test_features.py |

## リリースと検証

| # | 依頼 | 状態 | 根拠 |
|---|---|---|---|
| 60 | Setup.exe を組む | 済み | .github/workflows、packaging。CHANGELOG.md 0.5.x |
| 61 | Windows を主に検証する | 一部 | atelier/bench/windows_draw.py。実機は利用者待ち |
| 62 | 土日に実機で確かめるので、動く物をリリース | 一部 | 0.5.28 が実機で動くかは確かめていない |
| 63 | Actions を並列で使い、待たずに開発を進める | 一部 | 運用の決まり |
| 64 | リリースと Actions にゴミを残さない | 一部 | 未マージの FIX-*-20261114 のブランチが 19 本ある（rel526〜rel528 はマージ済みで残っている） |

## その他

| # | 依頼 | 状態 | 根拠 |
|---|---|---|---|
| 65 | バグだけでなく設計を見直す | 未着手 | 設計の見直しの文書が無い。0.5.23 で一度に外したことが、設計を見直さずに戻した例 |
| 66 | 遅い原因を調べて直す | 一部 | engine.py:143（bf16 を測る）。0.5.21 の 18 倍の遅れの直しは 0.5.23 で消え、backui で戻す |
| 67 | 未実装の機能を全部やる | 一部 | この表 |
| 68 | その他のバグも直す | 一部 | 一覧が無い |

## 11-06 の依頼

| # | 依頼 | 状態 | 根拠 |
|---|---|---|---|
| 69 | 赤ペンの項目ごとにレイヤー、指示はそのレイヤーのコメント | 済み | atelier/panels/layer_panel.py:124-128（「赤ペン n: 指示」の行）。試験: test_redpenfix.py |
| 70 | 赤ペンの直しを右クリックからも | 済み | 2026-11-22 窓で見た。赤ペンの印の右クリックに「赤ペン 1 の中だけ加工」と「言葉で指示…」が出た（K5 と同じ写し） |
| 71 | レイヤーの重ね順（透明、AI の絵、足したレイヤーと赤ペン） | 一部 | 2026-11-22 窓で見た。赤ペンの行はレイヤーの欄の一番上に出た（赤ペン 1: 笑顔に → 上の絵 → レイヤー 1）。透明のレイヤー 1 の重ね順は見ていない |
| 72 | 描く枚数を指定する欄 | 済み | atelier/app/main_window.py:683-686（count_spin）。試験: test_aitabs.py |
| 73 | レイヤーを消したら、そのレイヤーの絵も消す | 済み | atelier/paint/canvas.py:615（delete_layer）。試験: test_canvasfix.py、test_uifix.py |
| 74 | レイヤーごとの保存 | 済み | atelier/files/project_file.py:3（zip の中にレイヤーごとの PNG）、app.py:5358（PSD）。試験: test_canvasfix.py。ORA は 0.5.23 で消えた |
| 75 | 絵を日付のディレクトリに分けて置く | 一部 | atelier/app/main_window.py:2533（日付のディレクトリ）。描いた絵の置き場の全部の経路かは確かめていない |
| 76 | 加工の精度を上げ、崩れを防ぎ、崩れを検品 | 一部 | 試験: test_nobreak.py（目と髪の色が変わったら戻す） |
| 77 | 拡大した後の加工が重くて止まる | 一部 | finishers.py:557、573（tiled、at_work_size）。試験: test_finish_big.py |
| 78 | 加工を直感的に、組み合わせをお気に入りに | 一部 | finishers.py:1064（組み合わせを順に掛ける） |
| 79 | アプリのウィンドウにもテーマ | 済み | atelier/ui/themes.py:288、app.py:1609。試験: test_menuedit.py |
| 80 | メニューの最適化・表示の編集・並べ替え | 一部 | atelier/ui/menu_editor.py、app.py:4343。試験: test_menuedit.py |
| 81 | リボンの最適化・並べ替え・区切り・固定 | 一部 | atelier/ui/ribbon.py。試験: test_viewtools.py |
| 82 | メニューとタブで共通の項目は同じ機能、タブで右クリック | 一部 | atelier/agent/commands.py |
| 83 | よく使う物はボタンに | 一部 | atelier/ui/layouts.py |
| 84 | ブラシのデモ表示 | 済み | atelier/panels/brush_preview.py、app.py:1014。試験: test_brushtools.py |
| 85 | 特殊な色、カラーパレット、描く道具の充実 | 一部 | 色の欄は color_panel.py。0.5.23 で消えた palette.py（操作を探す窓）は 2026-11-22 に atelier/ui/command_palette.py として戻した |
| 86 | チャットで繰り返しや予定の依頼、アップロードの自動化 | 未着手 | atelier/agent/scheduler.py は模型の scheduler の設定で、予定の依頼ではない |
| 87 | ワードではなく文で依頼・修正・加工 | 未着手 | main に根拠無し。origin/claude/FIX-fixprompt-20261114 が直しの指示の訳を作る |
| 88 | 参考画像を探させる、参考先を保存 | 一部 | 参考画像を探す（設定のメニュー、ai_drawing.py:50、references.find_images）と学習セットの書き出し（export_kohya）はある。窓で探して置くのは見ていない |
| 89 | プリセットの充実 | 一部 | atelier/panels/ai_panel.py:18 |
| 90 | 多言語に対応 | 一部 | atelier/ui/i18n.py:15。試験: test_usability.py |
| 91 | 全ての文言を見直す | 一部 | 0.5.18 以降の直しだけ |
| 92 | 今までのフィードバックを活かす | 未着手 | 0.5.23 で前のフィードバックの直しが消えた |
| 93 | アプリ版とウェブサービス版の準備 | 未着手 | 後で |
| 94 | その他のバグを見つけて直し、最適化を進める | 一部 | 0.5.26（ロック・非表示のレイヤーが変わっていた直し） |

## 成果物（deliverables.md）

| # | 依頼 | 状態 | 根拠 |
|---|---|---|---|
| E1 | アプリのウィンドウで起動する CharacterDesigner | 一部 | deliverables.md は app/start.sh と app/launch.py を挙げるが、app/ は #381（e508cf29）で外れ、今は chatdraw のアプリ。deliverables.md の完成条件が今のリポジトリに合っていない |
| E2 | 仕事の進み具合の表示（経過と何回目か） | 一部 | 進みの欄が「工程 i/N 名前」と累計の工程の数を読む（activity_panel.py:203-207）。工程ごとの秒は ai_results.py:116。描いて表示を見るのはメモリ不足で落ちて見ていない |
| F1 | キャラクターデザインは CharacterDesigner と、服飾は FashionDesigner と一緒に開発する（2026-11-21） | 一部 | docs/knowledge/integration.md に役目と進め方を書いた。CharacterDesigner は atelier/extensions.py の拡張で載る。FashionDesigner との受け渡しは PNG までで、SVG はまだ開けない |
| F2 | CharacterDesigner から移行できない、描けない（2026-11-22） | 直した（未確認） | 部品・設定の引き継ぎを足した。Windows で描く確かめは atelier-e2e |
| F3 | 液タブの画面全体を、全画面の描く領域として使えるようにする。そのために、すべての窓（欄・帯）を窓として独立できるようにする（2026-11-22） （欄・帯・チャットは独立させた窓どうしで組み替え・統合もできる） | 着手 | |
| F4 | Edge が IE からお気に入りを引き継ぐような、CharacterDesigner からの引き継ぎにする。AtelIer を入れるときに CharacterDesigner も入れられ、CharacterDesigner を入れるときに AtelIer があれば拡張も入れる。0.1.1〜0.1.4 が利用者の機械に作った余計な物を片付ける（2026-11-22） | 着手 | |
| F5 | 精度優先は工程の数で打ち切らない。直しがあれば工程を足し、要る工程の数と累計の工程の数を出す。時間や工程切れで通っていない絵で終えない（2026-11-22） | 着手 | |
| F6 | CharacterDesigner のリポジトリが無くても AtelIer の開発と動きが成り立つところまで引き継いで完成させる（2026-11-22） | 着手 | |
| F7 | 精度優先で描いている途中にアタリを表示しない（前に指示したのにデグレした。2026-11-22） | 直した | atelier/ai/phases.py の NO_PREVIEW |
| F8 | 精度優先の設計の見直し: 描いている途中で別の絵にしない、ゼロに戻っていきなり最後の工程へ飛ばない、同じ絵を続けて描いて工程の数を稼がない（2026-11-22） | 着手 | |
| F9 | 窓と欄を中身と画面の大きさに合わせて自動で整える。特に進みの欄（大きすぎる・小さすぎる・文字が切れる・空きが多い）（2026-11-22） | 直した | atelier/panels/activity_panel.py の _fit、atelier/ui/window_fit.py の fit_dock_height |
| F10 | 通知のポップアップが出たまま消えない。種類ごとに「出さない / 数秒で消す（秒を選ぶ）/ 押すまで残す」を設定で選べるようにする（2026-11-22） | 直した | atelier/ui/notice_rules.py、設定の「通知」、進み具合の欄の「知らせ」 |
| F11 | 精度優先の表示に描かない工程「目的」を出さない。描く工程だけを 1 から数え、N も描く工程の数にする（2026-11-22） | 直した | atelier/ui/phase_display.py |
| F12 | 精度優先の工程の管理を見直し、細かく分ける。1 つの工程で描く・測る・直すを全部していたのを、描く・確かめる（項目ごと）・直す（崩れごと）・確かめ直す（直した項目だけ）の工程に分け、計画の表で持つ（2026-11-22） | 直した | atelier/ai/phase_plan.py、atelier/ai/phase_items.py、atelier/ai/phases.py |
| F13 | ストレスになる所の洗い出し。初めて使う人として主な作業を歩き、待ち時間・手数・覚えない設定・出たまま邪魔な物・答えの無い操作・戻せない操作・確かめの窓・文字の切れ・分からないエラー・落ちる所を一覧にし、不具合は直す（2026-11-22） | 直した | docs/reports/stress-audit.md、atelier/app/window/files.py の new_blank |
| F14 | 普通のペイントソフトとしても魅力的にする。全部の欄と帯（ツールバー）を独立したウィンドウにでき（最小化・前面固定・タスクバー・モニターの間で動かせる）、キャンバスを選んだモニターの全画面にでき、外した物を組み替えて戻せ、モニターの組ごとに配置を名前で保存・呼び出しでき、無いモニターの窓は今の画面へ戻し、欄ごとにタッチ向けを選べるようにする。全ウィンドウ化を売りにする。レイアウトは縛らず全て自由に置けるようにし、自動で整える処理が手で置いた配置を上書きしないようにする。外した窓の置き場所を閉じるときに自動で残し、開き直してもずれないようにする（2026-11-22） | 直した | atelier/app/window/group_window.py、atelier/ui/screens.py、atelier/ui/touch.py、atelier/ui/layouts.py |
| F15 | AI 抜きでも真面に戦えるレベルにする。ほかの描画ソフト（CLIP STUDIO PAINT・Krita・Photoshop・Procreate・MediBang・FireAlpaca・SAI）と毎日使う基本の機能を照らし、壊れている物から直し、無い基本を効く順に作る。長期の開発で周を重ねる（2026-11-23） | 着手 | docs/reports/paint-parity.md（表と残りの順番）、atelier/paint/canvas.py、atelier/files/project_file.py |
| F16 | 描画の基本の 2 周目。自由変形（拡大・縮小・回転・反転・ゆがみ、確定と取り消し、選択範囲だけ）、レイヤーフォルダー（入れる・出す・畳む・表示・不透明度・合成、作業ファイルと PSD の往復）、ペンの傾きと筆圧の曲線、選択範囲の拡張・縮小・ぼかし。「背景」の縮小図が空に見える件を確かめる。ブラシの欄に塗りつぶしと入り抜きの設定を出す（2026-11-22） | 直した | atelier/paint/canvas.py、atelier/panels/transform_dialog.py、atelier/panels/layer_panel.py、atelier/files/project_file.py、atelier/app/main_window.py |
| F17 | Logo, Emblem, 3D, VirtualDesigner にも対応させる。CharacterDesigner・FashionDesigner と同じ形（拡張の置き場、インストーラーの選べる部品、各インストーラーが置き場へ入れる）で載せられるようにし、名前を 1 か所の一覧で持つ。中身の決まっていないデザイナーの入口は作らない（2026-11-23） | 直した | atelier/extension_catalog.py、packaging/extension_sections.py、packaging/get-extension.ps1 |
| F18 | 各拡張機能は AtelIer のために設計するが、単体でも機能させ、ほかの AI サービスからでも利用できるように設計する。6 つのデザイナー（Character、Fashion、Logo、Emblem、3D、Virtual）の設計の決まりにする（2026-11-23） | 決まりを書いた | CLAUDE.md、docs/knowledge/integration.md |
| F19 | 精度優先で直せない崩れ（アタリの人数など）が出ても聞いて止まらず、前の工程の絵を土台に種を替え強さを上げて描き直す（ゼロから描かない、前と同じ絵は数えない、回数に上限なし）。聞いて止まったときも止めたときも、検品を通っていない絵（とくにアタリ）はキャンバスに出さず隠したレイヤーにだけ置き、最後まで通ったときだけ出して「描けました」と知らせる（2026-11-23） | 直した | atelier/ai/phases.py、atelier/app/window/ai_results.py、atelier/bench/end_to_end.py、tests/test_phases.py |
| F20 | AtelIer を使う人は拡張機能だけを入れればよい（容量がかさみ重複するため）。使う物はタイトルで選ばせ、タイトルはビジュアルで魅せる。開発は分担するが、AtelIer が統括し、AtelIer のための開発をする（2026-11-23） | 決まりを書いた（タイトルの画面は別の作業） | CLAUDE.md、docs/knowledge/integration.md |
| F21 | お互い良いところ、使えるところは採用していくことで開発工数を削減する（AtelIer と 6 つのデザイナー）（2026-11-23） | 決まりと、採用し合う物の表を書いた（コードは変えていない） | CLAUDE.md、docs/knowledge/integration.md |
| F22 | 後はタイトルで選択させて使わせる。タイトルもビジュアルで魅せる。AtelIer がデザイナーを統括する。起動するとロゴと、描く画面・拡張の置き場に入ったデザイナーのタイル（名前・絵・一言）を出し、押すとその画面に入る。入っていない物は Release のある物だけ小さな「入れる」のタイルにする。最後に使った物を覚え、「次から出さない」と「ファイル」の「タイルの画面…」を置く（2026-11-23） | 直した | atelier/app/title_screen.py、atelier/extensions.py、atelier/app/main_window.py、tests/test_extensions.py |
