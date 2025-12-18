# plaid_utils.py
import datetime as dt
from typing import Tuple

import pandas as pd

from plaid.model.sandbox_public_token_create_request import (
    SandboxPublicTokenCreateRequest,
)
from plaid.model.products import Products
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.transactions_get_request import TransactionsGetRequest

from plaid_client import plaid_client


def create_sandbox_item() -> Tuple[str, str]:
    """
    Create a fake sandbox Item and return (access_token, item_id).
    """
    request = SandboxPublicTokenCreateRequest(
        institution_id="ins_109508",  # First Platypus Bank (sandbox)
        initial_products=[Products("transactions")],
        # NOTE: sandbox_public_token_create in this SDK version
        # does NOT accept 'country_codes', so we leave it out.
    )
    response = plaid_client.sandbox_public_token_create(request)
    public_token = response.public_token

    exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
    exchange_response = plaid_client.item_public_token_exchange(exchange_request)
    access_token = exchange_response.access_token
    item_id = exchange_response.item_id
    return access_token, item_id



def fetch_transactions(
    access_token: str,
    start_date: dt.date,
    end_date: dt.date,
) -> pd.DataFrame:
    """
    Fetch transactions between start_date and end_date for a given access_token.
    """
    request = TransactionsGetRequest(
        access_token=access_token,
        start_date=start_date,
        end_date=end_date,
    )
    response = plaid_client.transactions_get(request)

    accounts = response.accounts
    transactions = response.transactions

    rows = []
    account_lookup = {a.account_id: a.name for a in accounts}

    for t in transactions:
        rows.append(
            {
                "date": t.date,
                "name": t.name,
                "amount": t.amount,
                "account": account_lookup.get(t.account_id, ""),
                "category": " > ".join(t.category) if t.category else "Uncategorized",
                "merchant_name": t.merchant_name,
                "iso_currency_code": t.iso_currency_code,
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df
