"""Thin async DNS helper. Everything in the engine goes through query() so tests can patch one function."""

_resolver = None


def _get_resolver():
    global _resolver
    if _resolver is None:
        import dns.asyncresolver

        try:
            r = dns.asyncresolver.Resolver()
        except Exception:
            r = dns.asyncresolver.Resolver(configure=False)
            r.nameservers = ["1.1.1.1", "8.8.8.8"]
        r.lifetime = 3.0
        r.timeout = 2.0
        _resolver = r
    return _resolver


async def query(name: str, rdtype: str) -> list[str]:
    """Returns normalized text answers; [] on NXDOMAIN / no answer / timeout.
    MX -> "<pref> <host>", TXT -> joined string, others -> rdata text without trailing dot."""
    import dns.exception

    try:
        answer = await _get_resolver().resolve(name, rdtype)
    except dns.exception.DNSException:
        return []
    except Exception:
        return []
    out: list[str] = []
    for rd in answer:
        if rdtype == "MX":
            out.append(f"{rd.preference} {rd.exchange.to_text().rstrip('.')}")
        elif rdtype == "TXT":
            out.append(b"".join(rd.strings).decode("utf-8", "replace"))
        else:
            out.append(rd.to_text().rstrip("."))
    return out


def parse_mx(records: list[str]) -> list[str]:
    """Sorted (by preference) MX host names."""
    parsed = []
    for r in records:
        try:
            pref, host = r.split(None, 1)
            parsed.append((int(pref), host.strip().lower()))
        except ValueError:
            continue
    return [h for _, h in sorted(parsed) if h and h != "."]
