'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

type InfoTopic = 'security' | 'privacy' | 'terms';

const MODAL_CONTENT: Record<InfoTopic, { title: string; summary: string; points: string[] }> = {
  security: {
    title: 'Security Architecture',
    summary: 'StarkEven is engineered with defense-in-depth across network egress, authentication, and billing integrity.',
    points: [
      'API keys are generated using cryptographically random tokens and stored solely as SHA-256 digests.',
      'Outbound enrichment HTTP requests validate resolved DNS records and block loopback, link-local, and private network ranges against SSRF.',
      'Billing and bulk completion webhooks enforce constant-time HMAC-SHA256 verification and atomic replay protection.',
      'SMTP mailbox verification completes at RCPT TO without transmitting email payloads.',
    ],
  },
  privacy: {
    title: 'Privacy Notice',
    summary: 'StarkEven processes publicly accessible business domain metadata and organization-scoped telemetry.',
    points: [
      'Organization records, API keys, usage logs, and Lead Autopilot deliveries are strictly isolated by authenticated org ID.',
      'Domain enrichment payloads reflect public website headers, DNS records, and public careers pages.',
      'Cached enrichment entries expire automatically after 24 hours.',
      'No third-party AI model training or external LLM inference is ever performed on your queries or delivered leads.',
    ],
  },
  terms: {
    title: 'Terms of Service',
    summary: 'Transparent credit metering and predictable API usage terms for every StarkEven workspace.',
    points: [
      'Live domain enrichment, email verification, and newly discovered Autopilot leads deduct 1 credit per uncached lookup.',
      'Cached enrichment repeats within 24 hours and network-blocked SMTP checks (unverifiable_network) are never billed.',
      'Each plan enforces a per-minute sliding-window rate limit to ensure consistent sub-second platform availability.',
      'API keys may be scoped, rotated, or revoked immediately from the dashboard at any time.',
    ],
  },
};

export default function LandingFooter() {
  const [modal, setModal] = useState<InfoTopic | null>(null);

  useEffect(() => {
    if (!modal) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setModal(null);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [modal]);

  const active = modal ? MODAL_CONTENT[modal] : null;

  return (
    <footer className="border-t border-black/[0.08] bg-[#FBFBFD] px-5 py-16 text-sm text-[#1D1D1F]/70 dark:border-white/[0.08] dark:bg-[#0B0B0C] dark:text-[#F5F5F7]/65">
      <div className="mx-auto grid max-w-[1120px] gap-10 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-3">
          <p className="text-[15px] font-semibold tracking-tight text-[#1D1D1F] dark:text-[#F5F5F7]">
            StarkEven
          </p>
          <p className="max-w-xs text-[13px] leading-relaxed text-[#1D1D1F]/60 dark:text-[#F5F5F7]/60">
            Deterministic B2B company enrichment, autonomous lead discovery, bulk CSV pipelines, and non-intrusive SMTP verification.
          </p>
          <p className="pt-2 text-xs text-[#1D1D1F]/45 dark:text-[#F5F5F7]/45">
            © {new Date().getFullYear()} StarkEven. All rights reserved.
          </p>
        </div>

        <div className="space-y-3">
          <p className="text-xs font-semibold tracking-wide text-[#1D1D1F] dark:text-[#F5F5F7]">
            Platform
          </p>
          <ul className="space-y-2.5 text-[13px]">
            <li>
              <a href="#demo" className="transition hover:text-[#1D1D1F] dark:hover:text-[#F5F5F7]">
                Live Demo
              </a>
            </li>
            <li>
              <a href="#pricing" className="transition hover:text-[#1D1D1F] dark:hover:text-[#F5F5F7]">
                Pricing
              </a>
            </li>
            <li>
              <a href="/docs" className="transition hover:text-[#1D1D1F] dark:hover:text-[#F5F5F7]">
                API Docs
              </a>
            </li>
          </ul>
        </div>

        <div className="space-y-3">
          <p className="text-xs font-semibold tracking-wide text-[#1D1D1F] dark:text-[#F5F5F7]">
            Account
          </p>
          <ul className="space-y-2.5 text-[13px]">
            <li>
              <Link href="/login" className="transition hover:text-[#1D1D1F] dark:hover:text-[#F5F5F7]">
                Sign In
              </Link>
            </li>
            <li>
              <Link href="/dashboard" className="transition hover:text-[#1D1D1F] dark:hover:text-[#F5F5F7]">
                Dashboard
              </Link>
            </li>
            <li>
              <a href="#api" className="transition hover:text-[#1D1D1F] dark:hover:text-[#F5F5F7]">
                REST Reference
              </a>
            </li>
          </ul>
        </div>

        <div className="space-y-3">
          <p className="text-xs font-semibold tracking-wide text-[#1D1D1F] dark:text-[#F5F5F7]">
            Trust &amp; Legal
          </p>
          <ul className="space-y-2.5 text-[13px]">
            <li>
              <button
                type="button"
                onClick={() => setModal('security')}
                className="transition hover:text-[#1D1D1F] dark:hover:text-[#F5F5F7]"
              >
                Security
              </button>
            </li>
            <li>
              <button
                type="button"
                onClick={() => setModal('privacy')}
                className="transition hover:text-[#1D1D1F] dark:hover:text-[#F5F5F7]"
              >
                Privacy
              </button>
            </li>
            <li>
              <button
                type="button"
                onClick={() => setModal('terms')}
                className="transition hover:text-[#1D1D1F] dark:hover:text-[#F5F5F7]"
              >
                Terms
              </button>
            </li>
          </ul>
        </div>
      </div>

      {active && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="footer-info-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
          onClick={() => setModal(null)}
        >
          <div
            className="w-full max-w-lg rounded-2xl border border-black/[0.08] bg-white p-6 text-[#1D1D1F] shadow-2xl dark:border-white/[0.1] dark:bg-[#141416] dark:text-[#F5F5F7]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 id="footer-info-modal-title" className="text-lg font-semibold tracking-tight">
                  {active.title}
                </h3>
                <p className="mt-1 text-[13px] text-[#1D1D1F]/65 dark:text-[#F5F5F7]/65">
                  {active.summary}
                </p>
              </div>
              <button
                type="button"
                aria-label="Close modal"
                onClick={() => setModal(null)}
                className="rounded-lg border border-black/[0.08] px-2.5 py-1 text-xs font-medium text-[#1D1D1F]/70 transition hover:bg-black/[0.04] dark:border-white/[0.1] dark:text-[#F5F5F7]/70 dark:hover:bg-white/[0.06]"
              >
                Close
              </button>
            </div>
            <ul className="mt-5 space-y-2.5 border-t border-black/[0.08] pt-4 text-[13px] leading-relaxed text-[#1D1D1F]/80 dark:border-white/[0.08] dark:text-[#F5F5F7]/80">
              {active.points.map((pt) => (
                <li key={pt} className="flex gap-2.5">
                  <span aria-hidden="true" className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-600 dark:bg-brand-500" />
                  <span>{pt}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </footer>
  );
}
