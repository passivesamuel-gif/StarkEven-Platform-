import type { EnrichData } from '@/lib/api';

function SocialPill({ href, label }: { href: string | null | undefined; label: string }) {
  if (!href) return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="rounded-full border border-black/[0.08] bg-[#F5F5F7] px-3 py-1 text-xs font-medium text-[#0071E3] transition hover:bg-black/[0.05] dark:border-white/[0.08] dark:bg-[#2C2C2E] dark:text-[#0A84FF] dark:hover:bg-white/[0.08]"
    >
      {label}
    </a>
  );
}

export default function EnrichResult({ data, cached }: { data: EnrichData; cached?: boolean }) {
  const c = data.company;
  return (
    <div className="space-y-5 rounded-2xl border border-black/[0.06] bg-white p-6 text-left shadow-[0_1px_3px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-lg font-semibold tracking-[-0.02em] text-[#1D1D1F] dark:text-[#F5F5F7]">
            {c.name ?? data.domain}
          </h3>
          <p className="font-mono text-xs text-[#6E6E73] dark:text-[#8E8E93]">{data.domain}</p>
        </div>
        {cached !== undefined && (
          <span className="rounded-full bg-[#F5F5F7] px-3 py-1 text-xs font-medium text-[#6E6E73] dark:bg-[#2C2C2E] dark:text-[#8E8E93]">
            {cached ? 'Cached (free)' : 'Live lookup'}
          </span>
        )}
      </div>

      {c.description && (
        <p className="text-sm leading-relaxed text-[#1D1D1F]/80 dark:text-[#F5F5F7]/80">
          {c.description}
        </p>
      )}

      {(c.linkedin || c.twitter || c.github) && (
        <div className="flex flex-wrap gap-2">
          <SocialPill href={c.linkedin} label="LinkedIn" />
          <SocialPill href={c.twitter} label="X / Twitter" />
          <SocialPill href={c.github} label="GitHub" />
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl bg-[#F5F5F7] p-4 dark:bg-[#2C2C2E]">
          <h4 className="mb-1 text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
            Email infrastructure
          </h4>
          <p className="text-sm font-medium text-[#1D1D1F] dark:text-[#F5F5F7]">
            {data.email.provider ?? 'No mail servers found'}
          </p>
          {data.email.spf !== undefined && (
            <p className="mt-0.5 text-xs text-[#6E6E73] dark:text-[#8E8E93]">
              SPF {data.email.spf ? 'configured' : 'not found'}
            </p>
          )}
        </div>

        <div className="rounded-2xl bg-[#F5F5F7] p-4 dark:bg-[#2C2C2E]">
          <h4 className="mb-1 text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
            Hiring signals
          </h4>
          <p className="text-sm font-medium text-[#1D1D1F] dark:text-[#F5F5F7]">
            {data.hiring.has_careers_page ? 'Careers page detected' : 'No careers page found'}
          </p>
          {data.hiring.ats && data.hiring.ats.length > 0 && (
            <p className="mt-0.5 text-xs text-[#6E6E73] dark:text-[#8E8E93]">
              ATS: {data.hiring.ats.join(', ')}
            </p>
          )}
        </div>
      </div>

      <div>
        <h4 className="mb-2.5 text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
          Tech stack ({data.tech_stack.length})
        </h4>
        {data.tech_stack.length === 0 ? (
          <p className="text-sm text-[#6E6E73] dark:text-[#8E8E93]">No technologies detected.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {data.tech_stack.map((t) => (
              <span
                key={t.name}
                title={t.category}
                className="rounded-full border border-black/[0.06] bg-[#F5F5F7] px-3 py-1 text-xs font-medium text-[#1D1D1F] dark:border-white/[0.08] dark:bg-[#2C2C2E] dark:text-[#F5F5F7]"
              >
                {t.name}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
