'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ApiError, clearToken, getMe, getToken } from '@/lib/api';
import type { Me } from '@/lib/api';
import ThemeToggle from './ThemeToggle';

export default function LandingHeader() {
  const [me, setMe] = useState<Me | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setChecked(true);
      return;
    }
    let active = true;
    getMe()
      .then((user) => {
        if (active) setMe(user);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearToken();
        }
      })
      .finally(() => {
        if (active) setChecked(true);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <header className="glass fixed inset-x-0 top-0 z-50 border-b border-black/[0.08] dark:border-white/[0.08]">
      <div className="mx-auto flex h-14 max-w-[1120px] items-center justify-between gap-2 px-3.5 sm:gap-4 sm:px-6">
        <Link
          href="/"
          className="shrink-0 whitespace-nowrap text-[15px] font-semibold tracking-tight text-[#1D1D1F] dark:text-[#F5F5F7]"
        >
          StarkEven
        </Link>

        <nav className="hidden items-center gap-7 text-[13px] font-medium text-[#1D1D1F]/70 dark:text-[#F5F5F7]/70 md:flex">
          <a href="#features" className="shrink-0 whitespace-nowrap transition-colors hover:text-[#1D1D1F] dark:hover:text-[#F5F5F7]">
            Features
          </a>
          <a href="#api" className="shrink-0 whitespace-nowrap transition-colors hover:text-[#1D1D1F] dark:hover:text-[#F5F5F7]">
            API
          </a>
          <a href="#pricing" className="shrink-0 whitespace-nowrap transition-colors hover:text-[#1D1D1F] dark:hover:text-[#F5F5F7]">
            Pricing
          </a>
          <a href="/docs" className="shrink-0 whitespace-nowrap transition-colors hover:text-[#1D1D1F] dark:hover:text-[#F5F5F7]">
            Docs
          </a>
        </nav>

        <div className="flex shrink-0 items-center gap-1.5 sm:gap-3">
          <ThemeToggle />
          {checked && me ? (
            <>
              <Link
                href="/dashboard"
                data-testid="header-credit-pill"
                className="shrink-0 whitespace-nowrap rounded-full border border-black/[0.08] bg-white px-2.5 py-1 text-[11px] font-medium tabular-nums text-[#1D1D1F] transition hover:bg-black/[0.03] dark:border-white/[0.1] dark:bg-[#141416] dark:text-[#F5F5F7] dark:hover:bg-white/[0.06] sm:px-3 sm:text-xs"
              >
                {me.credit_balance.toLocaleString()} credits
              </Link>
              <Link
                href="/dashboard"
                className="shrink-0 whitespace-nowrap rounded-full bg-[#1D1D1F] px-2.5 py-1.5 text-[11px] font-medium text-white transition hover:bg-black dark:bg-[#F5F5F7] dark:text-[#0B0B0C] dark:hover:bg-white sm:px-3.5 sm:text-[13px]"
              >
                Go to Dashboard →
              </Link>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="shrink-0 whitespace-nowrap px-2 py-1.5 text-[13px] font-medium text-[#1D1D1F]/75 transition hover:text-[#1D1D1F] dark:text-[#F5F5F7]/75 dark:hover:text-[#F5F5F7]"
              >
                Sign in
              </Link>
              <Link
                href="/login"
                className="shrink-0 whitespace-nowrap rounded-full bg-[#1D1D1F] px-3.5 py-1.5 text-[13px] font-medium text-white transition hover:bg-black dark:bg-[#F5F5F7] dark:text-[#0B0B0C] dark:hover:bg-white"
              >
                Start free
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
