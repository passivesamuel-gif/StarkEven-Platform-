"""Deterministic technology fingerprinting from HTML, response headers and DNS records."""

# (name, category, html/script patterns, header patterns, dns patterns) -- all lowercase substrings.
SIGNATURES: list[tuple] = [
    ("HubSpot", "Marketing / CRM", ("js.hs-scripts.com", "js.hsforms.net", "hs-analytics.net", "hubspotusercontent"), (), ("hubspot",)),
    ("Salesforce", "CRM", (".force.com", "salesforceliveagent", "pi.pardot.com"), (), ("_spf.salesforce.com", "salesforce.com")),
    ("Stripe", "Payments", ("js.stripe.com", "checkout.stripe.com"), (), ("stripe-verification",)),
    ("PayPal", "Payments", ("paypalobjects.com", "paypal.com/sdk"), (), ()),
    ("Braintree", "Payments", ("braintreegateway.com", "js.braintreegateway.com"), (), ()),
    ("Shopify", "E-commerce", ("cdn.shopify.com", "myshopify.com"), ("x-shopify-stage", "x-shopid"), ("shops.myshopify.com",)),
    ("Intercom", "Customer support", ("widget.intercom.io", "intercomcdn.com"), (), ()),
    ("Zendesk", "Customer support", ("static.zdassets.com", "zendesk.com"), (), ("zendesk.com",)),
    ("Freshworks", "Customer support", ("freshdesk.com", "freshworks.com", "freshchat"), (), ("freshdesk.com",)),
    ("Drift", "Chat / Sales", ("js.driftt.com", "drift.com/"), (), ()),
    ("Crisp", "Chat", ("client.crisp.chat",), (), ()),
    ("Segment", "Analytics / CDP", ("cdn.segment.com", "cdn.segment.io"), (), ()),
    ("Google Analytics", "Analytics", ("google-analytics.com", "googletagmanager.com/gtag"), (), ()),
    ("Google Tag Manager", "Tag management", ("googletagmanager.com/gtm.js",), (), ()),
    ("Mixpanel", "Analytics", ("cdn.mxpnl.com", "mixpanel.com/"), (), ()),
    ("Amplitude", "Analytics", ("cdn.amplitude.com",), (), ()),
    ("Heap", "Analytics", ("heapanalytics.com", "heap-analytics"), (), ()),
    ("Hotjar", "Analytics", ("static.hotjar.com",), (), ()),
    ("FullStory", "Analytics", ("edge.fullstory.com", "fullstory.com/s/fs.js"), (), ()),
    ("Optimizely", "Experimentation", ("cdn.optimizely.com",), (), ()),
    ("Meta Pixel", "Advertising", ("connect.facebook.net", "fbq("), (), ()),
    ("LinkedIn Insight", "Advertising", ("snap.licdn.com",), (), ()),
    ("TikTok Pixel", "Advertising", ("analytics.tiktok.com",), (), ()),
    ("Marketo", "Marketing automation", ("munchkin.marketo.net", "mktoresp"), (), ("mktomail.com", "marketo.com")),
    ("Mailchimp", "Email marketing", ("chimpstatic.com", "list-manage.com"), (), ("mcsv.net", "mailchimp")),
    ("Klaviyo", "Email marketing", ("static.klaviyo.com", "klaviyo.com/onsite"), (), ("klaviyomail.com",)),
    ("SendGrid", "Email delivery", (), (), ("sendgrid.net",)),
    ("Mailgun", "Email delivery", (), (), ("mailgun.org",)),
    ("Postmark", "Email delivery", (), (), ("postmarkapp.com", "mtasv.net")),
    ("Amazon SES", "Email delivery", (), (), ("amazonses.com",)),
    ("Google Workspace", "Email / Productivity", (), (), ("aspmx.l.google.com", "_spf.google.com", "googlemail.com", "smtp.google.com")),
    ("Microsoft 365", "Email / Productivity", (), (), ("mail.protection.outlook.com", "spf.protection.outlook.com")),
    ("Zoho", "Email / Productivity", ("zohopublic.com", "zoho.com/salesiq"), (), ("zoho.com", "zoho.eu")),
    ("Cloudflare", "CDN / Security", ("cdnjs.cloudflare.com", "cloudflareinsights.com"), ("server: cloudflare", "cf-ray"), ("cloudflare.net",)),
    ("AWS", "Cloud", ("amazonaws.com", "cloudfront.net"), ("x-amz-", "server: amazons3", "awselb"), ("amazonaws.com",)),
    ("Fastly", "CDN", (), ("x-fastly-request-id", "server: fastly"), ("fastly.net",)),
    ("Akamai", "CDN", ("akamaihd.net", "akamaized.net"), ("akamaighost", "x-akamai"), ("akamai.net", "edgekey.net")),
    ("Vercel", "Hosting", (), ("server: vercel", "x-vercel-id"), ("vercel-dns.com",)),
    ("Netlify", "Hosting", (), ("server: netlify", "x-nf-request-id"), ("netlify.app", "netlify.com")),
    ("WordPress", "CMS", ("/wp-content/", "/wp-includes/"), ("x-pingback",), ()),
    ("Webflow", "CMS / Site builder", ("webflow.com", "data-wf-page"), (), ()),
    ("Squarespace", "CMS / Site builder", ("static1.squarespace.com", "squarespace.com"), (), ()),
    ("Wix", "CMS / Site builder", ("wixstatic.com", "static.parastorage.com"), ("x-wix-request-id",), ()),
    ("Next.js", "Web framework", ("/_next/static", "__next_data__"), ("x-powered-by: next.js",), ()),
    ("Nuxt", "Web framework", ("/_nuxt/", "__nuxt"), (), ()),
    ("Gatsby", "Web framework", ("___gatsby",), (), ()),
    ("Angular", "Web framework", ("ng-version=",), (), ()),
    ("Sentry", "Monitoring", ("browser.sentry-cdn.com", "sentry.io"), (), ()),
    ("Datadog", "Monitoring", ("datadoghq-browser-agent.com", "datadoghq.com"), (), ()),
    ("New Relic", "Monitoring", ("js-agent.newrelic.com", "nr-data.net"), (), ()),
    ("OneTrust", "Privacy / Consent", ("cdn.cookielaw.org", "onetrust.com"), (), ()),
    ("reCAPTCHA", "Security", ("google.com/recaptcha", "gstatic.com/recaptcha"), (), ()),
    ("Calendly", "Scheduling", ("assets.calendly.com", "calendly.com/"), (), ()),
    ("Typeform", "Forms", ("embed.typeform.com",), (), ()),
]


def detect_tech(html: str, headers: str, dns: str) -> list[dict]:
    html, headers, dns = html.lower(), headers.lower(), dns.lower()
    found = []
    for name, category, h_pats, hd_pats, d_pats in SIGNATURES:
        if (
            any(p in html for p in h_pats)
            or any(p in headers for p in hd_pats)
            or any(p in dns for p in d_pats)
        ):
            found.append({"name": name, "category": category})
    return found
