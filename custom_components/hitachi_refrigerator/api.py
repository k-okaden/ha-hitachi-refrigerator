"""Client for the Hitachi refrigerator cloud (日立冷蔵庫コンシェルジュアプリ).

Request and response bodies are `key=value&...` strings encrypted with
AES/CBC and zero-byte padding. Login uses keys built into the app (read
from keys.json); everything after login uses the session's ckdn_key/ckdn_iv.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

LOGIN_URL = "https://kadenfan.hitachi.co.jp/my/api/login2"
CGI_URL = "https://tkg.capsys21.hitachi-gls.co.jp/cgi-bin/ap_outer_ctrl_filter2.cgi"
APP_ID = "9"
LOGIN_USER_AGENT = "okhttp/4.12.0"

_TIMEOUT = aiohttp.ClientTimeout(total=30)
_JST = ZoneInfo("Asia/Tokyo")
# The app sends the encrypted body without a Content-Type header.
_NO_CONTENT_TYPE = ("Content-Type",)


class HitachiError(Exception):
    """Communication with the Hitachi cloud failed."""


class HitachiAuthError(HitachiError):
    """The email address or password was rejected."""


class HitachiSessionError(HitachiError):
    """The saved session no longer works; log in again."""


@dataclass
class HitachiSession:
    cspf_id: str
    ckdn_token: str
    ckdn_key: str
    ckdn_iv: str

    def as_dict(self) -> dict[str, str]:
        return {
            "cspf_id": self.cspf_id,
            "ckdn_token": self.ckdn_token,
            "ckdn_key": self.ckdn_key,
            "ckdn_iv": self.ckdn_iv,
        }


@dataclass
class HitachiDevice:
    src: str
    dst: str
    user_name: str
    nickname: str

    @property
    def mac(self) -> str:
        # DST is 8 hex digits + the Wi-Fi MAC + 4 hex digits
        mac = self.dst[8:20].lower()
        return ":".join(mac[i : i + 2] for i in range(0, 12, 2))


@dataclass
class CameraImage:
    filename: str
    url: str
    captured_at: datetime


def encrypt(key: bytes, iv: bytes, text: str) -> bytes:
    data = text.encode()
    # BouncyCastle's ZeroBytePadding adds a full block when already aligned.
    data += b"\0" * (16 - len(data) % 16)
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return enc.update(data) + enc.finalize()


def decrypt(key: bytes, iv: bytes, data: bytes) -> str:
    if not data or len(data) % 16:
        raise HitachiSessionError(f"Unexpected response ({len(data)} bytes)")
    dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    # Responses end with zero padding plus filler bytes; the app strips them with trim().
    return (dec.update(data) + dec.finalize()).rstrip(bytes(range(0x21))).decode(
        "utf-8", "replace"
    )


def _to_form(params: dict[str, str]) -> str:
    # The app joins key=value pairs without URL-encoding.
    return "&".join(f"{k}={v}" for k, v in params.items())


def _parse_body(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = dict(part.partition("=")[::2] for part in text.split("&"))
    if not isinstance(parsed, dict):
        raise HitachiSessionError("Unexpected response")
    return parsed


def folder_name(dst: str) -> str:
    """AppAmazonUtil.getFolderName: bit-invert each 8-hex-digit chunk of DST."""
    return "".join(f"{(~int(dst[i:i + 8], 16)) & 0xFFFFFFFF:08X}" for i in (0, 8, 16))


def parse_captured_at(filename: str) -> datetime | None:
    # D20261027194735000_OK.jpg -> 2026-10-27 19:47:35 JST
    try:
        return datetime.strptime(filename[1:15], "%Y%m%d%H%M%S").replace(tzinfo=_JST)
    except ValueError:
        return None


class HitachiClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        keys: dict[str, str],
        email: str,
        password: str,
        saved: HitachiSession | None = None,
    ) -> None:
        self._http = session
        self._keys = keys
        self._email = email
        self._password = password
        self.session = saved

    async def login(self) -> HitachiSession:
        key = bytes.fromhex(self._keys["login_key"])
        iv = bytes.fromhex(self._keys["login_iv"])
        body = encrypt(
            key, iv, _to_form({"email": self._email, "password": self._password, "app_id": APP_ID})
        )
        try:
            raw = await self._post(LOGIN_URL, body, LOGIN_USER_AGENT)
            res = _parse_body(
                decrypt(
                    bytes.fromhex(self._keys["login_resp_key"]),
                    bytes.fromhex(self._keys["login_resp_iv"]),
                    raw,
                )
            )
        except (aiohttp.ClientResponseError, HitachiSessionError) as err:
            raise HitachiError(f"Login request failed: {err}") from err
        if not res.get("ckdn_token"):
            raise HitachiAuthError(f"Login rejected (status={res.get('status')})")
        self.session = HitachiSession(
            cspf_id=res["cspf_id"],
            ckdn_token=res["ckdn_token"],
            ckdn_key=res["ckdn_key"],
            ckdn_iv=res["ckdn_iv"],
        )
        return self.session

    async def get_devices(self) -> list[HitachiDevice]:
        res = await self._cgi(lambda s: {"CMD": "GETDEVIDHID", "HID": s.cspf_id, "APPTYPE": APP_ID})
        if "DEVINFO" not in res:
            raise HitachiError(f"No device list in response: {sorted(res)}")
        devices = []
        for item in filter(None, res["DEVINFO"].split("|")):
            fields = item.split(",")
            if len(fields) >= 4:
                devices.append(HitachiDevice(fields[0], fields[2], fields[1], fields[3]))
        return devices

    async def get_camera_images(self, dst: str, position: str) -> list[CameraImage]:
        """Recent images for one camera position, oldest first."""
        target = f"refrigerator/camera/{folder_name(dst)}/device/{position}/"
        res = await self._cgi(lambda s: {"CMD": "GETS3DOWNLOADURL", "DST": dst, "TARGET": target})
        if str(res.get("success")) != "0":
            raise HitachiError(f"GETS3DOWNLOADURL failed (success={res.get('success')})")
        images = []
        for item in res.get("urllist") or []:
            name, url = item.get("filename", ""), item.get("url", "")
            if name.endswith(".jpg") and "old/" not in url:
                if captured_at := parse_captured_at(name):
                    images.append(CameraImage(name, url, captured_at))
        return sorted(images, key=lambda i: i.captured_at)

    async def download(self, url: str) -> bytes:
        try:
            async with self._http.get(url, timeout=_TIMEOUT) as resp:
                resp.raise_for_status()
                return await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HitachiError(f"Image download failed: {err}") from err

    async def _cgi(self, build) -> dict[str, Any]:
        """POST to the CGI, logging in again once if the session has expired."""
        if self.session is None:
            await self.login()
        try:
            return await self._cgi_once(build(self.session))
        except HitachiSessionError:
            await self.login()
            return await self._cgi_once(build(self.session))

    async def _cgi_once(self, params: dict[str, str]) -> dict[str, Any]:
        assert self.session is not None
        key = bytes.fromhex(self.session.ckdn_key)
        iv = bytes.fromhex(self.session.ckdn_iv)
        try:
            raw = await self._post(CGI_URL, encrypt(key, iv, _to_form(params)), self.session.ckdn_token)
        except aiohttp.ClientResponseError as err:
            if err.status in (401, 403):
                raise HitachiSessionError(str(err)) from err
            raise HitachiError(str(err)) from err
        return _parse_body(decrypt(key, iv, raw))

    async def _post(self, url: str, body: bytes, user_agent: str) -> bytes:
        try:
            async with self._http.post(
                url,
                data=body,
                headers={"User-Agent": user_agent},
                skip_auto_headers=_NO_CONTENT_TYPE,
                timeout=_TIMEOUT,
            ) as resp:
                resp.raise_for_status()
                return await resp.read()
        except aiohttp.ClientResponseError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HitachiError(f"Request failed: {err}") from err
