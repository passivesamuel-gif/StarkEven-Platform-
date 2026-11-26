'use client';

import type { Me } from '@/lib/api';

type PlanCard = {
  id: 'starter' | 'growth' | 'agency';
  name: string;
  price: string;
  creditsLabel: string;
  audience: string;
  features: string[];
  checkoutBaseUrl: string | undefined;
  envName: string;
  featured?: boolean;
};

const PLANS: PlanCard[] = [
  {
    id: 'starter',
    name: 'Starter',
    price: '$79/mo',
    creditsLabel: '1,000 credits',
    audience: 'For lean outbound & engineering teams',
    features: [
      '1,000 monthly enrichment & verification credits',
      '24-hour smart cache (repeat lookups free)',
      'Bulk CSV batches up to 10,000 domains',
    ],
    checkoutBaseUrl: process.env.NEXT_PUBLIC_CHECKOUT_STARTER_URL,
    envName: 'NEXT_PUBLIC_CHECKOUT_STARTER_URL',
  },
  {
    id: 'growth',
    name: 'Growth',
    price: '$199/mo',
    creditsLabel: '4,000 credits + Lead Autopilot',
    audience: 'Recommended for automated pipeline generation',
    features: [
      '4,000 monthly credits across all endpoints',
      'Lead Autopilot scheduled ICP discovery & verification',
      'HubSpot, Salesforce & signed webhook delivery',
    ],
    checkoutBaseUrl: process.env.NEXT_PUBLIC_CHECKOUT_GROWTH_URL,
    envName: 'NEXT_PUBLIC_CHECKOUT_GROWTH_URL',
    featured: true,
  },
  {
    id: 'agency',
    name: 'Agency',
    price: '$499/mo',
    creditsLabel: '15,000 credits',
    audience: 'For high-volume data & lead agencies',
    features: [
      '15,000 monthly credits with priority throughput',
      'Up to 3,000 requests/min sliding-window quota',
      'Unlimited Autopilot campaigns & CSV exports',
    ],
    checkoutBaseUrl: process.env.NEXT_PUBLIC_CHECKOUT_AGENCY_URL,
    envName: 'NEXT_PUBLIC_CHECKOUT_AGENCY_URL',
  },
];

function formatCurrentPlan(planTier: string): string {
  const normalized = planTier.toLowerCase();
  if (normalized === 'pro' || normalized === 'growth') return 'Growth $199/mo';
  if (normalized === 'enterprise' || normalized === 'agency') return 'Agency $499/mo';
  return 'Starter Free';
}

function buildCheckoutHref(baseUrl: string, orgId: number): string {
  const trimmed = baseUrl.trim();
  const sep = trimmed.includes('?') ? '&' : '?';
  return `${trimmed}${sep}checkout[custom][org_id]=${encodeURIComponent(String(orgId))}`;
}

export default function BillingPanel({ me }: { me: Me }) {
  const currentPlanLabel = formatCurrentPlan(me.plan_tier);

  return (
    <div className="space-y-6">
      {/* Current Plan & Credit Summary */}
      <div className="flex flex-col gap-4 rounded-2xl border border-black/[0.06] bg-white p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
            Current Plan · Organization #{me.id}
          </p>
          <div className="flex flex-wrap items-baseline gap-3">
            <h1 className="text-2xl font-semibold tracking-[-0.02em] text-[#1D1D1F] dark:text-[#F5F5F7]">
              {currentPlanLabel}
            </h1>
            <span className="rounded-full bg-[#F5F5F7] px-3 py-1 text-xs font-medium tabular-nums text-[#6E6E73] dark:bg-[#2C2C2E] dark:text-[#8E8E93]">
              {me.rate_limit_per_min.toLocaleString()} req/min
            </span>
          </div>
          <p className="text-sm text-[#6E6E73] dark:text-[#8E8E93]">
            Remaining balance:{' '}
            <strong className="font-semibold tabular-nums text-[#1D1D1F] dark:text-[#F5F5F7]">
              {me.credit_balance.toLocaleString()} credits
            </strong>
          </p>
        </div>

        <p className="text-xs text-[#6E6E73] dark:text-[#8E8E93] sm:text-right">
          Credits are provisioned automatically via verified billing webhooks upon checkout.
        </p>
      </div>

      {/* Upgrade Plans */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {PLANS.map((plan) => {
          const checkoutUrl = plan.checkoutBaseUrl?.trim()
            ? buildCheckoutHref(plan.checkoutBaseUrl, me.id)
            : null;
          return (
            <div
              key={plan.id}
              data-testid={`billing-plan-${plan.id}`}
              className={`flex flex-col justify-between space-y-5 rounded-2xl border bg-white p-6 shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:bg-[#1C1C1E] dark:shadow-none ${
                plan.featured
                  ? 'border-[#0071E3] dark:border-[#0A84FF]'
                  : 'border-black/[0.06] dark:border-white/[0.08]'
              }`}
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-base font-semibold tracking-[-0.02em] text-[#1D1D1F] dark:text-[#F5F5F7]">
                    {plan.name}
                  </h3>
                  {plan.featured && (
                    <span className="rounded-full bg-[#0071E3]/10 px-3 py-1 text-xs font-medium text-[#0071E3] dark:bg-[#0A84FF]/15 dark:text-[#0A84FF]">
                      Recommended
                    </span>
                  )}
                </div>

                <div>
                  <p className="text-3xl font-semibold tracking-[-0.02em] tabular-nums text-[#1D1D1F] dark:text-[#F5F5F7]">
                    {plan.price}
                  </p>
                  <p className="mt-1 text-sm font-medium text-[#0071E3] dark:text-[#0A84FF]">
                    {plan.creditsLabel}
                  </p>
                </div>

                <p className="text-xs text-[#6E6E73] dark:text-[#8E8E93]">
                  {plan.audience}
                </p>

                <ul className="space-y-2 rounded-2xl bg-[#F5F5F7] p-4 text-xs leading-relaxed text-[#1D1D1F]/80 dark:bg-[#2C2C2E] dark:text-[#F5F5F7]/80">
                  {plan.features.map((feat) => (
                    <li key={feat} className="flex gap-2">
                      <span aria-hidden="true" className="text-[#0071E3] dark:text-[#0A84FF]">•</span>
                      <span>{feat}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {checkoutUrl ? (
                <a
                  href={checkoutUrl}
                  rel="noopener noreferrer"
                  className={
                    plan.featured
                      ? 'inline-flex w-full items-center justify-center rounded-full bg-[#0071E3] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#0077ED] dark:bg-[#0A84FF] dark:hover:bg-[#2E96FF]'
                      : 'inline-flex w-full items-center justify-center rounded-full border border-black/[0.1] bg-[#F5F5F7] px-5 py-2.5 text-sm font-medium text-[#1D1D1F] transition hover:bg-black/[0.06] dark:border-white/[0.1] dark:bg-[#2C2C2E] dark:text-[#F5F5F7]'
                  }
                >
                  Upgrade to {plan.name}
                </a>
              ) : (
                <button
                  type="button"
                  disabled
                  title={`Set ${plan.envName} at build time to enable ${plan.name} checkout`}
                  className={
                    plan.featured
                      ? 'inline-flex w-full cursor-not-allowed items-center justify-center rounded-full bg-[#0071E3]/60 px-5 py-2.5 text-sm font-medium text-white dark:bg-[#0A84FF]/50'
                      : 'inline-flex w-full cursor-not-allowed items-center justify-center rounded-full border border-black/[0.08] bg-[#F5F5F7] px-5 py-2.5 text-sm font-medium text-[#6E6E73] dark:border-white/[0.08] dark:bg-[#2C2C2E] dark:text-[#8E8E93]'
                  }
                >
                  Configure {plan.name} Checkout
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
