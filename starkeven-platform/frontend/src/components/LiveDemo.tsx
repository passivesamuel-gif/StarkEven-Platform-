'use client';

import { useState } from 'react';
import { demoLookup, enrichDomain, errMsg, getToken } from '@/lib/api';
import type { EnrichResponse } from '@/lib/api';
import EnrichResult from './EnrichResult';

export default function LiveDemo() {
  const [domain, setDomain] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EnrichResponse | null>(null);

  async function run() {
    if (!domain.trim()) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      // Signed-in visitors use the real endpoint; everyone else gets the limited public demo.
      setResult(getToken() ? await enrichDomain(domain.trim()) : await demoLookup(domain.trim()));
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-2xl">
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          className="input !rounded-full !border !border-black/[0.1] !bg-[#FBFBFD] !px-5 !py-3 !text-base dark:!border-white/[0.12] dark:!bg-[#0B0B0C] dark:!text-[#F5F5F7] dark:placeholder-white/40"
          placeholder="Try it: stripe.com"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') void run(); }}
          aria-label="Company domain"
        />
        <button className="btn w-full whitespace-nowrap !rounded-full !px-6 sm:w-auto" onClick={() => void run()} disabled={busy || !domain.trim()}>
          {busy ? 'Looking up…' : 'Enrich'}
        </button>
      </div>
      {error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/60 dark:text-red-300">{error}</p>}
      {result && <div className="mt-4"><EnrichResult data={result.data} cached={result.cached} /></div>}
    </div>
  );
}
