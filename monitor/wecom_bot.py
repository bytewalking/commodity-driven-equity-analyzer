"""WeCom Smart Robot notification via WebSocket long connection.

Protocol:
  wss://openws.work.weixin.qq.com
  1. Connect
  2. Send auth frame  (cmd=aibot_subscribe)
  3. Wait for ack     (errcode=0)
  4. Send message     (cmd=aibot_send_msg)
  5. Wait for ack     (errcode=0)
  6. Disconnect
"""

from __future__ import annotations

import asyncio
import json
import random
import string
import threading
import time
from typing import Any


_WS_URL = "wss://openws.work.weixin.qq.com"
_AUTH_TIMEOUT = 10   # seconds
_SEND_TIMEOUT = 10   # seconds


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _req_id(prefix: str) -> str:
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{int(time.time() * 1000)}_{rand}"


async def _send_async(
    bot_id: str,
    secret: str,
    chatid: str,
    content: str,
) -> tuple[bool, str]:
    """Core async implementation: connect → auth → send → disconnect."""
    try:
        import websockets
    except ImportError:
        return False, "请先安装依赖：pip install websockets"

    try:
        async with websockets.connect(_WS_URL, ping_interval=None, open_timeout=10) as ws:

            # ── Step 1: authenticate ──────────────────────────────────────
            auth_id = _req_id("aibot_subscribe")
            await ws.send(json.dumps({
                "cmd": "aibot_subscribe",
                "headers": {"req_id": auth_id},
                "body": {"bot_id": bot_id, "secret": secret},
            }))

            raw = await asyncio.wait_for(ws.recv(), timeout=_AUTH_TIMEOUT)
            ack: dict[str, Any] = json.loads(raw)
            if ack.get("errcode", -1) != 0:
                return False, f"认证失败（{ack.get('errcode')}）: {ack.get('errmsg', '未知')}"

            # ── Step 2: send message ──────────────────────────────────────
            send_id = _req_id("aibot_send_msg")
            await ws.send(json.dumps({
                "cmd": "aibot_send_msg",
                "headers": {"req_id": send_id},
                "body": {
                    "chatid": chatid,
                    "msgtype": "markdown",
                    "markdown": {"content": content},
                },
            }))

            # Server may push a msg_callback before the send ack arrives;
            # loop until we get the ack for our specific req_id.
            deadline = time.monotonic() + _SEND_TIMEOUT
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False, "等待发送回执超时"
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                ack = json.loads(raw)
                # Match by req_id; ignore unrelated callbacks
                if ack.get("headers", {}).get("req_id") == send_id:
                    if ack.get("errcode", -1) != 0:
                        return False, f"发送失败（{ack.get('errcode')}）: {ack.get('errmsg', '未知')}"
                    return True, ""

    except asyncio.TimeoutError:
        return False, "连接或响应超时"
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Public API (synchronous wrapper safe for Streamlit)
# ---------------------------------------------------------------------------

async def _test_auth_async(bot_id: str, secret: str) -> tuple[bool, str]:
    """Connect and authenticate only — no message sent."""
    try:
        import websockets
    except ImportError:
        return False, "请先安装依赖：pip install websockets"

    try:
        async with websockets.connect(_WS_URL, ping_interval=None, open_timeout=10) as ws:
            auth_id = _req_id("aibot_subscribe")
            await ws.send(json.dumps({
                "cmd": "aibot_subscribe",
                "headers": {"req_id": auth_id},
                "body": {"bot_id": bot_id, "secret": secret},
            }))
            raw = await asyncio.wait_for(ws.recv(), timeout=_AUTH_TIMEOUT)
            ack: dict[str, Any] = json.loads(raw)
            if ack.get("errcode", -1) != 0:
                return False, f"认证失败（{ack.get('errcode')}）: {ack.get('errmsg', '未知')}"
            return True, ""
    except asyncio.TimeoutError:
        return False, "连接超时"
    except Exception as exc:
        return False, str(exc)


def test_auth(bot_id: str, secret: str) -> tuple[bool, str]:
    """
    Test connectivity and authentication without sending any message.
    Does NOT require a chatid.
    Returns (success: bool, error_msg: str).
    """
    result: list = [False, "未执行"]

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result[0], result[1] = loop.run_until_complete(_test_auth_async(bot_id, secret))
        finally:
            loop.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=15)
    if t.is_alive():
        return False, "整体超时（15 s）"
    return result[0], result[1]


def send_markdown(
    bot_id: str,
    secret: str,
    chatid: str,
    content: str,
) -> tuple[bool, str]:
    """
    Send a Markdown message to a WeCom group or user via the Smart Robot API.

    Parameters
    ----------
    bot_id  : Bot ID from the WeCom developer console
    secret  : Bot secret
    chatid  : Group chatid or user userid to send to
    content : Markdown-formatted message body (max 20 480 bytes)

    Returns
    -------
    (success: bool, error_msg: str)
    """
    result: list = [False, "未执行"]

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result[0], result[1] = loop.run_until_complete(
                _send_async(bot_id, secret, chatid, content)
            )
        finally:
            loop.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=25)
    if t.is_alive():
        return False, "整体超时（25 s）"
    return result[0], result[1]


# ---------------------------------------------------------------------------
# Message builder
# ---------------------------------------------------------------------------

def build_signal_message(signals: list[dict[str, Any]]) -> str:
    """Build a Markdown-formatted signal notification from a list of signal dicts."""
    from datetime import date
    today = date.today().isoformat()

    lines = [f"## 📊 商品因子信号通知\n> {today}\n"]
    for s in signals:
        sig = s.get("signal", "-")
        emoji = "🟢" if sig == "买入" else "🔴"
        z = s.get("zscore", 0)
        lines += [
            f"**{s.get('stock_name', '-')}**（{s.get('stock_code', '')}）",
            f"> 商品：{s.get('commodity', '-')}",
            f"> 信号：{emoji} **{sig}**　Z-Score：`{z:.2f}`",
            "",
        ]
    lines.append("> ⚠️ 本信号仅供参考，不构成投资建议。")
    return "\n".join(lines)
