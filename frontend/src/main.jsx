import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    ...options, headers: { 'Content-Type': 'application/json', ...options.headers },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}

function App() {
  const [prompts, setPrompts] = useState([]);
  const [promptId, setPromptId] = useState('');
  const [name, setName] = useState('ticket-classifier');
  const [template, setTemplate] = useState('');
  const [provider, setProvider] = useState('mock');
  const [model, setModel] = useState('mock');
  const [baselineId, setBaselineId] = useState('');
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [detail, setDetail] = useState(null);
  const [filter, setFilter] = useState('all');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState(null);

  useEffect(() => {
    let active = true;
    Promise.all([api('/prompts'), api('/health')]).then(([list, info]) => {
      if (!active) return;
      setPrompts(list); setPromptId(String(list[0]?.id || '')); setHealth(info);
    }).catch(e => active && setError(e.message));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const prompt = prompts.find(p => String(p.id) === promptId);
    if (prompt) { setTemplate(prompt.template); setName(prompt.name); }
  }, [promptId, prompts]);

  useEffect(() => {
    let active = true;
    let timer;
    async function refresh() {
      try {
        const [list, data] = await Promise.all([
          api('/runs'), selectedRun ? api(`/runs/${selectedRun}`) : Promise.resolve(null),
        ]);
        if (active) { setRuns(list); setDetail(data); }
      } catch (e) { if (active) setError(e.message); }
      finally { if (active) timer = setTimeout(refresh, 2000); }
    }
    refresh();
    return () => { active = false; clearTimeout(timer); };
  }, [selectedRun]);

  async function saveVersion(e) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const saved = await api('/prompts', { method: 'POST', body: JSON.stringify({ name, template }) });
      setPrompts(await api('/prompts')); setPromptId(String(saved.id));
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function runEvaluation() {
    setBusy(true); setError('');
    try {
      const run = await api('/runs', { method: 'POST', body: JSON.stringify({
        prompt_id: Number(promptId), provider, model, baseline_id: baselineId ? Number(baselineId) : null,
      }) });
      setDetail(null); setSelectedRun(run.id);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  const saved = prompts.find(p => String(p.id) === promptId);
  const unsaved = saved && (saved.template !== template || saved.name !== name);
  const rows = (detail?.results || []).filter(row => filter === 'all' ||
    (filter === 'regressions' && row.regression) ||
    (filter === 'failures' && (!row.format_ok || !row.accuracy_ok || row.error)));

  return <main>
    <header><div><p className="eyebrow">EVALUATE · COMPARE · RELEASE</p><h1>PromptLab<span> / </span></h1>
      <p className="subtitle">A clearer view of what your prompt changed.</p></div>
      <span className="dataset">{health ? `${health.dataset_cases} synthetic cases` : 'Connecting…'}</span></header>
    <aside className="notice">Results appear after you run an evaluation. The mock provider checks the pipeline; real model quality requires an HTTP provider.</aside>
    {error && <div role="alert" className="error">{error}<button onClick={() => setError('')}>Dismiss</button></div>}
    <section className="workspace">
      <form className="panel editor" onSubmit={saveVersion}>
        <div className="section-heading"><h2>Prompt versions</h2><span className="tag">IMMUTABLE</span></div>
        <label>Saved version<select value={promptId} onChange={e => setPromptId(e.target.value)}>
          {prompts.map(p => <option key={p.id} value={p.id}>{p.name} · v{p.version}</option>)}
        </select></label>
        <label>Prompt name<input required maxLength={80} pattern="[a-zA-Z0-9_-]+" value={name} onChange={e => setName(e.target.value)}/></label>
        <label>Template<textarea required rows={10} value={template} onChange={e => setTemplate(e.target.value)}/></label>
        <p className="hint">Use {'{{input}}'} for the test case. Save edits as a new immutable version before evaluating.</p>
        <button className="secondary" disabled={busy || !unsaved}>Save new version</button>
      </form>
      <div className="panel controls">
        <h2>New evaluation</h2>
        <label>Provider<select value={provider} onChange={e => { setProvider(e.target.value); setModel(e.target.value === 'mock' ? 'mock' : ''); setBaselineId(''); }}>
          <option value="mock">Mock · no API calls</option><option value="http">HTTP · configured model endpoint</option>
        </select></label>
        <label>Model<input required value={model} maxLength={200} onChange={e => setModel(e.target.value)}/></label>
        <label>Compare with baseline<select value={baselineId} onChange={e => setBaselineId(e.target.value)}>
          <option value="">No baseline</option>
          {runs.filter(r => r.status === 'completed' && r.provider === provider && r.model === model && r.prompt_name === saved?.name)
            .map(r => <option key={r.id} value={r.id}>Run #{r.id} · v{r.prompt_version} · {r.passed}/{r.total} passed</option>)}
        </select></label>
        <button className="primary" disabled={busy || !promptId || !model.trim() || unsaved} onClick={runEvaluation}>{busy ? 'Saving…' : 'Run evaluation →'}</button>
        <p className="hint">Runs pytest over the saved version. HTTP evaluations send all test inputs to your configured provider and may incur costs.</p>
      </div>
    </section>
    <section className="panel history"><h2>Evaluation history</h2>
      {runs.length === 0 ? <p className="empty">No evaluations yet. Select a prompt and start your first run.</p> :
        <div className="table-wrap"><table><thead><tr><th>Run / prompt</th><th>Provider</th><th>Status</th><th>Passed</th><th>Regressions</th><th>Gate</th><th>Started</th></tr></thead>
          <tbody>{runs.map(r => <tr key={r.id} className={selectedRun === r.id ? 'selected' : ''}>
            <td><button className="link" onClick={() => { setDetail(null); setSelectedRun(r.id); }}>#{r.id} · {r.prompt_name} v{r.prompt_version}</button></td>
            <td>{r.provider} / {r.model}</td><td><span className={`status ${r.status}`}>{r.status}</span></td>
            <td>{r.passed} / {r.total} <small>({r.evaluated} evaluated)</small></td>
            <td>{r.baseline_id ? r.regressions : '—'}</td><td>{r.status === 'completed' ? (r.release_gate_passed ? 'Pass' : 'Blocked') : 'Pending'}</td>
            <td>{new Date(r.started_at).toLocaleString()}</td></tr>)}</tbody></table></div>}
    </section>
    {selectedRun && <section className="panel detail">
      <div className="section-heading"><h2>Run #{selectedRun} · case results</h2>
        <select aria-label="Filter results" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All cases</option><option value="failures">Failures & errors</option><option value="regressions">Regressions</option></select></div>
      {!detail ? <p className="empty">Loading results…</p> : <>
        {detail.error && <p role="alert" className="error">{detail.error}</p>}
        <div className="stats"><div><strong>{detail.passed}/{detail.total}</strong><span>Passed</span></div>
          <div><strong>{detail.format_failures}</strong><span>Format failures</span></div><div><strong>{detail.accuracy_failures}</strong><span>Accuracy failures</span></div>
          <div><strong>{detail.execution_errors}</strong><span>Provider errors</span></div><div><strong>{detail.baseline_id ? detail.regressions : '—'}</strong><span>Regressed cases</span></div></div>
        <p className="hint">Baseline: {detail.baseline_id ? `run #${detail.baseline_id}` : 'none'}. Format and accuracy failures can overlap. Dataset: <code>{detail.dataset_sha.slice(0, 12)}</code></p>
        {rows.length === 0 ? <p className="empty">No matching results yet.</p> : <div className="table-wrap"><table><thead><tr><th>Case / input</th><th>Expected</th><th>Actual output</th><th>Checks</th><th>Change</th></tr></thead>
          <tbody>{rows.map(row => <tr key={row.case_id}><td><strong>{row.case_id}</strong><p>{row.input}</p></td><td><pre>{JSON.stringify(row.expected, null, 2)}</pre></td>
            <td><pre>{row.output || '(no output)'}</pre>{row.baseline_output !== null && <details><summary>Baseline output</summary><pre>{row.baseline_output}</pre></details>}</td>
            <td>{row.error ? <span className="bad">{row.error}</span> : <><div className={row.format_ok ? 'good' : 'bad'}>Format: {row.format_ok ? 'pass' : 'fail'}</div><div className={row.accuracy_ok ? 'good' : 'bad'}>Accuracy: {row.accuracy_ok ? 'pass' : 'fail'}</div></>}<small>{row.latency_ms.toFixed(1)} ms</small></td>
            <td className={row.regression ? 'bad' : ''}>{row.regression ? [row.format_regression && 'Format', row.accuracy_regression && 'Accuracy'].filter(Boolean).join(' + ') : '—'}</td></tr>)}</tbody></table></div>}
      </>}
    </section>}
    <footer>PromptLab · reproducible inputs, visible changes</footer>
  </main>;
}

createRoot(document.getElementById('root')).render(<App/>);
