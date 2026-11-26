'use client';

import { useEffect, useRef, useState } from 'react';
import { bulkStatus, downloadBulk, errMsg, startBulkCsv } from '@/lib/api';
import type { BulkStatus } from '@/lib/api';

export default function BulkPanel({ onSpend, signingSecret }: { onSpend: () => void; signingSecret?: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [webhook, setWebhook] = useState('');
  const [batch, setBatch] = useState<string | null>(null);
  const [status, setStatus] = useState<BulkStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!batch) return;
    const tick = async () => {
      try {
        const s = await bulkStatus(batch);
        setStatus(s);
        if (s.status === 'completed' || s.status === 'failed') {
          if (timer.current) clearInterval(timer.current);
          onSpend();
        }
      } catch (e) {
        setError(errMsg(e));
        if (timer.current) clearInterval(timer.current);
      }
    };
    void tick();
    timer.current = setInterval(() => void tick(), 2000);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batch]);

  async function start() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const res = await startBulkCsv(file, webhook);
      setBatch(res.batch_id);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    if (!batch) return;
    try {
      const blob = await downloadBulk(batch);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `starkeven-${batch}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(errMsg(e));
    }
  }

  const pct = status ? Math.round(status.progress * 100) : 0;
  return (
    <div className="space-y-6">
      <div className="space-y-5 rounded-2xl border border-black/[0.06] bg-white p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none">
        <div>
          <h1 className="text-xl font-semibold tracking-[-0.02em] text-[#1D1D1F] dark:text-[#F5F5F7]">
            Bulk CSV Enrichment
          </h1>
          <p className="mt-1 text-sm text-[#6E6E73] dark:text-[#8E8E93]">
            Upload a CSV with a <code className="rounded bg-[#F5F5F7] px-1.5 py-0.5 font-mono text-xs dark:bg-[#2C2C2E]">domain</code> column (up to 10,000 rows, 5 MB). Cached domains are free; each live lookup costs 1 credit.
          </p>
        </div>

        <div className="space-y-3 rounded-2xl bg-[#F5F5F7] p-4 dark:bg-[#2C2C2E]">
          <label className="block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
            CSV File
          </label>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-[#1D1D1F] file:mr-3 file:rounded-full file:border-0 file:bg-white file:px-4 file:py-1.5 file:text-xs file:font-medium file:text-[#1D1D1F] hover:file:bg-black/[0.04] dark:text-[#F5F5F7] dark:file:bg-[#1C1C1E] dark:file:text-[#F5F5F7]"
          />
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <input
            className="w-full rounded-xl border border-black/[0.08] bg-[#F5F5F7] px-4 py-2.5 text-sm text-[#1D1D1F] placeholder-[#6E6E73]/70 focus:border-[#0071E3] focus:bg-white focus:outline-none dark:border-white/[0.08] dark:bg-[#2C2C2E] dark:text-[#F5F5F7] dark:placeholder-[#8E8E93] dark:focus:border-[#0A84FF]"
            placeholder="Webhook URL (optional)"
            value={webhook}
            onChange={(e) => setWebhook(e.target.value)}
          />
          <button
            type="button"
            className="inline-flex w-full shrink-0 items-center justify-center whitespace-nowrap rounded-full bg-[#0071E3] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#0077ED] disabled:cursor-not-allowed disabled:opacity-50 dark:bg-[#0A84FF] dark:hover:bg-[#2E96FF] sm:w-auto"
            disabled={!file || busy}
            onClick={() => void start()}
          >
            {busy ? 'Uploading…' : 'Start bulk enrichment'}
          </button>
        </div>

        {signingSecret && (
          <details className="rounded-2xl bg-[#F5F5F7] px-4 py-3 text-xs text-[#6E6E73] dark:bg-[#2C2C2E] dark:text-[#8E8E93]">
            <summary className="cursor-pointer font-medium text-[#1D1D1F] dark:text-[#F5F5F7]">
              Webhook signing secret
            </summary>
            <p className="mt-2 break-all font-mono text-[#1D1D1F] dark:text-[#F5F5F7]">{signingSecret}</p>
            <p className="mt-1">
              Verify header <code>X-StarkEven-Signature</code> = sha256 HMAC of <code>{'{timestamp}.{raw body}'}</code> using this secret.
            </p>
          </details>
        )}
      </div>

      {error && (
        <p className="rounded-2xl border border-[#FF3B30]/25 bg-[#FF3B30]/10 px-4 py-3 text-sm text-[#D70015] dark:text-[#FF453A]">
          {error}
        </p>
      )}

      {status && (
        <div className="space-y-4 rounded-2xl border border-black/[0.06] bg-white p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="inline-flex items-center gap-2 rounded-full bg-[#F5F5F7] px-3 py-1 text-xs font-medium capitalize text-[#1D1D1F] dark:bg-[#2C2C2E] dark:text-[#F5F5F7]">
              {status.status}
            </span>
            <span className="tabular-nums text-[#6E6E73] dark:text-[#8E8E93]">
              {status.processed_domains} / {status.total_domains} domains · {status.credits_used} credits
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-[#F5F5F7] dark:bg-[#2C2C2E]">
            <div
              className="h-full rounded-full bg-[#0071E3] transition-all dark:bg-[#0A84FF]"
              style={{ width: `${pct}%` }}
            />
          </div>
          {status.status === 'failed' && (
            <p className="text-sm text-[#D70015] dark:text-[#FF453A]">
              Job failed: {status.error ?? 'unknown error'}
            </p>
          )}
          {status.status === 'completed' && (
            <button
              type="button"
              className="inline-flex w-full items-center justify-center rounded-full bg-[#0071E3] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#0077ED] dark:bg-[#0A84FF] dark:hover:bg-[#2E96FF] sm:w-auto"
              onClick={() => void download()}
            >
              Download Enriched CSV
            </button>
          )}
        </div>
      )}
    </div>
  );
}
