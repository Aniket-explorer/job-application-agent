const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) } });
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return response.json() as Promise<T>;
}
export type Job = { id: string; source: string; company: string; title: string; location?: string; canonical_url: string; match_score?: number; status: string; created_at: string };
export type Application = { id: string; job_id: string; channel: string; status: string; match_score: number; dry_run: boolean; created_at: string; error?: string };
export type Connector = { source: string; enabled: boolean; configured: boolean; discovery_supported: boolean; application_supported: boolean; status: string; note: string };
