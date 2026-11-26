'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { errMsg, getDailyUsage, getUsage } from '@/lib/api';
import type { DailyUsageResponse, UsageRow } from '@/lib/api';
import { useTheme } from './ThemeContext';

type ChartPoint = {
  date: string;
  label: string;
  credits_used: number;
  requests: number;
};

function formatDayLabel(isoDate: string): string {
  const [y, m, d] = isoDate.split('-').map(Number);
  const dt = new Date(Date.UTC(y, (m || 1) - 1, d || 1));
  return dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

function UsageTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: ChartPoint }>;
}) {
  if (!active || !payload?.length || !payload[0]?.payload) return null;
  const pt = payload[0].payload;
  return (
    <div className="rounded-2xl border border-black/[0.08] bg-white px-3.5 py-2.5 text-xs shadow-lg dark:border-white/[0.1] dark:bg-[#2C2C2E] dark:text-[#F5F5F7]">
      <p className="font-semibold text-[#1D1D1F] dark:text-[#F5F5F7]">{pt.label} ({pt.date})</p>
      <p className="mt-1 tabular-nums text-[#0071E3] dark:text-[#0A84FF]">
        Credits used: <span className="font-semibold">{pt.credits_used.toLocaleString()}</span>
      </p>
      <p className="tabular-nums text-[#6E6E73] dark:text-[#8E8E93]">
        Requests: <span className="font-medium text-[#1D1D1F] dark:text-[#F5F5F7]">{pt.requests.toLocaleString()}</span>
      </p>
    </div>
  );
}

function csvCell(v: string | number): string {
  const s = String(v);
  const safe = /^[=+\-@\t\r]/.test(s) ? `'${s}` : s;
  return /[,"\r\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

export default function UsagePanel({ refreshKey }: { refreshKey: number }) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const [days, setDays] = useState<7 | 30 | 90>(30);
  const [rows, setRows] = useState<UsageRow[]>([]);
  const [daily, setDaily] = useState<DailyUsageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setError(null);
    Promise.all([getUsage(), getDailyUsage(days)])
      .then(([usageRows, dailySummary]) => {
        if (!active) return;
        setRows(usageRows);
        setDaily(dailySummary);
      })
      .catch((e: unknown) => {
        if (active) setError(errMsg(e));
      });
    return () => {
      active = false;
    };
  }, [refreshKey, days]);

  const chartData = useMemo<ChartPoint[]>(() => {
    if (!daily?.daily?.length) return [];
    return daily.daily.map((d) => ({
      ...d,
      label: formatDayLabel(d.date),
    }));
  }, [daily]);

  function handleDownloadCsv() {
    if (!daily?.daily?.length) return;
    const lines = [
      'date,credits_used,requests',
      ...daily.daily.map((d) => [csvCell(d.date), csvCell(d.credits_used), csvCell(d.requests)].join(',')),
    ];
    const blob = new Blob([lines.join('\n') + '\n'], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `starkeven-usage-${days}d.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  const gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';
  const tickColor = isDark ? '#8E8E93' : '#6E6E73';
  const barColor = isDark ? '#0A84FF' : '#0071E3';

  return (
    <div className="space-y-6">
      {error && (
        <p className="rounded-2xl border border-[#FF3B30]/25 bg-[#FF3B30]/10 px-4 py-3 text-sm text-[#D70015] dark:text-[#FF453A]">
          {error}
        </p>
      )}

      <div
        className="rounded-2xl border border-black/[0.06] bg-white p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none"
        data-testid="usage-chart-card"
      >
        <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-[-0.02em] text-[#1D1D1F] dark:text-[#F5F5F7]">
              Usage &amp; Telemetry
            </h1>
            <p className="mt-0.5 text-xs text-[#6E6E73] dark:text-[#8E8E93]">
              Daily credit consumption over the last {days} days (UTC)
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div
              role="group"
              aria-label="Usage timeframe"
              className="inline-flex items-center gap-1 rounded-full border border-black/[0.06] bg-[#F5F5F7] p-1 dark:border-white/[0.08] dark:bg-[#2C2C2E]"
            >
              {([7, 30, 90] as const).map((range) => {
                const active = days === range;
                return (
                  <button
                    key={range}
                    type="button"
                    data-testid={`usage-range-${range}d`}
                    onClick={() => setDays(range)}
                    className={`rounded-full px-3 py-1 text-xs font-medium tabular-nums transition ${
                      active
                        ? 'bg-white text-[#1D1D1F] shadow-sm dark:bg-[#1C1C1E] dark:text-[#F5F5F7]'
                        : 'text-[#6E6E73] hover:text-[#1D1D1F] dark:text-[#8E8E93] dark:hover:text-[#F5F5F7]'
                    }`}
                  >
                    {range}d
                  </button>
                );
              })}
            </div>

            <button
              type="button"
              onClick={handleDownloadCsv}
              disabled={!daily?.daily?.length}
              data-testid="usage-download-csv"
              className="inline-flex items-center whitespace-nowrap rounded-full border border-black/[0.1] bg-[#F5F5F7] px-3.5 py-1.5 text-xs font-medium text-[#1D1D1F] transition hover:bg-black/[0.06] disabled:opacity-50 dark:border-white/[0.1] dark:bg-[#2C2C2E] dark:text-[#F5F5F7] dark:hover:bg-white/[0.1]"
            >
              Download CSV
            </button>
          </div>
        </div>

        <div className="mb-4 flex flex-wrap items-center gap-5 text-xs text-[#6E6E73] dark:text-[#8E8E93]">
          <span>
            <strong className="font-semibold tabular-nums text-[#1D1D1F] dark:text-[#F5F5F7]">
              {(daily?.total_credits ?? 0).toLocaleString()}
            </strong>{' '}
            credits used
          </span>
          <span>
            <strong className="font-semibold tabular-nums text-[#1D1D1F] dark:text-[#F5F5F7]">
              {(daily?.total_requests ?? 0).toLocaleString()}
            </strong>{' '}
            requests
          </span>
        </div>

        <div className="h-60 w-full min-w-0" data-testid="usage-chart">
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 6, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridColor} />
                <XAxis
                  dataKey="label"
                  tick={{ fill: tickColor, fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: gridColor }}
                  minTickGap={24}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fill: tickColor, fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  cursor={{ fill: isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 113, 227, 0.08)' }}
                  content={<UsageTooltip />}
                />
                <Bar
                  dataKey="credits_used"
                  name="Credits used"
                  fill={barColor}
                  radius={[5, 5, 0, 0]}
                  maxBarSize={24}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-[#6E6E73] dark:text-[#8E8E93]">
              Loading usage chart…
            </div>
          )}
        </div>
      </div>

      {/* Mobile stacked cards (< 768px) */}
      <div className="space-y-3 md:hidden" data-testid="usage-mobile-list">
        {rows.length === 0 && (
          <div className="rounded-2xl border border-black/[0.06] bg-white py-8 text-center text-sm text-[#6E6E73] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:text-[#8E8E93]">
            No requests yet.
          </div>
        )}
        {rows.map((r) => (
          <div
            key={r.id}
            className="space-y-2 rounded-2xl border border-black/[0.06] bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none"
          >
            <div className="flex items-start justify-between gap-2">
              <code className="min-w-0 flex-1 break-all font-mono text-xs font-medium text-[#1D1D1F] dark:text-[#F5F5F7]">
                {r.endpoint}
              </code>
              <span
                className={`shrink-0 rounded-full px-3 py-0.5 text-xs font-medium tabular-nums ${
                  r.status_code >= 400
                    ? 'bg-[#FF3B30]/15 text-[#D70015] dark:text-[#FF453A]'
                    : 'bg-[#34C759]/15 text-[#248A3D] dark:text-[#30D158]'
                }`}
              >
                {r.status_code}
              </span>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-[#6E6E73] dark:text-[#8E8E93]">
              <span className="tabular-nums">
                Credits: <strong className="text-[#1D1D1F] dark:text-[#F5F5F7]">{r.credits_used}</strong> ·{' '}
                <strong className="text-[#1D1D1F] dark:text-[#F5F5F7]">{r.latency_ms} ms</strong>
              </span>
              <span className="tabular-nums">{new Date(r.created_at).toLocaleString()}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Desktop table (>= 768px) */}
      <div className="hidden overflow-x-auto rounded-2xl border border-black/[0.06] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-black/[0.06] text-xs font-medium text-[#6E6E73] dark:border-white/[0.08] dark:text-[#8E8E93]">
            <tr>
              <th className="px-5 py-3">Time</th>
              <th className="px-5 py-3">Request</th>
              <th className="px-5 py-3">Status</th>
              <th className="px-5 py-3">Credits</th>
              <th className="px-5 py-3">Latency</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-8 text-center text-[#6E6E73] dark:text-[#8E8E93]">
                  No requests yet.
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-black/[0.04] last:border-0 dark:border-white/[0.06]">
                <td className="px-5 py-3 text-xs tabular-nums text-[#6E6E73] dark:text-[#8E8E93]">
                  {new Date(r.created_at).toLocaleString()}
                </td>
                <td className="px-5 py-3 font-mono text-xs text-[#1D1D1F] dark:text-[#F5F5F7]">{r.endpoint}</td>
                <td className="px-5 py-3">
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium tabular-nums ${
                      r.status_code >= 400
                        ? 'bg-[#FF3B30]/15 text-[#D70015] dark:text-[#FF453A]'
                        : 'bg-[#34C759]/15 text-[#248A3D] dark:text-[#30D158]'
                    }`}
                  >
                    {r.status_code}
                  </span>
                </td>
                <td className="px-5 py-3 tabular-nums text-[#1D1D1F] dark:text-[#F5F5F7]">{r.credits_used}</td>
                <td className="px-5 py-3 tabular-nums text-[#6E6E73] dark:text-[#8E8E93]">{r.latency_ms} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
