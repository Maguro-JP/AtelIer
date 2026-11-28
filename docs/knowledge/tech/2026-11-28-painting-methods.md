# 塗りの手法と工程

- 日付: 2026-11-28
- 語: 塗り,水彩,油絵,厚塗り,アニメ塗り,ガッシュ,アクリル,グレージング,ウェット・イン・ウェット,painterly,stroke-based,消しゴム

## 情報

見た日はどれも 2026-11-28 です。

- 水彩は透明で、暗くした所を明るく戻せないので、明るい所から暗い所へ、大きい形から小さい形へ進める。グレージングは乾いた層の上に透明な層を重ねる（wet on dry）。ウェット・イン・ウェットは濡れた紙に置いて混ぜ、乾き方がずれるとブルーム（硬い縁のむら）が出る。出所: https://www.paintingwithwatercolors.com/2011/01/how-to-paint-watercolor-paintings/ 、https://www.creativebloq.com/how-to/create-glazes-with-watercolour 、https://danielsmith.com/tutorials/extra-fine-watercolors/four-basic-watercolor-washes/ （3 つの出所で一致）
- 油絵は fat over lean（下の層ほど油が少なく、上ほど多い。逆だと割れる）。ブロックインは暗い所 → 中間 → 一番明るい所の順に置く出所と、逆の出所がある。向きは層を通して揃える。アラプリマは乾かさずに濡れた上へ描く直接法。出所: https://www.naturalpigments.com/artist-materials/simple-rules-oil-painting 、https://drawpaintacademy.com/alla-prima-painting-tips/ 、https://finearttutorials.com/guide/how-to-start-an-oil-painting/
- ガッシュとアクリルは不透明なので、暗い所から明るい所へ置け、明るい色を暗い色の上に重ねられる。大きい平筆で大きい面、小さい丸筆で細部。出所: https://www.gathered.how/arts-crafts/art/painting/how-to-paint-with-gouache 、https://www.creativebloq.com/illustration/how-paint-gouache-21619154
- アニメ塗りは、線画 → ベタの下塗り（部位ごと、クリッピング）→ 光源を決める → 影 1〜2 段（同じ色相で暗く彩度を上げた硬い縁の形）→ ハイライト。色ごとに 2〜3 段。出所: https://www.clipstudio.net/how-to-draw/archives/162911 、https://www.clipstudio.net/oekaki/archives/153260 、https://graphixly.com/blogs/news/tips-for-cel-shading
- 厚塗りは、大きく形を取って色を置き（色置き）、描き込みのブラシで面を重ねて形を出し、境を馴染ませ、最後にブレンドモードで色味を整える。ブラシは 2〜3 種に絞る。出所: https://www.clipstudio.net/oekaki/archives/152679 、https://www.clipstudio.net/oekaki/archives/169396 、https://www.clipstudio.net/oekaki/archives/151840 （グリザイユ）
- 既にある知識: 人のアニメ塗りの工程とレイヤーの分け方は `docs/knowledge/painting-workflow.md`、精度優先の工程は `docs/knowledge/drawing-phases.md`
- img2img の strength は加える雑音の量で、大きいほど元から離れる。inpaint の強さは 0.5 前後から始める例が多い。ControlNet tile は強さを上げても元の中身を保つ。出所: https://huggingface.co/docs/diffusers/main/en/api/pipelines/stable_diffusion/img2img.md 、https://stable-diffusion-art.com/?p=6941
- ストロークで描く研究: Paint Transformer（ICCV 2021、筆の組を一度に予測する。公式は PaddlePaddle、Apache-2.0）https://arxiv.org/abs/2108.03798 、https://github.com/wzmsltw/PaintTransformer 。Learning to Paint（ICCV 2019、強化学習と微分できる描画器、MIT）https://github.com/megvii-research/ICCV2019-LearningToPaint 。どちらも最後のコミットの日付は見ていない
- 確かめていない: 消しゴムでなぞって消す人の手順（練り消しで軽く叩く、線に沿って消す）は、この回の検索で出所を取れていない

## 知識

- どの手法でも、順は「大きい面 → 小さい面」「太い筆 → 細い筆」「境の柔らかい物 → 硬い物」です。変わるのは明暗の向きだけです
  - 透明な画材（水彩、グレージング、乗算の影）は明るい → 暗い。上の層は下を暗くしかできないので、明るさは最初に残す
  - 不透明な画材（油絵の不透明な描き方、ガッシュ、アクリル、デジタルの厚塗り）は暗い（または中間）→ 明るい。一番明るい所は最後に置く
  - アニメ塗りはベタの固有色 → 影（乗算・暗く）→ ハイライト（加算・明るく）で、層ごとに向きが決まっている
- 重ねるとき、上の層は下の層より面が小さい。面が下より広い層は、下で決めた形を壊す（このリポジトリで絵全体の描き重ねが色と形を変えた件と同じ理由）
- 層の数はおよそ 3〜5 です。アニメ塗りは色ごとに 2〜3 段、水彩は 3〜5 回のウォッシュ、油絵はブロックイン・中間・明部・仕上げ
- 使えない場合: 写真や 3D の描き直し（光が物理で決まる）、ドット絵（減色を最後に掛ける別の工程）。明暗の向きを出所が逆に言う所（油絵のブロックイン）は、手法の既定として選ぶ値で、正解ではない

## アルゴリズム

入力: 線画の工程が終わった絵、部位分け（`phase_tools.parts`）、光源（`phase_tools.light`）、手法（anime、brush、watercolor、oil、gouache）。
出力: 段ごとの絵（隠したレイヤー）と、段ごとの数字。

1. 面を取る。部位分けの面を面積の大きい順に並べる。読めなければ、色を減らした塊（`brush_reveal` の平塗りの塊と同じ取り方）で代える
2. 下塗り（全手法）。面ごとに固有色の平均を 1 色置く。模型は使わず処理で置く（強さ 0）
3. 手法の表（`drawing-phases.md` の「塗りの手法と工程」）の段を順に行う。段ごとに、囲み = その段の面の和、筆の大きさ = 短い辺 × 段の比、強さ = 段の値で、囲みの中だけを描き重ね、外を元の画素に戻す（`phases._inside` と同じ合成）
4. 段のあとに数字を測る（明暗の幅、色の数、縁の硬さ、囲みの外の差、前の段との差）。前の段で決めた物（固有色の色相、影の形）が崩れたら、その面だけを消して描き直す
5. 消して描き直す: 消す所は崩れた画素の 1 画素幅の帯だけにし、消しゴムの筆跡（線に沿う道）でなぞってから、同じ段の筆で描き直す
6. 次の段へ。最後の段のあとに全体の確かめ（縮めた明暗、反転）を通す

端の場合: 部位分けが空（全体を 1 面とし、段の囲みを明暗の閾で作る）。面が絵の半分を超える（その段だけ強さを半分にする）。光源が読めない（上から左の既定を使い、私の推測と記録する）。
費用: 段の数 × 面の数の描き重ね。囲みが小さいので 1 回は全体の描き重ねより短い（測っていない）。

## 技術
<!-- まだ作っていない。この回は調べと設計だけで、実装は別の作業で行う（phases.py を直している作業と重ねないため）。作る場所の予定は paint_methods.py（手法の表）と phase_tools.py（面の取り出しと段の数字）、テストは test_paint_methods.py -->

## 実装
<!-- まだ当てていない -->
