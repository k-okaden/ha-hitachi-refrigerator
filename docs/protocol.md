# 日立 R-HXCC62T / 冷蔵庫コンシェルジュアプリ 解析メモ

- アプリ: `jp.co.hitachi_gls.refrigerator2019` v1.13.0 (targetSdk 35)
- 冷蔵庫本体は LAN 側で何も待ち受けていない (ECHONET Lite も無応答)。クラウド経由のみ。
- 内容は APK の静的解析と、実機での動作確認による。

## サーバー
| 用途 | URL |
|---|---|
| 会員ログイン | `POST https://kadenfan.hitachi.co.jp/my/api/login2` |
| 冷蔵庫の制御・情報 | `POST https://tkg.capsys21.hitachi-gls.co.jp/cgi-bin/ap_outer_ctrl_filter2.cgi` |
| 食品管理 | `https://tfm.capsys21.hitachi-gls.co.jp/` (ヘッダー `x-hgls-capsys21-token`) |
| カメラ画像 | S3 署名付きURL (バケット `hap-ckdn-spapp`) |

## 本文の暗号化
- 本文は `key=value&key=value` 形式の文字列を **AES/CBC、ゼロ埋めパディング** で暗号化したバイト列 (Content-Type なし)
- 応答も同じ方式で暗号化。復号すると JSON か `key=value&...` 形式
- 鍵とIV:
  | 通信 | 鍵 / IV |
  |---|---|
  | `login2` の送信 | `CoConstant.HTTP_ENCKEY` / `CoConstant.ivBytes` (アプリ内の固定値) |
  | `login2` の応答 | `GsonResponseBodyCustomHitachiWebConverter` 内の固定値 (同じ値) |
  | `ap_outer_ctrl_filter2.cgi` | ログイン応答の `ckdn_key` / `ckdn_iv` (16進文字列 → バイト列) |
  | `ap_outer_ctrl_filter.cgi` | `CoConstant.HTTP_ENCKEY_Constant` / `AESCryptUtils.ivBytes` |
- 固定値は `jp/co/hitachi_ap/base_appliance_app/constant/CoConstant.java` 等にある (`tools/extract_keys.py` で取り出す)

## 認証の流れ
1. `login2` に `email`, `password`, `app_id=9` を送る
2. 応答: `cspf_id`, `token`, `ckdn_token`, `ckdn_key`, `ckdn_iv`, `ckdn_device_key`, `login_datetime`, `agree_cd`, `status`
3. 以降のCGIは **`User-Agent` ヘッダーに `ckdn_token`** を入れて送る
4. ログイン確認: `CMD=LOGINCHK`, `cspf_id`, `login_datetime`, `app_id=9`

## 冷蔵庫の特定 (SRC / DST)
- `CMD=GETDEVIDHID`, `HID=<cspf_id>`, `APPTYPE=9` → `DEVINFO` に機器一覧
- 各機器の `src` = アプリ側ID (mobileId)、`dst` = 冷蔵庫ID (productId, 16進24桁)
- 以降のリクエストに `SRC` / `DST` を付ける

## カメラ画像
- フォルダ名: DST を8桁ずつ3つに分け、それぞれ32bitでビット反転して16進(大文字)でつなげたもの (`AppAmazonUtil.getFolderName`)
- `CMD=GETS3DOWNLOADURL`, `DST=<dst>`, `TARGET=refrigerator/camera/<フォルダ名>/device/<位置>/`
  - 位置: `left` / `center` / `right` / `freezer` / `upper-select` / `lower-select` (既定 `center`)
- 応答 `success=0` のとき `urllist[]` に `filename` と `url` (署名付き)。`.jpg` が冷蔵庫カメラの画像
- `url` を普通に GET すれば画像が取れる。URLに `old/` を含むものは古い画像

## そのほか取れそうな情報
| CMD | 追加パラメータ | 中身 |
|---|---|---|
| `DELIVERY` | `START`, `END` | ドア開閉(出し入れ)履歴 |
| `GETINF` | `DATA` | 本体の状態 |
| `STOREDINFORMATIONGET` | なし | 重量(在庫)情報 |
| `COURSEINF` | `MODEL=CAMERA_INF`, `VERSION` | カメラ設定の定義 |

## 証明書
- network_security_config なし、証明書ピンニングなし

## 実機で確認済み (2026-10, `tools/fridge_camera.py`)
- ログイン → `GETDEVIDHID` → `GETS3DOWNLOADURL` → 画像ダウンロードまで動作
- `DEVINFO` 形式: `src,ユーザー名,dst,ニックネーム` (複数台は `|` 区切り)
- DST の9〜20桁目は冷蔵庫の Wi-Fi MAC アドレス
- 画像は `hap-ckdn-refrigerator-image-convert` バケットの署名付きURL
- ファイル名 `D<YYYYMMDDhhmmss>000_OK.jpg` = 撮影日時。`lastmodified` はアップロード日時
- 各位置で最新6枚が返る
  | 位置 | 中身 | 解像度 |
  |---|---|---|
  | `center` | 冷蔵室の棚 | 1330x1080 |
  | `left` / `right` | 左右のドアポケット | 約590x1020 |
  | `freezer` / `upper-select` / `lower-select` | この機種では空 | - |

## 未確定
- `GETINF` の `DATA` に入れる値
- ログインし直すとスマホ側アプリがログアウトされるか (同時ログインの可否)
