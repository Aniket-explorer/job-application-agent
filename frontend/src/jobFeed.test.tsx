import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Job, MatchAssessment, ProfileStatus } from './api';
import { JobFeed } from './JobsPage';
import { arrangeJobs, explainableScore, isManualRecord, meetsMinimum } from './jobFeed';

const assessment = (total: number | null, overrides: Partial<MatchAssessment> = {}): MatchAssessment => ({
  total_score: total,
  threshold: 50,
  meets_threshold: total !== null && total >= 50,
  match_status: total === null ? 'insufficient_information' : 'scored',
  factors: [
    { key: 'technical_skills', weight: 30, status: 'matched', score: 100, findings: ['python matched'] },
    { key: 'role', weight: 25, status: 'matched', score: 100, findings: ['title overlaps Backend Engineer'] },
    { key: 'experience', weight: 20, status: 'unknown', score: null, findings: ['years were not stated'] },
    { key: 'domain', weight: 15, status: 'mismatch', score: 0, findings: ['payments was not found'] },
    { key: 'location', weight: 10, status: 'matched', score: 100, findings: ['remote matches the preference'] },
  ],
  matched_skills: ['python'],
  missing_skills: ['kubernetes'],
  warnings: ['unknown:experience'],
  weight_used: 80,
  weight_excluded: 20,
  ...overrides,
});

function job(overrides: Partial<Job>): Job {
  return {
    id: 'job-1',
    source: 'manual',
    origin: 'manual',
    company: 'Example Co',
    title: 'Backend Engineer',
    location: 'Remote',
    canonical_url: 'https://jobs.example.com/1',
    match_score: 71.5,
    status: 'active',
    created_at: '2026-10-26T00:00:00Z',
    ...overrides,
  };
}

describe('job arrangement', () => {
  const jobs = [
    job({ id: 'low', title: 'Low role', match_score: 40, assessment: assessment(40) }),
    job({ id: 'high', title: 'High role', match_score: 10, assessment: assessment(80) }),
    job({ id: 'unknown', title: 'Unknown role', match_score: 90, assessment: assessment(null) }),
  ];

  it('sorts by the explainable score and drops unknown or below-threshold jobs', () => {
    expect(arrangeJobs(jobs, 50, true).map((item) => item.id)).toEqual(['high']);
    expect(arrangeJobs(jobs, 50, false).map((item) => item.id)).toEqual(['high', 'low', 'unknown']);
  });

  it('does not treat an import score or a null score as an explainable match', () => {
    const imported = job({ assessment: undefined, match_score: 71.5 });
    expect(explainableScore(imported)).toBeNull();
    expect(meetsMinimum(imported, 50)).toBe(false);
    expect(meetsMinimum(job({ assessment: assessment(50) }), 50)).toBe(true);
    expect(meetsMinimum(job({ assessment: assessment(49.9) }), 50)).toBe(false);
    expect(meetsMinimum(job({ assessment: assessment(null), match_score: 90 }), 50)).toBe(false);
  });

  it('treats a missing origin on a manual source as a test record', () => {
    expect(isManualRecord(job({ origin: undefined, source: 'manual' }))).toBe(true);
    expect(isManualRecord(job({ origin: 'discovered', source: 'career_page' }))).toBe(false);
  });

  it('repeats the same order for the same input', () => {
    const once = arrangeJobs(jobs, 50, false).map((item) => item.id);
    const twice = arrangeJobs(jobs, 50, false).map((item) => item.id);
    expect(twice).toEqual(once);
  });
});

describe('JobFeed display', () => {
  let root: Root | null = null;
  let container: HTMLDivElement | null = null;

  afterEach(() => {
    act(() => root?.unmount());
    container?.remove();
    root = null;
    container = null;
  });

  async function render(jobs: Job[], threshold = 50, profileStatus: ProfileStatus | null = null) {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(
        <JobFeed jobs={jobs} threshold={threshold} busy={false} profileStatus={profileStatus} onDryRun={vi.fn()} onRecalculate={vi.fn()} />,
      );
    });
    return container;
  }

  it('keeps manual records out of the discovered list and explains the empty source', async () => {
    const view = await render([job({ id: 'smoke', title: 'Backend Engineer' })]);
    const discovered = view.querySelector('[data-section="discovered"]');
    const manual = view.querySelector('[data-section="manual"]');
    expect(discovered?.textContent).toContain('No discovered jobs yet');
    expect(discovered?.textContent).toContain('are not discovered listings');
    expect(discovered?.textContent).not.toContain('Backend Engineer');
    expect(manual?.textContent).toContain('Manual test record');
    expect(manual?.textContent).toContain('Backend Engineer');
    expect(manual?.textContent).toContain('71.5%');
    expect(manual?.textContent).toContain('Import score');
  });

  it('shows the category breakdown and leaves an unknown factor unscored', async () => {
    const view = await render([
      job({
        id: 'scored',
        title: 'Platform Engineer',
        origin: 'discovered',
        source: 'career_page',
        assessment: assessment(82.5),
      }),
    ]);
    const discovered = view.querySelector('[data-section="discovered"]');
    expect(discovered?.textContent).toContain('Discovered listing');
    expect(discovered?.textContent).toContain('82.5%');
    expect(discovered?.textContent).toContain('Technical skills');
    expect(discovered?.textContent).toContain('30% weight');
    expect(discovered?.textContent).toContain('python matched');
    expect(discovered?.textContent).toContain('Matched skills: python');
    expect(discovered?.textContent).toContain('Missing required skills: kubernetes');
    expect(discovered?.textContent).toContain('Experience was left out because the information is unknown');
    expect(discovered?.textContent).not.toContain('Experience50%');
    expect(view.querySelector('[data-section="manual"]')?.textContent).toContain('No manual test records');
  });

  it('filters with the configured minimum and can show jobs below it', async () => {
    const view = await render(
      [
        job({ id: 'keep', title: 'Keep role', assessment: assessment(80) }),
        job({ id: 'drop', title: 'Drop role', assessment: assessment(49.9) }),
      ],
      50,
    );
    expect(view.textContent).toContain('Keep role');
    expect(view.textContent).not.toContain('Drop role');
    const checkbox = view.querySelector('input[type="checkbox"]') as HTMLInputElement;
    await act(async () => {
      checkbox.click();
    });
    expect(view.textContent).toContain('Drop role');
    expect(view.textContent).toContain('49.9%');
  });

  it('shows a message when the profile file is missing', async () => {
    const status: ProfileStatus = {
      profile_present: false,
      profile_valid: false,
      resume_text_available: false,
      warnings: ['profile_missing'],
      message: 'No profile file was found. Add storage/profile.json with only facts you can confirm.',
    };
    const view = await render([], 50, status);
    expect(view.querySelector('[data-profile-status="profile_missing"]')?.textContent).toContain('No profile file was found');
  });
});
