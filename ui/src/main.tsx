import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
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
  tool_calls: Array<{ tool: string; status: string; arguments: Record<string, unknown>; result?: Record<string, unknown>; error?: string }>;
  warnings: string[];
  validation: Record<string, unknown>;
  trace: Record<string, unknown>;
  reasoning?: Array<{ kind: string; label: string; source?: string }>;
  suggested_followups: string[];
};

const isSavedAnalysis = (analysis: Analysis) => !analysis.validation?.blocked && !analysis.validation?.clarification_required;

function ResultTable({ table }: { table: Analysis["tables"][number] }) {
  return (
    <div className="table-wrap">
      <h3>{table.name} · {table.row_count} rows</h3>
      <table>
        <thead><tr>{table.columns.map((col) => <th key={col}>{col}</th>)}</tr></thead>
        <tbody>{table.rows.slice(0, 12).map((row, idx) => <tr key={idx}>{table.columns.map((col) => <td key={col}>{String(row[col] ?? "")}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

const api = async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
  const token = localStorage.getItem("demoToken") || "";
  const headers = new Headers(init.headers);
  if (token) headers.set("x-demo-key", token);
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) throw new Error(await formatApiError(response));
  return response.json();
};

const formatApiError = async (response: Response): Promise<string> => {
  if (response.status === 413) {
    return "Upload is too large for this demo. Try a smaller CSV/XLSX file or reduce the number of rows and columns before uploading.";
  }

  const contentType = response.headers.get("content-type") || "";
  const body = await response.text();
  if (contentType.includes("application/json")) {
    try {
      const parsed = JSON.parse(body) as { detail?: unknown; message?: unknown };
      const detail = parsed.detail ?? parsed.message;
      if (typeof detail === "string") return detail;
      if (detail) return JSON.stringify(detail);
    } catch {
      return body || `Request failed with status ${response.status}.`;
    }
  }

  const plain = body.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  return plain || `Request failed with status ${response.status}.`;
};

function Plot({ figure }: { figure: unknown }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false;
    import("plotly.js-dist-min").then(({ default: Plotly }) => {
      if (!cancelled && ref.current) {
        Plotly.react(ref.current, figure as never, {}, { responsive: true, displayModeBar: false });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [figure]);
  return <div className="plot" ref={ref} />;
}

function ToolTrace({ analysis }: { analysis: Analysis | null }) {
  if (!analysis) return <p>Run an analysis to inspect validated tool outputs.</p>;

  const tableForTool = (tool: string) => {
    if (tool === "run_safe_sql") return analysis.tables.find((table) => table.name === "query_result");
    if (tool === "run_transform") return analysis.tables.find((table) => table.name === "transform_result");
    return undefined;
  };

  const outputSummary = (call: Analysis["tool_calls"][number]) => {
    if (call.status === "error") return call.error || "The tool failed validation.";
    if (call.tool === "profile_dataset") return `Profiled ${call.result?.row_count ?? "unknown"} rows and ${call.result?.column_count ?? "unknown"} columns.`;
    if (call.tool === "detect_data_quality_issues") return `Detected ${call.result?.issue_count ?? 0} data-quality issue(s).`;
    if (call.tool === "run_safe_sql" || call.tool === "run_transform") return `Returned ${call.result?.row_count ?? 0} row(s).`;
    if (call.tool === "create_chart") return `Created a validated ${call.result?.chart_type ?? "chart"} chart.`;
    if (call.tool === "summarize_result") return "Generated the final analyst answer.";
    return "Completed successfully.";
  };

  return (
    <>
      {analysis.tool_calls.map((call, index) => {
        const table = tableForTool(call.tool);
        return (
          <section key={`${call.tool}-${index}`} className="tool-output">
            <div className="tool-heading">
              <span>{call.tool}</span>
              <mark className={call.status}>{call.status}</mark>
            </div>
            <p>{outputSummary(call)}</p>
            {table && <ResultTable table={table} />}
            <details className="technical-input">
              <summary>Validated parameters</summary>
              <pre>{JSON.stringify(call.arguments, null, 2)}</pre>
            </details>
          </section>
        );
      })}
    </>
  );
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
  };

  const selectDataset = async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      const detail = await api<Dataset>(`/api/v1/datasets/${id}`);
      const history = await api<Analysis[]>(`/api/v1/datasets/${id}/analyses`);
      setSelected(detail);
      const visibleHistory = history.filter(isSavedAnalysis);
      setAnalyses(visibleHistory);
      setActiveAnalysis(visibleHistory[0] || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dataset load failed");
    } finally {
      setBusy(false);
    }
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
      if (isSavedAnalysis(response)) {
        setAnalyses((rows) => [response, ...rows.filter((row) => row.id !== response.id)]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setBusy(false);
    }
  };

  const runFollowup = (followup: string) => {
    const contextual = activeAnalysis?.validation?.clarification_required && activeAnalysis.question
      ? `${activeAnalysis.question} ${followup}`
      : followup;
    setQuestion(contextual);
    ask(contextual);
  };

  const closeDataset = () => {
    setSelected(null);
    setActiveAnalysis(null);
    setAnalyses([]);
    setError(null);
    loadDatasets().catch((err) => setError(err.message));
  };

  const profileColumns = selected?.profile?.columns || [];
  const previewColumns = selected?.profile?.preview?.[0] ? Object.keys(selected.profile.preview[0]) : [];
  const trustState = useMemo(() => {
    if (!activeAnalysis) return "waiting";
    if (activeAnalysis.validation.blocked) return "blocked";
    if (activeAnalysis.validation.sql_safety === "passed" || activeAnalysis.validation.transform_validation === "passed") return "validated";
    return "limited";
  }, [activeAnalysis]);
  const trustLabel = trustState === "waiting" ? "Ready" : trustState === "blocked" ? "Blocked" : trustState === "validated" ? "Validated" : "Limited";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <span className="eyebrow">Governed tabular analysis</span>
          <h1>Tabular AI Analyst</h1>
        </div>
        <label className="token-field">
          Demo token
          <input value={token} onChange={(event) => setToken(event.target.value)} />
        </label>
      </header>

      {!selected ? (
        <section className="start-screen">
          <div className="start-copy">
            <span className="eyebrow">Start with data</span>
            <h1>Ask useful questions without giving the model execution control.</h1>
            <p>Upload a table or load a demo dataset. The app profiles the data, runs only approved tools, and keeps technical detail out of the way until you ask for it.</p>
          </div>

          <div className="start-actions">
            <div className="primary-actions">
              <button disabled={busy} onClick={() => loadDemo("wine-quality")}>Load Wine Quality demo</button>
              <button disabled={busy} onClick={() => loadDemo("owid-co2")}>Load CO2 demo</button>
            </div>
            <label className="upload-box">
              <input type="file" accept=".csv,.xlsx" onChange={(event) => event.target.files?.[0] && upload(event.target.files[0])} />
              <span>Upload CSV/XLSX</span>
              <small>File type, size, rows, and columns are validated before analysis.</small>
            </label>
            {error && <div className="error">{error}</div>}
          </div>

          {datasets.length > 0 && (
            <section className="recent-datasets">
              <div>
                <span className="eyebrow">Recent datasets</span>
                <h2>Continue where you left off</h2>
              </div>
              <div className="dataset-list">
                {datasets.map((dataset) => (
                  <button key={dataset.id} onClick={() => selectDataset(dataset.id)}>
                    <strong>{dataset.original_filename}</strong>
                    <span>{dataset.row_count} rows · {dataset.column_count} columns</span>
                  </button>
                ))}
              </div>
            </section>
          )}
        </section>
      ) : (
        <section className="analysis-screen">
          <div className="dataset-bar">
            <div>
              <span className={`trust-pill ${trustState}`}>{trustLabel}</span>
              <h1>{selected.original_filename}</h1>
              <p>{selected.row_count} rows · {selected.column_count} columns · {selected.issues?.length ?? 0} detected issues</p>
            </div>
            <button className="secondary-action" onClick={closeDataset}>Change dataset</button>
          </div>

          <div className="question-panel">
            <label htmlFor="question-input">What do you want to know?</label>
            <textarea
              id="question-input"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask a governed analysis question..."
            />
            <div className="action-row">
              <button disabled={busy} onClick={() => ask()}>{busy ? "Running analysis..." : "Run analysis"}</button>
              <span>The backend validates every tool call before execution.</span>
            </div>
            <div className="prompt-row">
              {["Show the main data-quality issues.", "Create a chart for the key trend.", "Compare averages across the main category."].map((text) => (
                <button key={text} disabled={busy} onClick={() => { setQuestion(text); ask(text); }}>{text}</button>
              ))}
            </div>
            {error && <div className="error">{error}</div>}
          </div>

          {activeAnalysis ? (
            <article className="answer-panel">
              <div className="answer-heading">
                <div>
                  <span className="eyebrow">Answer</span>
                  <h2>Analyst Answer</h2>
                </div>
                <span className={`trust-pill ${trustState}`}>{trustLabel}</span>
              </div>
              <p>{activeAnalysis.answer}</p>
              {activeAnalysis.reasoning && activeAnalysis.reasoning.length > 0 && (
                <div className="reasoning-strip" aria-label="Analyst reasoning">
                  {activeAnalysis.reasoning.map((item, index) => (
                    <span className={`reasoning-chip ${item.kind}`} key={`${item.kind}-${item.label}-${index}`}>{item.label}</span>
                  ))}
                </div>
              )}
              {activeAnalysis.suggested_followups.length > 0 && (
                <div className="followup-panel">
                  <span>Follow-up options</span>
                  <div>
                    {activeAnalysis.suggested_followups.map((followup) => (
                      <button key={followup} disabled={busy} onClick={() => runFollowup(followup)}>{followup}</button>
                    ))}
                  </div>
                </div>
              )}
              {activeAnalysis.warnings.length > 0 && (
                <div className="warning-box">
                  {activeAnalysis.warnings.slice(0, 3).map((warning) => <span key={warning}>{warning}</span>)}
                </div>
              )}
              {activeAnalysis.charts.map((chart, index) => (
                <section className="chart-result" key={index}>
                  <h3>{chart.spec.title}</h3>
                  <Plot figure={chart.figure} />
                </section>
              ))}
              {activeAnalysis.tables.map((table) => (
                <ResultTable key={table.name} table={table} />
              ))}
            </article>
          ) : (
            <section className="empty-answer">
              <span className="eyebrow">Ready</span>
              <h2>Run your first governed analysis.</h2>
              <p>Start with one of the suggested questions or write your own. Tool traces, schema details, and previews stay hidden unless you open them.</p>
            </section>
          )}

          <section className="details-grid">
            <details>
              <summary>Dataset profile</summary>
              <div className="metric-grid">
                <div><span>Rows</span><strong>{selected.row_count}</strong></div>
                <div><span>Columns</span><strong>{selected.column_count}</strong></div>
                <div><span>Issues</span><strong>{selected.issues?.length ?? 0}</strong></div>
                <div><span>Saved analyses</span><strong>{analyses.length}</strong></div>
              </div>
              <div className="column-list">
                {profileColumns.map((column) => (
                  <div key={column.name}>
                    <strong>{column.name}</strong>
                    <span>{column.inferred_type} · {Math.round(column.missing_pct * 100)}% missing · {column.unique_count} unique</span>
                  </div>
                ))}
              </div>
            </details>

            <details>
              <summary>Quality warnings</summary>
              <div className="issue-list">
                {(selected.issues || []).map((issue, index) => <div className={issue.severity} key={index}>{issue.message}</div>)}
                {(selected.issues || []).length === 0 && <p>No quality warnings detected in the current profile.</p>}
              </div>
            </details>

            <details>
              <summary>History</summary>
              <div className="history-list">
                {analyses.map((analysis) => (
                  <button key={analysis.id} onClick={() => setActiveAnalysis(analysis)}>{analysis.question}</button>
                ))}
                {analyses.length === 0 && <p>No saved analyses yet.</p>}
              </div>
            </details>

            <details>
              <summary>Tool trace</summary>
              <div className="trace-list">
                <ToolTrace analysis={activeAnalysis} />
              </div>
            </details>

            <details>
              <summary>Preview</summary>
              {selected.profile?.preview && (
                <div className="mini-table">
                  <table>
                    <thead><tr>{previewColumns.slice(0, 5).map((col) => <th key={col}>{col}</th>)}</tr></thead>
                    <tbody>{selected.profile.preview.slice(0, 5).map((row, idx) => <tr key={idx}>{previewColumns.slice(0, 5).map((col) => <td key={col}>{String(row[col] ?? "")}</td>)}</tr>)}</tbody>
                  </table>
                </div>
              )}
            </details>
          </section>
        </section>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
