'use client';

import { useState } from 'react';
import { enrichDomain, errMsg } from '@/lib/api';
import type { EnrichResponse } from '@/lib/api';
import EnrichResult from './EnrichResult';

export default function EnrichPanel({ onSpend }: { onSpend: () => void }) {
  const [domain, setDomain] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<EnrichResponse | null>(null);

  async function run(force: boolean) {
    if (!domain.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setRes(await enrichDomain(domain.trim(), force));
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
            Company Enrichment
          </h1>
          <p className="mt-1 text-sm text-[#6E6E73] dark:text-[#8E8E93]">
            Fingerprint 54+ technologies, email infrastructure, and hiring signals from any domain. Cached lookups within 24 hours are free.
          </p>
        </div>

        <div className="flex flex-col gap-2.5 sm:flex-row">
          <input
            className="w-full rounded-xl border border-black/[0.08] bg-[#F5F5F7] px-4 py-2.5 text-sm text-[#1D1D1F] placeholder-[#6E6E73]/70 focus:border-[#0071E3] focus:bg-white focus:outline-none dark:border-white/[0.08] dark:bg-[#2C2C2E] dark:text-[#F5F5F7] dark:placeholder-[#8E8E93] dark:focus:border-[#0A84FF] dark:focus:bg-[#2C2C2E]"
            placeholder="example.com"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void run(false); }}
          />
          <button
            type="button"
            className="inline-flex w-full shrink-0 items-center justify-center whitespace-nowrap rounded-full bg-[#0071E3] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#0077ED] disabled:cursor-not-allowed disabled:opacity-50 dark:bg-[#0A84FF] dark:hover:bg-[#2E96FF] sm:w-auto"
            disabled={busy || !domain.trim()}
            onClick={() => void run(false)}
          >
            {busy ? 'Working…' : 'Enrich (1 credit)'}
          </button>
        </div>
      </div>

      {error && (
        <p className="rounded-2xl border border-[#FF3B30]/25 bg-[#FF3B30]/10 px-4 py-3 text-sm text-[#D70015] dark:text-[#FF453A]">
          {error}
        </p>
      )}

      {res && (
        <div className="space-y-4">
          <EnrichResult data={res.data} cached={res.cached} />
          <button
            type="button"
            className="inline-flex items-center justify-center rounded-full border border-black/[0.1] bg-white px-4 py-2 text-xs font-medium text-[#1D1D1F] transition hover:bg-black/[0.03] disabled:opacity-50 dark:border-white/[0.12] dark:bg-[#1C1C1E] dark:text-[#F5F5F7] dark:hover:bg-[#2C2C2E]"
            disabled={busy}
            onClick={() => void run(true)}
          >
            Refresh live data (1 credit)
          </button>
        </div>
      )}
    </div>
  );
}
