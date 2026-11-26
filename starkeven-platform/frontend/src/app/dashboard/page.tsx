'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { ApiError, clearToken, getMe, getToken } from '@/lib/api';
import type { Me } from '@/lib/api';
import AutopilotPanel from '@/components/AutopilotPanel';
import BillingPanel from '@/components/BillingPanel';
import BulkPanel from '@/components/BulkPanel';
import EmailNotificationSettings from '@/components/EmailNotificationSettings';
import EnrichPanel from '@/components/EnrichPanel';
import KeysPanel from '@/components/KeysPanel';
import UsagePanel from '@/components/UsagePanel';
import VerifyPanel from '@/components/VerifyPanel';
import ThemeToggle from '@/components/ThemeToggle';

type Tab = 'Autopilot' | 'Enrich' | 'Bulk CSV' | 'Verify' | 'API Keys' | 'Usage' | 'Billing' | 'Settings';

const NAV_ITEMS: { id: Tab; label: string }[] = [
  { id: 'Autopilot', label: 'Autopilot' },
  { id: 'Enrich', label: 'Enrich' },
  { id: 'Bulk CSV', label: 'Bulk CSV' },
  { id: 'Verify', label: 'Verify' },
  { id: 'API Keys', label: 'API Keys' },
  { id: 'Usage', label: 'Usage' },
  { id: 'Billing', label: 'Billing' },
  { id: 'Settings', label: 'Settings' },
];

function TabIcon({ id }: { id: Tab }) {
  const cls = 'h-4 w-4 shrink-0';
  switch (id) {
    case 'Autopilot':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={cls} aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <polygon points="15.5 8.5 13.5 13.5 8.5 15.5 10.5 10.5 15.5 8.5" />
        </svg>
      );
    case 'Enrich':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={cls} aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
      );
    case 'Bulk CSV':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={cls} aria-hidden="true">
          <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" />
          <path d="M14 3v5h5" />
          <path d="M8 13h8M8 17h5" />
        </svg>
      );
    case 'Verify':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={cls} aria-hidden="true">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      );
    case 'API Keys':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={cls} aria-hidden="true">
          <circle cx="7.5" cy="15.5" r="4.5" />
          <path d="m21 2-9.6 9.6M15.5 7.5l3 3" />
        </svg>
      );
    case 'Usage':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={cls} aria-hidden="true">
          <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
        </svg>
      );
    case 'Billing':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={cls} aria-hidden="true">
          <rect x="2" y="5" width="20" height="14" rx="2" />
          <path d="M2 10h20" />
        </svg>
      );
    case 'Settings':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={cls} aria-hidden="true">
          <line x1="4" y1="21" x2="4" y2="14" />
          <line x1="4" y1="10" x2="4" y2="3" />
          <line x1="12" y1="21" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12" y2="3" />
          <line x1="20" y1="21" x2="20" y2="16" />
          <line x1="20" y1="12" x2="20" y2="3" />
          <line x1="1" y1="14" x2="7" y2="14" />
          <line x1="9" y1="8" x2="15" y2="8" />
          <line x1="17" y1="16" x2="23" y2="16" />
        </svg>
      );
  }
}

export default function Dashboard() {
  const [me, setMe] = useState<Me | null>(null);
  const [tab, setTab] = useState<Tab>('Autopilot');
  const [tick, setTick] = useState(0);

  const refresh = useCallback(async () => {
    try {
      setMe(await getMe());
      setTick((t) => t + 1);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        clearToken();
        window.location.href = '/login';
      }
    }
  }, []);

  useEffect(() => {
    if (!getToken()) {
      window.location.href = '/login';
      return;
    }
    void refresh();
  }, [refresh]);

  function logout() {
    clearToken();
    window.location.href = '/';
  }

  function getInitials(companyName: string): string {
    const words = companyName.trim().split(/\s+/).filter(Boolean);
    if (words.length === 0) return 'ST';
    if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
    return `${words[0][0]}${words[1][0]}`.toUpperCase();
  }

  function getPlanBaselineCredits(planTier: string): number {
    const tier = planTier.toLowerCase();
    if (tier === 'pro' || tier === 'growth') return 4000;
    if (tier === 'enterprise' || tier === 'agency') return 15000;
    return 50;
  }

  if (!me) {
    return (
      <div className="min-h-screen bg-[#F5F5F7] p-12 text-center text-sm text-[#6E6E73] dark:bg-[#000000] dark:text-[#8E8E93]">
        Loading workspace…
      </div>
    );
  }

  const planBaseline = getPlanBaselineCredits(me.plan_tier);
  const lowCreditThreshold = Math.ceil(planBaseline * 0.1);
  const isLowCredit = me.credit_balance < lowCreditThreshold;
  const monogram = getInitials(me.name);

  return (
    <div className="min-h-screen bg-[#F5F5F7] text-[#1D1D1F] transition-colors dark:bg-[#000000] dark:text-[#F5F5F7]">
      {/* Minimalist Frosted-Glass Top Bar */}
      <header className="sticky top-0 z-40 h-14 border-b border-black/[0.08] bg-[#F5F5F7]/80 backdrop-blur-xl dark:border-white/[0.08] dark:bg-[#000000]/80">
        <div className="mx-auto flex h-full max-w-5xl items-center justify-between gap-3 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <Link
              href="/"
              className="shrink-0 whitespace-nowrap text-[17px] font-semibold tracking-[-0.02em] text-[#1D1D1F] dark:text-[#F5F5F7]"
            >
              StarkEven
            </Link>
            <div className="hidden min-w-0 items-center gap-2 border-l border-black/[0.08] pl-3 dark:border-white/[0.08] sm:flex">
              <span
                aria-hidden="true"
                data-testid="header-org-monogram"
                className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#1D1D1F] text-[10px] font-semibold tracking-tight text-white dark:bg-[#F5F5F7] dark:text-[#000000]"
              >
                {monogram}
              </span>
              <span
                data-testid="header-org-name"
                className="max-w-[180px] truncate text-xs font-medium text-[#1D1D1F] dark:text-[#F5F5F7]"
              >
                {me.name}
              </span>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => setTab('Billing')}
              title="Manage plan and credits"
              data-testid="dashboard-credit-pill"
              className="inline-flex h-8 items-center rounded-full border border-black/[0.08] bg-white px-3 text-xs font-semibold tabular-nums text-[#1D1D1F] transition hover:bg-black/[0.03] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:text-[#F5F5F7] dark:hover:bg-[#2C2C2E]"
            >
              {me.credit_balance.toLocaleString()} credits
            </button>
            <ThemeToggle />
            <button
              type="button"
              onClick={logout}
              aria-label="Sign out"
              className="inline-flex h-8 items-center gap-1.5 rounded-full border border-black/[0.08] bg-white px-2.5 text-xs font-medium text-[#1D1D1F] transition hover:bg-black/[0.03] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:text-[#F5F5F7] dark:hover:bg-[#2C2C2E] sm:px-3"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5" aria-hidden="true">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 pb-16 pt-6 sm:px-6 sm:pt-8">
        {isLowCredit && (
          <div
            role="status"
            data-testid="low-credit-banner"
            className="mb-5 flex flex-col gap-3 rounded-2xl border border-[#FF9F0A]/30 bg-[#FF9F0A]/10 px-4 py-3 text-xs text-[#9A4700] dark:border-[#FFD60A]/25 dark:bg-[#FFD60A]/10 dark:text-[#FFD60A] sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="flex items-center gap-2.5">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 shrink-0" aria-hidden="true">
                <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <span>
                <strong className="font-semibold">Low credit balance:</strong>{' '}
                <span className="tabular-nums font-semibold">{me.credit_balance.toLocaleString()}</span> credits remaining (below 10% of your plan quota). Top up to keep Autopilot and API calls running.
              </span>
            </div>
            <button
              type="button"
              onClick={() => setTab('Billing')}
              className="inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-full bg-[#1D1D1F] px-3.5 py-1.5 text-xs font-medium text-white transition hover:bg-black dark:bg-[#F5F5F7] dark:text-[#000000] dark:hover:bg-white"
            >
              Upgrade Plan
            </button>
          </div>
        )}

        {/* Segmented Control Navigation */}
        <nav aria-label="Workspace sections" className="mb-7">
          {/* Mobile 2/4-column segmented grid (< 768px) */}
          <div className="grid grid-cols-2 gap-1.5 rounded-2xl border border-black/[0.06] bg-black/[0.05] p-1.5 dark:border-white/[0.08] dark:bg-[#1C1C1E] sm:grid-cols-4 md:hidden">
            {NAV_ITEMS.map((item) => {
              const active = tab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  data-testid={`nav-mobile-${item.id}`}
                  onClick={() => setTab(item.id)}
                  className={`flex items-center justify-center gap-1.5 rounded-xl px-2 py-2.5 text-xs font-medium transition ${
                    active
                      ? 'bg-white text-[#1D1D1F] shadow-sm dark:bg-[#2C2C2E] dark:text-[#F5F5F7]'
                      : 'text-[#6E6E73] hover:text-[#1D1D1F] dark:text-[#8E8E93] dark:hover:text-[#F5F5F7]'
                  }`}
                >
                  <TabIcon id={item.id} />
                  <span className="whitespace-nowrap">{item.label}</span>
                </button>
              );
            })}
          </div>

          {/* Desktop centered Apple Segmented Control pill bar (>= 768px) */}
          <div className="hidden justify-center md:flex">
            <div className="inline-flex items-center gap-1 rounded-full border border-black/[0.06] bg-black/[0.05] p-1 dark:border-white/[0.08] dark:bg-[#1C1C1E]">
              {NAV_ITEMS.map((item) => {
                const active = tab === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setTab(item.id)}
                    className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-1.5 text-[13px] font-medium transition ${
                      active
                        ? 'bg-white text-[#1D1D1F] shadow-sm dark:bg-[#2C2C2E] dark:text-[#F5F5F7]'
                        : 'text-[#6E6E73] hover:text-[#1D1D1F] dark:text-[#8E8E93] dark:hover:text-[#F5F5F7]'
                    }`}
                  >
                    <TabIcon id={item.id} />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </nav>

        <div className="space-y-6">
          {tab === 'Autopilot' && <AutopilotPanel onSpend={refresh} />}
          {tab === 'Enrich' && <EnrichPanel onSpend={() => void refresh()} />}
          {tab === 'Bulk CSV' && <BulkPanel onSpend={() => void refresh()} signingSecret={me.callback_signing_secret} />}
          {tab === 'Verify' && <VerifyPanel onSpend={() => void refresh()} />}
          {tab === 'API Keys' && <KeysPanel />}
          {tab === 'Usage' && <UsagePanel refreshKey={tick} />}
          {tab === 'Billing' && <BillingPanel me={me} />}
          {tab === 'Settings' && (
            <div className="space-y-6" data-testid="account-settings-section">
              <div className="rounded-2xl border border-black/[0.06] bg-white p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none">
                <h1 className="text-xl font-semibold tracking-[-0.02em] text-[#1D1D1F] dark:text-[#F5F5F7]">
                  Account Settings
                </h1>
                <p className="mt-1 text-xs text-[#6E6E73] dark:text-[#8E8E93]">
                  Manage your workspace profile and automated email alert preferences.
                </p>

                <dl className="mt-5 divide-y divide-black/[0.06] border-t border-black/[0.06] text-xs dark:divide-white/[0.08] dark:border-white/[0.08]">
                  <div className="flex flex-wrap items-center justify-between gap-2 py-3.5">
                    <dt className="text-[#6E6E73] dark:text-[#8E8E93]">Organization</dt>
                    <dd className="font-medium text-[#1D1D1F] dark:text-[#F5F5F7]">{me.name}</dd>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2 py-3.5">
                    <dt className="text-[#6E6E73] dark:text-[#8E8E93]">Account Email</dt>
                    <dd className="font-medium text-[#1D1D1F] dark:text-[#F5F5F7]">{me.email ?? '—'}</dd>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2 py-3.5">
                    <dt className="text-[#6E6E73] dark:text-[#8E8E93]">Plan &amp; Rate Quota</dt>
                    <dd className="font-medium tabular-nums text-[#1D1D1F] dark:text-[#F5F5F7]">
                      {me.plan_tier} · {me.rate_limit_per_min.toLocaleString()} req/min
                    </dd>
                  </div>
                </dl>
              </div>

              <EmailNotificationSettings
                recipientEmail={me.email}
                initialLowCredits={me.notify_low_credits ?? true}
                initialCampaignReports={me.notify_campaign_reports ?? true}
                onUpdated={refresh}
              />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
