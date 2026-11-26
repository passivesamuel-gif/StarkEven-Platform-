import Link from 'next/link';
import FaqAccordion from '@/components/FaqAccordion';
import LandingFooter from '@/components/LandingFooter';
import LandingHeader from '@/components/LandingHeader';
import LiveDemo from '@/components/LiveDemo';
import Reveal from '@/components/Reveal';

const PLANS = [
  {
    name: 'Starter',
    price: '$79/mo',
    credits: '1,000 credits',
    note: 'Real-time company enrichment, bulk CSV batches, and SMTP email verification.',
    limit: '600 requests / min · 50 free trial credits to start',
    cta: 'Start free',
    featured: false,
  },
  {
    name: 'Growth',
    price: '$199/mo',
    credits: '4,000 credits + Lead Autopilot',
    note: 'Autonomous ICP lead discovery, enrichment, verification, and CRM webhook sync.',
    limit: '600 requests / min · Scheduled every 6h or on demand',
    cta: 'Launch Autopilot',
    featured: true,
  },
  {
    name: 'Agency',
    price: '$499/mo',
    credits: '15,000 credits',
    note: 'High-volume multi-campaign pipelines for outbound teams and data platforms.',
    limit: '3,000 requests / min · Priority batch execution',
    cta: 'Get started',
    featured: false,
  },
];

const STATS = [
  { n: '54+', l: 'Technologies fingerprinted' },
  { n: '24h', l: 'Smart caching, free repeats' },
  { n: '10,000', l: 'Domains per bulk CSV batch' },
  { n: '100%', l: 'Deterministic signals, zero guesswork' },
];

const CODE: { t: string; c: string }[] = [
  { t: 'curl -X POST https://api.starkeven.com/api/v1/enrich/domain \\', c: 'text-slate-300' },
  { t: '  -H "X-API-Key: sk_live_••••••••" \\', c: 'text-slate-300' },
  { t: '  -d \'{"domain": "stripe.com"}\'', c: 'text-slate-300' },
  { t: '', c: '' },
  { t: '{', c: 'text-slate-500' },
  { t: '  "company": { "name": "Stripe", "linkedin": "linkedin.com/company/stripe" },', c: 'text-emerald-300' },
  { t: '  "tech_stack": ["Stripe", "Cloudflare", "Segment", "Google Tag Manager"],', c: 'text-sky-300' },
  { t: '  "email": { "provider": "Google Workspace", "spf": true },', c: 'text-indigo-300' },
  { t: '  "hiring": { "ats": ["Greenhouse"], "has_careers_page": true }', c: 'text-amber-300' },
  { t: '}', c: 'text-slate-500' },
];

const STACK_PREVIEW = [
  'Stripe',
  'HubSpot',
  'Cloudflare',
  'Segment',
  'Shopify',
  'Intercom',
  'Next.js',
  'Salesforce',
];

export default function Home() {
  return (
    <main className="overflow-x-hidden bg-[#FBFBFD] text-[#1D1D1F] transition-colors dark:bg-[#0B0B0C] dark:text-[#F5F5F7]">
      <LandingHeader />

      {/* HERO */}
      <section className="relative px-5 pb-20 pt-32 text-center sm:pb-24 sm:pt-40">
        <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-[620px] overflow-hidden">
          <div className="floaty absolute left-1/2 top-8 h-[420px] w-[420px] -translate-x-[115%] rounded-full bg-indigo-200/35 blur-[110px] dark:bg-indigo-500/15" />
          <div
            className="floaty absolute left-1/2 top-20 h-[380px] w-[380px] translate-x-[15%] rounded-full bg-violet-200/30 blur-[110px] dark:bg-violet-500/15"
            style={{ animationDelay: '-4s' }}
          />
        </div>

        <div className="relative z-10 mx-auto max-w-[960px]">
          <Reveal>
            <p className="mb-4 text-sm font-medium tracking-wide text-brand-600 dark:text-brand-400">
              B2B Lead &amp; Data Intelligence
            </p>
          </Reveal>
          <Reveal delay={60}>
            <h1 className="mx-auto max-w-[820px] text-balance text-[40px] font-semibold leading-[1.06] tracking-[-0.04em] sm:text-6xl lg:text-[84px]">
              Know any company. <span className="grad">Instantly.</span>
            </h1>
          </Reveal>
          <Reveal delay={120}>
            <p className="mx-auto mt-6 max-w-[620px] text-lg leading-relaxed text-[#1D1D1F]/65 dark:text-[#F5F5F7]/65 sm:text-xl">
              Turn any domain into a structured lead profile—tech stack, email infrastructure, hiring signals, and autonomous ICP pipeline discovery.
            </p>
          </Reveal>
          <Reveal delay={180}>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-5">
              <Link
                href="/login"
                className="whitespace-nowrap rounded-full bg-[#1D1D1F] px-7 py-3 text-[15px] font-medium text-white transition hover:bg-black dark:bg-[#F5F5F7] dark:text-[#0B0B0C] dark:hover:bg-white"
              >
                Start free
              </Link>
              <a
                href="/docs"
                className="whitespace-nowrap text-[15px] font-medium text-brand-600 transition hover:underline dark:text-brand-400"
              >
                View API docs ›
              </a>
            </div>
          </Reveal>

          <Reveal delay={240} className="mt-14">
            <div
              id="demo"
              className="hairline-card mx-auto scroll-mt-20 p-4 sm:p-8"
            >
              <LiveDemo />
              <p className="mt-4 text-xs text-[#1D1D1F]/45 dark:text-[#F5F5F7]/45">
                Live lookup preview. Free accounts include 50 trial credits with full JSON and CSV access.
              </p>
            </div>
          </Reveal>
        </div>
      </section>

      {/* STATS */}
      <section className="px-5 pb-24">
        <div className="mx-auto grid max-w-[980px] grid-cols-2 gap-y-8 border-y border-black/[0.08] py-12 text-center dark:border-white/[0.08] md:grid-cols-4">
          {STATS.map((s, i) => (
            <Reveal key={s.l} delay={i * 60}>
              <p className="text-4xl font-semibold tracking-tight tabular-nums sm:text-5xl">{s.n}</p>
              <p className="mx-auto mt-2 max-w-[170px] text-[13px] text-[#1D1D1F]/60 dark:text-[#F5F5F7]/60">
                {s.l}
              </p>
            </Reveal>
          ))}
        </div>
      </section>

      {/* BENTO FEATURES */}
      <section id="features" className="px-5 pb-24">
        <div className="mx-auto max-w-[1120px]">
          <Reveal>
            <div className="mx-auto mb-12 max-w-[680px] text-center">
              <h2 className="text-balance text-3xl font-semibold tracking-[-0.03em] sm:text-5xl">
                Built for deterministic revenue pipelines.
              </h2>
              <p className="mt-4 text-base text-[#1D1D1F]/60 dark:text-[#F5F5F7]/60 sm:text-lg">
                Four focused engines working from live HTTP, DNS, MX, and careers signals—never synthetic AI guesses.
              </p>
            </div>
          </Reveal>

          <div className="grid gap-5 md:grid-cols-6">
            {/* Card 1: Autonomous Lead Generation */}
            <Reveal className="min-w-0 md:col-span-4">
              <div className="hairline-card flex h-full flex-col justify-between p-7 sm:p-9">
                <div>
                  <p className="text-xs font-medium tracking-wide text-brand-600 dark:text-brand-400">
                    Autonomous Lead Generation
                  </p>
                  <h3 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
                    Lead Autopilot
                  </h3>
                  <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-[#1D1D1F]/65 dark:text-[#F5F5F7]/65">
                    Define target keywords, required tech stack, hiring signals, and daily quotas. StarkEven automatically discovers, enriches, SMTP-verifies, and deduplicates fresh B2B leads into HubSpot, Salesforce, custom webhooks, or CSV.
                  </p>
                </div>
                <div className="mt-7 grid grid-cols-3 gap-3 border-t border-black/[0.08] pt-5 text-xs dark:border-white/[0.08]">
                  <div>
                    <span className="block text-[#1D1D1F]/50 dark:text-[#F5F5F7]/50">Cadence</span>
                    <span className="mt-0.5 block font-semibold tabular-nums">Every 6h + Run Now</span>
                  </div>
                  <div>
                    <span className="block text-[#1D1D1F]/50 dark:text-[#F5F5F7]/50">Daily Quota</span>
                    <span className="mt-0.5 block font-semibold tabular-nums">1 – 500 leads</span>
                  </div>
                  <div>
                    <span className="block text-[#1D1D1F]/50 dark:text-[#F5F5F7]/50">Deduplication</span>
                    <span className="mt-0.5 block font-semibold">Per-org atomic lock</span>
                  </div>
                </div>
              </div>
            </Reveal>

            {/* Card 2: Real-Time Company Enrichment */}
            <Reveal delay={80} className="min-w-0 md:col-span-2">
              <div className="hairline-card flex h-full flex-col justify-between p-7 sm:p-8">
                <div>
                  <p className="text-xs font-medium tracking-wide text-brand-600 dark:text-brand-400">
                    54+ Technologies
                  </p>
                  <h3 className="mt-2 text-2xl font-semibold tracking-tight">
                    Real-Time Company Enrichment
                  </h3>
                  <p className="mt-3 text-[15px] leading-relaxed text-[#1D1D1F]/65 dark:text-[#F5F5F7]/65">
                    Fingerprint frameworks, billing, CRM, email providers, SPF records, and ATS hiring pages in one REST call.
                  </p>
                </div>
                <p className="mt-6 border-t border-black/[0.08] pt-4 text-xs leading-relaxed text-[#1D1D1F]/55 dark:border-white/[0.08] dark:text-[#F5F5F7]/55">
                  {STACK_PREVIEW.join(' · ')}
                </p>
              </div>
            </Reveal>

            {/* Card 3: Bulk CSV Enrichment */}
            <Reveal className="min-w-0 md:col-span-2">
              <div className="hairline-card flex h-full flex-col justify-between p-7 sm:p-8">
                <div>
                  <p className="text-xs font-medium tracking-wide text-brand-600 dark:text-brand-400">
                    High Throughput
                  </p>
                  <h3 className="mt-2 text-2xl font-semibold tracking-tight">
                    Bulk CSV Enrichment
                  </h3>
                  <p className="mt-3 text-[15px] leading-relaxed text-[#1D1D1F]/65 dark:text-[#F5F5F7]/65">
                    Upload up to 10,000 domains in a single CSV, process concurrently via Redis workers, and receive HMAC-signed completion callbacks.
                  </p>
                </div>
                <p className="mt-6 border-t border-black/[0.08] pt-4 font-mono text-xs tabular-nums text-[#1D1D1F]/55 dark:border-white/[0.08] dark:text-[#F5F5F7]/55">
                  GET /api/v1/enrich/bulk/&#123;id&#125;/download
                </p>
              </div>
            </Reveal>

            {/* Card 4: SMTP Email Verification */}
            <Reveal delay={80} className="min-w-0 md:col-span-4">
              <div className="hairline-card flex h-full flex-col justify-between p-7 sm:p-9">
                <div>
                  <p className="text-xs font-medium tracking-wide text-brand-600 dark:text-brand-400">
                    Non-Intrusive Checks
                  </p>
                  <h3 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
                    SMTP Email Verification
                  </h3>
                  <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-[#1D1D1F]/65 dark:text-[#F5F5F7]/65">
                    Validate syntax, resolve MX providers, detect catch-all servers, and probe mailbox deliverability with fast 3-second timeouts—without ever sending an email. Blocked port-25 probes automatically refund credits.
                  </p>
                </div>
                <div className="mt-7 flex flex-wrap gap-x-6 gap-y-2 border-t border-black/[0.08] pt-5 text-xs text-[#1D1D1F]/60 dark:border-white/[0.08] dark:text-[#F5F5F7]/60">
                  <span>Syntax &amp; MX provider detection</span>
                  <span>·</span>
                  <span>Catch-all awareness</span>
                  <span>·</span>
                  <span>Automatic credit refund on network block</span>
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* API SHOWCASE */}
      <section id="api" className="border-y border-black/[0.08] bg-[#141416] px-5 py-24 text-[#F5F5F7] dark:border-white/[0.08]">
        <div className="mx-auto grid max-w-[1120px] items-center gap-12 lg:grid-cols-2">
          <Reveal className="min-w-0">
            <p className="text-xs font-medium tracking-wide text-indigo-400">
              Developer First
            </p>
            <h2 className="mt-2 text-balance text-3xl font-semibold leading-[1.08] tracking-[-0.03em] sm:text-5xl">
              One call. <span className="grad-light">The whole picture.</span>
            </h2>
            <p className="mt-5 max-w-md text-base leading-relaxed text-white/65 sm:text-lg">
              Clean REST endpoints, scoped API keys, free sandbox keys for testing, and 24-hour result caching so repeat lookups cost zero credits.
            </p>
            <a
              href="/docs"
              className="mt-7 inline-block text-[15px] font-medium text-indigo-300 transition hover:underline"
            >
              Read the interactive API docs ›
            </a>
          </Reveal>

          <Reveal delay={100} className="min-w-0 w-full">
            <div className="w-full max-w-full overflow-hidden rounded-2xl border border-white/[0.1] bg-[#0B0B0C] shadow-2xl">
              <div className="flex items-center gap-2 border-b border-white/[0.08] px-4 py-3">
                <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
                <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
                <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
                <span className="ml-2 font-mono text-xs text-white/45">enrich.sh</span>
              </div>
              <pre className="w-full overflow-x-auto p-5 font-mono text-[12.5px] leading-6">
                {CODE.map((l, i) => (
                  <div key={i} className={l.c}>
                    {l.t || '\u00A0'}
                  </div>
                ))}
              </pre>
            </div>
          </Reveal>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="px-5 py-24">
        <div className="mx-auto max-w-[980px]">
          <Reveal>
            <h2 className="mb-14 text-center text-balance text-3xl font-semibold tracking-[-0.03em] sm:text-5xl">
              Up and running in minutes.
            </h2>
          </Reveal>
          <div className="grid gap-10 md:grid-cols-3">
            {[
              ['01', 'Create an account', 'Start immediately with 50 free trial credits and no credit card required.'],
              ['02', 'Configure Autopilot or API keys', 'Launch an ICP discovery campaign in the dashboard or issue scoped live keys.'],
              ['03', 'Enrich and deliver', 'Receive verified companies, tech stacks, and contacts via REST, CSV, or CRM sync.'],
            ].map(([num, title, desc], i) => (
              <Reveal key={num} delay={i * 80}>
                <div className="border-t border-black/[0.08] pt-6 dark:border-white/[0.08]">
                  <span className="font-mono text-xs font-semibold tracking-widest tabular-nums text-brand-600 dark:text-brand-400">
                    {num}
                  </span>
                  <h3 className="mt-3 text-lg font-semibold tracking-tight">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-[#1D1D1F]/65 dark:text-[#F5F5F7]/65">
                    {desc}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* PRICING */}
      <section id="pricing" className="border-t border-black/[0.08] px-5 py-24 dark:border-white/[0.08]">
        <div className="mx-auto max-w-[1060px]">
          <Reveal>
            <div className="mb-14 text-center">
              <h2 className="text-balance text-3xl font-semibold tracking-[-0.03em] sm:text-5xl">
                Pay for verified intelligence.
              </h2>
              <p className="mt-3 text-base text-[#1D1D1F]/60 dark:text-[#F5F5F7]/60 sm:text-lg">
                Cached domain lookups are always free. Begin with 50 Starter Free trial credits.
              </p>
            </div>
          </Reveal>
          <div className="grid gap-5 md:grid-cols-3">
            {PLANS.map((p, i) => (
              <Reveal key={p.name} delay={i * 80}>
                <div
                  className={`hairline-card flex h-full flex-col justify-between p-8 ${
                    p.featured
                      ? 'ring-2 ring-brand-600/80 dark:ring-brand-400/80'
                      : ''
                  }`}
                >
                  <div>
                    <div className="flex items-baseline justify-between gap-2">
                      <h3 className="text-lg font-semibold">{p.name}</h3>
                      {p.featured && (
                        <span className="text-xs font-semibold text-brand-600 dark:text-brand-400">
                          Recommended
                        </span>
                      )}
                    </div>
                    <p className="mt-4 text-4xl font-semibold tracking-tight tabular-nums">{p.price}</p>
                    <p className="mt-1 text-sm font-medium text-brand-600 dark:text-brand-400">
                      {p.credits}
                    </p>
                    <p className="mt-4 text-sm leading-relaxed text-[#1D1D1F]/65 dark:text-[#F5F5F7]/65">
                      {p.note}
                    </p>
                    <p className="mt-3 text-xs text-[#1D1D1F]/50 dark:text-[#F5F5F7]/50">
                      {p.limit}
                    </p>
                  </div>
                  <Link
                    href="/login"
                    className={`mt-8 block rounded-full px-5 py-2.5 text-center text-sm font-medium transition ${
                      p.featured
                        ? 'bg-brand-600 text-white hover:bg-brand-700'
                        : 'bg-[#1D1D1F] text-white hover:bg-black dark:bg-[#F5F5F7] dark:text-[#0B0B0C] dark:hover:bg-white'
                    }`}
                  >
                    {p.cta}
                  </Link>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <FaqAccordion />

      {/* FINAL CTA */}
      <section className="px-5 py-24 text-center">
        <Reveal>
          <h2 className="mx-auto max-w-[680px] text-balance text-4xl font-semibold tracking-[-0.035em] sm:text-6xl">
            Start knowing <span className="grad">more.</span>
          </h2>
          <p className="mx-auto mt-4 max-w-md text-base text-[#1D1D1F]/60 dark:text-[#F5F5F7]/60">
            Create an account in seconds and run your first Lead Autopilot campaign or domain lookup.
          </p>
          <Link
            href="/login"
            className="mt-8 inline-block rounded-full bg-[#1D1D1F] px-8 py-3.5 text-[15px] font-medium text-white transition hover:bg-black dark:bg-[#F5F5F7] dark:text-[#0B0B0C] dark:hover:bg-white"
          >
            Create free account
          </Link>
        </Reveal>
      </section>

      <LandingFooter />
    </main>
  );
}
