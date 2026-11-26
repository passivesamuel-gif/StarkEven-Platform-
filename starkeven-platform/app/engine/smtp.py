"""Non-intrusive SMTP mailbox probe: EHLO -> MAIL FROM -> RCPT TO (+ catch-all probe) -> QUIT.
No message is ever sent (we never issue DATA)."""
import asyncio
import re
import secrets
from dataclasses import dataclass

_POLICY_WORDS = re.compile(
    r"block|spam|policy|denied|blacklist|blocklist|reputation|spamhaus|not authori|relay|"
    r"banned|rejected due|access denied|too many|rate limit|sender verify",
    re.I,
)


@dataclass
class ProbeResult:
    status: str  # valid | invalid | catch_all | unknown
    reason: str | None = None
    code: int | None = None


async def _read_reply(reader: asyncio.StreamReader, timeout: float) -> tuple[int, str]:
    lines: list[str] = []
    while True:
        raw = await asyncio.wait_for(reader.readline(), timeout)
        if not raw:
            raise ConnectionError("connection closed")
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        lines.append(line)
        if len(lines) > 50:
            raise ConnectionError("reply too long")
        if len(line) < 4 or line[3] != "-":
            break
    try:
        return int(lines[-1][:3]), " ".join(lines)
    except ValueError:
        raise ConnectionError("malformed reply")


async def _cmd(reader, writer, command: str, timeout: float) -> tuple[int, str]:
    writer.write((command + "\r\n").encode())
    await asyncio.wait_for(writer.drain(), timeout)
    return await _read_reply(reader, timeout)


def _classify_rcpt_rejection(code: int, text: str) -> ProbeResult:
    if 400 <= code < 500:
        return ProbeResult("unknown", "temporary_failure", code)  # greylisting / throttling
    if code in (550, 551, 553) and not _POLICY_WORDS.search(text) and " 5.7." not in f" {text}":
        return ProbeResult("invalid", "mailbox_rejected", code)
    return ProbeResult("unknown", "policy_rejection", code)


async def smtp_probe(
    host: str,
    email: str,
    *,
    port: int = 25,
    helo: str = "verify.starkeven.local",
    timeout: float = 3.0,
    catch_all_probe: bool = True,
) -> ProbeResult:
    domain = email.rsplit("@", 1)[-1]
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except (OSError, asyncio.TimeoutError):
        return ProbeResult("unknown", "connection_failed")  # e.g. outbound port 25 blocked
    try:
        code, _ = await _read_reply(reader, timeout)
        if code != 220:
            return ProbeResult("unknown", "bad_banner", code)
        code, _ = await _cmd(reader, writer, f"EHLO {helo}", timeout)
        if code >= 400:
            code, _ = await _cmd(reader, writer, f"HELO {helo}", timeout)
            if code >= 400:
                return ProbeResult("unknown", "helo_rejected", code)
        code, text = await _cmd(reader, writer, f"MAIL FROM:<verify@{helo}>", timeout)
        if code >= 400:
            return ProbeResult("unknown", "mail_from_rejected", code)
        code, text = await _cmd(reader, writer, f"RCPT TO:<{email}>", timeout)
        if code not in (250, 251):
            return _classify_rcpt_rejection(code, text)
        if not catch_all_probe:
            return ProbeResult("valid", None, code)
        random_rcpt = f"sk-{secrets.token_hex(8)}@{domain}"
        pcode, _ = await _cmd(reader, writer, f"RCPT TO:<{random_rcpt}>", timeout)
        if pcode in (250, 251):
            return ProbeResult("catch_all", "domain_accepts_all", code)
        return ProbeResult("valid", None, code)
    except (OSError, asyncio.TimeoutError, ConnectionError):
        return ProbeResult("unknown", "smtp_error")
    finally:
        try:
            writer.write(b"QUIT\r\n")
            await asyncio.wait_for(writer.drain(), 1.0)
        except Exception:
            pass
        writer.close()
