import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import Plotly from "plotly.js-dist-min";
import "./styles.css";

type Dataset = {
  id: string;
  original_filename: string;
  row_count: number;
  column_count: number;
  created_at: string;
  profile?: Profile;
  issues?: Issue[];
};

type Profile = {
  row_count: number;
  column_count: number;
  columns: Array<{
    name: string;
    inferred_type: string;
    missing_pct: number;
    unique_count: number;
    examples: unknown[];
  }>;
  preview: Record<string, unknown>[];
};

type Issue = { severity: string; type: string; column?: string; message: string };

type Analysis = {
  id: string;
  question: string;
  answer: string;
  tables: Array<{ name: string; columns: string[]; rows: Record<string, unknown>[]; row_count: number }>;
  charts: Array<{ figure: unknown; spec: { title: string; chart_type: string } }>;
  tool_calls: Array<{ tool: string; status: string; arguments: Record<string, unknown>; result?: Record<string, unknown> }>;
  warnings: string[];
  validation: Record<string, unknown>;
  trace: Record<string, unknown>;
  suggested_followups: string[];
};

const api = async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
  const token = localStorage.getItem("demoToken") || "";
  const headers = new Headers(init.headers);
  if (token) headers.set("x-demo-key", token);
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
};

function Plot({ figure }: { figure: unknown }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) {
      Plotly.react(ref.current, figure as never, {}, { responsive: true, displayModeBar: false });
    }
  }, [figure]);
  return <div className="plot" ref={ref} />;
}

function App() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState<Dataset | null>(null);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [activeAnalysis, setActiveAnalysis] = useState<Analysis | null>(null);
  const [question, setQuestion] = useState("Profile this dataset and tell me the main data-quality issues.");
  const [token, setToken] = useState(localStorage.getItem("demoToken") || "change-me-demo-token");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDatasets = async () => {
    const rows = await api<Dataset[]>("/api/v1/datasets");
    setDatasets(rows);
    if (!selected && rows[0]) await selectDataset(rows[0].id);
  };

  const selectDataset = async (id: string) => {
    const detail = await api<Dataset>(`/api/v1/datasets/${id}`);
    setSelected(detail);
    const history = await api<Analysis[]>(`/api/v1/datasets/${id}/analyses`);
    setAnalyses(history);
    setActiveAnalysis(history[0] || null);
  };

  useEffect(() => {
    localStorage.setItem("demoToken", token);
  }, [token]);

  useEffect(() => {
    loadDatasets().catch((err) => setError(err.message));
  }, []);

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const detail = await api<Dataset>("/api/v1/datasets/upload", { method: "POST", body: form });
      await loadDatasets();
      await selectDataset(detail.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const loadDemo = async (name: "wine-quality" | "owid-co2") => {
    setBusy(true);
    setError(null);
    try {
      const detail = await api<Dataset>(`/api/v1/datasets/demo/${name}`, { method: "POST" });
      await loadDatasets();
      await selectDataset(detail.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Demo load failed");
    } finally {
      setBusy(false);
    }
  };

  const ask = async (text = question) => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const response = await api<Analysis>(`/api/v1/datasets/${selected.id}/questions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: text })
      });
      setActiveAnalysis(response);
      setAnalyses((rows) => [response, ...rows.filter((row) => row.id !== response.id)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setBusy(false);
    }
  };

  const profileColumns = selected?.profile?.columns || [];
  const previewColumns = selected?.profile?.preview?.[0] ? Object.keys(selected.profile.preview[0]) : [];
  const trustState = useMemo(() => {
    if (!activeAnalysis) return "waiting";
    if (activeAnalysis.validation.blocked) return "blocked";
    if (activeAnalysis.validation.sql_safety === "passed") return "validated";
    return "limited";
  }, [activeAnalysis]);

  return (
    <main className="app-shell">
      <aside className="left-rail">
        <div className="brand-block">
          <span className="eyebrow">Governed Agent</span>
          <h1>Tabular AI Analyst</h1>
          <p>Natural-language analysis with bounded tools, validated SQL, chart specs, and replayable traces.</p>
        </div>
        <label className="token-box">
          Demo token
          <input value={token} onChange={(event) => setToken(event.target.value)} />
        </label>
        <label className="upload-box">
          <input type="file" accept=".csv,.xlsx" onChange={(event) => event.target.files?.[0] && upload(event.target.files[0])} />
          <span>Upload CSV/XLSX</span>
        </label>
        <div className="demo-row">
          <button disabled={busy} onClick={() => loadDemo("wine-quality")}>Wine demo</button>
          <button disabled={busy} onClick={() => loadDemo("owid-co2")}>CO2 demo</button>
        </div>
        <section>
          <h2>Datasets</h2>
          <div className="dataset-list">
            {datasets.map((dataset) => (
              <button className={selected?.id === dataset.id ? "selected" : ""} key={dataset.id} onClick={() => selectDataset(dataset.id)}>
                <strong>{dataset.original_filename}</strong>
                <span>{dataset.row_count} rows · {dataset.column_count} cols</span>
              </button>
            ))}
          </div>
        </section>
        <section>
          <h2>History</h2>
          <div className="history-list">
            {analyses.map((analysis) => (
              <button key={analysis.id} onClick={() => setActiveAnalysis(analysis)}>{analysis.question}</button>
            ))}
          </div>
        </section>
      </aside>

      <section className="workspace">
        <div className="command-strip">
          <div>
            <span className={`trust-pill ${trustState}`}>{trustState}</span>
            <h2>{selected ? selected.original_filename : "Upload a dataset to begin"}</h2>
          </div>
          <button disabled={busy || !selected} onClick={() => ask()}>{busy ? "Running..." : "Run analysis"}</button>
        </div>
        <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask a governed analysis question..." />
        <div className="prompt-row">
          {["Show the main data-quality issues.", "Create a chart for the key trend.", "Compare averages across the main category."].map((text) => (
            <button key={text} disabled={!selected || busy} onClick={() => { setQuestion(text); ask(text); }}>{text}</button>
          ))}
        </div>
        {error && <div className="error">{error}</div>}
        {activeAnalysis && (
          <article className="answer-panel">
            <h3>Analyst Answer</h3>
            <p>{activeAnalysis.answer}</p>
            {activeAnalysis.warnings.length > 0 && (
              <div className="warning-box">
                {activeAnalysis.warnings.map((warning) => <span key={warning}>{warning}</span>)}
              </div>
            )}
            {activeAnalysis.charts.map((chart, index) => <Plot key={index} figure={chart.figure} />)}
            {activeAnalysis.tables.map((table) => (
              <div className="table-wrap" key={table.name}>
                <h4>{table.name} · {table.row_count} rows</h4>
                <table>
                  <thead><tr>{table.columns.map((col) => <th key={col}>{col}</th>)}</tr></thead>
                  <tbody>{table.rows.slice(0, 12).map((row, idx) => <tr key={idx}>{table.columns.map((col) => <td key={col}>{String(row[col] ?? "")}</td>)}</tr>)}</tbody>
                </table>
              </div>
            ))}
          </article>
        )}
      </section>

      <aside className="inspector">
        <section className="metric-grid">
          <div><span>Rows</span><strong>{selected?.row_count ?? "–"}</strong></div>
          <div><span>Columns</span><strong>{selected?.column_count ?? "–"}</strong></div>
          <div><span>Issues</span><strong>{selected?.issues?.length ?? "–"}</strong></div>
          <div><span>Tools</span><strong>{activeAnalysis?.tool_calls.length ?? "–"}</strong></div>
        </section>
        <section>
          <h2>Schema Profile</h2>
          <div className="column-list">
            {profileColumns.map((column) => (
              <div key={column.name}>
                <strong>{column.name}</strong>
                <span>{column.inferred_type} · {Math.round(column.missing_pct * 100)}% missing · {column.unique_count} unique</span>
              </div>
            ))}
          </div>
        </section>
        <section>
          <h2>Quality Warnings</h2>
          <div className="issue-list">
            {(selected?.issues || []).map((issue, index) => <div className={issue.severity} key={index}>{issue.message}</div>)}
          </div>
        </section>
        <section>
          <h2>Tool Trace</h2>
          <div className="trace-list">
            {(activeAnalysis?.tool_calls || []).map((call, index) => (
              <details key={`${call.tool}-${index}`} open={index === 0}>
                <summary>{call.tool}</summary>
                <pre>{JSON.stringify({ arguments: call.arguments, result: call.result }, null, 2)}</pre>
              </details>
            ))}
          </div>
        </section>
        <section>
          <h2>Preview</h2>
          {selected?.profile?.preview && (
            <div className="mini-table">
              <table>
                <thead><tr>{previewColumns.slice(0, 4).map((col) => <th key={col}>{col}</th>)}</tr></thead>
                <tbody>{selected.profile.preview.slice(0, 5).map((row, idx) => <tr key={idx}>{previewColumns.slice(0, 4).map((col) => <td key={col}>{String(row[col] ?? "")}</td>)}</tr>)}</tbody>
              </table>
            </div>
          )}
        </section>
      </aside>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
