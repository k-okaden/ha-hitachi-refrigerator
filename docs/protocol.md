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

## 運転状況 (`GETINF`)
- `CMD=GETINF`, `SRC`, `DST`, `DATA=0001` → 応答 `GRP=0`, `DATA=0001,<16進文字列>` (`GRP=3` などは通信不可)
- 16進文字列の中身 (`DataGetInf.init`、位置は文字インデックス):
  | 位置 | 内容 |
  |---|---|
  | 0-12 | 状態の時刻 (年4桁・月・日・時・分) |
  | 16-18 | 状態ビット: bit0 製氷おそうじ中, bit2 急速製氷中, bit3 サッと急冷却中, bit5 クイック冷却中, bit6 急冷凍中 |
  | 18-20 | サイン: bit0 節電中, bit1 給水 (タンクの水切れ) |
  | 20-22 / 22-24 | 冷凍室 / 冷蔵室の温度設定 |
  | 24-26 | 温度設定の方式: 1 = 3段階 (2 / 6 / 10)、2 = 11段階 (1〜11) |
  | 26-28 | 節電モードの設定 (0 切 / 1 入) |
  | 28-30 | 真空チルドモード (0 切 / 1 真空氷温 / 2 真空チルド) |
  | 30-32 | 製氷 (0 停止 / 1 製氷 / 2 急速製氷) |
  | 32-34 | 冷却モードの設定ビット: bit0 スポット冷蔵, bit1 サッと急冷却, bit3 クイック冷却, bit4 急冷凍 |
  | 34-40 | 操作ロック, 電動引出, 音量 |
  | 40-44 / 44-48 | ドア開閉回数 今日 / 昨日 |
  | 48-54 | 積算運転時間 |
  | 54-60 / 60-66 | お知らせコード / エラーコード (ASCII 3文字、`000` = なし) |
  | 66-74 | 切替室の温度・モード (切替室のある機種) |
  | 74-78 / 78-82 | 引出ドア / 冷蔵室ドアの開放秒数 (今日) |
  | 82-86 / 86-90 | 同 (昨日) |
  | 90-114 | 重量センサー (1ドア機のみ) |
  | 114-122 | カメラ設定 (自動・手動撮影, ブザー, 撮影タイミング, ループシャッター) |
- 3段階の表示名 (HXCC などパターンB): 冷蔵室 2 弱め / 6 標準 / 10 チルド、冷凍室 2 弱め / 6 標準 / 10 強め
  (パターンAの機種は 弱 / 中 / 強。`R.array.ref_tem_N_pattern*`, `freeze_tem_N_pattern*`)
- 「運転状況」画面は `HR00301Fragment`、冷蔵庫設定は `HR00300Fragment`、冷却モードは `HR00303Fragment`、節電モードは `HR00304Fragment`

## そのほか取れそうな情報
| CMD | 追加パラメータ | 中身 |
|---|---|---|
| `DELIVERY` | `START`, `END` | ドア開閉(出し入れ)履歴 |
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
- `GETINF` の `DATA=0003` / `0004` (在庫ステップ用) の中身
- ログインし直すとスマホ側アプリがログアウトされるか (同時ログインの可否)
