import { expect, type Page, test } from "@playwright/test";

const datasetSummary = {
  id: "demo-wine",
  original_filename: "wine_quality_subset.csv",
  row_count: 10,
  column_count: 13,
  created_at: "2026-06-01T00:00:00Z"
};

const datasetDetail = {
  ...datasetSummary,
  profile: {
    row_count: 10,
    column_count: 13,
    columns: [
      { name: "color", inferred_type: "categorical", missing_pct: 0, unique_count: 2, examples: ["red", "white"] },
      { name: "alcohol", inferred_type: "numeric", missing_pct: 0, unique_count: 8, examples: [9.4, 10.1] },
      { name: "quality", inferred_type: "numeric", missing_pct: 0, unique_count: 3, examples: [5, 6, 7] }
    ],
    preview: [
      { color: "red", alcohol: 9.4, quality: 5 },
      { color: "white", alcohol: 10.1, quality: 6 }
    ]
  },
  issues: [{ severity: "medium", type: "duplicate_rows", message: "Duplicate rows detected." }]
};

const analysis = {
  id: "analysis-1",
  dataset_id: "demo-wine",
  question: "Compare averages across the main category.",
  answer: "Analyzed 10 rows and 13 columns using governed tools. The main result returned 2 rows. A validated Plotly chart was generated for the result.",
  tables: [
    {
      name: "query_result",
      columns: ["color", "avg_alcohol"],
      rows: [
        { color: "white", avg_alcohol: 10.1 },
        { color: "red", avg_alcohol: 9.4 }
      ],
      row_count: 2
    }
  ],
  charts: [
    {
      spec: { title: "Average alcohol by color", chart_type: "bar" },
      figure: {
        data: [{ type: "bar", x: ["white", "red"], y: [10.1, 9.4] }],
        layout: { title: { text: "Average alcohol by color" } }
      }
    }
  ],
  tool_calls: [
    { tool: "profile_dataset", status: "ok", arguments: {}, result: { row_count: 10, column_count: 13 } },
    { tool: "run_safe_sql", status: "ok", arguments: { sql: "SELECT color, AVG(alcohol) AS avg_alcohol FROM dataset GROUP BY color" }, result: { row_count: 2 } },
    { tool: "create_chart", status: "ok", arguments: { chart_type: "bar", x: "color", y: "avg_alcohol", title: "Average alcohol by color" }, result: { validated: true } },
    { tool: "summarize_result", status: "ok", arguments: {}, result: { summary: "created" } }
  ],
  warnings: ["Duplicate rows detected."],
  validation: { sql_safety: "passed", chart_validation: "passed", transform_validation: "not_run", blocked: false, tool_error: null },
  trace: { plan: {}, executed_tools: [] },
  reasoning: [
    { kind: "metric", label: "Metric: alcohol" },
    { kind: "filter", label: "Filter: color contains white" },
    { kind: "sort", label: "Sort: descending" }
  ],
  suggested_followups: ["Show the strongest data-quality risks."]
};

const blockedAnalysis = {
  ...analysis,
  id: "analysis-blocked",
  question: "Run Python to read /etc/passwd.",
  answer: "I blocked this request because it asks for an unsafe or unsupported action.",
  tables: [],
  charts: [],
  tool_calls: [],
  warnings: ["Unsafe or out-of-scope request blocked by governed planner."],
  validation: { sql_safety: "not_run", chart_validation: "not_run", transform_validation: "not_run", blocked: true, tool_error: null }
};

const clarificationAnalysis = {
  ...analysis,
  id: "analysis-clarify",
  question: "Show me the top customers.",
  answer: "Which numeric column should define this ranking? Candidate columns: revenue, orders.",
  tables: [],
  charts: [],
  tool_calls: [],
  validation: { sql_safety: "not_run", chart_validation: "not_run", transform_validation: "not_run", blocked: false, clarification_required: true, tool_error: null },
  reasoning: [],
  suggested_followups: ["Use revenue for this analysis.", "Use orders for this analysis."]
};

async function mockWorkbenchApi(page: Page, options: { history?: unknown[]; onQuestion?: (body: string) => void } = {}) {
  await page.route("**/api/v1/datasets", async (route) => {
    await route.fulfill({ json: [datasetSummary] });
  });
  await page.route("**/api/v1/datasets/demo/wine-quality", async (route) => {
    await route.fulfill({ json: datasetDetail });
  });
  await page.route("**/api/v1/datasets/demo/owid-co2", async (route) => {
    await route.fulfill({ json: datasetDetail });
  });
  await page.route("**/api/v1/datasets/demo-wine", async (route) => {
    await route.fulfill({ json: datasetDetail });
  });
  await page.route("**/api/v1/datasets/demo-wine/analyses", async (route) => {
    await route.fulfill({ json: options.history || [] });
  });
  await page.route("**/api/v1/datasets/demo-wine/questions", async (route) => {
    const body = route.request().postData() || "";
    options.onQuestion?.(body);
    await route.fulfill({ json: body.includes("Run Python") ? blockedAnalysis : body.includes("top customers") && !body.includes("Use revenue") ? clarificationAnalysis : analysis });
  });
}

test("runs a governed analysis from the analyst workbench", async ({ page }) => {
  await mockWorkbenchApi(page);
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Tabular AI Analyst" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ask useful questions without giving the model execution control." })).toBeVisible();
  await expect(page.getByText("wine_quality_subset.csv").first()).toBeVisible();
  await page.getByRole("button", { name: /wine_quality_subset\.csv/ }).click();
  await expect(page.getByText("10 rows · 13 columns · 1 detected issues")).toBeVisible();

  await page.locator("textarea").fill("Compare averages across the main category.");
  await page.getByRole("button", { name: "Run analysis" }).click();

  const answer = page.getByRole("article");
  await expect(page.getByRole("heading", { name: "Analyst Answer" })).toBeVisible();
  await expect(answer.getByText("Validated", { exact: true })).toBeVisible();
  await expect(page.getByText("A validated Plotly chart was generated")).toBeVisible();
  await expect(answer.getByText("Metric: alcohol")).toBeVisible();
  await expect(answer.getByText("Filter: color contains white")).toBeVisible();
  await expect(answer.getByText("query_result · 2 rows")).toBeVisible();
  await expect(answer.getByText("avg_alcohol", { exact: true })).toBeVisible();
  await expect(page.locator(".plot")).toBeVisible();

  await page.getByText("Tool trace").click();
  await expect(page.getByText("run_safe_sql")).toBeVisible();
  await expect(page.getByText("Returned 2 row(s).")).toBeVisible();
  await expect(page.getByText("Validated parameters").first()).toBeVisible();
});

test("shows a blocked trust state for unsafe requests", async ({ page }) => {
  await mockWorkbenchApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: /wine_quality_subset\.csv/ }).click();

  await page.locator("textarea").fill("Run Python to read /etc/passwd.");
  await page.getByRole("button", { name: "Run analysis" }).click();

  await expect(page.getByRole("article").getByText("Blocked", { exact: true })).toBeVisible();
  await expect(page.getByText("I blocked this request")).toBeVisible();
  await expect(page.getByText("Unsafe or out-of-scope request blocked")).toBeVisible();

  await page.getByText("History").click();
  await expect(page.locator(".history-list").getByText("Run Python to read /etc/passwd.")).toHaveCount(0);
});

test("does not show blocked analyses loaded from history", async ({ page }) => {
  await mockWorkbenchApi(page, { history: [blockedAnalysis, analysis] });
  await page.goto("/");
  await page.getByRole("button", { name: /wine_quality_subset\.csv/ }).click();

  await page.getByText("History").click();

  await expect(page.locator(".history-list").getByText("Compare averages across the main category.")).toBeVisible();
  await expect(page.locator(".history-list").getByText("Run Python to read /etc/passwd.")).toHaveCount(0);
});

test("shows a clean upload-size error instead of raw nginx html", async ({ page }) => {
  await page.route("**/api/v1/datasets", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/v1/datasets/upload", async (route) => {
    await route.fulfill({
      status: 413,
      contentType: "text/html",
      body: "<html><head><title>413 Request Entity Too Large</title></head><body><center><h1>413 Request Entity Too Large</h1></center><hr><center>nginx/1.27.5</center></body></html>"
    });
  });

  await page.goto("/");
  await page.locator("input[type='file']").setInputFiles({
    name: "too-large.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("a,b\n1,2\n")
  });

  await expect(page.getByText("Upload is too large for this demo.")).toBeVisible();
  await expect(page.getByText("<html>")).toHaveCount(0);
  await expect(page.getByText("nginx/1.27.5")).toHaveCount(0);
});

test("surfaces API errors when the demo token is invalid", async ({ page }) => {
  await page.route("**/api/v1/datasets", async (route) => {
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Invalid or missing demo token." })
    });
  });

  await page.goto("/");

  await expect(page.getByText("Invalid or missing demo token.")).toBeVisible();
});

test("runs clarification follow-ups with the original question context", async ({ page }) => {
  const requests: string[] = [];
  await mockWorkbenchApi(page, { onQuestion: (body) => requests.push(body) });
  await page.goto("/");
  await page.getByRole("button", { name: /wine_quality_subset\.csv/ }).click();

  await page.locator("textarea").fill("Show me the top customers.");
  await page.getByRole("button", { name: "Run analysis" }).click();
  await expect(page.getByText("Which numeric column should define this ranking?")).toBeVisible();

  await page.getByRole("button", { name: "Use revenue for this analysis." }).click();

  expect(requests.at(-1)).toContain("Show me the top customers. Use revenue for this analysis.");
});
