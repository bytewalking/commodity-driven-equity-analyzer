"""Email notification via SMTP (SSL)."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any


def send_signals(
    smtp_host: str,
    smtp_port: int,
    sender: str,
    password: str,
    recipients: list[str],
    signals: list[dict[str, Any]],
) -> tuple[bool, str]:
    """
    Send signal notification email.
    Returns (success, error_message).
    """
    if not signals:
        return False, "无信号可发送"
    if not recipients:
        return False, "未填写收件人"
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"【商品因子信号】{len(signals)} 个交易信号 - {_today()}"
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(_text_body(signals), "plain", "utf-8"))
        msg.attach(MIMEText(_html_body(signals), "html", "utf-8"))

        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as srv:
            srv.login(sender, password)
            srv.sendmail(sender, recipients, msg.as_string())
        return True, ""
    except Exception as e:
        return False, str(e)


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def _html_body(signals: list[dict]) -> str:
    rows = ""
    for s in signals:
        color = "#28a745" if s.get("signal") == "买入" else "#dc3545"
        rows += (
            f"<tr>"
            f"<td>{s.get('date', '-')}</td>"
            f"<td>{s.get('stock_name', '-')} ({s.get('stock_code', '')})</td>"
            f"<td>{s.get('commodity', '-')}</td>"
            f"<td style='color:{color};font-weight:bold'>{s.get('signal', '-')}</td>"
            f"<td>{s.get('zscore', 0):.2f}</td>"
            f"</tr>"
        )
    return f"""<!DOCTYPE html><html><body>
<h2 style="font-family:sans-serif">商品因子股票信号通知</h2>
<table border="1" cellpadding="6" cellspacing="0"
       style="border-collapse:collapse;font-family:sans-serif;font-size:14px">
  <thead style="background:#f5f5f5">
    <tr><th>日期</th><th>股票</th><th>商品</th><th>信号</th><th>Z-Score</th></tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
<p style="color:#888;font-size:12px;font-family:sans-serif;margin-top:16px">
  ⚠️ 本信号仅供参考，不构成投资建议。历史回测不代表未来收益。
</p>
</body></html>"""


def _text_body(signals: list[dict]) -> str:
    lines = [f"商品因子股票信号通知  {_today()}", "=" * 40]
    for s in signals:
        lines += [
            f"日期: {s.get('date', '-')}",
            f"股票: {s.get('stock_name', '-')} ({s.get('stock_code', '')})",
            f"商品: {s.get('commodity', '-')}",
            f"信号: {s.get('signal', '-')}",
            f"Z-Score: {s.get('zscore', 0):.2f}",
            "-" * 20,
        ]
    lines.append("\n免责声明：本信号仅供参考，不构成投资建议。")
    return "\n".join(lines)
