from urllib.parse import urlparse

import httpx

from ..netguard import assert_public_url, request_guard

_transport = None  # tests inject httpx.MockTransport
HUBSPOT_URL = "https://api.hubapi.com/crm/v3/objects/companies"
SALESFORCE_API = "v59.0"


def _fields(record: dict) -> dict:
    company = record.get("company") or {}
    domain = record.get("domain", "")
    return {
        "name": company.get("name") or record.get("company_name") or domain,
        "domain": domain,
        "website": company.get("website") or (f"https://{domain}" if domain else ""),
        "description": (company.get("description") or record.get("meta_description") or "")[:1000],
        "linkedin": company.get("linkedin") or "",
    }


def format_hubspot(record: dict) -> dict:
    f = _fields(record)
    props = {
        "name": f["name"], "domain": f["domain"], "description": f["description"],
        "linkedin_company_page": f["linkedin"],
    }
    return {"properties": {k: v for k, v in props.items() if v}}


def format_salesforce(record: dict, sobject: str = "Account") -> dict:
    f = _fields(record)
    if sobject == "Lead":
        body = {"Company": f["name"], "LastName": "[not provided]", "Website": f["website"], "Description": f["description"]}
    else:
        body = {"Name": f["name"], "Website": f["website"], "Description": f["description"]}
    return {k: v for k, v in body.items() if v}


def format_webhook(record: dict) -> dict:
    return {"source": "starkeven", "event": "company.enriched", "record": record}


def _valid_salesforce_instance(url: str) -> str:
    p = urlparse(url or "")
    host = (p.hostname or "").lower()
    if p.scheme != "https" or not (host.endswith(".salesforce.com") or host.endswith(".force.com")):
        raise ValueError("instance_url must be an https URL on salesforce.com or force.com")
    return f"https://{host}"


async def push_to_crm(provider, target, record, *, instance_url=None, sobject="Account") -> dict:
    headers = {"Content-Type": "application/json", "User-Agent": "StarkEven-Export/1.0"}
    if provider == "hubspot":
        url, body = HUBSPOT_URL, format_hubspot(record)
        headers["Authorization"] = f"Bearer {target}"
    elif provider == "salesforce":
        base = _valid_salesforce_instance(instance_url or "")
        url = f"{base}/services/data/{SALESFORCE_API}/sobjects/{sobject}"
        body = format_salesforce(record, sobject)
        headers["Authorization"] = f"Bearer {target}"
    else:
        url = await assert_public_url(target)
        body = format_webhook(record)
    try:
        async with httpx.AsyncClient(
            timeout=15.0, follow_redirects=False, trust_env=False,
            event_hooks={"request": [request_guard]}, transport=_transport,
        ) as client:
            r = await client.post(url, json=body, headers=headers)
        ok = 200 <= r.status_code < 300
        return {
            "delivered": ok, "provider": provider, "upstream_status": r.status_code,
            "upstream_body": r.text[:500], "payload": body,
        }
    except httpx.HTTPError as e:
        return {
            "delivered": False, "provider": provider, "upstream_status": None,
            "upstream_body": type(e).__name__, "payload": body,
        }
