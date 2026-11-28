# 考える役の模型

- 日付: 2026-11-28
- 語: 思考,VLM,絵を読む,Qwen3.5,mmproj,llama.cpp,考える役,Florence-2,MiniCPM-V,Qwen2.5-VL

## 情報

見た日はどれも 2026-11-28 です。

- AtelIer の言葉の模型は llama-cpp-python の `Llama(model_path=...)` だけで読んでいる。mmproj（絵を読む部品）は読んでいない（`atelier/ai/engine.py` の `_llm_for`。コードを読んで確かめた）。Ollama・LM Studio・OpenAI 互換の窓口を使うコードは見当たらなかった（atelier の中を grep で確かめた）
- 目録の言葉の模型は Qwen3.5 0.8B・2B・4B、Gemma 4 E2B・E4B など（`atelier/models/catalog.py`）
- unsloth/Qwen3.5-4B-GGUF には mmproj-F16.gguf（672MB）と mmproj-BF16.gguf（676MB）があり、ライセンスは Apache-2.0。最後の更新は 9 か月前。出所: https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/tree/main
- Qwen3.5 の小さい模型の gguf は、mmproj を一緒に置いて llama.cpp の `--mmproj` で絵を読める。出所: https://huggingface.co/leok7v/Qwen3.5-2B 、https://huggingface.co/prithivMLmods/Qwen3.5-9B-MTP-GGUF （どちらも第三者の版で、公式のカードは見ていない）
- Qwen2.5-VL-7B-Instruct は Apache-2.0（2025-01-26 公開）。Florence-2 は MIT。Llama 3.2 Vision 11B は Llama 3.2 Community License で、EU での多モーダルの使用に制限がある。出所: https://blog.roboflow.com/local-vision-language-models/ 、https://www.koyeb.com/blog/best-multimodal-vision-models-in-2025 （一次の文書は見ていない）
- MiniCPM-V 4.5 のライセンスは、この回の検索では取れなかった
- Qwen2.5-VL 3B のライセンスは、この回の検索では取れなかった（7B と違う独自の許諾だった覚えがあるが、確かめていない）

## 知識

- 考える役に要るのは 2 つです。絵を読むこと（どこが崩れたか、どこが影か）と、決まった形で答えること（面・強さ・直し方）です。言葉だけの模型では絵を読めないので、絵の判断は数字の検品に頼るしかありません
- 推奨は Qwen3.5 4B に mmproj を足す形です。理由は次の 4 つです
  - 目録に既にある言葉の模型と同じ物なので、読み込みの経路（llama-cpp-python、C:\LLM）を増やさずに済みます
  - mmproj の 672MB を足すだけで済み、別の模型を重ねて入れません
  - Apache-2.0 です
  - 日本語で答えられます
- 代わりの候補は次の 3 つです
  - Florence-2（MIT、0.23B・0.77B）は速く、枠と説明を返します。ただし考える力は無く、決まった問い（物の場所、説明）にしか答えません。検品の補いには使えます
  - Qwen2.5-VL 7B は読む力が高いものの、CPU では遅くなります（測っていない）
  - Llama 3.2 Vision 11B は大きく、EU の制限があるので取りません
- 使えない場合があります。CPU だけの機械で 4B の VLM に 1 枚読ませると数十秒かかる見込みです（測っていない）。そのときは工程ごとに 1 回だけ読ませ、数字の検品で足りる所は読ませません
- 思考の模型の答えは、間違える前提で扱います。決まった形に合わない答えは捨て、数字の検品と食い違ったら数字の方を取ります。頼みに無い語は描く模型に渡しません

## アルゴリズム

入力は、頼みの訳、工程の名前、前の工程の絵（長い辺を 768 に縮めたもの）、検品の結果（枠と数字）、手法の表の段です。
出力は、その段の設定（JSON の欄: phase、faces、colors、light、brush、mask、strength、fix）です。

1. 思考の模型があり、mmproj が読めるかを見る。無ければ 6 に進む
2. 描く前に、絵と検品の結果と手法の表の段の幅を渡し、段の設定を JSON で答えさせる。言葉の欄は渡さず、選ばせない
3. 答えを確かめる。形に合わない答え、表の幅の外の値、絵の外の囲み、頼みに無い語を含む答えは捨てて 6 に進む
4. 描いた後に、前と後の絵と検品の結果を渡し、崩れと直し方（move、rotate、paste、erase_redraw、none）を答えさせる
5. 数字の検品と照らす。数字で崩れがあるのに none と答えたら、数字の方を取る
6. 代わりの手順に進む。手法の表の初めの値と、検品の数字から決めた直し方を使う
7. 決めた設定と、その出どころ（思考の模型か代わりの手順か）を phases.json に残す

端の場合は次のとおりです。
- 模型が答えない（時間切れ 60 秒、私の推測）ときは 6 に進む
- 絵が大きすぎるときは縮める
- 答えが日本語の頼みを英語の語に置き換えようとしたときは、その欄を捨てる

費用は、1 工程につき描く前と描いた後の 2 回の推論です。1 回の秒数は測っていません。

## 技術
<!-- まだ作っていない。この回は調べと設計だけ。作る場所の予定は atelier/ai/thinker.py（思考の模型への問いと答えの確かめ）と、engine.py の mmproj の読み込み。テストは test_thinker.py（形に合わない答え・頼みに無い語を捨てるか） -->

## 実装
<!-- まだ当てていない -->
