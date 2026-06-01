import pandas as pd
import pytest
from fastapi import HTTPException

from tabular_analyst.services.sql_safety import run_safe_sql, validate_readonly_sql


def test_select_query_is_allowed():
    assert validate_readonly_sql("select country, co2 from dataset") == "select country, co2 from dataset"


@pytest.mark.parametrize("sql", [
    "delete from dataset",
    "select * from dataset; drop table dataset",
    "copy dataset to '/tmp/out.csv'",
    "select * from read_csv('/etc/passwd')",
    "pragma show_tables",
])
def test_unsafe_sql_is_blocked(sql):
    with pytest.raises(HTTPException):
        validate_readonly_sql(sql)


def test_safe_sql_runs_with_limit():
    df = pd.DataFrame({"country": ["Spain", "France"], "co2": [1.0, 2.0]})
    result = run_safe_sql(df, 'select country, co2 from dataset order by co2 desc')
    assert result["row_count"] == 2
    assert result["rows"][0]["country"] == "France"

