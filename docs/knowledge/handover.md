# CharacterDesigner からの引き継ぎの一覧

2026-11-21 時点。流用元は CharacterDesigner の main（コミット 4a9e809）。AtelIer 側は PR #1 のブランチにあります。

## キャラクターデザインの分け方（2026-11-21 に済ませた）

- キャラクターデザインは CharacterDesigner の拡張 `character_designer/` になりました（AtelIer の `atelier/chara/` から移した 5 ファイル）。CharacterDesigner の `pyproject.toml` が AtelIer を依存に持ち、entry points の `atelier.extensions` で窓に付きます
- CharacterDesigner の `chatdraw/` は AtelIer と重複するので消しました。キャラクターデザインのテスト（`test_charafile`、`test_modes` と `test_lora` と `test_original_finish` のキャラクターデザインの部分）も CharacterDesigner の `tests/` に移しました
- AtelIer からは `atelier/chara/`、`bible/`、`designs/`、`templates/`、`tools/showcase.py` を消しました

## CharacterDesigner に残す物

- キャラクターデザインの拡張: `character_designer/`
- `bible/`、`characters/`、`library/`、`designs/`、`templates/`、`docs/`、`.github/`、`packaging/`、`tests/`（道具とキャラクターデザインの試験）
- `tools/` と `casts/` と `styles/` と `config/` のうち、下の「両方にある」に無いファイル

## AtelIer に移した（146 ファイル。置き場の対応は docs/STRUCTURE.md）

`chatdraw/` のうち、上の「残す物」以外の全部です。テストは `chatdraw/tests/` の 85 ファイルを `tests/` に移しました。

## 両方にある（79 ファイル。AtelIer が写しを持っている）

キャラクターデザインの道具も読むので、CharacterDesigner から消すかは 1 つずつ決めます。

- `casts/body-plans.json`
- `casts/body-types.json`
- `casts/brushes.json`
- `casts/demi3d.json`
- `casts/demihuman-cards.json`
- `casts/free-words.json`
- `casts/patterns.json`
- `casts/poses.json`
- `casts/rom.json`
- `config/draw-request.json`
- `config/verify-models.txt`
- `styles/anime-norms.json`
- `styles/baseline.json`
- `styles/draw-bias.json`
- `styles/face-template.json`
- `styles/genres.json`
- `styles/occlusion.json`
- `styles/photoreal-norms.json`
- `styles/settei.json`
- `styles/skin-texture.json`
- `tools/engine/chara3d.py`
- `tools/engine/human.py`
- `tools/engine/pose_depth.py`
- `tools/engine/pose_prop.py`
- `tools/engine/rom_check.py`
- `tools/engine/turnaround.py`
- `tools/engine/viewer/vrm-base.html`
- `tools/engine/vrm_repack.py`
- `tools/engine/vrm_shoot.mjs`
- `tools/gen/assets.py`
- `tools/gen/atmosphere.py`
- `tools/gen/background.py`
- `tools/gen/baseline.py`
- `tools/gen/bible.py`
- `tools/gen/brushes.py`
- `tools/gen/data_home.py`
- `tools/gen/charsheet.py`
- `tools/gen/cleanup.py`
- `tools/gen/demi.py`
- `tools/gen/design.py`
- `tools/gen/detail.py`
- `tools/gen/device.py`
- `tools/gen/edit.py`
- `tools/gen/facecheck.py`
- `tools/gen/faceform.py`
- `tools/gen/feet.py`
- `tools/gen/filters.py`
- `tools/gen/fix.py`
- `tools/gen/free_text.py`
- `tools/gen/hands.py`
- `tools/gen/hires.py`
- `tools/gen/imgproc.py`
- `tools/gen/inking.py`
- `tools/gen/joints.py`
- `tools/gen/layers.py`
- `tools/gen/legcount.py`
- `tools/gen/lightplan.py`
- `tools/gen/lineart.py`
- `tools/gen/manga.py`
- `tools/gen/materials.py`
- `tools/gen/measure.py`
- `tools/gen/models.py`
- `tools/gen/normlearn.py`
- `tools/gen/occlusion.py`
- `tools/gen/people.py`
- `tools/gen/perspective.py`
- `tools/gen/pieces.py`
- `tools/gen/poses.py`
- `tools/gen/qc.py`
- `tools/gen/retouch.py`
- `tools/gen/settei.py`
- `tools/gen/setup.py`
- `tools/gen/sheetlayout.py`
- `tools/gen/stylize.py`
- `tools/gen/tagger.py`
- `tools/gen/tile.py`
- `tools/gen/tones.py`
- `tools/gen/traits.json`
- `tools/gen/upscale.py`
