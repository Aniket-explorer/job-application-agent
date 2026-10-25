import { useEffect, useState } from 'react';
import { BriefcaseBusiness, ClipboardList, Settings as SettingsIcon, Radio, RefreshCw, ExternalLink, ShieldCheck } from 'lucide-react';
import { api, type Job, type Application, type Connector } from './api';

type Page = 'Overview' | 'Jobs' | 'Applications' | 'Connectors & Settings';
export default function App() {
  const [page, setPage] = useState<Page>('Overview');
  const [jobs, setJobs] = useState<Job[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function refresh() {
    setBusy(true); setError('');
    try {
      const [j, a, c] = await Promise.all([api<Job[]>('/api/jobs'), api<Application[]>('/api/applications'), api<Connector[]>('/api/connectors')]);
      setJobs(j); setApplications(a); setConnectors(c);
    } catch (e) { setError(e instanceof Error ? e.message : 'API unavailable'); }
    finally { setBusy(false); }
  }
  useEffect(() => { void refresh(); }, []);
  async function dryRun(job: Job) {
    try { await api<Application>('/api/applications', { method: 'POST', body: JSON.stringify({ job_id: job.id }) }); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not prepare application'); }
  }
  const nav: { name: Page; icon: typeof BriefcaseBusiness }[] = [
    { name: 'Overview', icon: Radio }, { name: 'Jobs', icon: BriefcaseBusiness }, { name: 'Applications', icon: ClipboardList }, { name: 'Connectors & Settings', icon: SettingsIcon }
  ];
  return <div className="layout">
    <aside className="sidebar"><div className="brand"><div className="brand-icon">JA</div><div><strong>Job Agent</strong><small>Personal workspace</small></div></div>
      <nav>{nav.map(item => <button key={item.name} className={page === item.name ? 'nav-item active' : 'nav-item'} onClick={() => setPage(item.name)}><item.icon size={18}/>{item.name}</button>)}</nav>
      <div className="sidebar-note"><ShieldCheck size={18}/><div><b>Dry-run mode</b><p>No emails or applications are submitted by this starter.</p></div></div>
    </aside>
    <main className="main"><header className="topbar"><div><span className="eyebrow">PERSONAL AUTOMATION</span><h1>{page}</h1></div><button className="button secondary" onClick={() => void refresh()} disabled={busy}><RefreshCw size={16}/>{busy ? 'Refreshing…' : 'Refresh'}</button></header>
      {error && <div className="error">{error}<button onClick={() => setError('')}>Dismiss</button></div>}
      {page === 'Overview' && <><section className="cards"><Metric label="Jobs discovered" value={jobs.length} note="Imported or discovered listings"/><Metric label="Dry-run applications" value={applications.length} note="No live submissions"/><Metric label="Configured sources" value={connectors.filter(c=>c.configured).length} note={`${connectors.length} connector slots`}/><Metric label="Follow-ups due" value="—" note="Follow-up worker not implemented"/></section><section className="panel"><div className="panel-heading"><div><h2>Recent jobs</h2><p>Jobs imported into your local workspace</p></div><button className="text-button" onClick={()=>setPage('Jobs')}>View all →</button></div><JobTable jobs={jobs.slice(0,5)} onDryRun={dryRun}/></section><section className="notice"><ShieldCheck/><div><b>Safe by default</b><p>Provider integrations are unconfigured until their access permissions and current terms are verified. Live mode is intentionally unavailable.</p></div></section></>}
      {page === 'Jobs' && <section className="panel"><div className="panel-heading"><div><h2>Job feed</h2><p>Match threshold: 50% · Original resume strategy selected</p></div><span className="pill">{jobs.length} jobs</span></div><JobTable jobs={jobs} onDryRun={dryRun}/></section>}
      {page === 'Applications' && <section className="panel"><div className="panel-heading"><div><h2>Application tracker</h2><p>Dry-run records only</p></div></div>{applications.length ? <div className="table-wrap"><table><thead><tr><th>Job ID</th><th>Channel</th><th>Match</th><th>Status</th><th>Created</th></tr></thead><tbody>{applications.map(a=><tr key={a.id}><td className="mono">{a.job_id.slice(-8)}</td><td>{a.channel}</td><td>{a.match_score}%</td><td><span className="pill amber">{a.status}</span></td><td>{new Date(a.created_at).toLocaleString()}</td></tr>)}</tbody></table></div>:<Empty title="No application records yet" text="Open Jobs and choose Prepare dry run to create a test record."/>}</section>}
      {page === 'Connectors & Settings' && <><section className="panel"><div className="panel-heading"><div><h2>Source connectors</h2><p>Access has not been assumed or verified.</p></div></div><div className="connector-list">{connectors.map(c=><div className="connector" key={c.source}><div className="connector-logo">{c.source.slice(0,2).toUpperCase()}</div><div className="connector-body"><div className="connector-title"><b>{c.source.replace('_',' ')}</b><span className="pill gray">{c.status}</span></div><p>{c.note}</p><small>Discovery: {c.discovery_supported ? 'supported' : 'not configured'} · Application: {c.application_supported ? 'supported' : 'not configured'}</small></div></div>)}</div></section><section className="panel settings"><h2>Automation policy</h2><div className="setting-row"><div><b>Operating mode</b><p>Dry-run only; live mode is blocked by the API.</p></div><span className="pill green">Enabled</span></div><div className="setting-row"><div><b>Minimum match score</b><p>Jobs below this threshold cannot be prepared.</p></div><strong>50%</strong></div><div className="setting-row"><div><b>Search frequency</b><p>Hourly scheduler placeholder; no external calls until a connector is configured.</p></div><strong>60 min</strong></div><div className="setting-row"><div><b>Resume strategy</b><p>Original resume, checksum storage not yet implemented.</p></div><strong>Original</strong></div><div className="setting-row"><div><b>Follow-up tracking</b><p>UI placeholder; reply parsing and reminders are a later phase.</p></div><span className="pill gray">Planned</span></div></section></>}
      <footer>Local development scaffold · API <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">docs <ExternalLink size={12}/></a></footer>
    </main>
  </div>;
}
function Metric({label,value,note}:{label:string;value:string|number;note:string}) { return <div className="metric"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>; }
function JobTable({jobs,onDryRun}:{jobs:Job[];onDryRun:(job:Job)=>void}) { if(!jobs.length) return <Empty title="No jobs yet" text="Use the API's manual import endpoint to add a test listing. Connectors are intentionally unconfigured."/>; return <div className="table-wrap"><table><thead><tr><th>Role / company</th><th>Source</th><th>Match</th><th>Status</th><th>Action</th></tr></thead><tbody>{jobs.map(j=><tr key={j.id}><td><b>{j.title}</b><small className="subline">{j.company} · {j.location || 'Location not specified'}</small><a className="job-link" href={j.canonical_url} target="_blank" rel="noreferrer">Open listing <ExternalLink size={11}/></a></td><td>{j.source}</td><td><span className={`score ${(j.match_score||0)>=50?'good':'low'}`}>{j.match_score ?? 0}%</span></td><td><span className="pill green">{j.status}</span></td><td><button className="button small" disabled={(j.match_score||0)<50} onClick={()=>onDryRun(j)}>Prepare dry run</button></td></tr>)}</tbody></table></div>; }
function Empty({title,text}:{title:string;text:string}) { return <div className="empty"><BriefcaseBusiness size={25}/><b>{title}</b><p>{text}</p></div>; }
