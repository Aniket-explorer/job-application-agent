import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, errorMessage, loadWorkspace } from './api';

afterEach(() => vi.unstubAllGlobals());

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('api client', () => {
  it('returns parsed JSON for successful responses', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ id: '1' }]));
    vi.stubGlobal('fetch', fetchMock);

    await expect(api<{ id: string }[]>('/api/v1/sources')).resolves.toEqual([{ id: '1' }]);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/sources',
      expect.objectContaining({ headers: expect.objectContaining({ 'Content-Type': 'application/json' }) }),
    );
  });

  it('uses the error envelope message', async () => {
    const response = jsonResponse({ code: 'policy_violation', message: 'Live mode is not implemented' }, 422);
    await expect(errorMessage(response)).resolves.toBe('422: Live mode is not implemented');
  });

  it('uses a legacy detail string when the body is not an envelope', async () => {
    const response = jsonResponse({ detail: 'Job not found' }, 404);
    await expect(errorMessage(response)).resolves.toBe('404: Job not found');
  });

  it('keeps plain-text error bodies', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('bad gateway', { status: 502 })));
    await expect(api('/api/v1/jobs')).rejects.toThrow('502: bad gateway');
  });
});

describe('loadWorkspace', () => {
  it('reads jobs and applications from the versioned page envelope', async () => {
    const settings = {
      dry_run: true,
      minimum_match_score: 50,
      search_interval_minutes: 60,
      followup_enabled: true,
      global_pause: true,
      automation_enabled: false,
    };
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.endsWith('/api/v1/jobs?page_size=100')) return jsonResponse({ items: [{ id: 'job-1' }], total: 1, page: 1, page_size: 100 });
        if (url.endsWith('/api/v1/applications?page_size=100')) return jsonResponse({ items: [{ id: 'app-1' }], total: 1, page: 1, page_size: 100 });
        if (url.endsWith('/api/v1/sources')) return jsonResponse([{ source: 'gmail', configured: false }]);
        if (url.endsWith('/api/v1/automation/settings')) return jsonResponse(settings);
        return jsonResponse({ message: 'missing' }, 404);
      }),
    );

    await expect(loadWorkspace()).resolves.toEqual({
      jobs: [{ id: 'job-1' }],
      applications: [{ id: 'app-1' }],
      connectors: [{ source: 'gmail', configured: false }],
      settings,
    });
  });
});
