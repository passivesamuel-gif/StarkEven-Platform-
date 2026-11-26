'use client';

import { useEffect, useState } from 'react';
import {
  errMsg,
  getNotificationSettings,
  updateNotificationSettings,
} from '@/lib/api';

type SettingKey = 'notify_low_credits' | 'notify_campaign_reports';

type EmailNotificationSettingsProps = {
  recipientEmail?: string | null;
  initialLowCredits?: boolean;
  initialCampaignReports?: boolean;
  onUpdated?: () => Promise<void> | void;
};

type ToggleOption = {
  key: SettingKey;
  title: string;
  description: string;
  testId: string;
};

const OPTIONS: ToggleOption[] = [
  {
    key: 'notify_low_credits',
    title: 'Low credit warnings',
    description:
      'Send an email alert when remaining organization credits drop below 10% of your plan quota.',
    testId: 'toggle-low-credit-warnings',
  },
  {
    key: 'notify_campaign_reports',
    title: 'Campaign completion reports',
    description:
      'Send a summary email with newly delivered leads and remaining credits after each Lead Autopilot run.',
    testId: 'toggle-campaign-reports',
  },
];

export default function EmailNotificationSettings({
  recipientEmail,
  initialLowCredits = true,
  initialCampaignReports = true,
  onUpdated,
}: EmailNotificationSettingsProps) {
  const [lowCredits, setLowCredits] = useState<boolean>(initialLowCredits);
  const [campaignReports, setCampaignReports] = useState<boolean>(initialCampaignReports);
  const [resolvedEmail, setResolvedEmail] = useState<string | null>(recipientEmail ?? null);
  const [loading, setLoading] = useState<boolean>(true);
  const [savingKey, setSavingKey] = useState<SettingKey | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLowCredits(initialLowCredits);
  }, [initialLowCredits]);

  useEffect(() => {
    setCampaignReports(initialCampaignReports);
  }, [initialCampaignReports]);

  useEffect(() => {
    let active = true;
    getNotificationSettings()
      .then((res) => {
        if (!active) return;
        setLowCredits(res.notify_low_credits);
        setCampaignReports(res.notify_campaign_reports);
        if (res.recipient_email) setResolvedEmail(res.recipient_email);
      })
      .catch((err: unknown) => {
        if (active) setError(errMsg(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function handleToggle(key: SettingKey) {
    if (loading || savingKey !== null) return;
    const prevLow = lowCredits;
    const prevCampaign = campaignReports;
    const nextValue = key === 'notify_low_credits' ? !prevLow : !prevCampaign;

    setError(null);
    setStatusMessage(null);
    setSavingKey(key);
    if (key === 'notify_low_credits') setLowCredits(nextValue);
    else setCampaignReports(nextValue);

    try {
      const updated = await updateNotificationSettings(
        key === 'notify_low_credits'
          ? { notify_low_credits: nextValue }
          : { notify_campaign_reports: nextValue },
      );
      setLowCredits(updated.notify_low_credits);
      setCampaignReports(updated.notify_campaign_reports);
      if (updated.recipient_email) setResolvedEmail(updated.recipient_email);
      setStatusMessage('Preferences saved');
      if (onUpdated) await onUpdated();
    } catch (err) {
      setLowCredits(prevLow);
      setCampaignReports(prevCampaign);
      setError(errMsg(err));
    } finally {
      setSavingKey(null);
    }
  }

  return (
    <section
      aria-labelledby="email-notifications-heading"
      data-testid="email-notification-settings"
      className="rounded-2xl border border-black/[0.06] bg-white p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none"
    >
      <div className="flex flex-col gap-2 border-b border-black/[0.06] pb-5 dark:border-white/[0.08] sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2
            id="email-notifications-heading"
            className="text-base font-semibold tracking-[-0.02em] text-[#1D1D1F] dark:text-[#F5F5F7]"
          >
            Email Notifications
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-[#6E6E73] dark:text-[#8E8E93]">
            {resolvedEmail
              ? `Alerts are delivered to ${resolvedEmail}.`
              : 'Choose which automated operational alerts your workspace receives.'}
          </p>
        </div>

        <div className="min-h-[20px] shrink-0 text-xs font-medium" aria-live="polite">
          {savingKey !== null ? (
            <span className="text-[#6E6E73] dark:text-[#8E8E93]">Saving…</span>
          ) : statusMessage ? (
            <span data-testid="notification-saved-status" className="text-[#248A3D] dark:text-[#30D158]">
              {statusMessage}
            </span>
          ) : null}
        </div>
      </div>

      {error && (
        <p
          role="alert"
          className="mt-4 rounded-xl border border-[#FF3B30]/25 bg-[#FF3B30]/10 px-3.5 py-2.5 text-xs text-[#D70015] dark:text-[#FF453A]"
        >
          {error}
        </p>
      )}

      <div className="divide-y divide-black/[0.06] dark:divide-white/[0.08]">
        {OPTIONS.map((opt) => {
          const checked = opt.key === 'notify_low_credits' ? lowCredits : campaignReports;
          const isBusy = savingKey === opt.key;
          return (
            <div
              key={opt.key}
              className="flex flex-col gap-3 py-5 first:pt-5 last:pb-1 sm:flex-row sm:items-center sm:justify-between sm:gap-6"
            >
              <div className="min-w-0 flex-1 space-y-1">
                <label
                  htmlFor={opt.key}
                  className="block cursor-pointer text-sm font-medium text-[#1D1D1F] dark:text-[#F5F5F7]"
                >
                  {opt.title}
                </label>
                <p className="text-xs leading-relaxed text-[#6E6E73] dark:text-[#8E8E93]">
                  {opt.description}
                </p>
              </div>

              <div className="flex shrink-0 items-center justify-between gap-3 sm:justify-end">
                <span
                  className={`text-xs font-medium whitespace-nowrap ${
                    checked
                      ? 'text-[#1D1D1F] dark:text-[#F5F5F7]'
                      : 'text-[#6E6E73] dark:text-[#8E8E93]'
                  }`}
                >
                  {loading ? 'Loading…' : checked ? 'Enabled' : 'Paused'}
                </span>

                <button
                  id={opt.key}
                  type="button"
                  role="switch"
                  aria-checked={checked}
                  aria-label={opt.title}
                  data-testid={opt.testId}
                  disabled={loading || isBusy || savingKey !== null}
                  onClick={() => void handleToggle(opt.key)}
                  className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer items-center rounded-full border border-transparent transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0071E3] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 dark:focus-visible:ring-[#0A84FF] dark:focus-visible:ring-offset-[#1C1C1E] ${
                    checked
                      ? 'bg-[#0071E3] dark:bg-[#0A84FF]'
                      : 'bg-black/[0.14] dark:bg-[#3A3A3C]'
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm transition-transform duration-200 ${
                      checked ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
