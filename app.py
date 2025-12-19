
import datetime as dt
import pandas as pd
import streamlit as st
import plotly.express as px

from plaid_utils import create_sandbox_item, fetch_transactions
from analytics import apply_category_rules, add_cashflow_columns, monthly_summary
from config import DEFAULT_BUDGETS
from analytics import classify_transaction_type

st.set_page_config(
    page_title="Personal Finance Dashboard",
    layout="wide",
)

st.title("Personal Finance Dashboard (Plaid Sandbox)")
st.write(
    "This demo connects to a **fake** bank account via Plaid Sandbox, "
    "pulls transactions, and visualizes your spending."
)

# Sidebar controls 
st.sidebar.header("Controls")

if "access_token" not in st.session_state:
    st.session_state.access_token = None

# Date range
today = dt.date.today()
default_start = today - dt.timedelta(days=30)

start_date = st.sidebar.date_input("Start date", default_start)
end_date = st.sidebar.date_input("End date", today)

if start_date > end_date:
    st.sidebar.error("Start date must be before end date.")

# Button to connect sandbox account
if st.sidebar.button("Connect Sandbox Account"):
    with st.spinner("Creating sandbox item and fetching access token..."):
        access_token, item_id = create_sandbox_item()
        st.session_state.access_token = access_token
        st.success(f"Connected to sandbox item: {item_id}")

# Fetches transactions when we have an access token
df = pd.DataFrame()

if st.session_state.access_token:
    if st.sidebar.button("📥 Load Transactions"):
        with st.spinner("Fetching transactions from Plaid..."):
            df = fetch_transactions(
                st.session_state.access_token,
                start_date,
                end_date,
            )
            if df.empty:
                st.warning("No transactions for this period.")
            else:
                df = apply_category_rules(df)
                df = add_cashflow_columns(df)
                df = classify_transaction_type(df)
                st.session_state["transactions_df"] = df

    else:
        st.info("Connect a sandbox account from the sidebar to get started.")

# If we already fetched earlier, keep it in session_state
if "transactions_df" in st.session_state and df.empty:
    df = st.session_state["transactions_df"]

# --- Main content ---
if not df.empty:
    st.subheader("Overview")

       # Filters
    st.sidebar.subheader("Filters")
    category_options = ["All"] + sorted(df["category_overridden"].dropna().unique().tolist())
    selected_category = st.sidebar.selectbox("Category", category_options)
    merchant_query = st.sidebar.text_input("Search merchant/name", "")
    exclude_transfers = st.sidebar.checkbox("Exclude transfers/payments from charts", value=True)

    # Start with filtered df
    fdf = df.copy()

    if selected_category != "All":
        fdf = fdf[fdf["category_overridden"] == selected_category]

    if merchant_query.strip():
        q = merchant_query.lower().strip()
        fdf = fdf[
            fdf["name"].fillna("").str.lower().str.contains(q)
            | fdf["merchant_name"].fillna("").str.lower().str.contains(q)
        ]

    # Analysis df (used for charts)
    fdf_analysis = fdf.copy()
    if exclude_transfers:
        fdf_analysis = fdf_analysis[fdf_analysis["txn_type"] != "transfer"]

    # Top metrics
    total_income = fdf["income"].sum()
    total_spend = fdf["spend"].sum()
    net_cashflow = total_income - total_spend

    c1, c2, c3 = st.columns(3)
    c1.metric("Income", f"${total_income:,.2f}")
    c2.metric("Spending", f"${total_spend:,.2f}")
    c3.metric("Net Cashflow", f"${net_cashflow:,.2f}")

    # Monthly summary
    st.markdown("## Monthly Summary")

    msum, _ = monthly_summary(fdf_analysis)

    # Income vs Spending (bar chart)
    fig_m = px.bar(
        msum,
        x="month",
        y=["income", "spend"],
        barmode="group",
        labels={"value": "Amount ($)", "month": "Month"}
    )
    st.plotly_chart(fig_m, width="stretch")

    # Net cashflow (line chart)
    fig_net = px.line(
        msum,
        x="month",
        y="net",
        markers=True,
        labels={"net": "Net Cashflow ($)", "month": "Month"}
    )
    st.plotly_chart(fig_net, width="stretch")

    # Category breakdown (donut: top categories + Other)
    cat_spend = (
        fdf_analysis[fdf_analysis["spend"] > 0]
        .groupby("category_overridden")["spend"]
        .sum()
        .sort_values(ascending=False)
    )

    top_n = 6
    top = cat_spend.head(top_n)
    other = cat_spend.iloc[top_n:].sum()
    if other > 0:
        top = pd.concat([top, pd.Series({"Other": other})])

    cat_spend_df = top.reset_index()
    cat_spend_df.columns = ["category_overridden", "spend"]

    fig_cat = px.pie(
        cat_spend_df,
        names="category_overridden",
        values="spend",
        hole=0.5
    )
    fig_cat.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig_cat, width="stretch")

    
    # Budgets
    st.markdown("## Budgets & Alerts")

    if "budgets" not in st.session_state:
        st.session_state["budgets"] = DEFAULT_BUDGETS.copy()

    budgets = st.session_state["budgets"]

    available_cats = sorted(fdf["category_overridden"].dropna().unique().tolist())
    if available_cats:
        budget_cat = st.selectbox("Budget category", available_cats)
        new_budget = st.number_input(
            "Monthly budget ($)",
            min_value=0.0,
            value=float(budgets.get(budget_cat, 0.0)),
            step=10.0,
        )
        if st.button("Save budget"):
            budgets[budget_cat] = float(new_budget)
            st.success(f"Saved budget for {budget_cat}: ${new_budget:.0f}")

    # Current month comparison
    fdf["month"] = fdf["date"].dt.to_period("M").astype(str)
    current_month = fdf["month"].max()
    month_df = fdf[fdf["month"] == current_month]

    month_spend = (
        month_df[month_df["spend"] > 0]
        .groupby("category_overridden")["spend"]
        .sum()
        .reset_index()
    )
    month_spend["budget"] = month_spend["category_overridden"].map(budgets).fillna(0.0)
    month_spend["remaining"] = month_spend["budget"] - month_spend["spend"]

    def status_row(row):
        if row["budget"] <= 0:
            return "No budget set"
        if row["remaining"] >= 0:
            return "✅ On track"
        return "🚨 Over budget"

    month_spend["status"] = month_spend.apply(status_row, axis=1)

    st.write(f"**Current month:** {current_month}")
    st.dataframe(month_spend.sort_values("spend", ascending=False), width="stretch", hide_index=True)

    # Export
    st.markdown("## Export")
    csv = fdf.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download filtered transactions (CSV)",
        data=csv,
        file_name="transactions_filtered.csv",
        mime="text/csv",
    )

    # Transactions table
    st.markdown("## Transactions")
    st.dataframe(
        fdf.sort_values("date", ascending=False).reset_index(drop=True),
        width="stretch",
        hide_index=True,
    )
else:
    st.write("No data to display yet.")

   