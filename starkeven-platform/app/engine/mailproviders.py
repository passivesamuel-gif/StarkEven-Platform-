_MX_PROVIDERS = [
    ("Google Workspace", ("aspmx.l.google.com", "googlemail.com", "smtp.google.com")),
    ("Microsoft 365", ("mail.protection.outlook.com",)),
    ("Zoho Mail", ("zoho.com", "zoho.eu", "zoho.in", "zoho.com.au")),
    ("Proofpoint", ("pphosted.com", "ppe-hosted.com")),
    ("Mimecast", ("mimecast.com",)),
    ("Barracuda", ("barracudanetworks.com",)),
    ("Cisco Email Security", ("iphmx.com",)),
    ("Proton Mail", ("protonmail.ch",)),
    ("Fastmail", ("messagingengine.com",)),
    ("Yandex Mail", ("yandex.net", "yandex.ru")),
    ("Amazon WorkMail", ("awsapps.com",)),
    ("Rackspace Email", ("emailsrvr.com",)),
    ("GoDaddy Email", ("secureserver.net",)),
    ("Namecheap Private Email", ("privateemail.com",)),
    ("Cloudflare Email Routing", ("mx.cloudflare.net",)),
    ("Mailgun", ("mailgun.org",)),
]


def classify_email_provider(mx_hosts: list[str]) -> str | None:
    if not mx_hosts:
        return None
    joined = [h.lower() for h in mx_hosts]
    for name, needles in _MX_PROVIDERS:
        if any(n in h for h in joined for n in needles):
            return name
    return "Custom / self-hosted"
