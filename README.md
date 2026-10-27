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

カメラは冷蔵室のドアを開けると撮影し、画像をクラウドに上げます。このインテグレーションは 5 分ごとにクラウドを確認し、新しい画像だけをダウンロードします。
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

1. HACS → 右上メニュー → **カスタムリポジトリ** → `https://github.com/k-okaden/ha-hitachi`、種類は **Integration**
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
