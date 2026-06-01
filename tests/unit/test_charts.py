import pandas as pd

from tabular_analyst.domain.schemas import ChartSpec
from tabular_analyst.services.charts import build_chart


def test_chart_spec_builds_plotly_figure():
    df = pd.DataFrame({"year": [2020, 2021], "co2": [1.0, 2.0]})
    chart = build_chart(df, ChartSpec(chart_type="line", x="year", y="co2", title="CO2 trend"))
    assert chart["validated"] is True
    assert chart["spec"]["chart_type"] == "line"
    assert "data" in chart["figure"]

