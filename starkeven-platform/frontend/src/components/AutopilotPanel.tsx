'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createAutopilotCampaign,
  deleteAutopilotCampaign,
  downloadAutopilotLeadsCsv,
  errMsg,
  listAutopilotCampaigns,
  listAutopilotLeads,
  runAutopilotCampaignNow,
  updateAutopilotCampaign,
} from '@/lib/api';
import type { AutopilotCampaign, CrmProvider, DeliveredLead } from '@/lib/api';

const PRESET_TECH = ['Stripe', 'HubSpot', 'Shopify', 'Salesforce', 'Intercom'] as const;

const CRM_LABELS: Record<CrmProvider, string> = {
  none: 'None',
  hubspot: 'HubSpot',
  salesforce: 'Salesforce',
  webhook: 'Custom Webhook',
};

function parseCsvItems(raw: string): string[] {
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

function mergeUnique(items: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    const trimmed = item.trim();
    if (!trimmed) continue;
    const key = trimmed.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      out.push(trimmed);
    }
  }
  return out;
}

export default function AutopilotPanel({ onSpend }: { onSpend: () => Promise<void> | void }) {
  const [campaigns, setCampaigns] = useState<AutopilotCampaign[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [leads, setLeads] = useState<DeliveredLead[]>([]);
  const [leadsTotal, setLeadsTotal] = useState(0);
  const [loadingCampaigns, setLoadingCampaigns] = useState(true);
  const [loadingLeads, setLoadingLeads] = useState(false);

  // Progressive disclosure controls
  const [showCreator, setShowCreator] = useState(true);
  const [showDelivery, setShowDelivery] = useState(false);

  // Form state
  const [name, setName] = useState('');
  const [keywords, setKeywords] = useState<string[]>([]);
  const [keywordInput, setKeywordInput] = useState('');
  const [selectedTech, setSelectedTech] = useState<string[]>([]);
  const [customTechInput, setCustomTechInput] = useState('');
  const [requireHiring, setRequireHiring] = useState(false);
  const [dailyQuota, setDailyQuota] = useState('25');
  const [crmProvider, setCrmProvider] = useState<CrmProvider>('none');
  const [crmTarget, setCrmTarget] = useState('');
  const [creating, setCreating] = useState(false);

  // Action feedback
  const [runningId, setRunningId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toasts, setToasts] = useState<{ id: number; kind: 'success' | 'info' | 'error'; text: string }[]>([]);
  const toastSeq = useRef(0);
  const toastTimers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const pushToast = useCallback((kind: 'success' | 'info' | 'error', text: string) => {
    const id = ++toastSeq.current;
    setToasts((prev) => [...prev.slice(-3), { id, kind, text }]);
    const t = setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== id));
    }, 4500);
    toastTimers.current.push(t);
  }, []);

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
      for (const t of toastTimers.current) clearTimeout(t);
    };
  }, []);

  const fetchLeads = useCallback(async (campaignId: string) => {
    setLoadingLeads(true);
    try {
      const page = await listAutopilotLeads(campaignId, 50, 0);
      setLeads(page.items);
      setLeadsTotal(page.total);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoadingLeads(false);
    }
  }, []);

  const loadCampaigns = useCallback(async (preferredId?: string | null) => {
    try {
      const list = await listAutopilotCampaigns();
      setCampaigns(list);
      setSelectedId((prev) => {
        const target = preferredId !== undefined ? preferredId : prev;
        if (target && list.some((c) => c.id === target)) return target;
        return list[0]?.id ?? null;
      });
      return list;
    } catch (e) {
      setError(errMsg(e));
      return [];
    } finally {
      setLoadingCampaigns(false);
    }
  }, []);

  useEffect(() => {
    void loadCampaigns();
  }, [loadCampaigns]);

  useEffect(() => {
    if (selectedId) {
      void fetchLeads(selectedId);
    } else {
      setLeads([]);
      setLeadsTotal(0);
    }
  }, [selectedId, fetchLeads]);

  function commitKeywordInput(raw: string) {
    const parsed = parseCsvItems(raw);
    if (parsed.length > 0) {
      setKeywords((prev) => mergeUnique([...prev, ...parsed]));
    }
    setKeywordInput('');
  }

  function handleKeywordKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      commitKeywordInput(keywordInput);
    } else if (e.key === 'Backspace' && !keywordInput && keywords.length > 0) {
      setKeywords((prev) => prev.slice(0, -1));
    }
  }

  function togglePresetTech(tech: string) {
    setSelectedTech((prev) =>
      prev.includes(tech) ? prev.filter((t) => t !== tech) : [...prev, tech],
    );
  }

  function stepQuota(delta: number) {
    const cur = Number.parseInt(dailyQuota, 10) || 25;
    const next = Math.min(500, Math.max(1, cur + delta));
    setDailyQuota(String(next));
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);

    const allKeywords = mergeUnique([...keywords, ...parseCsvItems(keywordInput)]);
    if (!name.trim()) {
      setError('Please enter a campaign name.');
      return;
    }
    if (allKeywords.length === 0) {
      setError('Please add at least one target keyword.');
      return;
    }

    const quotaNum = Math.min(500, Math.max(1, Number.parseInt(dailyQuota, 10) || 25));
    const allTech = mergeUnique([...selectedTech, ...parseCsvItems(customTechInput)]);

    setCreating(true);
    try {
      const created = await createAutopilotCampaign({
        name: name.trim(),
        target_keywords: allKeywords,
        required_tech_stack: allTech,
        require_hiring: requireHiring,
        daily_lead_quota: quotaNum,
        target_crm_provider: crmProvider,
        target_crm_url_or_token: crmProvider === 'none' ? null : crmTarget.trim() || null,
      });
      setName('');
      setKeywords([]);
      setKeywordInput('');
      setSelectedTech([]);
      setCustomTechInput('');
      setRequireHiring(false);
      setDailyQuota('25');
      setCrmProvider('none');
      setCrmTarget('');
      setShowDelivery(false);
      setNotice(`Campaign "${created.name}" created.`);
      pushToast('success', `Campaign "${created.name}" created.`);
      await loadCampaigns(created.id);
    } catch (err) {
      const msg = errMsg(err);
      setError(msg);
      pushToast('error', msg);
    } finally {
      setCreating(false);
    }
  }

  async function handleRunNow(campaign: AutopilotCampaign) {
    setError(null);
    setNotice(null);
    setRunningId(campaign.id);
    setSelectedId(campaign.id);
    const previousRunAt = campaign.last_run_at;
    const previousTotal = campaign.total_leads_delivered;
    try {
      await runAutopilotCampaignNow(campaign.id);
      const qMsg = `Run queued for "${campaign.name}". Discovering and verifying leads…`;
      setNotice(qMsg);
      pushToast('info', qMsg);

      let attempts = 0;
      const poll = async () => {
        attempts += 1;
        const updatedList = await loadCampaigns(campaign.id);
        await fetchLeads(campaign.id);
        await onSpend();
        const current = updatedList.find((c) => c.id === campaign.id);
        const finished =
          current &&
          (current.last_run_at !== previousRunAt ||
            current.total_leads_delivered !== previousTotal);
        if (finished || attempts >= 6) {
          setRunningId(null);
          if (current) {
            const added = current.total_leads_delivered - previousTotal;
            const doneMsg =
              added > 0
                ? `Run complete for "${current.name}": ${added} new lead${added === 1 ? '' : 's'} delivered.`
                : `Run complete for "${current.name}".`;
            setNotice(doneMsg);
            pushToast('success', doneMsg);
          }
          return;
        }
        pollTimer.current = setTimeout(() => void poll(), 900);
      };
      pollTimer.current = setTimeout(() => void poll(), 800);
    } catch (err) {
      const msg = errMsg(err);
      setError(msg);
      pushToast('error', msg);
      setRunningId(null);
    }
  }

  async function handleToggleStatus(campaign: AutopilotCampaign) {
    setError(null);
    setNotice(null);
    setBusyId(campaign.id);
    const nextStatus = campaign.status === 'active' ? 'paused' : 'active';
    try {
      await updateAutopilotCampaign(campaign.id, { status: nextStatus });
      await loadCampaigns(campaign.id);
      pushToast('info', `Campaign "${campaign.name}" ${nextStatus === 'active' ? 'resumed' : 'paused'}.`);
    } catch (err) {
      const msg = errMsg(err);
      setError(msg);
      pushToast('error', msg);
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(campaign: AutopilotCampaign) {
    setError(null);
    setNotice(null);
    setBusyId(campaign.id);
    try {
      await deleteAutopilotCampaign(campaign.id);
      setConfirmDeleteId(null);
      const msg = `Deleted campaign "${campaign.name}".`;
      setNotice(msg);
      pushToast('info', msg);
      await loadCampaigns(selectedId === campaign.id ? null : selectedId);
    } catch (err) {
      const msg = errMsg(err);
      setError(msg);
      pushToast('error', msg);
    } finally {
      setBusyId(null);
    }
  }

  async function handleExportCsv(campaign: AutopilotCampaign) {
    setError(null);
    try {
      const blob = await downloadAutopilotLeadsCsv(campaign.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `autopilot-${campaign.id}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      pushToast('success', `Exported CSV for "${campaign.name}".`);
    } catch (err) {
      const msg = errMsg(err);
      setError(msg);
      pushToast('error', msg);
    }
  }

  const selectedCampaign = campaigns.find((c) => c.id === selectedId) ?? null;

  return (
    <div className="space-y-6">
      {/* Top Hero Bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-[-0.02em] text-[#1D1D1F] dark:text-[#F5F5F7]">
            Lead Autopilot
          </h1>
          <p className="mt-0.5 text-sm text-[#6E6E73] dark:text-[#8E8E93]">
            Autonomous B2B prospect discovery &amp; verification
          </p>
        </div>

        <button
          type="button"
          onClick={() => setShowCreator((v) => !v)}
          data-testid="toggle-new-campaign"
          className="inline-flex w-full shrink-0 items-center justify-center whitespace-nowrap rounded-full bg-[#0071E3] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#0077ED] dark:bg-[#0A84FF] dark:hover:bg-[#2E96FF] sm:w-auto"
        >
          {showCreator ? 'Hide Builder' : '+ New Campaign'}
        </button>
      </div>

      {/* Apple-Grouped Settings Campaign Creator */}
      {showCreator && (
        <form
          onSubmit={(e) => void handleCreate(e)}
          className="space-y-4 rounded-2xl border border-black/[0.06] bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none sm:p-6"
        >
          {/* Section 1 — Target Profile */}
          <div className="space-y-3 rounded-2xl bg-[#F5F5F7] p-4 dark:bg-[#2C2C2E]">
            <p className="text-xs font-semibold text-[#6E6E73] dark:text-[#8E8E93]">
              Target Profile
            </p>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="min-w-0">
                <label
                  htmlFor="autopilot-name"
                  className="mb-1.5 block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]"
                >
                  Campaign Name
                </label>
                <input
                  id="autopilot-name"
                  className="w-full rounded-xl border border-black/[0.08] bg-white px-3.5 py-2 text-sm text-[#1D1D1F] placeholder-[#6E6E73]/60 focus:border-[#0071E3] focus:outline-none dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:text-[#F5F5F7] dark:placeholder-[#8E8E93] dark:focus:border-[#0A84FF]"
                  placeholder="US SaaS Stripe Prospects"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>

              <div className="min-w-0">
                <label
                  htmlFor="autopilot-keywords"
                  className="mb-1.5 block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]"
                >
                  Target Keywords
                </label>
                <div className="rounded-xl border border-black/[0.08] bg-white px-3 py-1.5 focus-within:border-[#0071E3] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:focus-within:border-[#0A84FF]">
                  {keywords.length > 0 && (
                    <div className="mb-1.5 flex flex-wrap gap-1.5">
                      {keywords.map((kw) => (
                        <span
                          key={kw}
                          className="inline-flex items-center gap-1 rounded-full bg-[#1D1D1F] px-2.5 py-0.5 text-xs font-medium text-white dark:bg-[#F5F5F7] dark:text-[#000000]"
                        >
                          {kw}
                          <button
                            type="button"
                            aria-label={`Remove keyword ${kw}`}
                            className="opacity-70 hover:opacity-100"
                            onClick={() => setKeywords((prev) => prev.filter((item) => item !== kw))}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                  <input
                    id="autopilot-keywords"
                    className="w-full bg-transparent py-0.5 text-sm text-[#1D1D1F] placeholder-[#6E6E73]/60 focus:outline-none dark:text-[#F5F5F7] dark:placeholder-[#8E8E93]"
                    placeholder="b2b saas, shopify agency"
                    value={keywordInput}
                    onChange={(e) => setKeywordInput(e.target.value)}
                    onKeyDown={handleKeywordKeyDown}
                    onBlur={() => {
                      if (keywordInput.includes(',')) commitKeywordInput(keywordInput);
                    }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Section 2 — Signal Filters */}
          <div className="space-y-4 rounded-2xl bg-[#F5F5F7] p-4 dark:bg-[#2C2C2E]">
            <p className="text-xs font-semibold text-[#6E6E73] dark:text-[#8E8E93]">
              Signal Filters
            </p>

            <div className="space-y-2.5">
              <div className="flex flex-wrap gap-2">
                {PRESET_TECH.map((tech) => {
                  const active = selectedTech.includes(tech);
                  return (
                    <button
                      key={tech}
                      type="button"
                      aria-pressed={active}
                      onClick={() => togglePresetTech(tech)}
                      className={`rounded-full px-3.5 py-1.5 text-xs font-medium transition ${
                        active
                          ? 'bg-[#1D1D1F] text-white dark:bg-[#F5F5F7] dark:text-[#000000]'
                          : 'border border-black/[0.08] bg-white text-[#1D1D1F] hover:bg-black/[0.04] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:text-[#F5F5F7] dark:hover:bg-white/[0.06]'
                      }`}
                    >
                      {tech}
                    </button>
                  );
                })}
              </div>
              <input
                aria-label="Additional required tech stack"
                className="w-full rounded-xl border border-black/[0.08] bg-white px-3.5 py-2 text-sm text-[#1D1D1F] placeholder-[#6E6E73]/60 focus:border-[#0071E3] focus:outline-none dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:text-[#F5F5F7] dark:placeholder-[#8E8E93] dark:focus:border-[#0A84FF]"
                placeholder="Additional tools (comma-separated, optional)"
                value={customTechInput}
                onChange={(e) => setCustomTechInput(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-3 border-t border-black/[0.06] pt-3 dark:border-white/[0.08] sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center justify-between gap-4 sm:justify-start">
                <div>
                  <span className="block text-sm font-medium text-[#1D1D1F] dark:text-[#F5F5F7]">
                    Actively hiring only
                  </span>
                  <span className="block text-xs text-[#6E6E73] dark:text-[#8E8E93]">
                    Require careers page or ATS platform
                  </span>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={requireHiring}
                  aria-label="Actively hiring only"
                  onClick={() => setRequireHiring((v) => !v)}
                  className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none ${
                    requireHiring ? 'bg-[#34C759]' : 'bg-black/[0.16] dark:bg-white/[0.2]'
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow-sm transition ${
                      requireHiring ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between gap-3 sm:justify-end">
                <label
                  htmlFor="autopilot-quota"
                  className="text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]"
                >
                  Daily Quota
                </label>
                <div className="inline-flex items-center rounded-full border border-black/[0.08] bg-white p-0.5 dark:border-white/[0.08] dark:bg-[#1C1C1E]">
                  <button
                    type="button"
                    aria-label="Decrease daily quota"
                    onClick={() => stepQuota(-5)}
                    className="h-7 w-7 rounded-full text-sm font-medium text-[#1D1D1F] hover:bg-black/[0.05] dark:text-[#F5F5F7] dark:hover:bg-white/[0.08]"
                  >
                    −
                  </button>
                  <input
                    id="autopilot-quota"
                    type="number"
                    min={1}
                    max={500}
                    value={dailyQuota}
                    onChange={(e) => setDailyQuota(e.target.value)}
                    className="w-14 bg-transparent text-center text-sm font-semibold tabular-nums text-[#1D1D1F] focus:outline-none dark:text-[#F5F5F7]"
                  />
                  <button
                    type="button"
                    aria-label="Increase daily quota"
                    onClick={() => stepQuota(5)}
                    className="h-7 w-7 rounded-full text-sm font-medium text-[#1D1D1F] hover:bg-black/[0.05] dark:text-[#F5F5F7] dark:hover:bg-white/[0.08]"
                  >
                    +
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Section 3 — Collapsible Delivery Destination */}
          <div className="rounded-2xl bg-[#F5F5F7] dark:bg-[#2C2C2E]">
            <button
              type="button"
              aria-expanded={showDelivery}
              onClick={() => setShowDelivery((v) => !v)}
              className="flex w-full items-center justify-between px-4 py-3 text-left text-xs font-semibold text-[#1D1D1F] dark:text-[#F5F5F7]"
            >
              <span>CRM &amp; Webhook Delivery (Optional)</span>
              <span className="text-xs text-[#6E6E73] dark:text-[#8E8E93]">
                {showDelivery ? 'Hide' : 'Configure'}
              </span>
            </button>

            {showDelivery && (
              <div className="grid grid-cols-1 gap-3 border-t border-black/[0.06] px-4 pb-4 pt-3 dark:border-white/[0.08] sm:grid-cols-2">
                <div className="min-w-0">
                  <label
                    htmlFor="autopilot-crm"
                    className="mb-1 block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]"
                  >
                    Destination
                  </label>
                  <select
                    id="autopilot-crm"
                    className="w-full rounded-xl border border-black/[0.08] bg-white px-3.5 py-2 text-sm text-[#1D1D1F] focus:border-[#0071E3] focus:outline-none dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:text-[#F5F5F7] dark:focus:border-[#0A84FF]"
                    value={crmProvider}
                    onChange={(e) => setCrmProvider(e.target.value as CrmProvider)}
                  >
                    <option value="none">None</option>
                    <option value="hubspot">HubSpot</option>
                    <option value="salesforce">Salesforce</option>
                    <option value="webhook">Custom Webhook</option>
                  </select>
                </div>
                <div className="min-w-0">
                  <label
                    htmlFor="autopilot-crm-target"
                    className="mb-1 block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]"
                  >
                    {crmProvider === 'webhook' ? 'Webhook URL' : 'Target URL / Token'}
                  </label>
                  <input
                    id="autopilot-crm-target"
                    className="w-full rounded-xl border border-black/[0.08] bg-white px-3.5 py-2 text-sm text-[#1D1D1F] placeholder-[#6E6E73]/60 focus:border-[#0071E3] focus:outline-none disabled:opacity-50 dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:text-[#F5F5F7] dark:placeholder-[#8E8E93] dark:focus:border-[#0A84FF]"
                    disabled={crmProvider === 'none'}
                    placeholder={
                      crmProvider === 'webhook'
                        ? 'https://example.com/hook'
                        : crmProvider === 'none'
                          ? 'Select a destination'
                          : 'CRM API token'
                    }
                    value={crmTarget}
                    onChange={(e) => setCrmTarget(e.target.value)}
                  />
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <p className="text-xs text-[#6E6E73] dark:text-[#8E8E93]">
              1 credit per newly discovered, uncached lead.
            </p>
            <button
              type="submit"
              disabled={creating}
              className="inline-flex w-full items-center justify-center rounded-full bg-[#0071E3] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#0077ED] disabled:opacity-50 dark:bg-[#0A84FF] dark:hover:bg-[#2E96FF] sm:w-auto"
            >
              {creating ? 'Creating…' : 'Create Campaign'}
            </button>
          </div>
        </form>
      )}

      {notice && (
        <p className="rounded-2xl border border-[#34C759]/25 bg-[#34C759]/10 px-4 py-3 text-sm text-[#248A3D] dark:text-[#30D158]">
          {notice}
        </p>
      )}
      {error && (
        <p className="rounded-2xl border border-[#FF3B30]/25 bg-[#FF3B30]/10 px-4 py-3 text-sm text-[#D70015] dark:text-[#FF453A]">
          {error}
        </p>
      )}

      {/* Active Campaigns List */}
      <div className="space-y-4">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-sm font-semibold text-[#1D1D1F] dark:text-[#F5F5F7]">
            Campaigns <span className="tabular-nums text-[#6E6E73] dark:text-[#8E8E93]">({campaigns.length})</span>
          </h2>
        </div>

        {loadingCampaigns ? (
          <div className="rounded-2xl border border-black/[0.06] bg-white p-8 text-center text-sm text-[#6E6E73] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:text-[#8E8E93]">
            Loading campaigns…
          </div>
        ) : campaigns.length === 0 ? (
          <div className="rounded-2xl border border-black/[0.06] bg-white p-8 text-center text-sm text-[#6E6E73] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:text-[#8E8E93]">
            No Lead Autopilot campaigns yet. Create one above to start discovering qualified leads.
          </div>
        ) : (
          <div className="space-y-4">
            {campaigns.map((c) => {
              const isSelected = c.id === selectedId;
              const isRunning = runningId === c.id;
              const isBusy = busyId === c.id;
              return (
                <div
                  key={c.id}
                  data-testid={`campaign-card-${c.id}`}
                  className={`space-y-4 rounded-2xl border bg-white p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] transition dark:bg-[#1C1C1E] dark:shadow-none ${
                    isRunning
                      ? 'border-[#0071E3] ring-2 ring-[#0071E3]/20 dark:border-[#0A84FF] dark:ring-[#0A84FF]/25'
                      : isSelected
                        ? 'border-[#0071E3] dark:border-[#0A84FF]'
                        : 'border-black/[0.06] dark:border-white/[0.08]'
                  }`}
                >
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 flex-1 space-y-2.5">
                      <div className="flex flex-wrap items-center gap-2.5">
                        <button
                          type="button"
                          onClick={() => setSelectedId(c.id)}
                          className="text-left text-lg font-semibold tracking-[-0.02em] text-[#1D1D1F] transition hover:text-[#0071E3] dark:text-[#F5F5F7] dark:hover:text-[#0A84FF]"
                        >
                          {c.name}
                        </button>
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
                            isRunning
                              ? 'bg-[#0071E3]/15 text-[#0071E3] dark:bg-[#0A84FF]/20 dark:text-[#0A84FF]'
                              : c.status === 'active'
                                ? 'bg-[#34C759]/15 text-[#248A3D] dark:text-[#30D158]'
                                : 'bg-[#FF9F0A]/15 text-[#B25000] dark:text-[#FFD60A]'
                          }`}
                        >
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              isRunning
                                ? 'animate-pulse bg-[#0071E3] dark:bg-[#0A84FF]'
                                : c.status === 'active'
                                  ? 'bg-[#34C759]'
                                  : 'bg-[#FF9F0A]'
                            }`}
                          />
                          {isRunning ? 'Discovering…' : c.status === 'active' ? 'Active' : 'Paused'}
                        </span>
                        {c.require_hiring && (
                          <span className="rounded-full bg-[#F5F5F7] px-3 py-1 text-xs font-medium text-[#1D1D1F] dark:bg-[#2C2C2E] dark:text-[#F5F5F7]">
                            Hiring only
                          </span>
                        )}
                        {c.target_crm_provider !== 'none' && (
                          <span className="rounded-full bg-[#F5F5F7] px-3 py-1 text-xs font-medium text-[#6E6E73] dark:bg-[#2C2C2E] dark:text-[#8E8E93]">
                            {CRM_LABELS[c.target_crm_provider]}
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap gap-1.5">
                        {c.target_keywords.map((kw) => (
                          <span
                            key={kw}
                            className="rounded-full bg-[#F5F5F7] px-3 py-1 text-xs font-medium text-[#1D1D1F] dark:bg-[#2C2C2E] dark:text-[#F5F5F7]"
                          >
                            {kw}
                          </span>
                        ))}
                        {c.required_tech_stack.map((tech) => (
                          <span
                            key={tech}
                            className="rounded-full border border-black/[0.08] bg-white px-3 py-1 text-xs font-medium text-[#6E6E73] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:text-[#8E8E93]"
                          >
                            {tech}
                          </span>
                        ))}
                      </div>

                      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-[#6E6E73] dark:text-[#8E8E93]">
                        <span>
                          Leads delivered:{' '}
                          <strong className="font-semibold tabular-nums text-[#1D1D1F] dark:text-[#F5F5F7]">
                            {c.total_leads_delivered}
                          </strong>
                        </span>
                        <span>
                          Quota:{' '}
                          <strong className="font-semibold tabular-nums text-[#1D1D1F] dark:text-[#F5F5F7]">
                            {c.daily_lead_quota}/day
                          </strong>
                        </span>
                        <span>
                          Last run:{' '}
                          <strong className="font-semibold tabular-nums text-[#1D1D1F] dark:text-[#F5F5F7]">
                            {c.last_run_at ? new Date(c.last_run_at).toLocaleString() : 'Never'}
                          </strong>
                        </span>
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-2 lg:justify-end">
                      <button
                        type="button"
                        disabled={isRunning || isBusy}
                        onClick={() => void handleRunNow(c)}
                        data-testid={`run-now-${c.id}`}
                        className={`inline-flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-full bg-[#0071E3] px-4 py-2 text-xs font-medium text-white transition hover:bg-[#0077ED] disabled:opacity-60 dark:bg-[#0A84FF] dark:hover:bg-[#2E96FF] sm:flex-none ${
                          isRunning ? 'animate-pulse' : ''
                        }`}
                      >
                        {isRunning && (
                          <span className="h-2 w-2 rounded-full bg-white animate-ping" aria-hidden="true" />
                        )}
                        <span>{isRunning ? 'Running…' : 'Run Now'}</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleExportCsv(c)}
                        className="inline-flex flex-1 items-center justify-center whitespace-nowrap rounded-full border border-black/[0.1] bg-[#F5F5F7] px-4 py-2 text-xs font-medium text-[#1D1D1F] transition hover:bg-black/[0.06] dark:border-white/[0.1] dark:bg-[#2C2C2E] dark:text-[#F5F5F7] dark:hover:bg-white/[0.1] sm:flex-none"
                      >
                        Export CSV
                      </button>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => void handleToggleStatus(c)}
                        className="inline-flex flex-1 items-center justify-center whitespace-nowrap rounded-full border border-black/[0.1] bg-white px-4 py-2 text-xs font-medium text-[#1D1D1F] transition hover:bg-black/[0.04] disabled:opacity-50 dark:border-white/[0.1] dark:bg-[#1C1C1E] dark:text-[#F5F5F7] dark:hover:bg-[#2C2C2E] sm:flex-none"
                      >
                        {c.status === 'active' ? 'Pause' : 'Resume'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setSelectedId(isSelected ? null : c.id)}
                        className="inline-flex flex-1 items-center justify-center whitespace-nowrap rounded-full border border-black/[0.1] bg-white px-4 py-2 text-xs font-medium text-[#0071E3] transition hover:bg-black/[0.04] dark:border-white/[0.1] dark:bg-[#1C1C1E] dark:text-[#0A84FF] dark:hover:bg-[#2C2C2E] sm:flex-none"
                      >
                        {isSelected ? 'Hide Leads' : 'View Leads'}
                      </button>
                      {confirmDeleteId === c.id ? (
                        <div className="flex w-full gap-2 sm:w-auto">
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => void handleDelete(c)}
                            className="inline-flex flex-1 items-center justify-center whitespace-nowrap rounded-full bg-[#FF3B30] px-4 py-2 text-xs font-medium text-white transition hover:opacity-90 disabled:opacity-50 sm:flex-none"
                          >
                            Confirm Delete
                          </button>
                          <button
                            type="button"
                            onClick={() => setConfirmDeleteId(null)}
                            className="inline-flex flex-1 items-center justify-center whitespace-nowrap rounded-full border border-black/[0.1] bg-white px-4 py-2 text-xs font-medium text-[#1D1D1F] dark:border-white/[0.1] dark:bg-[#1C1C1E] dark:text-[#F5F5F7] sm:flex-none"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          disabled={isBusy}
                          onClick={() => setConfirmDeleteId(c.id)}
                          className="inline-flex flex-1 items-center justify-center whitespace-nowrap rounded-full border border-black/[0.1] bg-white px-4 py-2 text-xs font-medium text-[#D70015] transition hover:bg-[#FF3B30]/10 disabled:opacity-50 dark:border-white/[0.1] dark:bg-[#1C1C1E] dark:text-[#FF453A] sm:flex-none"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Expandable Delivered Leads Viewer */}
      {selectedCampaign && (
        <div
          className="space-y-4 rounded-2xl border border-black/[0.06] bg-white p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none"
          data-testid="delivered-leads-viewer"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-base font-semibold tracking-[-0.02em] text-[#1D1D1F] dark:text-[#F5F5F7]">
                Delivered Leads — {selectedCampaign.name}
              </h3>
              <p className="text-xs tabular-nums text-[#6E6E73] dark:text-[#8E8E93]">
                Showing {leads.length} of {leadsTotal} verified &amp; deduplicated leads
              </p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void fetchLeads(selectedCampaign.id)}
                className="rounded-full border border-black/[0.1] bg-[#F5F5F7] px-3.5 py-1.5 text-xs font-medium text-[#1D1D1F] transition hover:bg-black/[0.06] dark:border-white/[0.1] dark:bg-[#2C2C2E] dark:text-[#F5F5F7]"
              >
                Refresh
              </button>
              <button
                type="button"
                onClick={() => void handleExportCsv(selectedCampaign)}
                className="rounded-full border border-black/[0.1] bg-[#F5F5F7] px-3.5 py-1.5 text-xs font-medium text-[#1D1D1F] transition hover:bg-black/[0.06] dark:border-white/[0.1] dark:bg-[#2C2C2E] dark:text-[#F5F5F7]"
              >
                Export CSV
              </button>
            </div>
          </div>

          {loadingLeads ? (
            <p className="py-6 text-center text-sm text-[#6E6E73] dark:text-[#8E8E93]">
              Loading delivered leads…
            </p>
          ) : leads.length === 0 ? (
            <p className="py-6 text-center text-sm text-[#6E6E73] dark:text-[#8E8E93]">
              No leads delivered for this campaign yet. Click &ldquo;Run Now&rdquo; to trigger discovery.
            </p>
          ) : (
            <>
              {/* Mobile stacked lead cards (< 768px) */}
              <div className="space-y-3 md:hidden" data-testid="leads-mobile-list">
                {leads.map((lead) => (
                  <div
                    key={lead.id}
                    className="rounded-2xl bg-[#F5F5F7] p-4 dark:bg-[#2C2C2E]"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-[#1D1D1F] dark:text-[#F5F5F7]">
                          {lead.company_name || lead.domain}
                        </p>
                        <p className="break-all font-mono text-xs text-[#0071E3] dark:text-[#0A84FF]">
                          {lead.domain}
                        </p>
                      </div>
                      {lead.email_provider && (
                        <span className="shrink-0 rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-[#1D1D1F] dark:bg-[#1C1C1E] dark:text-[#F5F5F7]">
                          {lead.email_provider}
                        </span>
                      )}
                    </div>

                    {lead.verified_emails.length > 0 && (
                      <div className="mt-3">
                        <span className="block text-[11px] font-medium text-[#6E6E73] dark:text-[#8E8E93]">
                          Verified Emails
                        </span>
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {lead.verified_emails.map((email) => (
                            <span
                              key={email}
                              className="break-all rounded-full bg-[#34C759]/15 px-2.5 py-0.5 font-mono text-xs text-[#248A3D] dark:text-[#30D158]"
                            >
                              {email}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {lead.tech_stack.length > 0 && (
                      <div className="mt-3">
                        <span className="block text-[11px] font-medium text-[#6E6E73] dark:text-[#8E8E93]">
                          Tech Stack
                        </span>
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {lead.tech_stack.map((tech) => (
                            <span
                              key={tech}
                              className="rounded-full bg-white px-2.5 py-0.5 text-xs text-[#1D1D1F] dark:bg-[#1C1C1E] dark:text-[#F5F5F7]"
                            >
                              {tech}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {lead.hiring_ats.length > 0 && (
                      <div className="mt-3">
                        <span className="block text-[11px] font-medium text-[#6E6E73] dark:text-[#8E8E93]">
                          Hiring ATS
                        </span>
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {lead.hiring_ats.map((ats) => (
                            <span
                              key={ats}
                              className="rounded-full bg-[#0071E3]/10 px-2.5 py-0.5 text-xs font-medium text-[#0071E3] dark:bg-[#0A84FF]/15 dark:text-[#0A84FF]"
                            >
                              {ats}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Desktop leads table (>= 768px) */}
              <div className="hidden overflow-x-auto md:block">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-black/[0.06] text-xs font-medium text-[#6E6E73] dark:border-white/[0.08] dark:text-[#8E8E93]">
                    <tr>
                      <th className="px-3 py-2.5">Company &amp; Domain</th>
                      <th className="px-3 py-2.5">Tech Stack</th>
                      <th className="px-3 py-2.5">Email Infra</th>
                      <th className="px-3 py-2.5">Verified Emails</th>
                      <th className="px-3 py-2.5">Hiring ATS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leads.map((lead) => (
                      <tr key={lead.id} className="border-b border-black/[0.04] align-top last:border-0 dark:border-white/[0.06]">
                        <td className="px-3 py-3.5">
                          <div className="font-semibold text-[#1D1D1F] dark:text-[#F5F5F7]">
                            {lead.company_name || lead.domain}
                          </div>
                          <div className="font-mono text-xs text-[#0071E3] dark:text-[#0A84FF]">
                            {lead.domain}
                          </div>
                        </td>
                        <td className="px-3 py-3.5">
                          <div className="flex flex-wrap gap-1.5">
                            {lead.tech_stack.length > 0 ? (
                              lead.tech_stack.map((tech) => (
                                <span
                                  key={tech}
                                  className="rounded-full bg-[#F5F5F7] px-2.5 py-0.5 text-xs text-[#1D1D1F] dark:bg-[#2C2C2E] dark:text-[#F5F5F7]"
                                >
                                  {tech}
                                </span>
                              ))
                            ) : (
                              <span className="text-xs text-[#6E6E73] dark:text-[#8E8E93]">—</span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-3.5 text-xs text-[#1D1D1F] dark:text-[#F5F5F7]">
                          {lead.email_provider || 'Unknown'}
                        </td>
                        <td className="px-3 py-3.5">
                          <div className="flex flex-col gap-1">
                            {lead.verified_emails.length > 0 ? (
                              lead.verified_emails.map((email) => (
                                <span
                                  key={email}
                                  className="inline-block w-fit rounded-full bg-[#34C759]/15 px-2.5 py-0.5 font-mono text-xs text-[#248A3D] dark:text-[#30D158]"
                                >
                                  {email}
                                </span>
                              ))
                            ) : (
                              <span className="text-xs text-[#6E6E73] dark:text-[#8E8E93]">None</span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-3.5">
                          <div className="flex flex-wrap gap-1.5">
                            {lead.hiring_ats.length > 0 ? (
                              lead.hiring_ats.map((ats) => (
                                <span
                                  key={ats}
                                  className="rounded-full bg-[#0071E3]/10 px-2.5 py-0.5 text-xs font-medium text-[#0071E3] dark:bg-[#0A84FF]/15 dark:text-[#0A84FF]"
                                >
                                  {ats}
                                </span>
                              ))
                            ) : (
                              <span className="text-xs text-[#6E6E73] dark:text-[#8E8E93]">—</span>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {toasts.length > 0 && (
        <div
          aria-live="polite"
          className="pointer-events-none fixed bottom-5 right-5 z-50 flex w-[calc(100vw-2.5rem)] max-w-sm flex-col gap-2"
        >
          {toasts.map((t) => (
            <div
              key={t.id}
              data-testid="autopilot-toast"
              className={`pointer-events-auto flex items-start justify-between gap-3 rounded-2xl border px-4 py-3 text-xs shadow-lg backdrop-blur-xl ${
                t.kind === 'error'
                  ? 'border-[#FF3B30]/30 bg-white/95 text-[#D70015] dark:border-[#FF453A]/30 dark:bg-[#1C1C1E]/95 dark:text-[#FF453A]'
                  : t.kind === 'success'
                    ? 'border-[#34C759]/30 bg-white/95 text-[#248A3D] dark:border-[#30D158]/30 dark:bg-[#1C1C1E]/95 dark:text-[#30D158]'
                    : 'border-black/[0.08] bg-white/95 text-[#1D1D1F] dark:border-white/[0.1] dark:bg-[#1C1C1E]/95 dark:text-[#F5F5F7]'
              }`}
            >
              <span className="leading-relaxed">{t.text}</span>
              <button
                type="button"
                aria-label="Dismiss notification"
                onClick={() => dismissToast(t.id)}
                className="shrink-0 opacity-60 transition hover:opacity-100"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
