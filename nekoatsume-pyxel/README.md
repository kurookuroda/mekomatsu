# nekoatsume-pyxel

Pyxel で作る「ねこあつめ」風の放置ゲーム(いまは文字だけの UI)。
[nekoatsume_py](https://github.com/kurookuroda/nekoatsume_py)(コンソール版)のルールを移植しています。
デスクトップ(Windows / macOS / Linux)とブラウザ(スマホ含む)で動かせます。

## リポジトリ構成

```
nekoatsume-pyxel/
├── nekoatsume.py              # Pyxel の UI(起動するスクリプト)
├── game.py                    # ゲームのルール(Pyxel に依存しない)
├── test_game.py               # ルールのテスト(pytest)
├── tools/ui_smoke.py          # UI のスモークテスト(タップ操作の再現とスクリーンショット)
├── PixelMplus12-Regular.ttf   # 日本語ピクセルフォント(要ライセンス確認・下記参照)
└── README.md
```

`nekoatsume.py` と `game.py` とフォントは **リポジトリ直下(フラット)** に置きます
(Pyxel Web Launcher はスクリプトと同じ場所のファイルを読むため)。

## 遊び方

- 起動: `pip install pyxel` のあと `pyxel run nekoatsume.py`
- ブラウザ: `https://kitao.github.io/pyxel/wasm/launcher/?run=<ユーザー名>.<リポジトリ名>.nekoatsume`
  - スマホでは末尾に `&gamepad=enabled` を付けると仮想ゲームパッドが出ます(このゲームでは使いません。付けなくて構いません)
- 操作: タップ / クリック。リストはドラッグ(PC はホイールや ↑↓ キー)でスクロール。1〜5 キーで下のタブを切り替え

流れは、ショップで買う → もちものからおもちゃとエサを庭に置く → 猫が来て、帰るときにさかなを置いていく → 「にわ」で受け取る、です。
エサは300分(5時間)でなくなります。アプリを閉じている間も、実時間のぶんだけ進みます。

## 用意するファイル

**PixelMplus12-Regular.ttf** は [PixelMplus](https://github.com/itouhiro/PixelMplus) の配布ページから取得してください。
再配布する場合は、配布元のライセンスに従い、ライセンス文書も同梱してください。
フォントがなくても動きますが、日本語が表示されません。

## セーブ

`pyxel.user_data_dir()` が返すフォルダの `save.json` に、操作のたびと1分ごとに自動保存します。
ブラウザ版で、ページを閉じても残るかどうかは、まだ確認できていません(下記)。

## 開発

```
pip install pyxel pytest
pytest -q                          # ゲームのルール(22 件)
python3 tools/ui_smoke.py          # UI(画面のない Linux では xvfb-run を付ける。tools/ui_smoke.py 冒頭を参照)
pyxel package . nekoatsume.py      # 複数ファイルを .pyxapp にまとめる(Launcher の ?play= や app2html で使える)
```

## コンソール版からの意図的な変更

1. 庭の容量判定を `<` から `<=` にしました(元は6マスあっても5マスしか使えませんでした)。
2. 大型キャットハウスをサイズ 7 → 6 にしました(元は置けず、エサ扱いで購入されていました)。
3. アイテムの種別(おもちゃ / エサ)を、サイズの閾値ではなく `kind` で判定します。
4. 内部IDと表示名を分けました(セーブデータのキーは `rubber_ball` のようなID)。
5. おもちゃを庭から外すと、遊んでいた猫はさかなを置いて帰ります(元は無報酬で追い出していました)。
6. エサを置き換えるとき、残りが捨てられることを確認するダイアログを出します。

猫の来訪率・滞在時間・報酬の計算は元と同じです。元の `update.tick` で測った経済
(おもちゃ5個・エサ常時で、銀 約112/時、来訪 約9回/時、滞在 平均約18分)と一致することを、`test_game.py` で確認しています。
以前のコンソール版の `data.json` は引き継げません(移行処理は未実装)。

## 動作確認の状況

確認済み(Linux + 仮想ディスプレイ):

- ゲームのルール(pytest 22 件)
- UI の画面遷移・購入・配置・エサの置き換え・受け取り・セーブ/ロード
- `pyxel package` で .pyxapp を作れること

**未確認(公開前に確認したいこと)**:

- Pyxel Web Launcher(`?run=`)で `game.py` を import できるか。できない場合は `.pyxapp` にして `?play=` で動かす
- ブラウザ版で `user_data_dir` のセーブが、ページを閉じても残るか
- スマホ実機でのタップとドラッグスクロール
- フォントのライセンスと同梱可否

## これから

- 猫ごとの個性(好物のおもちゃ、来訪率、押し出しの強さ)と、図鑑の充実
- 絵(スプライト)の追加
- 経済の調整(使い道のない銀の解消)
