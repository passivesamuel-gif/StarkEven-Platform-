'use client';

import { useCallback, useEffect, useState } from 'react';
import { createKey, errMsg, listKeys, revokeKey, rotateKey } from '@/lib/api';
import type { ApiKeyRow, NewKey } from '@/lib/api';

export default function KeysPanel() {
  const [keys, setKeys] = useState<ApiKeyRow[]>([]);
  const [name, setName] = useState('');
  const [env, setEnv] = useState<'live' | 'test'>('live');
  const [days, setDays] = useState('');
  const [fresh, setFresh] = useState<NewKey | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      setKeys(await listKeys());
    } catch (e) {
      setError(errMsg(e));
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<NewKey | { revoked: boolean }>) {
    setError(null);
    try {
      const res = await fn();
      if ('api_key' in res) { setFresh(res); setCopied(false); }
      await load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setError('Copy failed; select the key and copy it manually.');
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-4 rounded-2xl border border-black/[0.06] bg-white p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none">
        <div>
          <h1 className="text-xl font-semibold tracking-[-0.02em] text-[#1D1D1F] dark:text-[#F5F5F7]">
            API Keys
          </h1>
          <p className="mt-1 text-sm text-[#6E6E73] dark:text-[#8E8E93]">
            Issue scoped live keys or free sandbox keys for testing. Keys are hashed immediately and shown once.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 rounded-2xl bg-[#F5F5F7] p-4 dark:bg-[#2C2C2E] sm:grid-cols-2 md:flex md:flex-wrap md:items-end">
          <div className="min-w-0 md:min-w-[10rem] md:flex-1">
            <label className="mb-1.5 block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
              Key name
            </label>
            <input
              className="w-full rounded-xl border border-black/[0.08] bg-white px-3.5 py-2 text-sm text-[#1D1D1F] placeholder-[#6E6E73]/60 focus:border-[#0071E3] focus:outline-none dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:text-[#F5F5F7] dark:placeholder-[#8E8E93] dark:focus:border-[#0A84FF]"
              placeholder="e.g. production"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="min-w-0">
            <label className="mb-1.5 block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
              Type
            </label>
            <select
              className="w-full rounded-xl border border-black/[0.08] bg-white px-3.5 py-2 text-sm text-[#1D1D1F] focus:border-[#0071E3] focus:outline-none dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:text-[#F5F5F7] dark:focus:border-[#0A84FF]"
              value={env}
              onChange={(e) => setEnv(e.target.value === 'test' ? 'test' : 'live')}
            >
              <option value="live">Live</option>
              <option value="test">Sandbox (free, sample data)</option>
            </select>
          </div>
          <div className="min-w-0 md:w-28">
            <label className="mb-1.5 block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
              Expires (days)
            </label>
            <input
              className="w-full rounded-xl border border-black/[0.08] bg-white px-3.5 py-2 text-sm tabular-nums text-[#1D1D1F] placeholder-[#6E6E73]/60 focus:border-[#0071E3] focus:outline-none dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:text-[#F5F5F7] dark:placeholder-[#8E8E93] dark:focus:border-[#0A84FF]"
              inputMode="numeric"
              placeholder="never"
              value={days}
              onChange={(e) => setDays(e.target.value.replace(/\D/g, ''))}
            />
          </div>
          <button
            type="button"
            className="inline-flex w-full items-center justify-center whitespace-nowrap rounded-full bg-[#0071E3] px-5 py-2 text-sm font-medium text-white transition hover:bg-[#0077ED] dark:bg-[#0A84FF] dark:hover:bg-[#2E96FF] sm:col-span-2 md:w-auto"
            onClick={() => void act(() => createKey(name.trim() || 'default', env, days ? Number(days) : undefined))}
          >
            Create key
          </button>
        </div>
      </div>

      {fresh && (
        <div className="rounded-2xl border border-[#FF9F0A]/30 bg-[#FF9F0A]/10 p-5">
          <p className="text-sm font-semibold text-[#994700] dark:text-[#FFD60A]">
            Copy your new key now. It will not be shown again.
          </p>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
            <code className="flex-1 break-all rounded-xl bg-white px-3.5 py-2.5 font-mono text-sm text-[#1D1D1F] dark:bg-[#1C1C1E] dark:text-[#F5F5F7]">
              {fresh.api_key}
            </code>
            <div className="flex gap-2">
              <button
                type="button"
                className="flex-1 rounded-full border border-black/[0.1] bg-white px-4 py-2 text-xs font-medium text-[#1D1D1F] dark:border-white/[0.1] dark:bg-[#1C1C1E] dark:text-[#F5F5F7] sm:flex-none"
                onClick={() => void copy(fresh.api_key)}
              >
                {copied ? 'Copied' : 'Copy'}
              </button>
              <button
                type="button"
                className="flex-1 rounded-full bg-[#1D1D1F] px-4 py-2 text-xs font-medium text-white dark:bg-[#F5F5F7] dark:text-[#000000] sm:flex-none"
                onClick={() => setFresh(null)}
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {error && (
        <p className="rounded-2xl border border-[#FF3B30]/25 bg-[#FF3B30]/10 px-4 py-3 text-sm text-[#D70015] dark:text-[#FF453A]">
          {error}
        </p>
      )}

      {/* Mobile stacked cards (< 768px) */}
      <div className="space-y-3 md:hidden" data-testid="keys-mobile-list">
        {keys.length === 0 && (
          <div className="rounded-2xl border border-black/[0.06] bg-white py-8 text-center text-sm text-[#6E6E73] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:text-[#8E8E93]">
            No API keys yet.
          </div>
        )}
        {keys.map((k) => {
          const expiresLabel = k.expires_at ? new Date(k.expires_at).toLocaleDateString() : 'Never';
          return (
            <div
              key={k.id}
              className="space-y-3 rounded-2xl border border-black/[0.06] bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-[#1D1D1F] dark:text-[#F5F5F7]">{k.name}</p>
                  <p className="mt-0.5 break-all font-mono text-xs text-[#6E6E73] dark:text-[#8E8E93]">{k.key_prefix}</p>
                </div>
                {k.is_active ? (
                  <span className="shrink-0 rounded-full bg-[#34C759]/15 px-3 py-1 text-xs font-medium text-[#248A3D] dark:text-[#30D158]">
                    Active
                  </span>
                ) : (
                  <span className="shrink-0 rounded-full bg-[#F5F5F7] px-3 py-1 text-xs font-medium text-[#6E6E73] dark:bg-[#2C2C2E] dark:text-[#8E8E93]">
                    Revoked
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 rounded-2xl bg-[#F5F5F7] p-3 text-xs dark:bg-[#2C2C2E]">
                <div>
                  <span className="block text-[11px] text-[#6E6E73] dark:text-[#8E8E93]">Expires</span>
                  <span className="font-medium tabular-nums text-[#1D1D1F] dark:text-[#F5F5F7]">{expiresLabel}</span>
                </div>
                <div>
                  <span className="block text-[11px] text-[#6E6E73] dark:text-[#8E8E93]">Last used</span>
                  <span className="font-medium tabular-nums text-[#1D1D1F] dark:text-[#F5F5F7]">
                    {k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : 'Never'}
                  </span>
                </div>
              </div>
              {k.is_active && (
                <div className="flex flex-col gap-2 pt-1">
                  <button
                    type="button"
                    className="w-full rounded-full border border-black/[0.1] bg-[#F5F5F7] px-4 py-2 text-xs font-medium text-[#1D1D1F] dark:border-white/[0.1] dark:bg-[#2C2C2E] dark:text-[#F5F5F7]"
                    onClick={() => void act(() => rotateKey(k.id))}
                  >
                    Rotate
                  </button>
                  <button
                    type="button"
                    className="w-full rounded-full border border-black/[0.1] bg-white px-4 py-2 text-xs font-medium text-[#D70015] dark:border-white/[0.1] dark:bg-[#1C1C1E] dark:text-[#FF453A]"
                    onClick={() => { if (window.confirm('Revoke this key? Apps using it stop working immediately.')) void act(() => revokeKey(k.id)); }}
                  >
                    Revoke
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Desktop table (>= 768px) */}
      <div className="hidden overflow-x-auto rounded-2xl border border-black/[0.06] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-black/[0.06] text-xs font-medium text-[#6E6E73] dark:border-white/[0.08] dark:text-[#8E8E93]">
            <tr>
              <th className="px-5 py-3">Name</th>
              <th className="px-5 py-3">Key</th>
              <th className="px-5 py-3">Status</th>
              <th className="px-5 py-3">Expires</th>
              <th className="px-5 py-3">Last used</th>
              <th className="px-5 py-3" />
            </tr>
          </thead>
          <tbody>
            {keys.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-[#6E6E73] dark:text-[#8E8E93]">
                  No API keys yet.
                </td>
              </tr>
            )}
            {keys.map((k) => (
              <tr key={k.id} className="border-b border-black/[0.04] last:border-0 dark:border-white/[0.06]">
                <td className="px-5 py-3.5 font-medium text-[#1D1D1F] dark:text-[#F5F5F7]">{k.name}</td>
                <td className="px-5 py-3.5 font-mono text-xs text-[#6E6E73] dark:text-[#8E8E93]">{k.key_prefix}</td>
                <td className="px-5 py-3.5">
                  {k.is_active ? (
                    <span className="rounded-full bg-[#34C759]/15 px-3 py-1 text-xs font-medium text-[#248A3D] dark:text-[#30D158]">
                      Active
                    </span>
                  ) : (
                    <span className="rounded-full bg-[#F5F5F7] px-3 py-1 text-xs font-medium text-[#6E6E73] dark:bg-[#2C2C2E] dark:text-[#8E8E93]">
                      Revoked
                    </span>
                  )}
                </td>
                <td className="px-5 py-3.5 text-xs tabular-nums text-[#6E6E73] dark:text-[#8E8E93]">
                  {k.expires_at ? new Date(k.expires_at).toLocaleDateString() : 'Never'}
                </td>
                <td className="px-5 py-3.5 text-xs tabular-nums text-[#6E6E73] dark:text-[#8E8E93]">
                  {k.last_used_at ? new Date(k.last_used_at).toLocaleString() : 'Never'}
                </td>
                <td className="space-x-2 px-5 py-3.5 text-right">
                  {k.is_active && (
                    <>
                      <button
                        type="button"
                        className="rounded-full border border-black/[0.1] bg-[#F5F5F7] px-3 py-1 text-xs font-medium text-[#1D1D1F] hover:bg-black/[0.06] dark:border-white/[0.1] dark:bg-[#2C2C2E] dark:text-[#F5F5F7]"
                        onClick={() => void act(() => rotateKey(k.id))}
                      >
                        Rotate
                      </button>
                      <button
                        type="button"
                        className="rounded-full border border-black/[0.1] bg-white px-3 py-1 text-xs font-medium text-[#D70015] hover:bg-[#FF3B30]/10 dark:border-white/[0.1] dark:bg-[#1C1C1E] dark:text-[#FF453A]"
                        onClick={() => { if (window.confirm('Revoke this key? Apps using it stop working immediately.')) void act(() => revokeKey(k.id)); }}
                      >
                        Revoke
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
