<p align="center">
  <img src="atelier/assets/logo.svg" alt="AtelIer のロゴ。A と I だけがオレンジ色" width="360">
</p>

# AtelIer

人が使う、AI が使う、AI を使うペイントソフトです。読み方は「アトリエ」で、名前の中の A と I が AI を表します。

![左に道具の帯とカラーとレイヤーの欄、中央にキャンバスとチャット、右に AI の欄と履歴が並ぶ画面](docs/images/main-window.png)

CharacterDesigner の描画アプリから、キャラクターデザイン以外の部品を移して作っています。いまは移している途中で、まだ直していない所は [docs/STRUCTURE.md](docs/STRUCTURE.md) に書いています。

キャラクターデザイン（設定資料、三面図、表情差分、キャラクターファイル）は、CharacterDesigner が拡張として足します。AtelIer を入れたあとに CharacterDesigner のパッケージを入れると、起動したときに entry points（`atelier.extensions`）で見つかり、「キャラクターデザイン」のメニューとモードが出ます。拡張の口は `atelier/extensions.py`、つながり方は [docs/integration.md](docs/integration.md) に書いています。

## 主な機能

- 人が描く: ブラシ 6 種と筆圧、消しゴム、ぼかし、スプレー、指先、塗りつぶし、グラデーション、図形、文字、選択範囲、レイヤー
- 描く補助: 手ぶれ補正、対称、定規（平行線、同心円、放射、パース）、描いて止めると形を整える
- AI を使う: 言葉で頼んで描く、ラフの線に沿って描く、赤ペンで囲んだ所だけ直す、綺麗にする、拡大する、画風を替える
- AI が使う: 人の筆と同じ経路で線を引く入口（`Canvas.draw_stroke`）と、チャットの言葉でアプリを操作する仕組み
- ファイル: 作業ファイル（`.atelier`、レイヤーごと）、PNG と PSD の書き出し、自動保存、ごみ箱、タイムラプス
- 見た目: 7 つのテーマ、欄の配置の保存、メニューと帯の並べ替え

AI で描くには、絵のモデルと、それを動かす部品（torch、diffusers）が要ります。モデルが無くても、人が描く機能は使えます。

## 動作環境

- Python 3.11 以上
- PySide6 6.6 以上、NumPy、Pillow
- 起動とテストを確かめたのは、Linux（画面なし）の Python 3.13 と PySide6 6.12 です
- Windows と macOS の実機、絵のモデルを入れた状態では、このリポジトリになってから確かめていません

## セットアップ手順

1. リポジトリを取得します。

   ```bash
   git clone https://github.com/Maguro-JP/AtelIer.git
   cd AtelIer
   ```

2. 仮想環境を作って入ります。ほかの Python の部品と混ざらないようにするためです。

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate    # Windows は .venv\Scripts\activate
   ```

3. 依存を入れます。

   ```bash
   pip install -e ".[dev]"
   ```

## 使い方

```bash
python -m atelier
```

初めて起動すると、使い方のツアーとモードの選択が出ます。道具の帯のボタンにカーソルを合わせると、名前とキーが出ます。

| 操作 | キー |
|---|---|
| ペン、消しゴム | B、E |
| 塗りつぶし、スポイト | G、I |
| 四角の選択、投げなわ | M、L |
| 元に戻す、やり直す | Ctrl+Z、Ctrl+Y |
| 保存、PNG で書き出す | Ctrl+S、Ctrl+E |

## 設定

| 環境変数 | 用途 | 必須 |
|---|---|---|
| `ATELIER_HOME` | アプリの設定・部品・記録の置き場を変えます | 任意 |
| `LLM_HOME` | モデルの置き場を変えます（設定で選んだ置き場があれば、そちらが先です） | 任意 |
| `ATELIER_OUTPUT` | 描いた絵の保存先を変えます | 任意 |

## ディレクトリ構成

| 場所 | 役割 |
|---|---|
| `atelier/app/` | 窓と起動 |
| `atelier/paint/` | 作画の中核（キャンバス、ブラシ、描く補助） |
| `atelier/panels/` | 欄（カラー、レイヤー、AI、チャット、ライブラリー） |
| `atelier/ui/` | テーマ、アイコン、ロゴ、欄の配置、ヘルプ |
| `atelier/files/` | 置き場、作業ファイル、ごみ箱 |
| `atelier/ai/`、`atelier/models/`、`atelier/words/`、`atelier/qc/` | AI で描く・直す、モデルの管理、頼みの言葉、検品 |
| `atelier/agent/` | チャットと、言葉での操作 |
| `tools/`、`styles/`、`casts/`、`config/` | アプリが読む道具の台本と基準 |
| `tests/` | テスト |
| `docs/` | 決めたこと（[decisions.md](docs/decisions.md)）、構成と対応表（[STRUCTURE.md](docs/STRUCTURE.md)）、モデルの一覧（[models.md](docs/models.md)） |

## 開発者向け情報

```bash
python3 scripts/run_tests.py                 # テストを、ファイルごとに別の処理で流します
python3 scripts/run_tests.py test_brushtools # 1 ファイルだけ流します
python3 -m pyflakes atelier                  # 静的な検査
```

モデルの部品（torch、diffusers）が無い環境では、`tests/needs_models.txt` に書いたファイルを飛ばします。

## ライセンス

ソースは公開していますが、利用の許諾はしていません。詳しくは [LICENSE](LICENSE) を読んでください。依存している PySide6 は LGPL、NumPy は BSD ライセンスです。
