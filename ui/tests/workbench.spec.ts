import { expect, test } from "@playwright/test";

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
  suggested_followups: ["Show the strongest data-quality risks."]
};

test.beforeEach(async ({ page }) => {
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
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/v1/datasets/demo-wine/questions", async (route) => {
    await route.fulfill({ json: analysis });
  });
});

test("runs a governed analysis from the analyst workbench", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Tabular AI Analyst" })).toBeVisible();
  await expect(page.getByText("wine_quality_subset.csv").first()).toBeVisible();
  await expect(page.getByText("Duplicate rows detected.")).toBeVisible();

  await page.locator("textarea").fill("Compare averages across the main category.");
  await page.getByRole("button", { name: "Run analysis" }).click();

  await expect(page.getByRole("heading", { name: "Analyst Answer" })).toBeVisible();
  await expect(page.getByText("validated", { exact: true })).toBeVisible();
  await expect(page.getByText("A validated Plotly chart was generated")).toBeVisible();
  await expect(page.getByText("run_safe_sql")).toBeVisible();
  await expect(page.getByText("query_result · 2 rows")).toBeVisible();
  await expect(page.getByText("avg_alcohol", { exact: true })).toBeVisible();
});
