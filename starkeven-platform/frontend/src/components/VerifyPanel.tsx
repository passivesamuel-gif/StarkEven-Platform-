'use client';

import { useState } from 'react';
import { errMsg, verifyEmail } from '@/lib/api';
import type { VerifyResult } from '@/lib/api';

const LABEL: Record<VerifyResult['smtp_deliverable'], { text: string; cls: string }> = {
  valid: { text: 'Deliverable', cls: 'bg-[#34C759]/15 text-[#248A3D] dark:text-[#30D158]' },
  invalid: { text: 'Mailbox does not exist', cls: 'bg-[#FF3B30]/15 text-[#D70015] dark:text-[#FF453A]' },
  catch_all: { text: 'Catch-all domain (cannot confirm mailbox)', cls: 'bg-[#FF9F0A]/15 text-[#B25000] dark:text-[#FFD60A]' },
  unknown: { text: 'Could not determine', cls: 'bg-[#F5F5F7] text-[#6E6E73] dark:bg-[#2C2C2E] dark:text-[#8E8E93]' },
  unverifiable_network: { text: 'SMTP blocked on network (credit refunded)', cls: 'bg-[#FF9F0A]/15 text-[#B25000] dark:text-[#FFD60A]' },
};

export default function VerifyPanel({ onSpend }: { onSpend: () => void }) {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<VerifyResult | null>(null);

  async function run() {
    if (!email.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setRes(await verifyEmail(email.trim()));
      onSpend();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-black/[0.06] bg-white p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none">
        <div className="mb-4">
          <h1 className="text-xl font-semibold tracking-[-0.02em] text-[#1D1D1F] dark:text-[#F5F5F7]">
            Email Verifier
          </h1>
          <p className="mt-1 text-sm text-[#6E6E73] dark:text-[#8E8E93]">
            Check syntax, MX mail provider, and non-intrusive SMTP mailbox reachability without sending a message.
          </p>
        </div>

        <div className="flex flex-col gap-2.5 sm:flex-row">
          <input
            className="w-full rounded-xl border border-black/[0.08] bg-[#F5F5F7] px-4 py-2.5 text-sm text-[#1D1D1F] placeholder-[#6E6E73]/70 focus:border-[#0071E3] focus:bg-white focus:outline-none dark:border-white/[0.08] dark:bg-[#2C2C2E] dark:text-[#F5F5F7] dark:placeholder-[#8E8E93] dark:focus:border-[#0A84FF]"
            type="email"
            placeholder="jane@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void run(); }}
          />
          <button
            type="button"
            className="inline-flex w-full shrink-0 items-center justify-center whitespace-nowrap rounded-full bg-[#0071E3] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#0077ED] disabled:cursor-not-allowed disabled:opacity-50 dark:bg-[#0A84FF] dark:hover:bg-[#2E96FF] sm:w-auto"
            disabled={busy || !email.trim()}
            onClick={() => void run()}
          >
            {busy ? 'Checking…' : 'Verify (1 credit)'}
          </button>
        </div>
      </div>

      {error && (
        <p className="rounded-2xl border border-[#FF3B30]/25 bg-[#FF3B30]/10 px-4 py-3 text-sm text-[#D70015] dark:text-[#FF453A]">
          {error}
        </p>
      )}

      {res && (
        <div className="space-y-4 rounded-2xl border border-black/[0.06] bg-white p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-mono text-sm font-medium text-[#1D1D1F] dark:text-[#F5F5F7]">
              {res.email}
            </span>
            <span className={`inline-block rounded-full px-3 py-1 text-xs font-medium ${LABEL[res.smtp_deliverable].cls}`}>
              {LABEL[res.smtp_deliverable].text}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="rounded-2xl bg-[#F5F5F7] p-3.5 dark:bg-[#2C2C2E]">
              <span className="block text-xs text-[#6E6E73] dark:text-[#8E8E93]">Format</span>
              <span className="mt-0.5 block text-sm font-semibold">{res.format_valid ? 'Valid' : 'Invalid'}</span>
            </div>
            <div className="rounded-2xl bg-[#F5F5F7] p-3.5 dark:bg-[#2C2C2E]">
              <span className="block text-xs text-[#6E6E73] dark:text-[#8E8E93]">MX Records</span>
              <span className="mt-0.5 block text-sm font-semibold">{res.mx_valid ? 'Found' : 'None'}</span>
            </div>
            <div className="rounded-2xl bg-[#F5F5F7] p-3.5 dark:bg-[#2C2C2E]">
              <span className="block text-xs text-[#6E6E73] dark:text-[#8E8E93]">Mail Provider</span>
              <span className="mt-0.5 block text-sm font-semibold">{res.provider ?? 'N/A'}</span>
            </div>
          </div>

          {res.reason && (
            <p className="text-xs text-[#6E6E73] dark:text-[#8E8E93]">
              Detail: {res.reason.replace(/_/g, ' ')}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
