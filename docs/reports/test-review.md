# 試験の見直し（tests/ の 185 ファイル）

試験が通ったことは、アプリが動くことの根拠になりません。この表では、各ファイルが利用者のどの操作を本物の経路で見張っているかを仕分けています。書き換えと削除はしていません。

確かめ方の分け方は次のとおりです。本物は、実際のクラスや関数を通して、出た画素・ファイル・窓を見る物です。偽物は、mock・patch・偽の模型で中身をすり替える物です。ソースは、ソースの文字を読む物です。その時だけは、1 回のバグの形だけを固定する物です。作り物の入力で実際の関数を呼ぶ単体の測りも「本物」に入れていますが、操作の全体は見ていません。

秒の欄は `QT_QPA_PLATFORM=offscreen python3 -m unittest tests.<名前>` を 1 回流した結果です。模型の要らない 159 ファイルを流し終えました。test_timelapse_rebuild.py は、計っている途中でリポジトリから消えたので、表から外れています（私は消していません）。tests/needs_models.txt に載っている 26 ファイルは流していません。

## 数

- 要る: 82 ファイル
- まとめる: 92 ファイル（ファイルは今 184 です）
- 要らない: 10 ファイル（cdhome, cycle_refs, ensemble, folds, hub_defaults, modeldoc, pick_pose, record_policy, structure, zukan）
- 要らない物を外して減る秒: 3.2 秒です（模型の要らない 159 ファイル全体で 367.8 秒）

## 本物の経路で見ている試験が 1 つも無い操作

1. 模型で実際に描く（AI モードも精度優先の工程も）。描く試験はすべて FakePainter などの偽の模型です（phases, omakase, modes, chatdraw）
2. 模型を取る。Hugging Face と Civitai の通信はすべて偽物です。本物の部品を通るのは fetchfile の取り直しの部分だけです
3. 赤ペンの直しと加工を、本物の模型で囲みの中だけに掛けること。窓の経路は通りますが、描き直すのは偽の模型です
4. 検品を、本物の模型（手・部位分け・タグ）で実際に描いた絵に掛けること。作り物の点か偽の模型の入力しかありません
5. 作業ファイルの保存と読み込みを窓から往復すること。この経路は aitabs と chatdraw にしかなく、どちらも模型が要るため、Linux では飛ばされます
6. 更新すること。updater.newer の版の比べ方を見ているだけで、取って入れ替えて起動する経路はありません
7. 入れてから起動すること。build は組む道具の出力、bundle は import だけを見ており、入れたアプリの窓が開くまでは見ていません（atelier-e2e の Actions は tests/ の外なので、この見直しには入れていません）
8. チャットを、本物の言葉の模型で使うこと。local_llm と chatbrain の模型は偽物です

## 表

| ファイル | 操作 | 確かめ方 | 重なり | 判定 | 理由 | 秒 |
|---|---|---|---|---|---|---|
| test_aitabs | AI の欄のタブ・作業ファイルの保存と読み込み | 偽物 | aiui, layerkeep | 要る | 作業ファイルの save_project を窓から流す数少ない試験。模型は偽物 | 模型が要る |
| test_aiui | AI の欄の並び・全体表示 | 本物 | aitabs, panels | まとめる（panels） | 欄の並びの見張りは panels と同じ窓を開いて見る | 6.0 秒 14 件 通った |
| test_assets | 無し（素材の出典の確かめ） | 本物 | - | まとめる（build） | 配布物の中身の規則で、利用者の操作ではない | 0.2 秒 2 件 通った |
| test_autosel | 自動選択・赤ペンの囲み | 偽物 | redpen3, redpenfix, usability | 要る | 赤ペンを窓から押す経路。自動選択の模型は偽物 | 模型が要る |
| test_background | 描く（背景だけ） | 偽物 | phases | まとめる（phases） | 描く工程の 1 つの形を偽物で見るだけ | 0.4 秒 7 件 通った |
| test_background_style | 検品（背景・写実の寄り） | 本物 | qcbench | まとめる（検品の測りを 1 つに） | 作り物の画像で関数を呼ぶ単体の測り | 0.7 秒 20 件 通った |
| test_backui | 一括生成・作成枚数 | 偽物 | works, modes | 要る | 版を戻して消えた機能を窓から押して見張る | 模型が要る |
| test_baseline | 描く言葉（体の打ち消し） | 本物 | body, sanity, fixwords | 要る | 模型に渡る言葉を直接見る。adhere の前提 | 0.4 秒 16 件 通った |
| test_bench | 無し（測る台の読み方） | 本物 | qcbench | まとめる（qcbench） | 測る台の道具の単体 | 0.3 秒 5 件 通った |
| test_bible | 設定資料集の保存・言葉の組み立て | 偽物 | chatplan | まとめる（chatplan） | 資料の保存の単体。窓は通らない | 0.2 秒 18 件 通った |
| test_body | 描く言葉（頼みに足さない） | 本物 | baseline | まとめる（baseline） | 同じ body_words を見る 2 件だけ | 0.2 秒 2 件 通った |
| test_body_hands | 検品（頭身・手） | 本物 | pose_hands, finger_count | まとめる（検品の測りを 1 つに） | 作り物の骨格で関数を呼ぶ単体 | 0.3 秒 5 件 通った |
| test_brushtools | 描く（人の筆・色・道具） | 本物 | shapeassist, draw_api | 要る | 窓のブラシで描いて画素を見る | 3.9 秒 11 件 通った |
| test_bughunt | 全部の入口（落ちない） | その時だけ | freeze, works | まとめる（works） | 見つけた不具合の再現の寄せ集め | 3.2 秒 8 件 通った |
| test_build | 入れる（Setup.exe を組む） | 本物 | bundle | 要る | 組む道具の出力を見る。入れる操作の唯一の土台 | 14.1 秒 42 件 通った |
| test_bundle | 入れる（配布の中身で機能が呼べる） | 本物 | build | 要る | 配布の中身だけで import できるかを見る | 12.6 秒 2 件 通った |
| test_canvasfix | 赤ペン・レイヤー・保存 | 偽物 | redpen3, layercrash | まとめる（redpen3） | 赤ペンのレイヤーの行を redpen3 と二重に見る | 1.7 秒 5 件 通った |
| test_catalog | 模型を選ぶ（目録の絞り込み） | 偽物 | modelmgr, folders_ratings | まとめる（modelmgr） | ネットワークを偽物にした目録の単体 | 0.2 秒 7 件 通った |
| test_cdhome | 無し（置き場の組み立て） | ソース | shared_models, keepsettings | 要らない | ソースの文字で .cache を探すだけ。置き場は shared_models が実際に見る | 0.2 秒 2 件 通った |
| test_chara3d | 拡張（3D を作る） | 本物 | extensions | 要る | VRM と glTF を作って出た物を見る | 21.0 秒 10 件 通った |
| test_chatbrain | チャット | 偽物 | chatdraw, voicechat | まとめる（chatdraw） | チャットの流れを偽物で二重に見る | 13.0 秒 11 件 通った |
| test_chatdraw | チャットで描く・更新・保存ほか全般 | 偽物 | ほぼ全部 | まとめる（操作ごとに分ける） | 141 件の寄せ集め。操作ごとのファイルに分けて重なりを消す | 模型が要る |
| test_chatplan | チャットの頼み・プリセット | 偽物 | chatdraw, presetui | まとめる（chatdraw） | チャットの文の読みを chatdraw と二重に見る | 模型が要る |
| test_civitai | 模型を取る（Civitai） | 偽物 | modelmgr, shared_models | 要る | 取る経路で唯一 Civitai を見る。通信は偽物 | 1.0 秒 7 件 通った |
| test_cleanup | 加工（線と色の掃除） | 本物 | lineart, retouch | まとめる（加工の部品を 1 つに） | 部品の単体 | 1.1 秒 3 件 通った |
| test_closeup | 検品（部位の切り出し） | 本物 | face_check | まとめる（検品の測りを 1 つに） | 部品の単体 | 0.2 秒 3 件 通った |
| test_composition | 描く言葉（構図を足さない） | 本物 | baseline, weighted_prompt | 要る | 頼んでいない語を足さない決まりを模型に渡る言葉で見る | 0.2 秒 6 件 通った |
| test_confirm | 確かめの窓・ツアー | 本物 | panels | 要る | ボタンを押して窓を見る | 模型が要る |
| test_count_extra | 検品（持ち物の数） | 偽物 | held_items, pieces | まとめる（held_items） | 同じ持ち物の数え方を別の口で見る | 0.2 秒 5 件 通った |
| test_cpudtype | 描く（CPU で float32） | 偽物 | membudget, device | まとめる（device） | torch を偽物にして分岐だけを見る | 0.2 秒 3 件 通った |
| test_crashlog | 起動（落ちた記録） | 偽物 | - | 要る | 次の起動で前の落ちを拾う経路を見る | 0.2 秒 1 件 通った |
| test_crossrefs | 無し（関数があるか） | ソース | module_paths | まとめる（module_paths） | ソースを読む見張りを 1 つに | 0.4 秒 1 件 通った |
| test_cycle_refs | 無し（動物の周・参考の棚） | 本物 | - | 要らない | 利用者の操作に繋がらない部品の単体 | 0.2 秒 4 件 通った |
| test_detail_regions | 検品（細部の描き直しへ回す） | 偽物 | original_qc, outside_checks | まとめる（original_qc） | 検品の分岐を偽物で見るだけ | 0.2 秒 3 件 通った |
| test_detailtimelapse | 加工（ディテール追加）・タイムラプス | 偽物 | finish2, features | 要る | 窓から押して最後まで流す | 模型が要る |
| test_device | 描く（描く場所の選び） | 偽物 | cpudtype, membudget | 要る | GPU の無い機械で描けるかの分かれ目 | 0.1 秒 4 件 通った |
| test_director | 精度優先の工程の記録 | 本物 | phases | まとめる（phases） | 工程の記録を phases と二重に見る | 模型が要る |
| test_draw_api | 描く（筆の入力） | 本物 | brushtools | まとめる（brushtools） | 同じ筆の経路を API の口から見る | 0.2 秒 5 件 通った |
| test_drawbugs | 描く（模型ごとの読む・描く道） | 偽物 | quality_fix, perfamily | 要る | 模型ごとに渡る部品と引数を見る唯一の所 | 9.3 秒 15 件 通った |
| test_editing | 加工・あとからの直し | 偽物 | finish2, nobreak | まとめる（finish2） | 加工の流れを finish2 と二重に見る | 3.2 秒 16 件 通った |
| test_ensemble | 無し（重ねの並べ方） | 偽物 | - | 要らない | 利用者の窓から届かない道具の単体 | 0.9 秒 11 件 通った |
| test_extensions | 拡張の取り込み | 偽物 | chara3d | 要る | 拡張の口が本体で働くかを見る唯一の所 | 2.4 秒 8 件 通った |
| test_extra_items | 検品（頼んでいない服） | 本物 | unasked_wear, held_items | まとめる（held_items） | タグからの拾い方が 3 か所に分かれている | 0.2 秒 4 件 通った |
| test_eyes_under_bangs | 検品（目） | 本物 | face_check | まとめる（face_check） | 1 つの絵の形だけ | 0.6 秒 2 件 通った |
| test_face_check | 検品（顔） | 本物 | face_mask, eyes_under_bangs | 要る | 顔の検品の本体 | 0.2 秒 9 件 通った |
| test_face_mask | 検品（顔の範囲） | 本物 | face_check | まとめる（face_check） | 部品の単体 | 0.5 秒 2 件 通った |
| test_face_redraw_pipe | 赤ペンで直す（顔の描き直し） | 本物 | redpenfix | まとめる（redpenfix） | 別の模型を読まない 1 件だけ | 0.1 秒 1 件 通った |
| test_faceform_fit | 検品（顔の形） | 本物 | face_check | まとめる（face_check） | 部品の単体 | 0.8 秒 3 件 通った |
| test_favmodels | 模型を選ぶ（お気に入り） | 偽物 | modelmgr, modelblock | 要る | 役目ごとの模型を窓から選ぶ | 8.8 秒 15 件 通った |
| test_features | タイムラプス・SNS・音声・3D の入口 | 偽物 | detailtimelapse, voicechat | まとめる（detailtimelapse） | 入口があるかを偽物で見るだけ | 23.6 秒 7 件 通った |
| test_feet_count | 検品（足の指） | 本物 | finger_count | まとめる（finger_count） | 指を数える試験を 1 つに | 3.2 秒 4 件 通った |
| test_fetchfile | 模型を取る（続きから・回数） | 本物 | shared_models | 要る | 取り直しの経路を本物の部品で見る | 2.2 秒 4 件 通った |
| test_finger_count | 検品（手の指） | 本物 | feet_count, outside_checks | 要る | 指は毎回数える決まりの本体 | 0.4 秒 7 件 通った |
| test_finish2 | 加工（メニューから） | 偽物 | editing, nobreak, finish_quality | 要る | 加工のメニューを押して最後まで流す | 8.5 秒 7 件 通った |
| test_finish_big | 加工（大きな絵） | 本物 | finish_quality | まとめる（finish_quality） | 大きな絵の加工を二重に見る | 23.2 秒 9 件 通った |
| test_finish_quality | 加工（綺麗にする・画風） | 偽物 | nobreak, finish_big | 要る | 元の絵を崩さないかを画素で見る | 31.2 秒 35 件 通った |
| test_fix_tool | 赤ペンで直す（部分の描き直し） | 偽物 | loop, redpenfix | まとめる（redpenfix） | tools/gen の道具の単体 | 2.0 秒 8 件 通った |
| test_fixrequests | 赤ペンで直す（整える・消す） | 偽物 | redpenfix, nobreak | 要る | 窓から押して直しを通す | 模型が要る |
| test_fixwords | 赤ペンで直す（渡る言葉） | 偽物 | redpenfix | 要る | 直しの指示が模型に届くかを言葉で見る | 4.3 秒 14 件 通った |
| test_folders_ratings | 模型を選ぶ（点・タグ） | 偽物 | modelmgr, favmodels | まとめる（modelmgr） | 点とタグの保存を偽物で見る | 0.3 秒 4 件 通った |
| test_folds | 無し（しわの置き場） | 本物 | - | 要らない | 利用者の操作に繋がらない部品の単体 | 0.3 秒 8 件 通った |
| test_free_dict | 描く言葉（模型が無いとき） | 本物 | words | まとめる（words） | 訳の表を words と二重に見る | 0.3 秒 2 件 通った |
| test_freeze | 固まらない（全般） | その時だけ | bughunt, works | まとめる（works） | 直す前の形の再現の寄せ集め | 3.6 秒 9 件 通った |
| test_gate | 精度優先の工程（関所） | 偽物 | phases | まとめる（phases） | 工程の受け入れを偽物で見るだけ | 19.2 秒 7 件 通った |
| test_gen_modes | 描く（モードの門） | 本物 | modes | まとめる（modes） | モードの分かれ目を二重に見る | 0.1 秒 5 件 通った |
| test_hair_spec | 検品（髪の色） | 本物 | - | まとめる（検品の測りを 1 つに） | 1 つの形だけ | 0.5 秒 2 件 通った |
| test_hand_shift | 検品（手の枠） | その時だけ | hands_auto | まとめる（hands_auto） | 1 つの絵のずれだけを固定 | 0.2 秒 2 件 通った |
| test_handdraw_paint | 精度優先（塗りの段） | 本物 | phases | まとめる（phases） | 工程の 1 段の単体 | 0.4 秒 4 件 通った |
| test_hands_auto | 検品（手の枠） | 偽物 | hand_shift | まとめる（finger_count） | 手の検品の部品 | 0.2 秒 4 件 通った |
| test_hands_unavailable | 検品（読めない手） | 偽物 | origqc | 要る | 読めない絵を崩れとして扱う決まりの見張り | 0.2 秒 3 件 通った |
| test_headless | 描く（画面の部品なし） | 本物 | bundle | 要る | 描く処理が PySide6 無しで import できるか | 0.3 秒 3 件 通った |
| test_heads_tall | 検品（頭身） | 本物 | body_hands | まとめる（body_hands） | 同じ頭身の測り | 0.8 秒 2 件 通った |
| test_held_items | 検品（持ち物） | 本物 | count_extra, extra_items | 要る | 持ち物の検品の本体 | 0.3 秒 10 件 通った |
| test_hub_defaults | 模型を取る（既定） | ソース | shared_models | 要らない | ソースの順番を読むだけ。置き場は shared_models が見る | 0.1 秒 1 件 通った |
| test_imgproc | 加工（画像処理） | 本物 | imgproc_clean, imgproc_color | 要る | 加工の部品の本体で画素を見る | 1.4 秒 13 件 通った |
| test_imgproc_clean | 加工（ノイズ・ぼかし） | 本物 | imgproc | まとめる（imgproc） | 同じ imgproc | 1.0 秒 2 件 通った |
| test_imgproc_color | 加工（色） | 本物 | imgproc | まとめる（imgproc） | 同じ imgproc | 0.3 秒 7 件 通った |
| test_import_character_designer | 入れる（前の版からの引き継ぎ） | 本物 | keepsettings, shared_models | 要る | lessons の「置き場が空」を止める | 0.2 秒 2 件 通った |
| test_inspect_image | 検品（単独） | ソース | qcmanual | まとめる（qcmanual） | 検品の口をソースと単体で見る | 0.1 秒 4 件 通った |
| test_inspect_limbs | 検品（手足の数） | 本物 | legcount, outside_checks | まとめる（outside_checks） | 作り物の部位分けだけ | 0.3 秒 2 件 通った |
| test_iris_delta | 検品（瞳の色） | 本物 | face_check | まとめる（face_check） | 部品の単体 | 0.2 秒 4 件 通った |
| test_joints | 検品（関節） | 本物 | pose_missing | まとめる（pose_missing） | 部品の単体 | 0.3 秒 2 件 通った |
| test_kakou | 加工（画風の目録） | 本物 | finish2 | 要る | 加工の目録と漫画・線画の出力を見る | 3.1 秒 9 件 通った |
| test_keep_marks | 検品（外れた絵を残す） | ソース | original_qc | まとめる（original_qc） | 残し方をソースの文字で見る所が混ざる | 0.2 秒 13 件 通った |
| test_keepsettings | 更新（設定を引き継ぐ） | 偽物 | import_character_designer | 要る | 版をまたいで設定が残るかを見る唯一の所 | 0.2 秒 6 件 通った |
| test_layercrash | レイヤー | 本物 | layertools, canvasfix | 要る | 利用者と同じボタン・キーで押して落ちないか | 5.7 秒 8 件 通った |
| test_layerkeep | レイヤー・作業ファイル | 偽物 | aitabs, uifix | 要る | 閉じて開き直しても戻るかを見る | 模型が要る |
| test_layertools | レイヤー（コピー・反転） | 本物 | layercrash | 要る | 画素で結果を見る | 5.1 秒 9 件 通った |
| test_legacy_project | 作業ファイルの読み込み（前のアプリ） | 本物 | aitabs | 要る | .cdproj を開いて上書きしないかを見る | 0.2 秒 3 件 通った |
| test_legcount | 検品（脚） | 本物 | qc_legs | まとめる（qc_legs） | 同じ脚の数え方 | 0.4 秒 1 件 通った |
| test_legs_fused | 検品（脚） | 本物 | qc_legs | まとめる（qc_legs） | 同じ脚の検品 | 0.4 秒 3 件 通った |
| test_light_upscale | 加工（光・拡大） | 本物 | finish_big | まとめる（finish_big） | 部品の単体 | 0.3 秒 4 件 通った |
| test_limb_shadow | 検品（手足の影） | 本物 | - | まとめる（検品の測りを 1 つに） | 部品の単体 | 0.7 秒 3 件 通った |
| test_lineart | 加工（線画の清書） | 本物 | cleanup | 要る | 線画の清書の本体で画素を見る | 0.6 秒 9 件 通った |
| test_local_llm | チャット（手元の言葉の模型） | 偽物 | chatbrain | 要る | 言葉の模型の窓口を見る唯一の所 | 2.7 秒 9 件 通った |
| test_logo | 描く（ロゴ・スタンプ） | 偽物 | - | 要る | 模型の要らない処理は本物の画素で見る | 4.4 秒 13 件 通った |
| test_loop | 検品（直して検品し直す） | 偽物 | phases, fix_tool | まとめる（phases） | 検品を回す流れを二重に見る | 0.8 秒 5 件 通った |
| test_lora | 模型を使う（LoRA・学習セット） | 偽物 | ownstyle | 要る | 窓から押して最後まで通す | 0.9 秒 9 件 通った |
| test_membudget | 描く（メモリの予算） | 偽物 | memory, device | 要る | 落ちないための予算の計算を数字で見る | 1.3 秒 25 件 通った |
| test_memory | 描く（途中で落ちない） | 偽物 | membudget, pause | 要る | 描いている途中の落ちを窓で見る | 模型が要る |
| test_menuaudit | 右クリックのメニュー | 偽物 | menuedit, shortcuts | まとめる（shortcuts） | 右クリックの項目を二重に見る | 模型が要る |
| test_menuedit | メニューと帯の編集 | 偽物 | panels | 要る | 帯の出し入れを見る | 11.1 秒 10 件 通った |
| test_mirrorcheck | 検品（映り込み） | 本物 | qcmanual | 要る | 検品から赤ペンの印まで通す | 1.0 秒 9 件 通った |
| test_modelblock | 模型を選ぶ（非表示・ブロック） | 偽物 | favmodels, modelmgr | 要る | 外した模型が一覧・おまかせから消えるか | 0.4 秒 6 件 通った |
| test_modeldoc | 無し（docs と目録の一致） | ソース | - | 要らない | 文書の一致で、docs_check の仕事 | 0.2 秒 8 件 通った |
| test_modelmgr | 模型を選ぶ（管理） | 偽物 | favmodels, catalog | 要る | 模型の管理の窓 | 0.6 秒 13 件 通った |
| test_modelprune | 模型を選ぶ（一覧に出す物） | 偽物 | modelmgr | まとめる（modelmgr） | 一覧の剪定を二重に見る | 0.2 秒 6 件 通った |
| test_models | 模型を選ぶ（一覧と切り替え） | 偽物 | modelmgr | まとめる（modelmgr） | 偽の .safetensors で一覧を見る | 0.2 秒 7 件 通った |
| test_modes | 描く（モード・一括生成） | 偽物 | backui, gen_modes | 要る | 窓から押して最後まで通す | 4.2 秒 5 件 通った |
| test_module_paths | 起動（データの道） | ソース | crossrefs | 要る | lessons の道のずれを止める | 0.2 秒 1 件 通った |
| test_nobreak | 加工（壊さない） | 偽物 | finish_quality | まとめる（finish_quality） | 元を壊さないかを二重に見る | 模型が要る |
| test_nojson | 描く（保存先に絵だけ） | 偽物 | - | 要る | 保存の置き場を見る | 0.2 秒 4 件 通った |
| test_normlearn | 検品（基準の学習） | 本物 | original_qc | まとめる（original_qc） | 作り物の記録で学び方を見る | 0.2 秒 7 件 通った |
| test_not_solo | 検品（2 人目） | 本物 | outside_checks | まとめる（outside_checks） | 同じ 2 人目の検品 | 0.3 秒 3 件 通った |
| test_occlusion | 検品（隠れた手） | 本物 | - | まとめる（検品の測りを 1 つに） | 部品の単体 | 0.2 秒 9 件 通った |
| test_omakase | 描く（おまかせ） | 偽物 | phases, variety | 要る | 工程ごとの模型の選びを見る | 1.0 秒 16 件 通った |
| test_original_finish | 加工（仕上げ） | 偽物 | finish_quality | まとめる（finish_quality） | 仕上げの部品の単体 | 1.8 秒 7 件 通った |
| test_original_qc | 検品（作画監督） | 偽物 | origqc, keep_marks | 要る | 検品の本体 | 0.4 秒 15 件 通った |
| test_origqc | 検品（検品不能） | その時だけ | hands_unavailable | まとめる（hands_unavailable） | 1 回の回帰だけ | 0.2 秒 2 件 通った |
| test_outside_checks | 検品（模型の外） | 偽物 | not_solo, finger_count | 要る | 模型の外の検品の本体 | 0.4 秒 12 件 通った |
| test_ownstyle | 模型を使う（自分の作風） | 偽物 | lora | まとめる（lora） | LoRA の重ね外しを二重に見る | 0.3 秒 4 件 通った |
| test_paint_tools | 加工（空気感・線） | 本物 | lineart | まとめる（lineart） | 部品の単体 | 0.7 秒 5 件 通った |
| test_panels | 欄の出し入れ | 偽物 | aiui, stop | 要る | 欄の出し入れを窓で見る | 模型が要る |
| test_pause | 描く（一時停止） | 本物 | memory | 要る | 打ち切りを捨てずに止めるかを窓で見る | 模型が要る |
| test_perfamily | 描く言葉（模型ごとの頼み方） | 偽物 | drawbugs | 要る | 模型ごとの言葉を見る | 0.2 秒 13 件 通った |
| test_phases | 描く（精度優先の工程） | 偽物 | director, gate, pipeline | 要る | 精度優先の流れの本体（模型は偽物） | 13.5 秒 31 件 通った |
| test_photoreal | 加工（写真級） | ソース | - | 要る | 写真級の部品の本体。ソースを読む所は外してよい | 2.4 秒 34 件 通った |
| test_pick_pose | 無し（下絵を選ぶ） | 本物 | - | 要らない | 窓から届かない道具の単体 | 0.2 秒 2 件 通った |
| test_pieces | 検品（途中切れ） | 本物 | count_extra | まとめる（held_items） | 持ち物の検品を 1 つに | 0.2 秒 3 件 通った |
| test_pipeline | 精度優先の工程（やり直し） | ソース | phases | まとめる（phases） | 工程のやり直しを二重に見る | 0.1 秒 4 件 通った |
| test_pose_hands | 検品（手の姿勢） | 本物 | pose_missing | まとめる（pose_missing） | 同じ姿勢の検品 | 0.2 秒 5 件 通った |
| test_pose_missing | 検品（姿勢） | 本物 | pose_hands | 要る | 頼んだ姿勢が出たかの本体 | 0.3 秒 5 件 通った |
| test_presetui | プリセット・チャット | 偽物 | chatplan | まとめる（chatplan） | プリセットを二重に見る | 模型が要る |
| test_proportions | 検品（体の比） | 本物 | skeleton | まとめる（skeleton） | 同じ骨の比 | 0.6 秒 4 件 通った |
| test_pull | 描く（前の頼みに引っ張られない） | 偽物 | variety | 要る | 新しく描く頼みが渡る言葉を見る | 6.5 秒 8 件 通った |
| test_qc | 検品（下ごしらえ） | 本物 | qc_counts | まとめる（qc_counts） | 部品の単体 | 0.5 秒 8 件 通った |
| test_qc_counts | 検品（崩れの数） | 本物 | qc | 要る | 崩れの数を本当の数にする本体 | 0.5 秒 3 件 通った |
| test_qc_legs | 検品（脚） | 偽物 | legcount, legs_fused | 要る | 脚の検品の本体 | 0.9 秒 35 件 通った |
| test_qc_scars | 検品（描き直しの跡） | 本物 | fix_tool | 要る | 跡の検品の本体 | 0.4 秒 5 件 通った |
| test_qc_seams | 検品（背景の継ぎ目） | 本物 | - | まとめる（検品の測りを 1 つに） | 部品の単体 | 1.5 秒 4 件 通った |
| test_qc_tiles | 検品（拡大升目） | 本物 | - | まとめる（検品の測りを 1 つに） | 部品の単体 | 0.5 秒 1 件 通った |
| test_qcbench | 検品（精度の台） | 偽物 | bench | 要る | 検品の精度を数字で測る台 | 0.4 秒 29 件 通った |
| test_qcmanual | 検品（手で呼ぶ） | 偽物 | mirrorcheck, inspect_image | 要る | 窓から押して検品を通す | 模型が要る |
| test_qcparts | 検品（部品の名前） | ソース | qcparts_ui | まとめる（qcparts_ui） | 名前の一致をソースで見る | 0.1 秒 3 件 通った |
| test_qcparts_ui | 模型を取る（検品の部品） | 偽物 | qcparts | 要る | 初回の取得と取り直しを窓で見る | 1.0 秒 5 件 通った |
| test_quality | 描く（模型の外の質） | 偽物 | quality_fix | まとめる（quality_fix） | 質の処理を二重に見る | 0.5 秒 20 件 通った |
| test_quality_fix | 描く（質を下げていた所） | 偽物 | drawbugs | まとめる（drawbugs） | 模型の構成の取り違えを二重に見る | 0.9 秒 10 件 通った |
| test_ratefreeze | 模型を選ぶ（評価） | 偽物 | folders_ratings | 要る | 評価で固まらないかを窓で見る | 模型が要る |
| test_record_policy | 無し（記録の言い回し） | ソース | - | 要らない | 文書の検査で precheck の仕事 | 0.2 秒 2 件 通った |
| test_redpen3 | 赤ペンで直す（レイヤー・確定） | 偽物 | canvasfix, redpenfix | 要る | 赤ペンのレイヤーの本体 | 模型が要る |
| test_redpenfix | 赤ペンで直す（囲んで直す） | 本物 | redpen3, fixrequests | 要る | 囲み、指示、直すを窓から押す | 模型が要る |
| test_redpeninput | 赤ペン（指示の欄） | 本物 | typeguard | まとめる（typeguard） | 打った文字が取られない見張りを 1 つに | 3.9 秒 8 件 通った |
| test_retouch | 加工（レタッチ） | 本物 | imgproc | まとめる（imgproc） | 部品の単体 | 0.7 秒 11 件 通った |
| test_ribbonfamily | リボンの道具 | 本物 | viewtools | まとめる（viewtools） | リボンを二重に見る | 2.9 秒 6 件 通った |
| test_rom | 拡張（3D の関節） | 本物 | chara3d | まとめる（chara3d） | 3D の部品の単体 | 0.1 秒 6 件 通った |
| test_sanity | 描く言葉・検品（あり得ない絵） | 偽物 | baseline | 要る | 打ち消しと検品の本体 | 8.2 秒 13 件 通った |
| test_scene_light | 検品（光の食い違い） | 本物 | - | まとめる（検品の測りを 1 つに） | 部品の単体 | 0.6 秒 7 件 通った |
| test_sent | 描く（渡した言葉を見せる） | 本物 | - | 要る | 模型に渡した言葉を窓で見る | 1.1 秒 3 件 通った |
| test_settei | 無し（設定画の表） | 本物 | sheet_formats | まとめる（sheet_formats） | 設定画の部品を 1 つに | 0.2 秒 3 件 通った |
| test_shapeassist | 描く（図形・定規・手ぶれ） | 本物 | brushtools | 要る | 筆の補助を画素で見る | 9.1 秒 19 件 通った |
| test_shared_models | 模型を使い回す | 偽物 | fetchfile, import_character_designer | 要る | 使い回しを見る唯一の所 | 0.5 秒 8 件 通った |
| test_sheet_formats | 無し（設定画の版） | 本物 | settei | まとめる（build） | データのファイルが読めるかだけ | 0.1 秒 10 件 通った |
| test_shortcuts | 右クリック・ショートカット | 偽物 | menuaudit | 要る | 項目を押して最後まで流す | 模型が要る |
| test_skeleton | 検品（骨の比） | 本物 | proportions | 要る | 骨の比の本体 | 0.2 秒 4 件 通った |
| test_skin_grain | 検品（肌のざらつき） | 本物 | - | まとめる（検品の測りを 1 つに） | 部品の単体 | 1.0 秒 4 件 通った |
| test_stop | 緊急停止・進み | 本物 | panels | 要る | 止める操作を窓で見る | 模型が要る |
| test_stray_color | 検品（頼んでいない色） | 本物 | - | まとめる（検品の測りを 1 つに） | 部品の単体 | 0.5 秒 6 件 通った |
| test_structure | 無し（置き場の決まり） | ソース | - | 要らない | 文書の決まりで docs_check の仕事 | 0.7 秒 5 件 通った |
| test_tabkey | キー操作（Tab） | 本物 | typeguard | まとめる（typeguard） | キーの見張りを 1 つに | 1.6 秒 3 件 通った |
| test_toneshade | 加工（段の影） | 本物 | - | まとめる（imgproc） | 部品の単体 | 0.6 秒 2 件 通った |
| test_toplayer | AI の結果をレイヤーの一番上へ | 偽物 | redpen3 | 要る | 全部の経路で一番上に置くかを見る | 2.8 秒 8 件 通った |
| test_typeguard | キー操作（打つ欄） | 本物 | redpeninput, tabkey | 要る | 打った文字が取られない見張り | 1.9 秒 7 件 通った |
| test_uifix | チャット・レイヤー・ライブラリー | その時だけ | layerkeep, voicechat | まとめる（layerkeep） | 回帰の寄せ集め | 模型が要る |
| test_unasked_wear | 検品（頼んでいない服） | 本物 | extra_items | まとめる（held_items） | タグの拾いを 1 つに | 0.2 秒 3 件 通った |
| test_usability | 選択（投げなわ・多角形） | 本物 | - | 要る | 画面の道具から押して画素で見る | 3.7 秒 8 件 通った |
| test_variety | 描く（似た絵にしない） | 偽物 | pull, omakase | 要る | 種と模型の選びを見る | 0.2 秒 10 件 通った |
| test_version | 更新（版の番号） | ソース | build | まとめる（build） | 版の番号は組むときに見る | 0.1 秒 1 件 通った |
| test_video_io | 無し（動画の読み書き） | 本物 | detailtimelapse | まとめる（detailtimelapse） | タイムラプスの部品 | 0.1 秒 1 件 通った |
| test_viewtools | 表示（回転・拡大） | 本物 | ribbonfamily | 要る | 表示の操作を窓で押して見る | 5.1 秒 11 件 通った |
| test_voicechat | チャット・音声入力 | 偽物 | chatbrain | 要る | チャットの操作を窓で見る | 模型が要る |
| test_weighted_prompt | 描く言葉（重み） | 本物 | composition | まとめる（composition） | 模型に渡る言葉を 1 つに | 0.1 秒 3 件 通った |
| test_words | 描く言葉（頼みの読み取り） | 偽物 | free_dict | 要る | 日本語の頼みを描く言葉に直す本体 | 模型が要る |
| test_works | 押して最後まで動く（全般） | 偽物 | bughunt, freeze | 要る | 押して動くかを窓で見る寄せ集めの受け皿 | 模型が要る |
| test_zukan | 無し（図鑑のまとめ） | 本物 | - | 要らない | 窓から届かない道具の単体 | 0.2 秒 1 件 通った |