# analytics.py
import pandas as pd
from config import CATEGORY_RULES

def apply_category_rules(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Build a text field for matching
    df["match_text"] = (
        df["merchant_name"].fillna("") + " " + df["name"].fillna("")
    ).str.lower()

    # Override category using your rules
    df["category_overridden"] = df["category"]
    for keyword, new_cat in CATEGORY_RULES:
        mask = df["match_text"].str.contains(keyword, na=False)
        df.loc[mask, "category_overridden"] = new_cat

    return df.drop(columns=["match_text"])

def add_cashflow_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Plaid amounts: typically positive = outflow (spend), negative = inflow
    df["spend"] = df["amount"].where(df["amount"] > 0, 0)
    df["income"] = (-df["amount"]).where(df["amount"] < 0, 0)
    df["net"] = df["income"] - df["spend"]
    return df

def monthly_summary(df: pd.DataFrame, category_col="category_overridden") -> pd.DataFrame:
    df = df.copy()
    df["month"] = df["date"].dt.to_period("M").astype(str)

    summary = (
        df.groupby("month")[["income", "spend", "net"]]
        .sum()
        .reset_index()
        .sort_values("month")
    )

    cat = (
        df[df["spend"] > 0]
        .groupby(["month", category_col])["spend"]
        .sum()
        .reset_index()
    )

    return summary, cat
