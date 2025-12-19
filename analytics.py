
import pandas as pd
from config import CATEGORY_RULES

def apply_category_rules(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    
    df["match_text"] = (
        df["merchant_name"].fillna("") + " " + df["name"].fillna("")
    ).str.lower()

    
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

def detect_recurring_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect recurring transactions (subscriptions) by looking for merchants
    with repeated charges at roughly regular intervals.

    Assumptions:
    - `df` has columns: date (datetime), name, merchant_name, amount, spend
    - spend > 0 indicates outgoing payments

    Returns a DataFrame of likely recurring merchants.
    """
    if df.empty:
        return pd.DataFrame()

    temp = df.copy()

    #Use merchant_name if available, otherwise fallback to name
    temp["merchant"] = temp["merchant_name"].fillna(temp["name"]).fillna("Unknown")

    # Only spending (outflows)
    temp = temp[temp["spend"] > 0].copy()

    #Need at least 3 transactions from the same merchant to call it "recurring"
    grouped = temp.groupby("merchant")

    rows = []
    for merchant, g in grouped:
        g = g.sort_values("date")

        if len(g) < 3:
            continue

        #Compute day gaps between consecutive transactions
        gaps = g["date"].diff().dt.days.dropna()

        if gaps.empty:
            continue

        median_gap = float(gaps.median())
        #Subscriptions are often weekly (~7), biweekly (~14), monthly (~30), yearly (~365)
        #We'll flag common ranges with a tolerance.
        is_weekly = 5 <= median_gap <= 9
        is_biweekly = 12 <= median_gap <= 18
        is_monthly = 25 <= median_gap <= 35
        is_yearly = 330 <= median_gap <= 400

        if not (is_weekly or is_biweekly or is_monthly or is_yearly):
            continue

        avg_amount = float(g["spend"].mean())
        last_date = g["date"].max()

        if is_weekly:
            freq = "Weekly"
        elif is_biweekly:
            freq = "Biweekly"
        elif is_monthly:
            freq = "Monthly"
        else:
            freq = "Yearly"

        rows.append({
            "merchant": merchant,
            "frequency": freq,
            "avg_amount": round(avg_amount, 2),
            "last_charge": last_date.date(),
            "transactions_count": len(g),
            "median_gap_days": round(median_gap, 1),
        })

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    #Sort by estimated monthly cost 
    multiplier = {"Weekly": 4, "Biweekly": 2, "Monthly": 1, "Yearly": 1/12}
    result["est_monthly_cost"] = result["avg_amount"] * result["frequency"].map(multiplier)
    result = result.sort_values("est_monthly_cost", ascending=False).reset_index(drop=True)

    return result

def classify_transaction_type(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a `txn_type` column:
    - 'transfer' for payments/deposits/transfers that shouldn't count as spending categories
    - 'spend' for normal outflows
    - 'income' for inflows
    """
    out = df.copy()

    text = (
        out["name"].fillna("") + " " + out["merchant_name"].fillna("")
    ).str.lower()

    # Common transfer/payment keywords (tune this list over time)
    transfer_keywords = [
        "payment", "credit card", "ach", "deposit", "transfer", "zelle", "venmo", "cash app",
        "wire", "cd deposit", "checking", "savings", "pymnt", "autopay"
    ]

    is_transfer = False
    for kw in transfer_keywords:
        is_transfer = is_transfer | text.str.contains(kw, na=False)

    out["txn_type"] = "spend"
    out.loc[out["amount"] < 0, "txn_type"] = "income"
    out.loc[is_transfer, "txn_type"] = "transfer"

    # Optional: override category for transfers to make tables clearer
    out.loc[out["txn_type"] == "transfer", "category_overridden"] = "Transfers/Payments"

    return out
