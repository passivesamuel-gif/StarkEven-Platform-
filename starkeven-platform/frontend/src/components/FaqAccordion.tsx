'use client';

import { useState } from 'react';

const FAQS = [
  {
    q: 'How does 24-hour smart caching save credits?',
    a: 'Every enriched domain result is cached in Redis for 24 hours. Repeated lookups for the same domain within that window return immediately and cost zero credits.',
  },
  {
    q: 'Does email verification send real emails or charge when port 25 is blocked?',
    a: 'No email is ever delivered during verification—StarkEven probes MX hosts up to RCPT TO with a 3-second timeout and quits cleanly. If outbound port 25 is blocked, the check returns "unverifiable_network" with valid MX metadata and automatically refunds the credit.',
  },
  {
    q: 'How does Lead Autopilot discover and deduplicate leads?',
    a: 'Lead Autopilot runs deterministic web discovery from your keywords, fingerprints each company’s tech stack and careers/ATS signals, verifies role mailboxes, and deduplicates atomically per organization before exporting to CSV or pushing to HubSpot, Salesforce, or webhooks.',
  },
  {
    q: 'What does the zero-cost-per-API-call Transactional OTP API support?',
    a: 'You can send and verify 6-digit OTP codes via your own SMTP relay (Gmail App Password, Brevo, or Postfix) or direct MX delivery with 60-second cooldowns, salted SHA-256 hashing, and automatic 5-attempt brute-force lockout.',
  },
  {
    q: 'How are credits and webhook callbacks secured?',
    a: 'Billing events require valid HMAC-SHA256 signatures from Stripe or Lemon Squeezy with atomic Redis + PostgreSQL idempotency. Bulk completion callbacks are signed with your organization’s dedicated signing secret.',
  },
];

export default function FaqAccordion() {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  return (
    <section id="faq" className="border-t border-black/[0.08] px-5 py-24 dark:border-white/[0.08]">
      <div className="mx-auto max-w-[780px]">
        <div className="mb-12 text-center">
          <h2 className="text-balance text-3xl font-semibold tracking-[-0.03em] sm:text-5xl">
            Frequently asked questions.
          </h2>
          <p className="mt-3 text-base text-[#1D1D1F]/60 dark:text-[#F5F5F7]/60">
            Clear answers on credits, deterministic signals, and infrastructure.
          </p>
        </div>

        <div className="divide-y divide-black/[0.08] rounded-[24px] border border-black/[0.08] bg-white dark:divide-white/[0.08] dark:border-white/[0.08] dark:bg-[#141416]">
          {FAQS.map((item, idx) => {
            const isOpen = openIndex === idx;
            return (
              <div key={item.q} className="px-6 py-5 sm:px-8">
                <button
                  type="button"
                  aria-expanded={isOpen}
                  aria-controls={`faq-panel-${idx}`}
                  data-testid={`faq-toggle-${idx}`}
                  onClick={() => setOpenIndex(isOpen ? null : idx)}
                  className="flex w-full items-center justify-between gap-4 text-left"
                >
                  <span className="text-[15px] font-semibold tracking-tight text-[#1D1D1F] dark:text-[#F5F5F7] sm:text-base">
                    {item.q}
                  </span>
                  <span
                    aria-hidden="true"
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-black/[0.08] text-sm font-medium text-[#6E6E73] transition-transform duration-200 dark:border-white/[0.08] dark:text-[#8E8E93] ${
                      isOpen ? 'rotate-45' : ''
                    }`}
                  >
                    +
                  </span>
                </button>
                {isOpen && (
                  <p
                    id={`faq-panel-${idx}`}
                    className="mt-3 pr-8 text-sm leading-relaxed text-[#1D1D1F]/65 dark:text-[#F5F5F7]/65"
                  >
                    {item.a}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
