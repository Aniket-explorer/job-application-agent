const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function errorMessage(response: Response): Promise<string> {
  const text = await response.text();
  try {
    const body = JSON.parse(text) as { message?: string; detail?: unknown };
    if (typeof body.message === 'string' && body.message) return `${response.status}: ${body.message}`;
    if (typeof body.detail === 'string' && body.detail) return `${response.status}: ${body.detail}`;
  } catch {
    // Plain-text errors from the legacy routes stay readable.
  }
  return `${response.status}: ${text}`;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json() as Promise<T>;
}

export type Job = {
  id: string;
  source: string;
  company: string;
  title: string;
  location?: string;
  canonical_url: string;
  match_score?: number;
  status: string;
  created_at: string;
};
export type Application = {
  id: string;
  job_id: string;
  channel: string;
  status: string;
  match_score: number;
  dry_run: boolean;
  created_at: string;
  error?: string;
};
export type Connector = {
  source: string;
  enabled: boolean;
  configured: boolean;
  discovery_supported: boolean;
  application_supported: boolean;
  status: string;
  note: string;
};
export type AutomationSettings = {
  dry_run: boolean;
  minimum_match_score: number;
  search_interval_minutes: number;
  followup_enabled: boolean;
  global_pause: boolean;
  automation_enabled: boolean;
};
export type Page<T> = { items: T[]; total: number; page: number; page_size: number };

export async function loadWorkspace() {
  const [jobsPage, applicationsPage, connectors, settings] = await Promise.all([
    api<Page<Job>>('/api/v1/jobs?page_size=100'),
    api<Page<Application>>('/api/v1/applications?page_size=100'),
    api<Connector[]>('/api/v1/sources'),
    api<AutomationSettings>('/api/v1/automation/settings'),
  ]);
  return { jobs: jobsPage.items, applications: applicationsPage.items, connectors, settings };
}
