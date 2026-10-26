import { useState } from 'react';
import { syncCareerPage, type Connector, type SyncSummary } from './api';
import { safeErrorCode, summaryRows, syncAvailability, syncFailureMessage } from './syncJobs';

export function SyncJobs({
  connector,
  busy,
  onSynced,
}: {
  connector: Connector | undefined;
  busy: boolean;
  onSynced: () => Promise<void>;
}) {
  const availability = syncAvailability(connector);
  const [confirming, setConfirming] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [summary, setSummary] = useState<SyncSummary | null>(null);
  const [failure, setFailure] = useState('');
  const locked = busy || syncing || !availability.available;

  async function start() {
    if (syncing || !availability.available) return;
    setSyncing(true);
    setFailure('');
    setSummary(null);
    try {
      const result = await syncCareerPage();
      setSummary(result);
      await onSynced();
    } catch (error) {
      setFailure(syncFailureMessage(error));
    } finally {
      setSyncing(false);
      setConfirming(false);
    }
  }

  return (
    <section className="panel" data-sync-panel>
      <div className="panel-heading">
        <div>
          <h2>Sync Greenhouse jobs</h2>
          <p>{availability.reason}</p>
        </div>
        <button className="button" type="button" disabled={locked || confirming} onClick={() => setConfirming(true)}>
          {syncing ? 'Syncing…' : 'Sync jobs'}
        </button>
      </div>
      {connector?.note ? <p className="sync-note">{connector.note}</p> : null}
      {confirming ? (
        <div className="notice" data-sync-confirm>
          <div>
            <b>Start a manual sync?</b>
            <p>This asks the API to read Greenhouse boards that are already configured. It does not submit applications, enable the connector, or change automation settings.</p>
            <div className="sync-actions">
              <button className="button" type="button" disabled={syncing} onClick={() => void start()}>
                {syncing ? 'Syncing…' : 'Start sync'}
              </button>
              <button className="button secondary" type="button" disabled={syncing} onClick={() => setConfirming(false)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {failure ? (
        <div className="error" data-sync-error role="alert">
          {failure}
        </div>
      ) : null}
      {summary ? (
        <dl className="sync-summary" data-sync-summary>
          {summaryRows(summary).map((row) => (
            <div key={row.label}>
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
          <div>
            <dt>Errors</dt>
            <dd>{summary.errors.length ? summary.errors.map((item) => safeErrorCode(item.code)).join(', ') : 'none'}</dd>
          </div>
        </dl>
      ) : null}
    </section>
  );
}
