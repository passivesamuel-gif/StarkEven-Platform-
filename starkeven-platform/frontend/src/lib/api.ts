export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : 'Something went wrong';
}

const TOKEN_KEY = 'starkeven_token';
export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}
export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

async function raise(res: Response): Promise<never> {
  let code = 'error';
  let message = `Request failed (${res.status})`;
  try {
    const body = await res.json();
    if (body && body.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
    }
  } catch {
    /* non-JSON error body */
  }
  throw new ApiError(res.status, code, message);
}

async function request<T>(path: string, init: RequestInit = {}, auth = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (auth) {
    const token = getToken();
    if (token) headers.set('Authorization', `Bearer ${token}`);
  }
  if (typeof init.body === 'string' && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const res = await fetch(path, { ...init, headers });
  if (!res.ok) return raise(res);
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) });

// ---- types
export type Company = {
  name: string | null; title: string | null; description: string | null; website: string | null;
  linkedin: string | null; twitter: string | null; github: string | null;
};
export type Tech = { name: string; category: string };
export type EnrichData = {
  domain: string;
  company: Company;
  tech_stack: Tech[];
  email: { provider: string | null; mx_hosts?: string[]; spf?: boolean };
  hiring: { has_careers_page: boolean; careers_url?: string | null; ats?: string[] };
  enriched_at?: string;
};
export type EnrichResponse = { cached: boolean; credits_used?: number; sandbox?: boolean; data: EnrichData };
export type Me = {
  id: number; name: string; plan_tier: string; credit_balance: number; rate_limit_per_min: number;
  email?: string; role?: string; callback_signing_secret?: string;
  notify_low_credits?: boolean; notify_campaign_reports?: boolean;
};
export type NotificationSettings = {
  notify_low_credits: boolean;
  notify_campaign_reports: boolean;
  recipient_email?: string | null;
};
export type ApiKeyRow = {
  id: number; name: string; key_prefix: string; scopes: string[]; is_active: boolean;
  expires_at: string | null; last_used_at: string | null; created_at: string;
};
export type NewKey = { api_key: string; id: number; key_prefix: string; scopes: string[] };
export type BulkStatus = {
  batch_id: string; status: 'queued' | 'processing' | 'completed' | 'failed';
  total_domains: number; processed_domains: number; progress: number; credits_used: number; error: string | null;
};
export type VerifyResult = {
  email: string; format_valid: boolean; mx_valid: boolean;
  smtp_deliverable: 'valid' | 'invalid' | 'catch_all' | 'unknown' | 'unverifiable_network'; provider: string | null; reason?: string;
};
export type UsageRow = {
  id: number; endpoint: string; status_code: number; credits_used: number; latency_ms: number; created_at: string;
};
export type DailyUsagePoint = { date: string; credits_used: number; requests: number };
export type DailyUsageResponse = {
  days: number; total_credits: number; total_requests: number; daily: DailyUsagePoint[];
};
export type CrmProvider = 'none' | 'hubspot' | 'salesforce' | 'webhook';
export type AutopilotCampaign = {
  id: string;
  org_id: number;
  name: string;
  status: 'active' | 'paused';
  target_keywords: string[];
  required_tech_stack: string[];
  require_hiring: boolean;
  daily_lead_quota: number;
  target_crm_provider: CrmProvider;
  target_crm_url_or_token: string | null;
  total_leads_delivered: number;
  last_run_at: string | null;
  created_at: string;
};
export type AutopilotCampaignCreate = {
  name: string;
  status?: 'active' | 'paused';
  target_keywords: string[];
  required_tech_stack: string[];
  require_hiring: boolean;
  daily_lead_quota: number;
  target_crm_provider: CrmProvider;
  target_crm_url_or_token?: string | null;
};
export type AutopilotCampaignPatch = Partial<AutopilotCampaignCreate>;
export type DeliveredLead = {
  id: string;
  campaign_id: string;
  org_id: number;
  domain: string;
  company_name: string | null;
  tech_stack: string[];
  email_provider: string | null;
  verified_emails: string[];
  hiring_ats: string[];
  delivered_at: string;
};
export type AutopilotLeadsPage = {
  total: number;
  limit: number;
  offset: number;
  items: DeliveredLead[];
};

// ---- calls
export async function loginAccount(email: string, password: string) {
  return request<{ access_token: string; organization_id: number }>(
    '/api/v1/auth/login',
    json({ email, password }),
    false,
  );
}
export async function registerAccount(email: string, password: string, org: string) {
  return request<{
    status: string;
    message: string;
    organization_id: number;
    credits: number;
    is_verified: boolean;
    expires_in: number;
  }>('/api/v1/auth/register', json({ email, password, organization_name: org || 'My Organization' }), false);
}
export async function confirmSignup(email: string, code: string) {
  return request<{
    access_token: string;
    token_type: string;
    organization_id: number;
    credits: number;
    is_verified: boolean;
  }>('/api/v1/auth/confirm-signup', json({ email, code }), false);
}
export async function resendSignupOtp(email: string) {
  return request<{ status: string; message: string }>('/api/v1/auth/resend-signup-otp', json({ email }), false);
}
export async function forgotPassword(email: string) {
  return request<{ status: string; message: string }>('/api/v1/auth/forgot-password', json({ email }), false);
}
export async function resetPassword(email: string, code: string, newPassword: string) {
  return request<{ access_token: string; token_type: string; organization_id: number }>(
    '/api/v1/auth/reset-password',
    json({ email, code, new_password: newPassword }),
    false,
  );
}
export const getMe = () => request<Me>('/api/v1/orgs/me');
export const getNotificationSettings = () => request<NotificationSettings>('/api/v1/orgs/me/notifications');
export const updateNotificationSettings = (payload: Partial<Pick<NotificationSettings, 'notify_low_credits' | 'notify_campaign_reports'>>) =>
  request<NotificationSettings>('/api/v1/orgs/me/notifications', { method: 'PATCH', body: JSON.stringify(payload) });
export const getUsage = () => request<UsageRow[]>('/api/v1/orgs/me/usage?limit=50');
export const getDailyUsage = (days = 30) => request<DailyUsageResponse>(`/api/v1/orgs/me/usage/daily?days=${days}`);
export const enrichDomain = (domain: string, force = false) =>
  request<EnrichResponse>('/api/v1/enrich/domain', json({ domain, force_refresh: force }));
export const demoLookup = (domain: string) => request<EnrichResponse>('/api/v1/demo/lookup', json({ domain }), false);
export const verifyEmail = (email: string) => request<VerifyResult>('/api/v1/verify/email', json({ email }));
export const listKeys = () => request<ApiKeyRow[]>('/api/v1/keys');
export const createKey = (name: string, environment: 'live' | 'test', expiresInDays?: number) =>
  request<NewKey>('/api/v1/keys', json({ name, environment, ...(expiresInDays ? { expires_in_days: expiresInDays } : {}) }));
export const rotateKey = (id: number) => request<NewKey>(`/api/v1/keys/${id}/rotate`, { method: 'POST' });
export const revokeKey = (id: number) => request<{ revoked: boolean }>(`/api/v1/keys/${id}`, { method: 'DELETE' });
export const bulkStatus = (id: string) => request<BulkStatus>(`/api/v1/enrich/bulk/${id}`);
export const startBulkCsv = (file: File, webhookUrl: string) => {
  const form = new FormData();
  form.append('file', file);
  if (webhookUrl.trim()) form.append('webhook_url', webhookUrl.trim());
  return request<{ batch_id: string; total_domains: number }>('/api/v1/enrich/bulk', { method: 'POST', body: form });
};
export async function downloadBulk(id: string): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`/api/v1/enrich/bulk/${id}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) return raise(res);
  return res.blob();
}

export const listAutopilotCampaigns = () => request<AutopilotCampaign[]>('/api/v1/autopilot/campaigns');
export const createAutopilotCampaign = (payload: AutopilotCampaignCreate) =>
  request<AutopilotCampaign>('/api/v1/autopilot/campaigns', json(payload));
export const updateAutopilotCampaign = (id: string, payload: AutopilotCampaignPatch) =>
  request<AutopilotCampaign>(`/api/v1/autopilot/campaigns/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
export const deleteAutopilotCampaign = (id: string) =>
  request<{ deleted: boolean; id: string }>(`/api/v1/autopilot/campaigns/${id}`, { method: 'DELETE' });
export const runAutopilotCampaignNow = (id: string) =>
  request<{ campaign_id: string; status: string }>(`/api/v1/autopilot/campaigns/${id}/run-now`, { method: 'POST' });
export const listAutopilotLeads = (id: string, limit = 50, offset = 0) =>
  request<AutopilotLeadsPage>(`/api/v1/autopilot/campaigns/${id}/leads?limit=${limit}&offset=${offset}`);
export async function downloadAutopilotLeadsCsv(id: string): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`/api/v1/autopilot/campaigns/${id}/leads?format=csv`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) return raise(res);
  return res.blob();
}
