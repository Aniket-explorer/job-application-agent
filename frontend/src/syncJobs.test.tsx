import { act, useState, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Connector, Job, SyncSummary } from './api';
import { JobFeed } from './JobsPage';
import { SyncJobs } from './CareerPageSync';
import { syncFailureMessage } from './syncJobs';

const disabled: Connector = {
  source: 'career_page',
  enabled: false,
  configured: false,
  discovery_supported: false,
  application_supported: false,
  status: 'not_configured',
  note: 'Greenhouse Job Board list API is implemented and disabled. No application endpoint is called.',
};

const ready: Connector = {
  ...disabled,
  enabled: true,
  configured: true,
  discovery_supported: true,
  status: 'configured',
  note: 'Greenhouse job-list sync is configured. Application submission is not implemented.',
};

const summary: SyncSummary = {
  status: 'completed',
  boards_checked: 2,
  jobs_fetched: 3,
  jobs_created: 1,
  jobs_updated: 1,
  duplicates_skipped: 1,
  jobs_skipped: 0,
  matches_written: 2,
  errors: [{ code: 'rate_limited' }, { code: 'boards-api.greenhouse.io/secret-token' }],
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('sync failure messages', () => {
  it('hides unexpected error bodies', () => {
    expect(syncFailureMessage(new TypeError('Failed to fetch'))).toContain('did not reach the API');
    expect(syncFailureMessage(new Error('409: lock token abc'))).toBe('A sync is already running. Wait for it to finish before trying again.');
    expect(syncFailureMessage(new Error('422: Greenhouse discovery is disabled. No external request was made.'))).toContain('disabled');
    expect(syncFailureMessage(new Error('500: Traceback token=secret'))).toBe('Sync could not be completed. The API returned an unexpected error.');
  });
});

describe('Sync jobs control', () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    act(() => root?.unmount());
    container?.remove();
    root = null;
    container = null;
    vi.unstubAllGlobals();
  });

  async function render(node: ReactNode) {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(node);
    });
    return container;
  }

  function buttonNamed(view: HTMLElement, name: string) {
    return [...view.querySelectorAll('button')].find((item) => item.textContent === name) as HTMLButtonElement;
  }

  it('explains a disabled connector and does not call the API', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const view = await render(<SyncJobs connector={disabled} busy={false} onSynced={vi.fn()} />);
    expect(view.textContent).toContain('Greenhouse discovery is disabled');
    expect(buttonNamed(view, 'Sync jobs').disabled).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('explains missing boards without enabling the connector', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const view = await render(
      <SyncJobs connector={{ ...disabled, enabled: true }} busy={false} onSynced={vi.fn()} />,
    );
    expect(view.textContent).toContain('No Greenhouse boards are configured');
    expect(view.textContent).toContain('cannot add them');
    expect(buttonNamed(view, 'Sync jobs').disabled).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('asks for confirmation and disables the control while the request is in progress', async () => {
    let release: (response: Response) => void = () => undefined;
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const view = await render(<SyncJobs connector={ready} busy={false} onSynced={vi.fn(async () => undefined)} />);
    expect(fetchMock).not.toHaveBeenCalled();
    await act(async () => {
      buttonNamed(view, 'Sync jobs').click();
    });
    expect(view.textContent).toContain('Start a manual sync?');
    expect(fetchMock).not.toHaveBeenCalled();
    await act(async () => {
      buttonNamed(view, 'Start sync').click();
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/sources/career_page/sync',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(buttonNamed(view, 'Syncing…').disabled).toBe(true);
    expect(buttonNamed(view, 'Cancel').disabled).toBe(true);
    await act(async () => {
      release(jsonResponse(summary));
    });
  });

  it('shows the safe summary after a successful sync', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(summary)));
    const view = await render(<SyncJobs connector={ready} busy={false} onSynced={vi.fn(async () => undefined)} />);
    await act(async () => {
      buttonNamed(view, 'Sync jobs').click();
    });
    await act(async () => {
      buttonNamed(view, 'Start sync').click();
    });
    const shown = view.querySelector('[data-sync-summary]')?.textContent || '';
    expect(shown).toContain('Boards checked2');
    expect(shown).toContain('Jobs fetched3');
    expect(shown).toContain('Jobs created1');
    expect(shown).toContain('Jobs updated1');
    expect(shown).toContain('Duplicates skipped1');
    expect(shown).toContain('Jobs skipped0');
    expect(shown).toContain('Match assessments written2');
    expect(shown).toContain('rate_limited');
    expect(shown).not.toContain('secret-token');
    expect(shown).toContain('unrecognized_error');
  });

  it('shows a 409 message and does not refresh jobs', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ code: 'sync_in_progress', message: 'A career page sync is already running.' }, 409)),
    );
    const onSynced = vi.fn(async () => undefined);
    const view = await render(<SyncJobs connector={ready} busy={false} onSynced={onSynced} />);
    await act(async () => {
      buttonNamed(view, 'Sync jobs').click();
    });
    await act(async () => {
      buttonNamed(view, 'Start sync').click();
    });
    expect(view.querySelector('[data-sync-error]')?.textContent).toContain('already running');
    expect(onSynced).not.toHaveBeenCalled();
  });

  it('shows a 422 configuration message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ code: 'no_boards', message: 'No Greenhouse boards are configured. No external request was made.' }, 422)),
    );
    const view = await render(<SyncJobs connector={ready} busy={false} onSynced={vi.fn()} />);
    await act(async () => {
      buttonNamed(view, 'Sync jobs').click();
    });
    await act(async () => {
      buttonNamed(view, 'Start sync').click();
    });
    expect(view.querySelector('[data-sync-error]')?.textContent).toContain('No Greenhouse boards are configured');
    expect(view.textContent).not.toContain('Traceback');
  });

  it('shows a network failure without a stack trace', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))));
    const view = await render(<SyncJobs connector={ready} busy={false} onSynced={vi.fn()} />);
    await act(async () => {
      buttonNamed(view, 'Sync jobs').click();
    });
    await act(async () => {
      buttonNamed(view, 'Start sync').click();
    });
    const message = view.querySelector('[data-sync-error]')?.textContent || '';
    expect(message).toContain('did not reach the API');
    expect(message).not.toContain('Failed to fetch');
  });

  it('refreshes discovered and manual jobs after a successful sync', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ ...summary, errors: [] })));
    const view = await render(<RefreshHarness />);
    expect(view.querySelector('[data-section="discovered"]')?.textContent).toContain('No discovered jobs yet');
    expect(view.querySelector('[data-section="manual"]')?.textContent).toContain('Manual test record');
    expect(view.textContent).toContain('Import score, not an explainable match');
    await act(async () => {
      buttonNamed(view, 'Sync jobs').click();
    });
    await act(async () => {
      buttonNamed(view, 'Start sync').click();
    });
    const discovered = view.querySelector('[data-section="discovered"]')?.textContent || '';
    const manual = view.querySelector('[data-section="manual"]')?.textContent || '';
    expect(discovered).toContain('Discovered listing');
    expect(discovered).toContain('Platform Engineer');
    expect(discovered).toContain('81.2%');
    expect(discovered).not.toContain('71.5%');
    expect(manual).toContain('Manual test record');
    expect(manual).toContain('Backend Engineer');
    expect(manual).toContain('Import score, not an explainable match');
    expect(view.textContent).toContain('minimum match score: 50%');
  });
});

function manualJob(): Job {
  return {
    id: 'manual-1',
    source: 'manual',
    origin: 'manual',
    company: 'Example Co',
    title: 'Backend Engineer',
    location: 'Remote',
    match_score: 71.5,
    status: 'active',
    created_at: '2026-10-26T00:00:00Z',
  };
}

function RefreshHarness() {
  const [jobs, setJobs] = useState<Job[]>([manualJob()]);
  return (
    <>
      <SyncJobs
        connector={ready}
        busy={false}
        onSynced={async () => {
          setJobs([
            manualJob(),
            {
              id: 'discovered-1',
              source: 'career_page',
              origin: 'discovered',
              company: 'Fixture Co',
              title: 'Platform Engineer',
              location: 'Remote',
              match_score: 71.5,
              status: 'active',
              created_at: '2026-10-26T00:00:00Z',
              assessment: {
                total_score: 81.2,
                threshold: 50,
                meets_threshold: true,
                match_status: 'scored',
                factors: [],
                matched_skills: [],
                missing_skills: [],
                warnings: [],
                weight_used: 80,
                weight_excluded: 20,
              },
            },
          ]);
        }}
      />
      <JobFeed jobs={jobs} threshold={50} busy={false} profileStatus={null} onDryRun={() => undefined} onRecalculate={() => undefined} />
    </>
  );
}
