import type { Job } from './api';

export const FACTOR_LABELS: Record<string, string> = {
  technical_skills: 'Technical skills',
  role: 'Job role',
  experience: 'Experience',
  domain: 'Domain',
  location: 'Location',
};

export function isManualRecord(job: Job): boolean {
  if (job.origin === 'manual' || job.origin === 'discovered') return job.origin === 'manual';
  return job.source === 'manual';
}

export function explainableScore(job: Job): number | null {
  if (!job.assessment) return null;
  return job.assessment.total_score;
}

export function meetsMinimum(job: Job, minimum: number): boolean {
  const score = explainableScore(job);
  return score !== null && score >= minimum;
}

export function arrangeJobs(jobs: Job[], minimum: number, onlyAtOrAboveMinimum: boolean): Job[] {
  const visible = onlyAtOrAboveMinimum ? jobs.filter((job) => meetsMinimum(job, minimum)) : jobs;
  return [...visible].sort((left, right) => {
    const leftScore = explainableScore(left);
    const rightScore = explainableScore(right);
    if (leftScore === null && rightScore === null) return left.title.localeCompare(right.title);
    if (leftScore === null) return 1;
    if (rightScore === null) return -1;
    if (rightScore !== leftScore) return rightScore - leftScore;
    return left.title.localeCompare(right.title);
  });
}
