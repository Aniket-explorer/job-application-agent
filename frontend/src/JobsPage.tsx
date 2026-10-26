import { useState } from 'react';
import type { Job, ProfileStatus } from './api';
import { FACTOR_LABELS, arrangeJobs, explainableScore, isManualRecord, meetsMinimum } from './jobFeed';

const WARNING_TEXT: Record<string, string> = {
  profile_missing: 'No profile file was found, so this job was not scored.',
  no_comparable_facts: 'The profile has no facts that can be compared with this job.',
  resume_not_configured: 'No readable resume filename is configured.',
  resume_text_unavailable: 'The resume file could not be read. The original file was not changed.',
  profile_invalid: 'The profile file is not valid, so no qualifications were assumed.',
};

export function JobFeed({
  jobs,
  threshold,
  busy,
  profileStatus,
  onDryRun,
  onRecalculate,
}: {
  jobs: Job[];
  threshold: number;
  busy: boolean;
  profileStatus: ProfileStatus | null;
  onDryRun: (job: Job) => void;
  onRecalculate: () => void;
}) {
  const [onlyQualified, setOnlyQualified] = useState(true);
  const manualSource = jobs.filter(isManualRecord);
  const manual = arrangeJobs(
    onlyQualified ? manualSource.filter((job) => job.assessment?.total_score == null || meetsMinimum(job, threshold)) : manualSource,
    threshold,
    false,
  );
  const discoveredSource = jobs.filter((job) => !isManualRecord(job));
  const discovered = arrangeJobs(discoveredSource, threshold, onlyQualified);

  return (
    <>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Job feed</h2>
            <p>Configured minimum match score: {threshold}%. Scores use only facts from the profile or the original resume.</p>
          </div>
          <button className="button secondary" type="button" disabled={busy} onClick={onRecalculate}>
            {busy ? 'Working…' : 'Recalculate scores'}
          </button>
        </div>
        {profileStatus && (!profileStatus.profile_present || !profileStatus.profile_valid || !profileStatus.resume_text_available) ? (
          <div className="notice" data-profile-status={profileStatus.warnings.join(' ')}>
            <div>
              <b>Profile and resume</b>
              <p>{profileStatus.message}</p>
            </div>
          </div>
        ) : null}
        <label className="feed-filter">
          <input
            type="checkbox"
            checked={onlyQualified}
            onChange={(event) => setOnlyQualified(event.target.checked)}
          />
          Show only jobs at or above {threshold}%
        </label>
      </section>
      <section className="panel" data-section="discovered">
        <div className="panel-heading">
          <div>
            <h2>Discovered listings</h2>
            <p>Jobs returned by a configured source. Manual test records are not listed here.</p>
          </div>
          <span className="pill">{discovered.length}</span>
        </div>
        {discovered.length ? (
          discovered.map((job) => <JobCard key={job.id} job={job} threshold={threshold} manual={false} onDryRun={onDryRun} />)
        ) : (
          <div className="empty">
            <b>{discoveredSource.length ? `No discovered jobs meet ${threshold}%` : 'No discovered jobs yet'}</b>
            <p>
              {discoveredSource.length
                ? 'Turn off the minimum-score filter to see discovered listings below the configured threshold.'
                : 'Discovery is not running. The Greenhouse connector stays disabled, so this list stays empty until a real source returns jobs. Manual test records are shown separately and are not discovered listings.'}
            </p>
          </div>
        )}
      </section>
      <section className="panel" data-section="manual">
        <div className="panel-heading">
          <div>
            <h2>Manual test records</h2>
            <p>Imported for local checks. These are not jobs discovered from a source.</p>
          </div>
          <span className="pill gray">Manual test</span>
        </div>
        {manual.length ? (
          manual.map((job) => <JobCard key={job.id} job={job} threshold={threshold} manual onDryRun={onDryRun} />)
        ) : (
          <div className="empty">
            <b>No manual test records in this view</b>
            <p>
              {onlyQualified
                ? `None of the stored manual records meet the configured minimum of ${threshold}%.`
                : 'No manual jobs are stored.'}
            </p>
          </div>
        )}
      </section>
    </>
  );
}

function JobCard({
  job,
  threshold,
  manual,
  onDryRun,
}: {
  job: Job;
  threshold: number;
  manual: boolean;
  onDryRun: (job: Job) => void;
}) {
  const score = explainableScore(job);
  const importScore = job.assessment ? null : (job.match_score ?? null);
  const qualified = meetsMinimum(job, threshold);
  const assessment = job.assessment;
  return (
    <article className="job-card" data-job-id={job.id}>
      <div className="job-card-head">
        <div>
          <b>{job.title}</b>
          <small className="subline">{job.company} · {job.location || 'Location not specified'}</small>
          {job.canonical_url ? (
            <a className="job-link" href={job.canonical_url} target="_blank" rel="noreferrer">Open listing</a>
          ) : null}
        </div>
        <div className="job-card-score">
          <span className={`score ${qualified ? 'good' : 'low'}`}>{score === null ? (importScore === null ? 'Not scored' : `${importScore}%`) : `${score}%`}</span>
          <span className={manual ? 'pill amber' : 'pill green'}>{manual ? 'Manual test record' : 'Discovered listing'}</span>
          {assessment ? null : importScore !== null ? <small className="subline">Import score, not an explainable match</small> : null}
        </div>
      </div>
      {assessment ? (
        <>
          <div className="breakdown">
            {assessment.factors.map((factor) => (
              <div className="factor" key={factor.key}>
                <b>{FACTOR_LABELS[factor.key] || factor.key}</b>
                <span>{factor.status === 'unknown' || factor.score === null ? 'Unknown' : `${factor.score}%`}</span>
                <small>{factor.weight}% weight · {factor.status}</small>
                {factor.findings.map((finding) => <small key={finding}>{finding}</small>)}
              </div>
            ))}
          </div>
          <p className="skill-line">Matched skills: {assessment.matched_skills.length ? assessment.matched_skills.join(', ') : 'none'}</p>
          <p className="skill-line">Missing required skills: {assessment.missing_skills.length ? assessment.missing_skills.join(', ') : 'none'}</p>
          {assessment.warnings.length ? (
            <ul className="warning-list">
              {assessment.warnings.map((warning) => <li key={warning}>{warningText(warning)}</li>)}
            </ul>
          ) : null}
        </>
      ) : (
        <p className="skill-line">No category breakdown is stored yet. Recalculate scores to compare this job with the profile.</p>
      )}
      <button className="button small" type="button" disabled={!qualified} onClick={() => onDryRun(job)}>
        Prepare dry run
      </button>
    </article>
  );
}

function warningText(warning: string): string {
  if (WARNING_TEXT[warning]) return WARNING_TEXT[warning];
  if (warning.startsWith('unknown:')) {
    const key = warning.slice('unknown:'.length);
    return `${FACTOR_LABELS[key] || key} was left out because the information is unknown. It was not given a score.`;
  }
  return warning;
}
