import json
from typing import Any

import pandas as pd
import plotly.express as px
from plotly.utils import PlotlyJSONEncoder
from fastapi import HTTPException, status

from tabular_analyst.domain.schemas import ChartSpec


def build_chart(df: pd.DataFrame, spec: ChartSpec) -> dict[str, Any]:
    for col in [spec.x, spec.y, spec.color]:
        if col and col not in df.columns:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Chart column not found: {col}")
    if spec.chart_type == "bar":
        fig = px.bar(df, x=spec.x, y=spec.y, color=spec.color, title=spec.title)
    elif spec.chart_type == "line":
        fig = px.line(df, x=spec.x, y=spec.y, color=spec.color, title=spec.title, markers=True)
    elif spec.chart_type == "scatter":
        fig = px.scatter(df, x=spec.x, y=spec.y, color=spec.color, title=spec.title)
    elif spec.chart_type == "histogram":
        fig = px.histogram(df, x=spec.x, color=spec.color, title=spec.title)
    elif spec.chart_type == "box":
        fig = px.box(df, x=spec.x, y=spec.y, color=spec.color, title=spec.title)
    elif spec.chart_type == "heatmap":
        corr = df.select_dtypes("number").corr(numeric_only=True)
        fig = px.imshow(corr, text_auto=True, title=spec.title)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported chart type.")
    fig.update_layout(template="plotly_white", margin=dict(l=40, r=20, t=60, b=40))
    figure = json.loads(json.dumps(fig.to_dict(), cls=PlotlyJSONEncoder))
    return {"spec": spec.model_dump(), "figure": figure, "validated": True}
