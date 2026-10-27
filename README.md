# Hitachi Refrigerator for Home Assistant

日立の冷蔵庫カメラ (「日立冷蔵庫コンシェルジュアプリ」対応機) の画像を Home Assistant に取り込むカスタムインテグレーションです。
冷蔵庫は LAN 側で何も待ち受けていないため、アプリと同じ日立のクラウド API を使います。

R-HXCC62T で動作確認しています。冷蔵庫カメラを搭載した他の機種 (HXCC / WXC など) でも動く可能性があります。

> 日立の公式 API ではありません。アプリを解析して作ったもので、日立側の仕様変更で動かなくなることがあります。

## できること

| エンティティ | 内容 |
|---|---|
| `camera.hitachi_fridge_center` | 冷蔵室の棚の最新画像 |
| `camera.hitachi_fridge_left` | 左ドアポケットの最新画像 |
| `camera.hitachi_fridge_right` | 右ドアポケットの最新画像 |
| `sensor.hitachi_fridge_last_captured` | 最後に撮影された日時 (≒最後にドアを開けた時刻) |

運転状況 (アプリの「冷蔵庫の運転状況」と同じ情報):

| エンティティ | 内容 |
|---|---|
| `sensor.hitachi_fridge_door_open_count_today` / `_yesterday` | ドア開閉回数 (今日 / 昨日) |
| `sensor.hitachi_fridge_fridge_door_open_time_today` | 冷蔵室ドアの開放時間 (今日) |
| `sensor.hitachi_fridge_drawer_open_time_today` | 引出ドア (冷凍室・野菜室など) の開放時間 (今日) |
| `sensor.hitachi_fridge_fridge_setting` | 冷蔵室の設定 (チルド / 標準 / 弱め) |
| `sensor.hitachi_fridge_freezer_setting` | 冷凍室の設定 (強め / 標準 / 弱め) |
| `sensor.hitachi_fridge_ice_mode` | 製氷室の設定 (急速製氷 / 製氷 / 製氷停止) |
| `binary_sensor.hitachi_fridge_quick_cooling_mode` | 冷却モードの「クイック冷却」 |
| `binary_sensor.hitachi_fridge_power_saving_mode` | 節電モード |
| `binary_sensor.hitachi_fridge_power_saving_active` | 消費電力を抑えて運転中 (節電モードが実際に効いているとき) |
| `binary_sensor.hitachi_fridge_water_tank_empty` | 給水タンクの水切れ |
| `binary_sensor.hitachi_fridge_quick_freezing` ほか | 急冷凍中・急速製氷中・サッと急冷却中・クイック冷却中・製氷おそうじ中 |
| `binary_sensor.hitachi_fridge_problem` | エラー / お知らせコードが出ている (コードは診断センサーで確認) |

温度設定の表示名は HXCC タイプ (R-HXCC62T など) のものです。11 段階の細かい設定にしている場合は 1〜11 の数字で表示されます。
昨日のドア開放時間と、この機種のアプリに出ない冷却モード (スポット冷蔵・サッと急冷却・急冷凍) のセンサーは初期状態で無効です。必要なら有効にしてください。

カメラは冷蔵室のドアを開けると撮影し、画像をクラウドに上げます。このインテグレーションは 5 分ごとにクラウドから運転状況と画像の一覧を取得し、新しい画像だけをダウンロードします。
カメラの属性 `captured_at` に撮影日時が入ります。

## 準備: 鍵ファイルを作る

アプリとクラウドの通信は AES で暗号化されていて、その鍵はアプリに埋め込まれています。
鍵はこのリポジトリには含めていないので、自分の端末のアプリから取り出してください。

1. Android 端末に「日立冷蔵庫コンシェルジュアプリ」を入れ、USB デバッグを有効にして PC につなぐ
2. APK を取り出して逆コンパイルする ([adb](https://developer.android.com/tools/adb) と [jadx](https://github.com/skylot/jadx) を使用)

   ```bash
   adb pull "$(adb shell pm path jp.co.hitachi_gls.refrigerator2019 | sed 's/package://' | tr -d '\r')" base.apk
   jadx -d jadx-out base.apk
   ```

3. 鍵を取り出す

   ```bash
   python3 tools/extract_keys.py jadx-out hitachi_refrigerator_keys.json
   ```

できた `hitachi_refrigerator_keys.json` を Home Assistant の `config/` フォルダ (`configuration.yaml` と同じ場所) に置きます。

## インストール

### HACS (カスタムリポジトリ)

1. HACS → 右上メニュー → **カスタムリポジトリ** → `https://github.com/k-okaden/ha-hitachi-refrigerator`、種類は **Integration**
2. 「Hitachi Refrigerator」をダウンロードして Home Assistant を再起動

### 手動

`custom_components/hitachi_refrigerator` を Home Assistant の `config/custom_components/` にコピーして再起動。

## 設定

**設定 → デバイスとサービス → 統合を追加 → Hitachi Refrigerator** で、アプリで使っている日立家電メンバーズクラブのメールアドレスとパスワードを入力します。

- ログイン後のセッションを保存して使い回すので、再起動のたびにログインはしません。期限が切れたら自動でログインし直します。
- パスワードを変えたときは、再ログインを求める通知が出ます。

## ダッシュボード

[`examples/dashboard_fridge.yaml`](examples/dashboard_fridge.yaml) に、3 つのカメラと最終撮影日時を並べたダッシュボードの例があります。
新しいダッシュボードを作り、**︙ → YAML 編集** に貼り付けてください。

## 単体で試す

Home Assistant なしで画像を取得するスクリプトもあります。

```bash
pip install cryptography requests
python3 tools/extract_keys.py jadx-out            # custom_components/hitachi_refrigerator/keys.json に保存
export HITACHI_EMAIL='...'
export HITACHI_PASSWORD='...'
python3 tools/fridge_camera.py --debug             # images/ に保存
```

## プロトコルメモ

通信の仕組み (暗号化、ログイン、機器 ID、画像パスの作り方、そのほかのコマンド) は [`docs/protocol.md`](docs/protocol.md) にまとめています。

## ライセンス

MIT
