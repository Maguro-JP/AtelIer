# 流用元の機能と AtelIer の照らし合わせ

CharacterDesigner の `chatdraw/`（195ef66 の 1 つ前、4a9e809）から移した機能が、AtelIer で動くかを 1 機能ずつ照らした表です。
機能の一覧は、流用元の docs/reports/user-requests.md、docs/reports/deliverables.md、.claude/skills/lessons/LESSONS.md、docs/knowledge/ から、利用者が頼んで入った物を集めました。

結果の意味（利用者の方針で、試験が通ったことを「動く」の根拠にしない）:

- 動く: アプリを起動して操作し、出た結果を目で見た（操作と結果を書く）
- 直した: 壊れていたので直し、直したあとアプリの操作で確かめた
- 壊れている: 落ちる所があり、直していない（流用元でも同じ所で落ちる）
- 確かめられない: アプリの操作で通せなかった（括弧に理由）
- 確かめていない: アプリの操作では見ていない。括弧に試験の様子を参考として書く。torch が要る物は、この環境では描けないので操作でも確かめられない

見方の限り: Linux の offscreen で流しました。Windows の実機、GPU、本物の模型では何も確かめていません。「確かめられない」の試験は、流用元でも同じ所で落ちることを 4a9e809 の写しで確かめました（test_uifix、test_detailtimelapse、test_chatplan、test_chatdraw、test_panels、test_layerkeep、test_original_finish）。

## 描く・AI

| 機能 | 流用元の担い手 | AtelIer の担い手 | 試験 | 結果 |
|---|---|---|---|---|
| 頼みの文から絵を描く（描くボタン、チャット） | engine.py、app.py | ai/engine.py、app/window/ai_drawing.py | test_chatdraw、test_aitabs、test_backui | 動く（AI モード・小さな模型で、描くワードに「赤いマフラーの女の子、海」を書いて「描く」を押した。118 秒で「描けました」と知らせ、キャンバスが「AI の絵 1」に置き換わった。前の絵に重ねていない） |
| 描く枚数の欄（枚数と種を分ける） | app.py（count_spin） | app/window/ai_drawing.py | test_aitabs、test_backui | 動く（枚数を 2 にして「描く」を押し、「2 枚描きました。履歴から選べます」と出て、種の違う 2 枚が出力の置き場に書かれた） |
| 精度優先（工程に分けて描く、工程 i/N の表示） | phases.py、phasetools.py | ai/phases.py、ai/phase_tools.py | test_phases、test_gen_modes、test_pause | 動く（精度優先で「描く」を押し、進みに「工程 1/12「目的」」「工程 2/12「サムネイル」」…と出た。240 秒で「止める」を押し、「止めました（工程 3 で止めました）」と残った崩れ 3 件が知らされ、止めた所までの絵が一番上のレイヤーに置かれた。検品を通るまでは見ていない） |
| AI モードと精度優先の切り替え | modes.py | app/modes.py | test_modes、test_gen_modes | 動く（描き方の欄を AI モードと精度優先に替えて「描く」を押し、AI モードは工程を出さずに描き、精度優先は工程 i/N を出した） |
| 二段で描く（構図から清書） | twostage.py | ai/two_stage.py | test_chatdraw（TwoStageTest） | 確かめていない（小さな模型の操作では二段の道に入らなかった） |
| 頼んだ言葉を勝手に足さない・変えない | engine.py | ai/engine.py | test_weighted_prompt、test_unasked_wear、test_not_solo | 確かめられない（模型に渡った言葉は画面に出ないので、操作では見られない） |
| 日本語の頼みをそのまま絵の模型に渡さない | jaterms.py | words/japanese_terms.py | test_words、test_chatplan | 確かめられない（同じ理由。日本語の頼みで描き終わることだけを見た） |
| 子どもを性的に描く頼みだけを止める | childsafe.py | words/child_safety.py | test_words | 確かめていない（操作では頼んでいない） |
| 構図の知識（遠近など） | composition.py | ai/composition.py | test_composition | 確かめられない（模型に渡る言葉の中の物で、画面に出ない） |
| おまかせ（模型の選び直し、自動の仕上げを掛けない） | omakase.py、choose.py | ai/omakase.py、ai/choose.py | test_omakase、test_original_finish | 確かめていない（操作では選んでいない） |
| 体型・手足の言葉 | body.py | words/body_words.py | test_body、test_body_hands、test_proportions | 確かめられない（模型に渡る言葉の中の物） |
| 背景の変化 | variety.py | ai/variety.py | test_background、test_background_style、test_variety | 確かめられない（模型に渡る言葉の中の物） |
| 写真のような絵 | engine.py | ai/engine.py | test_photoreal | 確かめられない（写真向けの模型が要る） |
| 担当編集者（サボりの記録だけ、描き直しに繋げない） | director.py | ai/director.py | test_director | 確かめていない |
| 緊急停止（読み込み中・工程の中でも止まる） | engine.py | ai/engine.py | test_stop | 動く（AI モードで描き始めて 4 秒後に「止める」を押し、0.5 秒で止まり「止めました（0.01 秒）」と出た。レイヤーは増えなかった。精度優先の工程の途中でも 0.36 秒で止まった） |
| メモリの使い方（落とさない、模型を降ろす、OOM でやり直す） | membudget.py | ai/memory_budget.py | test_membudget、test_memory、test_cpudtype | 確かめていない（落ちずに描けたことだけ。同じ機械のほかの処理と合わせてメモリが尽き、台本が 2 回落とされた。アプリの OOM のやり直しの道かは見ていない） |
| 一時停止と再開 | pausekeep.py | files/pause_keep.py | test_pause | 確かめていない |
| LoRA（Civitai・Hugging Face から取る） | lora.py、loradialog.py | ai/lora.py、panels/lora_dialog.py | test_lora、test_civitai | 確かめられない（Civitai・Hugging Face から取る LoRA が要る） |
| 参考画像を探す・参考先を保存 | refs.py | ai/references.py | test_chatplan（RefsTest） | 直した（「少女」が 1girl になり、beach_girl.png が見つからなかった。数を外した語でも探す。操作: 参考画像を探す関数に「海 少女」と置き場を渡し、beach_girl.png が返るのを見た。窓のボタンからは確かめていない） |
| 自分の画風の模型のように使う | ownstyle.py | ai/own_style.py | test_ownstyle | 確かめていない |
| 3D にする（入口） | to3d.py | ai/to_3d.py | test_chara3d | 確かめていない |
| ロゴ・エンブレム・スタンプ | logo.py | ai/logo_maker.py | test_logo | 確かめていない |
| 一括で描く | batch.py | ai/batch.py | test_confirm（BatchConfirmTest） | 確かめていない |

## 赤ペン・直し・加工

| 機能 | 流用元の担い手 | AtelIer の担い手 | 試験 | 結果 |
|---|---|---|---|---|
| 赤ペンの印（描く、文字の指示） | redpen.py | paint/redpen.py | test_redpeninput、test_keep_marks | 動く（赤ペンの四角で囲むと印 1 が付き、指示の欄が出た。「笑顔にする」を書いて確定を押すと欄が閉じ、印の横と欄に指示が残った） |
| 赤ペンを「赤ペン」レイヤーに出す（隠す・全部消す・1 つずつ消す） | layerpanel.py、redpen.py | panels/layer_panel.py、paint/redpen.py | test_redpen3、test_layertools | 直した（レイヤーの欄に「赤ペン 1: 笑顔にする」「赤ペン 2: 消す印」と別の行で出て、行の目を外すと隠れ、戻すと出た。1 つ消してから元に戻すと、消した印は戻らず残っていた印まで消えた（流用元も同じ）。印の操作の並びを覚えて、元に戻すで消した印を元の番号へ戻すように直した。直したあと、印 1 を消す→元に戻す→やり直す→元に戻すで、印は 1→2→1→2 と動き、指示もそろった） |
| 赤ペンの指示の確定ボタン、印の右クリックから囲みの中だけ加工 | app.py（_mark_menu、note_ok） | app/window/redpen.py | test_redpen3 | 動く（確定のボタンで欄が閉じた。番号の丸の上の右クリックに「赤ペン 1 の中だけ加工」が出て、線と塗りを整える・塗りのむらを均す・ジャギーも取る・整えるを押すと、どれも囲みの外で変わった画素は 0） |
| 赤ペンの直しは直した所だけのレイヤーにして一番上に置く | app.py、finishers.py | app/window/redpen.py、ai/finishers.py | test_redpenfix、test_toplayer | 直した（「描く」で直すと「赤ペンの直し 1」が一番上に選んだ状態で置かれた。修正依頼の指の形を整えるで、囲みの外が 2,114 画素変わった。直しの結果の透明度が囲みの外へはみ出していたので、囲みの中だけに絞るようにした。直したあと、「描く」で直して囲みの外 0 画素、囲みの中の差の平均 53.3） |
| 赤ペンのレイヤーを消したら何も残さない | workkeep.py、redpenclean.py | files/work_keep.py、files/redpen_clean.py | test_layerkeep、test_redpen3 | 確かめていない（直しのレイヤーを選んで「－」で消すと、レイヤーの一覧から消えた。作業の保存・履歴・ライブラリーに残らないかを見る段で、台本がメモリ不足で落とされた） |
| 囲みの外を変えない（境目の確かめ） | seamfix.py | ai/seam_fix.py | test_qc_seams、test_canvasfix | 直した（上の行と同じ。直したあと、赤ペンの直し 1 回と印の中だけの加工 4 つで、囲みの外で変わった画素はどれも 0） |
| AI の自動選択（選択と赤ペン） | autosel.py | ai/auto_select.py | test_autosel | 動く（絵の真ん中で自動選択を押し、印が 0→1 になった。自動選択の模型は取れず、部位分けで「skirt」18,665 画素を選んだと知らせた。SAM の道は確かめられない） |
| 修正依頼の一覧（右クリックから） | fixrequests.py、fixmenu.py | ai/fix_requests.py、ai/fix_menu.py | test_fixrequests、test_fixwords、test_fix_tool | 動く（印が無いときに選ぶと「直す所を囲んでください」と知らせた。印を付けて「指を 5 本に」を選ぶと、印の指示に書かれ、直しのレイヤーが一番上に置かれた。囲みの外 0 画素。「指の形を整える」は 2,114 画素変わったので、上の行で直した。直したあとの修正依頼では押し直していない） |
| 直しの指示を模型に届ける（訳せない語は知らせる） | engine.py | ai/engine.py | test_fixwords、test_sent | 確かめられない（模型に渡った言葉は画面に出ない。描くワードの欄に前の言葉が残ったまま直すと、会話には「描きます: 赤いマフラーの女の子」と出るが、囲みごとの指示は印の指示が先に使われることをコード（fix_regions、merge）で見た） |
| 加工（仕上げ、ディテール追加、奇麗にする） | finishers.py | ai/finishers.py | test_finish2、test_finish_big、test_finish_quality、test_nobreak | 動く（右クリックからディテール追加でエフェクトのレイヤー、まとめて綺麗にするで「綺麗にした絵」のレイヤーが一番上に置かれた。「線と塗りを整えるは変わりすぎたので強さを 0.25 に下げて混ぜました」と知らせた） |
| 画風を替える | restyle.py | ai/restyle.py | test_retouch、test_toneshade | 確かめられない（アニメの塗り・線画を押すと「模型のファイルが足りません。「模型の管理」で取り直してください」と知らせて止まった。画風の模型がこの機械に無い） |
| 拡大 | upscale.py | ai/upscale.py | test_light_upscale、test_works | 動く（1 枚にして 2 倍に拡大で 832×1216 が 1664×2432 になり、置き換えで置かれた。レイヤーのまま 2 倍に拡大は、作業ファイルの保存の窓が出たところで台本がメモリ不足で落とされ、見ていない） |
| 後処理（線、陰影） | postfx.py | ai/post_effects.py | test_limb_shadow、test_lineart | 確かめていない |
| 顔の部位の直し | facefeat.py | ai/face_features.py | test_face_redraw_pipe、test_face_mask、test_faceform_fit | 確かめられない（部位分けの模型が無い。「顔を守る印は、部位分けの模型が無いか顔が見つからないので使っていません」と知らせた） |
| 言葉で加工・登録した指示を 1 押しで掛ける | shortcuts.py | ai/shortcuts.py | test_shortcuts、test_voicechat | 動く（指示を「明るく」で登録すると「指示を登録しました」と出て、右クリックに「明るく」が出た。押すと囲みの中を直し、「赤ペンの直し 2」が一番上に置かれた） |
| 編集の道具（切り抜き、外へ描き足す） | edittools.py | ai/edit_tools.py | test_editing、test_works | 確かめていない（四方に広げる・背景を消す・透過の段の前に台本がメモリ不足で落とされた） |

## 検品

| 機能 | 流用元の担い手 | AtelIer の担い手 | 試験 | 結果 |
|---|---|---|---|---|
| 手・足の指を数える | handcheck.py | qc/hand_check.py | test_finger_count、test_feet_count、test_hands_auto | 動く（操作: library/feedback/body の全身のイラスト r64-front と、Actions で描いた 45003177026/1-composition.png をキャンバスに出し「編集 > 検品する」を押した。どちらも「検品: 崩れ 4 か所を赤ペンで囲みました」と出て、レイヤーの欄に赤ペン 4 件が並んだ。手は 2〜3 個、足は 2 個を見つけた。指の本数まで数えたのは composition の足 1 だけで「指が多い（6 本。5 本のはず）」、ほかの手・足は「指を数えられない（重なって隠れている／つぶれている）」で崩れとして囲んだ。手の指を本数として数えた所はまだ見ていない） |
| 体・脚の検品 | bodycheck.py | qc/body_check.py | test_legcount、test_legs_fused、test_qc_legs | 動く（同じ 2 枚で、体の点を読んで body_bad が空（体・脚の崩れ無し）と返った。前に出た「体の点を読めない」は出なかった。崩れのある体で囲む所は見ていない） |
| 左右の検品 | mirrorcheck.py | qc/mirror_check.py | test_mirrorcheck | 動く（同じ 2 枚で顔を 1 つ読み、左右を比べて gated・flaws とも空で返った。左右の崩れを囲む所は見ていない） |
| 頼んだ物が描けたかの検品 | requestcheck.py | qc/request_check.py | test_count_extra、test_extra_items、test_held_items | 動く（小さな模型で「a girl」を描き「検品する」を押すと、19.7 秒で「頼んでいない物: hat、weapon、witch hat」と知らせに出た。ライブラリーの絵では「体が多い（人 12 人、頼んだのは 1 人）」と出た） |
| 崩れの検品（読めない物は崩れ） | sanity.py | qc/sanity.py | test_sanity、test_qc、test_qc_counts | 動く（読めない手・顔・体を「検品できなかった所」として知らせに並べ、「崩れは見つかりませんでした」とは出さなかった） |
| 検品の手動実施（右クリック、赤ペンで出す） | qcmanual.py | qc/manual_check.py | test_qcmanual | 動く（ライブラリーの絵 walk.png を開いて「検品する」を押すと、43.5 秒で結果が右下の知らせに出た。場所の分かる崩れが無く、赤ペンの印は付かなかった） |
| 部位ごとの検品の表示 | qcparts.py | qc/parts.py | test_qcparts、test_qcparts_ui | 確かめられない（部位ごとに出すのは場所の分かる崩れがあるときで、今回の 2 枚では出なかった） |
| 独自の検品 | origqc.py | qc/original_qc.py | test_original_qc、test_origqc | 確かめられない（登録した検品が無く、アプリから掛ける所を通していない） |
| 検品の精度の台 | tools/gen/qcbench.py | tools/gen/qcbench.py | なし（流用元の test_qcbench は方針により移していない） | 確かめられない（アプリの外の台。アプリの操作の対象ではない） |
| 頼んだ通りに描けたかの点（adhere-bench） | adherebench.py | bench/adherence_bench.py | test_bench | 確かめられない（アプリの外の台。アプリの操作の対象ではない） |

## 模型の管理・取得

| 機能 | 流用元の担い手 | AtelIer の担い手 | 試験 | 結果 |
|---|---|---|---|---|
| 模型の目録と推奨 | models.py、catalog.json | models/catalog.py | test_catalog、test_models | 動く（「AI > 模型の管理…」で窓が開き、「おまかせ」と取得済みの tiny-stable-diffusion-xl-pipe が並んだ） |
| 模型の管理（評価 1 つ、タグ、★、非表示、削除は選んだときだけ） | manager.py、ratings.py | models/manager.py、models/ratings.py | test_modelmgr、test_folders_ratings、test_ratefreeze | 動く（同じ窓に「取得済み・未確認・0.0GB」の 1 行が出た。消す・非表示・タグは押していない） |
| お気に入りの模型の欄 | favpanel.py、favmodels.py | panels/favorite_models_panel.py、models/favorites.py | test_favmodels | 動く（全部押しの台本（メニュー・帯・欄のボタン 776 個を順に押す）で「AI > ★ お気に入り」の 2 件を押し、例外も誤りの知らせも出なかった） |
| 初回の取得 | setup.py、fetchfile.py | models/first_setup.py、files/fetch_file.py | test_fetchfile、test_pull | 確かめられない（「AI > おまかせ」で「模型の管理」の準備の窓が開くのは見た。取るのはネットに出るので通していない） |
| Hugging Face から足す | hfadd.py | models/hugging_face_add.py | test_hub_defaults | 動く（前の台本 drive_after で、模型の管理に名前を入れて足し、置き場の user_models.json に「Hugging Face の名前で足した」で入った。その模型で描けた） |
| 世間の評価の高い模型 | popular.py | models/popular.py | test_modelprune | 確かめられない（ネットに出る） |
| 模型の導入の文書 | modeldoc.py | models/model_doc.py | test_modeldoc | 動く（「ヘルプ > 手順書」で HelpDialog が 720×640 で開いた） |
| 模型を読めないときの知らせ | engine.py | ai/engine.py | test_modelblock、test_hands_unavailable | 動く（torch の無い処理で「欄:AI > ちびキャラに」を押すと「AI が使えません / 描く部品が読めません（diffusers, torch がありません）」と出た） |
| 模型ごとの描き方 | engine.py | ai/engine.py | test_perfamily | 確かめられない（描く処理は別の作業が見ている） |

## 言葉の模型・チャット

| 機能 | 流用元の担い手 | AtelIer の担い手 | 試験 | 結果 |
|---|---|---|---|---|
| 手元の言葉の模型 | assistant.py、tools/llm | agent/assistant.py | test_local_llm、test_chatbrain | 動く（チャットに「こんにちは。一言で返事をしてください」と送ると、Qwen3.5-2B が 30.8 秒で「こんにちは。AtelIer の案内役です…」と返した） |
| チャットで描く・直す・設定を変える | chatplan.py、commands.py | agent/chat_plan.py、agent/commands.py | test_chatplan | 確かめられない（描く・直すは別の作業が見ている。今回は会話の 1 往復だけ） |
| チャットと描くワードを分ける | chatwords.py、intent.py | words/chat_words.py、agent/intent.py | test_autosel、test_chatplan | 確かめられない（会話の 1 往復では描くワードを変える頼みを送っていない） |
| チャットの欄（履歴が残る、入力は下） | chatpanel.py | panels/chat_panel.py | test_uifix | 動く（上の 1 往復で、送った文と答えが時刻つきの吹き出しで残り、入力の欄は下にあるのを窓の写しで見た。前に直した落ちる所も、絵を置いたあと落ちなかった） |
| 繰り返し・予定の依頼 | scheduler.py | agent/scheduler.py | test_chatplan（WindowPlanTest） | 確かめられない（「設定 > 予約の一覧」は押して例外は出なかったが、予定を作る頼みは送っていない） |
| 音声入力 | voice.py | agent/voice.py | test_voicechat | 確かめられない（マイクのボタンを押すと「声で入力するには faster-whisper と sounddevice を入れてください」と出た。部品が入っていない） |
| 描くワード・禁止ワードの登録 | wordpanel.py | panels/word_panel.py | test_words、test_free_dict | 動く（全部押しの台本（メニュー・帯・欄のボタン 776 個を順に押す）でAI の欄の登録のボタンを押し、例外は出なかった） |
| 単語辞書と学び | worddict.py、wordlearn.py | words/dictionary.py、words/learning.py | test_free_dict、test_normlearn | 動く（「設定 > 単語辞書…」で WordDialog が 560×420 で開いた。学びは確かめていない） |
| 模型に渡した言葉をツールチップに出す | sent.py | files/sent.py | test_sent、test_panels（TooltipTest） | 動く（操作: 書く欄に QHelpEvent（カーソルを合わせたときと同じ ToolTip の出来事）を送り、QToolTip に「描いてほしい絵を日本語か英語で書き、…」が出た。描いていないので、模型に渡した言葉の行は出ていない） |

## 描く道具・レイヤー・画面

| 機能 | 流用元の担い手 | AtelIer の担い手 | 試験 | 結果 |
|---|---|---|---|---|
| ブラシと描く道具 | brush.py、canvas.py | paint/brush.py、paint/canvas.py | test_brushtools、test_paint_tools、test_handdraw_paint | 動く（操作: QTest の mousePress・mouseMove 31 回・mouseRelease でキャンバスにペンの線を引くと、描くレイヤーの色のある画素（2 画素おきに数えた）が 0 から 3016 に増え、Ctrl+Z で 0 に戻った。E・B・I・H のキーで道具が eraser・pen・eyedropper・hand に替わった） |
| ブラシの見本 | brushpreview.py | panels/brush_preview.py | test_brushtools | 確かめていない（線を引くのは通したが、見本の欄は見ていない） |
| 図形の補助、対称 | assist.py | paint/drawing_assist.py | test_shapeassist、test_layertools | 動く（全部押しの台本（メニュー・帯・欄のボタン 776 個を順に押す）で「表示 > 対称定規」「表示 > 定規」の全部を押し、例外は出なかった。線を引いての確かめはしていない） |
| レイヤー（コピー、切り取り、ロック、重ね順） | canvas.py、layerpanel.py | paint/canvas.py、panels/layer_panel.py | test_layertools、test_layercrash、test_toplayer | 動く（全部押しの台本（メニュー・帯・欄のボタン 776 個を順に押す）で「レイヤー」のメニュー 17 個とレイヤーの欄のボタンを押し、例外は出なかった） |
| AI の絵はキャンバスを置き換え、元に戻すで戻る | app.py | app/window/ai_results.py | test_uifix（LayerTest）、test_chatdraw | 動く（小さな模型で描くと「AI の絵 1」が一番上のレイヤーに置かれ、「描けました（元に戻すで前の絵に戻せます）」と出た。元に戻すは押していない） |
| 作業ファイル（レイヤーごと保存） | project.py | files/project_file.py | test_legacy_project、test_layerkeep | 動く（3 枚のレイヤーで「保存」を押すと 2,109,785 バイトの作品.atelier ができ、新規キャンバスにしてから開き直すと同じ 3 枚が戻った） |
| カラー・パレット | colorpanel.py | panels/color_panel.py | test_stray_color、test_panels | 動く（全部押しの台本（メニュー・帯・欄のボタン 776 個を順に押す）でカラーの欄のボタンを押し、例外は出なかった） |
| 欄の出し入れ・移動・配置 | layouts.py、tabdock.py | ui/layouts.py、ui/tab_dock.py | test_panels（PanelCombosTest）、test_chatdraw（LayoutTest） | 直した（おすすめの配置の右の欄が、表示とライブラリーのタブが上、AI が真ん中、履歴が下に分かれず、表示が 92 画素に潰れていた。右を上から表示・AI・履歴に積み、上の欄から中身の高さを配るようにした。「全部浮かせる」のあとのタブは、浮いたタブの窓にレイヤーが入って見えていたので、試験の見方を直した。窓の写しで見た） |
| プリセット（作る・直す・既定に戻す） | aipanel.py、presetdialog.py | panels/ai_panel.py、panels/preset_dialog.py | test_presetui、test_menuaudit、test_chatplan | 動く（全部押しの台本（メニュー・帯・欄のボタン 776 個を順に押す）で「配置」の 6 個と保存・書き出しを押し、例外は出なかった） |
| プリセットの欄にスクロールバーを出さない | aipanel.py | panels/ai_panel.py | test_panels（OverflowTest） | 直した（1280×720 のおすすめで表示の欄に縦の流す棒が出ていた。上の直しで 199 画素になり、棒が消えたのを窓の写しで見た） |
| AI の欄のタブ（模型、描くワード、登録、禁止ワード、登録） | aipanel.py | panels/ai_panel.py | test_aitabs、test_aiui | 動く（窓の写しで「指示」のタブに絵の模型、描くワードの順に並んでいるのを見た。下の登録までは欄の高さで流す棒の中） |
| テーマとテーマの編集 | themes.py、themeedit.py | ui/themes.py、ui/theme_editor.py | test_usability | 動く（テーマを「ナイト」「ペーパー」に替え、窓の写しで色が替わるのを見た。編集の窓は押していない） |
| メニューの編集・リボン | menuedit.py、ribbon.py | ui/menu_editor.py、ui/ribbon.py | test_menuedit、test_ribbonfamily、test_menuaudit | 動く（「ウィンドウ > メニューを編集…」「帯を編集…」「リボンの並びを変える…」の窓が開いた） |
| スクロールで値が変わらない | wheelguard.py | ui/wheel_guard.py | test_uifix | 動く（操作: 焦点の無い「枚数」の数の欄と「描き方」の選ぶ欄にホイールを上へ 3 回送り、値は 1 と 0 のまま変わらなかった。キャンバスへのホイール 3 回では拡大率が 0.128 から 0.195 に上がった） |
| 文字入力中にショートカットに取られない | typeguard.py | ui/type_guard.py | test_typeguard、test_tabkey | 動く（操作: 書く欄に焦点を置いて QTest.keyClicks で e と b を打つと、欄に「eb」が入り、道具は pen のままだった） |
| キーの割り当て、マウスの戻る・進む | keys.py | app/key_bindings.py | test_shortcuts、test_backui | 一部動く（キャンバスで E・B・I・H・Ctrl+Z を送り、道具の切り替えと元に戻すが効いた。割り当てを変える操作とマウスの戻る・進むは送っていない） |
| ツアー | tour.py、tours.py | ui/tour.py、ui/tours.py | test_usability | 動く（「使い方ツアー」で 1/5 から 5/5 まで「次へ」で進んだ。テーマの機能の案内も出た） |
| 進みのポップアップ・知らせ | notice.py、popup.py | ui/notice.py、ui/popup.py | test_confirm、test_chatdraw | 動く（検品と描いた結果が右下の知らせに出たのを窓の写しで見た） |
| 確かめの窓（直す前に聞く） | confirm.py | ui/confirm.py | test_confirm | 確かめられない（直す操作は別の作業が見ている） |
| 多言語 | i18n.py | ui/i18n.py | test_usability | 動く（操作: 言語を English にして開き直すと、メニューが File・Edit・View・AI・Logos and Stamps・加工・Settings・Selection・Layer・Window・Layout・Help に替わった。「加工」だけは訳が無く日本語のまま） |
| 表示の範囲（全体表示のタブ） | app.py | app/window/layout.py | test_viewtools | 動く（全部押しの台本（メニュー・帯・欄のボタン 776 個を順に押す）で「表示」の拡大・回転などを押し、例外は出なかった） |
| 関係するディレクトリを開く | folders.py | files/folders.py | test_module_paths | 動く（「ファイル > ディレクトリを開く」の 6 個で、それぞれの置き場を開く呼び出しが出た） |
| 落ちたあとの記録、デバッグモード | crashlog.py、debuglog.py | app/crash_log.py、app/debug_log.py | test_crashlog、test_backui | 動く（「ヘルプ > 落ちた記録を開く」「記録の置き場を開く」で crash.log と置き場を開く呼び出しが出た。デバッグモードは押していない） |
| 固まらない（重い言葉、窓の裏の糸） | app.py | app/window/files.py | test_freeze、test_bughunt、test_drawbugs | 動く（言葉の模型の答えを待つ 30.8 秒と検品の 43.5 秒の間も、台本の時計（0.25 秒ごと）が止まらずに進んだ） |

## 履歴・ライブラリー・作品

| 機能 | 流用元の担い手 | AtelIer の担い手 | 試験 | 結果 |
|---|---|---|---|---|
| 頼んだ言葉の履歴と頼み直し | app.py | app/window/history.py | test_chatdraw（UsabilityFixTest） | 動く（描いたあと履歴に 1 件入り、右クリックに「この設定で描き直す」「頼みの言葉を書く欄に入れる」が出た。アプリを開き直すと履歴は 0 件だった。流用元（origin/main の chatdraw/）も同じで、履歴の欄はその回に描いた絵を activity.add で足すだけで、起動のときに読み直す所が無い。両方の Window を作って 1 件足し、閉じて作り直すと、どちらも 1 件から 0 件になった。移したときに壊れた物ではない） |
| ライブラリー（右クリックから「一覧から外す」を除く） | librarypanel.py、library.py | panels/library_panel.py、files/library.py | test_works、test_panels | 動く（ライブラリーに 5 件が並び、右クリックに「消す（ごみ箱へ）…」があり「一覧から外す」は無かった） |
| ごみ箱（消す、戻す） | trash.py | files/trash.py | test_cleanup、test_panels（TrashTest） | 動く（「ファイル > ごみ箱…」で窓が開き「ごみ箱は空です」と出た。消して戻す所は通していない） |
| タイムラプス（描いたあとの逆算、録画、GIF） | timelapse.py | paint/timelapse.py | test_detailtimelapse、test_video_io | 直した（操作: アプリを起動し、64×96 の絵を AI の結果として置いた。直す前は Pillow 12 の MinFilter(1) が浮動小数点の例外を出し、AI の絵を置くたびにアプリごと落ちていた（流用元でも同じ）。直したあとは窓が残り、「AI の絵 1」が一番上のレイヤーに置かれ、履歴にも出たのを窓の写しで見た。test_detailtimelapse の残り 1 件は torch。8/9） |
| SNS に出す | share.py | ui/share.py | test_features | 確かめられない（外に出る。履歴の右クリックに「SNS に送る」があるのは見た） |
| 作品の記録・利用者の数字 | userstats.py | panels/user_stats.py | test_works | 動く（「ヘルプ > あなたの統計…」で「描いた絵: 3 枚」と出た） |

## 更新・配布

| 機能 | 流用元の担い手 | AtelIer の担い手 | 試験 | 結果 |
|---|---|---|---|---|
| アプリの更新 | updater.py | app/updater.py | test_version | 動く（「ヘルプ > 更新を確かめる」で、ネットに出る手前で止めると「更新を確かめられませんでした / ネットに届きませんでした」と出た） |
| 設定の移し替え | migrate.py | app/migrate.py | test_keepsettings | 確かめられない（前の版の設定のある機械を用意していない） |
| Setup.exe を組む | packaging/ | packaging/ | test_build | 確かめられない（Windows で組む。Actions の作業） |
| 拡張の登録口 | なし | extensions.py | test_extensions | 確かめられない（起動で読み込む所は通ったが、拡張を置いて確かめていない） |
| アプリのウィンドウで起動する | app.py | app/main_window.py | test_headless | 動く（offscreen で窓が開き、上の操作を全部その窓で行った） |

## CharacterDesigner に残した

| 機能 | 流用元の担い手 | 置き場 |
|---|---|---|
| キャラデザモード（設定資料集・三面図・表情差分がそろうまで場面の絵を描かない） | modes.py、charadesign.py | CharacterDesigner に残した（character_designer/chara_design.py） |
| キャラクターファイル（.chara） | charafile.py | CharacterDesigner に残した（character_designer/chara_file.py、test_charafile） |
| キャラクターシートの一括生成・PSD | batch.py（キャラの分） | CharacterDesigner に残した（character_designer/chara_batch.py） |
| 3D キャラの項目 | to3d.py のキャラの分 | CharacterDesigner に残した（test_chara_menu_3d） |
| 服のデザイン | fashion | CharacterDesigner に残した（test_fashion） |
| 設定画集 | sheet | CharacterDesigner に残した |

## 数

| 結果 | 数 |
|---|---|
| 動く | 34 |
| 直した | 4 |
| 確かめられない | 26 |
| 確かめていない | 38 |
| 合計（CharacterDesigner に残した 6 件を除く） | 102 |
