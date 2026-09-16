from __future__ import annotations

import pandas as pd


def included_transactions(transactions: pd.DataFrame) -> pd.DataFrame:
    """Transactions utilisables dans les statistiques et graphiques."""
    excluded = transactions["categorie_exclue"].fillna(0).astype(int).eq(1)
    return transactions.loc[~excluded].copy()


def uncategorized_mask(transactions: pd.DataFrame) -> pd.Series:
    """Vrai lorsque les catégories calculée et forcée sont toutes deux absentes."""
    calculated = transactions["categorie"]
    forced = transactions["categorie_forcee"]
    calculated_missing = (
        calculated.isna()
        | calculated.astype("string").str.strip().eq("").fillna(False)
    )
    forced_missing = (
        forced.isna()
        | forced.astype("string").str.strip().eq("").fillna(False)
    )
    return calculated_missing & forced_missing


def selected_transaction_id(
    transaction_table: pd.DataFrame, selected_rows: list[int]
) -> int | None:
    """Retourne l’ID sélectionné, ou aucun si Streamlit conserve un index périmé."""
    if not selected_rows:
        return None
    try:
        position = int(selected_rows[0])
    except (TypeError, ValueError):
        return None
    if position < 0 or position >= len(transaction_table):
        return None
    return int(transaction_table.iloc[position]["id"])


def _monthly_category_net_amounts(transactions: pd.DataFrame) -> pd.DataFrame:
    """Solde net mensuel par catégorie, hors catégories exclues."""
    included = included_transactions(transactions)
    if included.empty:
        return pd.DataFrame(columns=["mois", "categorie", "montant"])
    selected = included.copy()
    selected["mois"] = selected["date"].dt.to_period("M").astype(str)
    selected["categorie"] = selected["categorie_effective"].fillna("Non catégorisé")
    net = selected.groupby(["mois", "categorie"], as_index=False)["montant"].sum()
    net["montant"] = net["montant"].round(2)
    return net.loc[net["montant"].ne(0)].copy()


def _monthly_category_amounts(
    transactions: pd.DataFrame, *, income: bool
) -> pd.DataFrame:
    """Répartit chaque solde net mensuel dans un seul côté du tableau."""
    net = _monthly_category_net_amounts(transactions)
    if net.empty:
        return pd.DataFrame(columns=["mois", "categorie", "montant"])
    selected = net.loc[net["montant"] > 0 if income else net["montant"] < 0].copy()
    if not income:
        selected["montant"] = -selected["montant"]
    return selected.sort_values(
        ["mois", "montant"], ascending=[True, False]
    ).reset_index(drop=True)


def monthly_category_expenses(transactions: pd.DataFrame) -> pd.DataFrame:
    """Catégories au solde mensuel net négatif, affiché en valeur positive."""
    return _monthly_category_amounts(transactions, income=False)


def monthly_category_incomes(transactions: pd.DataFrame) -> pd.DataFrame:
    """Catégories au solde mensuel net positif."""
    return _monthly_category_amounts(transactions, income=True)


def total_and_forecast_balances(
    month_balance: float, previous_month_balance: float, remaining_debits: float
) -> tuple[float, float]:
    """Calcule le solde total puis le solde restant après prélèvements à venir."""
    total_balance = round(float(month_balance) + float(previous_month_balance), 2)
    forecast_balance = round(total_balance - float(remaining_debits), 2)
    return total_balance, forecast_balance
