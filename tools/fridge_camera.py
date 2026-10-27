"""日立冷蔵庫 (コンシェルジュアプリ対応機) のカメラ画像を取得するテストスクリプト。

使い方:
    export HITACHI_EMAIL='...'
    export HITACHI_PASSWORD='...'
    python3 tools/fridge_camera.py               # 全位置の最新画像を images/ に保存
    python3 tools/fridge_camera.py -p center     # 位置を指定
    python3 tools/fridge_camera.py --debug       # 応答の中身を表示 (トークンは伏せる)

必要なもの: pip install cryptography requests
ログイン情報は session.json に保存して使い回す (毎回ログインしない)。
固定鍵は tools/extract_keys.py で作った keys.json から読む。
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

HERE = Path(__file__).resolve().parent.parent
KEYS = json.loads((HERE / "custom_components/hitachi_refrigerator/keys.json").read_text())
SESSION_FILE = HERE / "session.json"
IMAGE_DIR = HERE / "images"

LOGIN_URL = "https://kadenfan.hitachi.co.jp/my/api/login2"
CGI_URL = "https://tkg.capsys21.hitachi-gls.co.jp/cgi-bin/ap_outer_ctrl_filter2.cgi"
APP_ID = "9"
OKHTTP_UA = "okhttp/4.12.0"
POSITIONS = ["center", "left", "right", "freezer", "upper-select", "lower-select"]
SECRET_FIELDS = {"token", "ckdn_token", "ckdn_key", "ckdn_iv", "ckdn_device_key", "cspf_id"}


# --- 暗号化 (AES/CBC/ZeroBytePadding, BouncyCastle 互換) ---

def encrypt(key: bytes, iv: bytes, text: str) -> bytes:
    data = text.encode()
    # BC の ZeroBytePadding はブロック境界ちょうどでも1ブロック足す
    data += b"\0" * (16 - len(data) % 16)
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return enc.update(data) + enc.finalize()


def decrypt(key: bytes, iv: bytes, data: bytes) -> str:
    if len(data) % 16:
        raise ValueError(f"暗号文の長さが16の倍数ではありません ({len(data)} バイト): {data[:200]!r}")
    dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    # 応答の末尾にはゼロ埋めに加えて 0x10 などの詰め物が付く。アプリは String.trim() で落としている
    return (dec.update(data) + dec.finalize()).rstrip(bytes(range(0x21))).decode("utf-8", "replace")


def to_form(params: dict) -> str:
    # アプリは URL エンコードせずに key=value を & でつなぐ
    return "&".join(f"{k}={v}" for k, v in params.items())


def parse_body(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        out = {}
        for part in text.split("&"):
            k, _, v = part.partition("=")
            out[k] = v
        return out


def masked(obj):
    if isinstance(obj, dict):
        return {k: ("***" if k in SECRET_FIELDS else masked(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [masked(v) for v in obj]
    if isinstance(obj, str) and obj.startswith("https://") and len(obj) > 80:
        return obj[:80] + "..."
    return obj


# --- API ---

def login(email: str, password: str) -> dict:
    key, iv = bytes.fromhex(KEYS["login_key"]), bytes.fromhex(KEYS["login_iv"])
    body = encrypt(key, iv, to_form({"email": email, "password": password, "app_id": APP_ID}))
    r = requests.post(LOGIN_URL, data=body, headers={"User-Agent": OKHTTP_UA}, timeout=30)
    r.raise_for_status()
    res = parse_body(decrypt(bytes.fromhex(KEYS["login_resp_key"]), bytes.fromhex(KEYS["login_resp_iv"]), r.content))
    if not res.get("ckdn_token"):
        raise SystemExit(f"ログイン失敗: {masked(res)}")
    return res


def cgi(session: dict, params: dict, debug: bool = False):
    key, iv = bytes.fromhex(session["ckdn_key"]), bytes.fromhex(session["ckdn_iv"])
    r = requests.post(CGI_URL, data=encrypt(key, iv, to_form(params)),
                      headers={"User-Agent": session["ckdn_token"]}, timeout=30)
    r.raise_for_status()
    res = parse_body(decrypt(key, iv, r.content))
    if debug:
        print(f"[{params['CMD']}]", json.dumps(masked(res), ensure_ascii=False, indent=2))
    return res


def get_session(relogin: bool) -> dict:
    if SESSION_FILE.exists() and not relogin:
        return json.loads(SESSION_FILE.read_text())
    email, password = os.environ.get("HITACHI_EMAIL"), os.environ.get("HITACHI_PASSWORD")
    if not email or not password:
        raise SystemExit("HITACHI_EMAIL と HITACHI_PASSWORD を環境変数に入れてください")
    print("ログインします...")
    s = login(email, password)
    SESSION_FILE.write_text(json.dumps(s))
    SESSION_FILE.chmod(0o600)
    return s


def get_devices(session: dict, debug: bool) -> list:
    res = cgi(session, {"CMD": "GETDEVIDHID", "HID": session["cspf_id"], "APPTYPE": APP_ID}, debug)
    raw = res.get("DEVINFO") or ""
    devices = []
    for item in filter(None, raw.split("|")):
        f = item.split(",")
        if len(f) >= 4:
            devices.append({"src": f[0], "user": f[1], "dst": f[2], "nickname": f[3]})
    return devices


def folder_name(dst: str) -> str:
    # AppAmazonUtil.getFolderName: 8桁ずつ32bitビット反転して16進でつなげる
    return "".join(f"{(~int(dst[i:i + 8], 16)) & 0xFFFFFFFF:08X}" for i in (0, 8, 16))


def fetch_images(session: dict, dst: str, position: str, all_images: bool, debug: bool) -> int:
    target = f"refrigerator/camera/{folder_name(dst)}/device/{position}/"
    res = cgi(session, {"CMD": "GETS3DOWNLOADURL", "DST": dst, "TARGET": target}, debug)
    items = res.get("urllist") or []
    if str(res.get("success")) != "0" or not items:
        print(f"  {position}: 画像なし (success={res.get('success')})")
        return 0
    saved = 0
    outdir = IMAGE_DIR / position
    outdir.mkdir(parents=True, exist_ok=True)
    for it in items:
        name, url = it.get("filename", ""), it.get("url", "")
        if not name.endswith(".jpg") or (not all_images and "old/" in url):
            continue
        img = requests.get(url, timeout=60)
        img.raise_for_status()
        (outdir / Path(name).name).write_bytes(img.content)
        saved += 1
        print(f"  {position}: {name} ({len(img.content) // 1024} KB)")
    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--position", choices=POSITIONS, action="append")
    ap.add_argument("--all", action="store_true", help="old/ の古い画像も取る")
    ap.add_argument("--relogin", action="store_true", help="保存したセッションを使わずログインし直す")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    session = get_session(args.relogin)
    try:
        devices = get_devices(session, args.debug)
    except (requests.HTTPError, ValueError) as e:
        if args.relogin:
            raise
        print(f"保存したセッションが使えませんでした ({e})。ログインし直します")
        session = get_session(True)
        devices = get_devices(session, args.debug)

    if not devices:
        raise SystemExit("冷蔵庫が見つかりません (--debug で応答を確認してください)")
    for d in devices:
        print(f"冷蔵庫: {d['nickname'] or '(名前なし)'}  DST={d['dst'][:6]}...")
        total = sum(fetch_images(session, d["dst"], p, args.all, args.debug)
                    for p in (args.position or POSITIONS))
        print(f"  合計 {total} 枚を {IMAGE_DIR.name}/ に保存")


if __name__ == "__main__":
    sys.exit(main())
