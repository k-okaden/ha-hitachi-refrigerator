"""jadx で逆コンパイルしたアプリから通信用の固定鍵を取り出して keys.json に保存する。

使い方: python3 tools/extract_keys.py <jadx の出力フォルダ> [保存先]
保存先の既定は custom_components/hitachi_refrigerator/keys.json
"""
import json
import re
import sys
from pathlib import Path

if len(sys.argv) < 2:
    raise SystemExit(__doc__)
ROOT = Path(sys.argv[1])
SRC = next(p for p in (ROOT / "sources", ROOT) if (p / "jp").is_dir()) / "jp/co/hitachi_ap/base_appliance_app"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else \
    Path(__file__).resolve().parent.parent / "custom_components/hitachi_refrigerator/keys.json"

# jadx が com.google.common.base.Ascii の定数名で出力するバイト値
ASCII = {
    "NUL": 0, "SOH": 1, "STX": 2, "ETX": 3, "EOT": 4, "ENQ": 5, "ACK": 6, "BEL": 7,
    "BS": 8, "HT": 9, "LF": 10, "VT": 11, "FF": 12, "CR": 13, "SO": 14, "SI": 15,
    "DLE": 16, "DC1": 17, "DC2": 18, "DC3": 19, "DC4": 20, "NAK": 21, "SYN": 22,
    "ETB": 23, "CAN": 24, "EM": 25, "SUB": 26, "ESC": 27, "FS": 28, "GS": 29,
    "RS": 30, "US": 31, "SP": 32, "DEL": 127,
}


def byte_array(java: str, name: str) -> str:
    m = re.search(rf"byte\[\] {name} = \{{([^}}]*)\}}", java)
    if not m:
        raise SystemExit(f"{name} が見つかりません")
    out = []
    for tok in m.group(1).split(","):
        tok = tok.strip()
        if tok.startswith("Ascii."):
            v = ASCII[tok[len("Ascii."):]]
        else:
            v = int(tok.replace("(byte)", "").strip())
        out.append(v & 0xFF)
    return bytes(out).hex()


co = (SRC / "constant/CoConstant.java").read_text()
aes = (SRC / "util/AESCryptUtils.java").read_text() if (SRC / "util/AESCryptUtils.java").exists() else \
    next(SRC.rglob("AESCryptUtils.java")).read_text()
web = (SRC / "remote/convert/GsonResponseBodyCustomHitachiWebConverter.java").read_text()

keys = {
    "login_key": byte_array(co, "HTTP_ENCKEY"),
    "login_iv": byte_array(co, "ivBytes"),
    "login_resp_key": byte_array(web, "HTTP_ENCKEY"),
    "login_resp_iv": byte_array(web, "ivBytes"),
    "filter_key": byte_array(co, "HTTP_ENCKEY_Constant"),
    "filter_iv": byte_array(aes, "ivBytes"),
}
OUT.write_text(json.dumps(keys, indent=2))
print(f"{OUT} に保存しました:")
for k, v in keys.items():
    print(f"  {k}: {len(v) // 2} バイト")
print("ログイン送信と応答の鍵が同じ:", keys["login_key"] == keys["login_resp_key"] and keys["login_iv"] == keys["login_resp_iv"])
