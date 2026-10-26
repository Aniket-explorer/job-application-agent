import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';

afterEach(() => vi.unstubAllGlobals());

describe('api client', () => {
  it('returns parsed JSON for successful responses', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([{ id: '1' }]), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(api<{ id: string }[]>('/api/jobs')).resolves.toEqual([{ id: '1' }]);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/jobs',
      expect.objectContaining({ headers: expect.objectContaining({ 'Content-Type': 'application/json' }) }),
    );
  });

  it('throws with status and body for error responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Live mode is not implemented', { status: 400 })));

    await expect(api('/api/settings', { method: 'PUT' })).rejects.toThrow('400: Live mode is not implemented');
  });
});
