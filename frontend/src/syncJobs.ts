import type { Connector, SyncSummary } from './api';

export type SyncAvailability = { available: boolean; reason: string };

const SAFE_CODES = /^[a-z0-9_]{1,40}$/;

export function syncAvailability(connector: Connector | undefined): SyncAvailability {
  if (!connector) {
    return { available: false, reason: 'Career page status was not returned, so sync is unavailable.' };
  }
  if (!connector.enabled) {
    return { available: false, reason: 'Greenhouse discovery is disabled. This dashboard cannot turn it on.' };
  }
  if (!connector.configured || !connector.discovery_supported) {
    return { available: false, reason: 'No Greenhouse boards are configured. This dashboard cannot add them.' };
  }
  return {
    available: true,
    reason: 'Sync reads boards already configured on the server. It does not submit applications or change settings.',
  };
}

export function syncFailureMessage(error: unknown): string {
  if (!(error instanceof Error) || error instanceof TypeError) {
    return 'The sync request did not reach the API. No settings were changed.';
  }
  if (error.message.startsWith('409:')) {
    return 'A sync is already running. Wait for it to finish before trying again.';
  }
  if (error.message.startsWith('422:')) {
    const detail = error.message.slice(4).trim();
    if (detail.startsWith('Greenhouse discovery is disabled') || detail.startsWith('No Greenhouse boards are configured')) {
      return detail;
    }
    return 'Sync is unavailable with the current configuration. No Greenhouse request was made.';
  }
  return 'Sync could not be completed. The API returned an unexpected error.';
}

export function safeErrorCode(code: unknown): string {
  return typeof code === 'string' && SAFE_CODES.test(code) ? code : 'unrecognized_error';
}

export function summaryRows(summary: SyncSummary): { label: string; value: number }[] {
  return [
    { label: 'Boards checked', value: summary.boards_checked },
    { label: 'Jobs fetched', value: summary.jobs_fetched },
    { label: 'Jobs created', value: summary.jobs_created },
    { label: 'Jobs updated', value: summary.jobs_updated },
    { label: 'Duplicates skipped', value: summary.duplicates_skipped },
    { label: 'Jobs skipped', value: summary.jobs_skipped },
    { label: 'Match assessments written', value: summary.matches_written },
  ];
}
