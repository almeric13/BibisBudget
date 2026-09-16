from __future__ import annotations

from datetime import date
import unicodedata

import altair as alt
import pandas as pd
import streamlit as st

import analytics
import db

st.set_page_config(page_title="BudgetBibis", page_icon="💶", layout="wide")


@st.cache_data(show_spinner=False)
def transactions(database_signature: tuple[str, int, int]) -> pd.DataFrame:
    # La signature invalide automatiquement le cache après un import Talend
    # ou le remplacement du fichier SQLite.
    return db.load_transactions()


@st.cache_data(show_spinner=False)
def references(database_signature: tuple[str, int, int]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return db.load_categories(), db.load_subcategories(), db.load_labels()


@st.cache_data(show_spinner=False)
def amortizations(database_signature: tuple[str, int, int]) -> pd.DataFrame:
    return db.load_amortizations()


@st.cache_data(show_spinner=False)
def monthly_debits(database_signature: tuple[str, int, int]) -> pd.DataFrame:
    return db.load_monthly_debits()


@st.cache_data(show_spinner=False)
def loans(database_signature: tuple[str, int, int]) -> pd.DataFrame:
    return db.load_current_loans()


def clear_cache() -> None:
    transactions.clear()
    references.clear()
    amortizations.clear()
    monthly_debits.clear()
    loans.clear()


def euros(value: float) -> str:
    return f"{value:,.2f} €".replace(",", " ").replace(".", ",")


def optional_int(value: int) -> int | None:
    return int(value) if value > 0 else None


def optional_text(value: object) -> str:
    return str(value) if pd.notna(value) else ""


def alphabetical_key(value: object) -> str:
    """Tri alphabétique insensible à la casse et aux accents."""
    normalized = unicodedata.normalize("NFKD", str(value))
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def full_dataframe_height(row_count: int, row_height: int = 35) -> int:
    """Hauteur nécessaire pour afficher toutes les lignes sans défilement interne."""
    return 38 + max(int(row_count), 1) * row_height + 3


def percentage_color(value: object) -> str:
    """Couleur lisible : retard, vigilance, puis objectif atteint."""
    if pd.isna(value):
        return ""
    percentage = float(value)
    if percentage > 90:
        return "background-color: #d1fae5; color: #065f46; font-weight: 600"
    if percentage >= 70:
        return "background-color: #fef3c7; color: #92400e; font-weight: 600"
    return "background-color: #fee2e2; color: #991b1b; font-weight: 600"


def completed_financial_progress_color(value: object) -> str:
    """Colore uniquement un avancement financier exactement égal à 100 %."""
    if pd.isna(value) or float(value) != 100.0:
        return ""
    return "background-color: #d1fae5; color: #065f46; font-weight: 600"


def category_icon(category: object) -> str:
    """Pictogramme représentatif déterminé à partir du nom de catégorie."""
    normalized = alphabetical_key(category)
    icon_keywords = (
        (("maison", "logement", "habitation", "loyer"), "🏠"),
        (("course", "aliment", "supermarche", "boulanger"), "🛒"),
        (("deplacement", "voiture", "transport", "train", "peage"), "🚗"),
        (("sante", "medec", "pharmacie"), "🩺"),
        (("ecole", "education", "scolaire"), "🎓"),
        (("sortie", "loisir", "restaurant", "vacance"), "🎉"),
        (("media", "internet", "telephone", "abonnement"), "📺"),
        (("eau",), "💧"),
        (("energie", "electricite", "gaz"), "⚡"),
        (("cadeau",), "🎁"),
        (("don",), "🤝"),
        (("epargne",), "🐷"),
        (("impot", "taxe"), "🧾"),
        (("assurance",), "🛡️"),
        (("transfert", "virement"), "↔️"),
        (("retraite",), "🌴"),
        (("non categor",), "❓"),
    )
    for keywords, icon in icon_keywords:
        if any(keyword in normalized for keyword in keywords):
            return icon
    return "📦"


def monthly_expense_visual_data(expenses: pd.DataFrame, top_count: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Prépare un camembert lisible et le classement complet des catégories."""
    ranking = expenses.sort_values("montant", ascending=False).reset_index(drop=True).copy()
    total = float(ranking["montant"].sum())
    ranking["rang"] = range(1, len(ranking) + 1)
    ranking["illustration"] = ranking["categorie"].map(category_icon)
    ranking["part"] = ranking["montant"].div(total).mul(100) if total else 0.0
    ranking["categorie_illustree"] = (
        ranking["illustration"] + "  " + ranking["categorie"].astype(str)
    )

    pie = ranking.head(top_count)[["categorie_illustree", "montant"]].copy()
    if len(ranking) > top_count:
        other_amount = float(ranking.iloc[top_count:]["montant"].sum())
        pie = pd.concat(
            [
                pie,
                pd.DataFrame(
                    {"categorie_illustree": ["🧩  Autres catégories"], "montant": [other_amount]}
                ),
            ],
            ignore_index=True,
        )
    pie["part"] = pie["montant"].div(total).mul(100) if total else 0.0
    return pie, ranking


def display_monthly_balance(
    balance: float, label: str = "Solde du mois (revenus − dépenses)"
) -> None:
    """Affiche un solde avec une couleur explicite selon son signe."""
    if balance > 0:
        color, background, border, icon = "#166534", "#dcfce7", "#22c55e", "▲"
    elif balance < 0:
        color, background, border, icon = "#991b1b", "#fee2e2", "#ef4444", "▼"
    else:
        color, background, border, icon = "#334155", "#f1f5f9", "#94a3b8", "●"
    st.markdown(
        f"""
        <div style="padding: 1rem 1.25rem; border-radius: .75rem; background: {background};
                    border-left: .45rem solid {border}; margin: .6rem 0 1rem 0;">
          <div style="font-size: .9rem; color: #475569; font-weight: 600;">
            {label}
          </div>
          <div style="font-size: 2rem; color: {color}; font-weight: 750; line-height: 1.25;">
            {icon}&nbsp; {euros(balance)}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.title("💶 BudgetBibis")
try:
    fk_errors = db.verify_database()
except Exception as exc:
    st.error(f"Impossible d’ouvrir la base : {exc}")
    st.stop()
if fk_errors:
    st.error("Références invalides détectées : " + "; ".join(fk_errors))
    st.stop()

database_signature = db.database_signature()
all_tx = transactions(database_signature)
categories, subcategories, labels = references(database_signature)
all_amortizations = amortizations(database_signature)
all_monthly_debits = monthly_debits(database_signature)
all_loans = loans(database_signature)
remaining_monthly_debits = db.monthly_debits_remaining()
previous_month_balance = db.load_previous_month_balance()

with st.sidebar:
    st.header("Filtres")
    min_date = all_tx["date"].min().date()
    max_date = all_tx["date"].max().date()
    selected_dates = st.date_input(
        "Période", value=(min_date, max_date), min_value=min_date, max_value=max_date
    )
    banks = st.multiselect(
        "Banques", sorted(all_tx["banque"].dropna().unique()),
        default=sorted(all_tx["banque"].dropna().unique()),
    )
    accounts = st.multiselect(
        "Comptes", sorted(all_tx["compte"].dropna().unique()),
        default=sorted(all_tx["compte"].dropna().unique()),
    )
    category_values = sorted(all_tx["categorie_effective"].dropna().unique())
    selected_categories = st.multiselect("Catégories effectives", category_values)
    uncategorized_only = st.checkbox("Uniquement non catégorisées")
    search = st.text_input("Rechercher dans les libellés")
    st.caption(f"Base : `{db.database_path()}`")

filtered = all_tx.copy()
if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
    start, end = selected_dates
    filtered = filtered[filtered["date"].dt.date.between(start, end)]
if banks:
    filtered = filtered[filtered["banque"].isin(banks)]
else:
    filtered = filtered.iloc[0:0]
if accounts:
    filtered = filtered[filtered["compte"].isin(accounts)]
else:
    filtered = filtered.iloc[0:0]
if selected_categories:
    filtered = filtered[filtered["categorie_effective"].isin(selected_categories)]
if uncategorized_only:
    filtered = filtered[analytics.uncategorized_mask(filtered)]
if search.strip():
    needle = search.strip()
    filtered = filtered[
        filtered["libelle_originale"].str.contains(needle, case=False, na=False)
        | filtered["libelle_transforme"].str.contains(needle, case=False, na=False)
    ]

(
    page_dashboard,
    page_transactions,
    page_monthly_debits,
    page_follow_up,
    page_loans,
    page_amortizations,
    page_rules,
) = st.tabs(
    [
        "📊 Tableau de bord",
        "🧾 Transactions",
        "📅 Mensualités",
        "🎯 Suivi",
        "🏠 Emprunts",
        "🏦 Amortissements",
        "⚙️ Référentiels et règles",
    ]
)

with page_dashboard:
    statistical_tx = analytics.included_transactions(filtered)
    income = statistical_tx.loc[statistical_tx["montant"] > 0, "montant"].sum()
    expenses = -statistical_tx.loc[statistical_tx["montant"] < 0, "montant"].sum()
    net = statistical_tx["montant"].sum()
    uncategorized = int(analytics.uncategorized_mask(statistical_tx).sum())
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Entrées", euros(income))
    c2.metric("Sorties", euros(expenses))
    c3.metric("Net", euros(net))
    c4.metric("Opérations comptabilisées", f"{len(statistical_tx)}")
    c5.metric("Non catégorisées", f"{uncategorized}")
    left, right = st.columns(2)
    with left:
        st.subheader("Entrées et sorties mensuelles")
        monthly = statistical_tx.assign(
            mois=statistical_tx["date"].dt.to_period("M").astype(str)
        )
        monthly = monthly.groupby("mois").agg(
            Entrees=("montant", lambda s: s[s > 0].sum()),
            Sorties=("montant", lambda s: -s[s < 0].sum()),
        )
        st.bar_chart(monthly, x_label="Mois", y_label="Montant (€)")
    with right:
        st.subheader("Dépenses par catégorie")
        expense_categories = (
            statistical_tx[statistical_tx["montant"] < 0]
            .assign(categorie_affichee=lambda x: x["categorie_effective"].fillna("Non catégorisé"))
            .groupby("categorie_affichee")["montant"]
            .sum()
            .abs()
            .sort_values(ascending=False)
            .rename("Dépenses")
        )
        st.bar_chart(expense_categories, horizontal=True, x_label="Montant (€)")

    st.divider()
    st.subheader("Dépenses et revenus du mois par catégorie")
    if statistical_tx.empty:
        st.info("Aucune opération à afficher pour les filtres sélectionnés.")
    else:
        available_months = sorted(
            statistical_tx["date"].dt.to_period("M").astype(str).unique(),
            reverse=True,
        )
        selected_month = st.selectbox("Mois affiché", available_months)
        monthly_expenses = analytics.monthly_category_expenses(statistical_tx)
        monthly_incomes = analytics.monthly_category_incomes(statistical_tx)
        month_expenses = monthly_expenses.loc[
            monthly_expenses["mois"] == selected_month, ["categorie", "montant"]
        ].reset_index(drop=True)
        month_incomes = monthly_incomes.loc[
            monthly_incomes["mois"] == selected_month, ["categorie", "montant"]
        ].reset_index(drop=True)

        total_month_expenses = float(month_expenses["montant"].sum())
        total_month_incomes = float(month_incomes["montant"].sum())

        expenses_column, incomes_column = st.columns(2)
        with expenses_column:
            st.markdown(f"#### Dépenses — {selected_month}")
            if month_expenses.empty:
                st.info("Aucune dépense pour ce mois.")
            else:
                st.dataframe(
                    month_expenses,
                    use_container_width=True,
                    hide_index=True,
                    height=full_dataframe_height(len(month_expenses)),
                    row_height=35,
                    column_config={
                        "categorie": "Catégorie",
                        "montant": st.column_config.NumberColumn(
                            "Dépenses", format="%.2f €"
                        ),
                    },
                )
                st.metric("Total des dépenses du mois", euros(total_month_expenses))

        with incomes_column:
            st.markdown(f"#### Revenus — {selected_month}")
            if month_incomes.empty:
                st.info("Aucun revenu pour ce mois.")
            else:
                st.dataframe(
                    month_incomes,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "categorie": "Catégorie",
                        "montant": st.column_config.NumberColumn(
                            "Revenus", format="%.2f €"
                        ),
                    },
                )
                st.metric("Total des revenus du mois", euros(total_month_incomes))

        month_balance = total_month_incomes - total_month_expenses
        remaining_total = round(
            float(remaining_monthly_debits["reste_a_prelever"].sum()), 2
        )
        balance_column, previous_balance_column, remaining_column = st.columns(3)
        with balance_column:
            display_monthly_balance(month_balance)
        with previous_balance_column:
            display_monthly_balance(
                previous_month_balance, "Solde du mois précédent"
            )
            st.caption("Valeur saisie dans l’onglet Suivi.")
        with remaining_column:
            st.markdown("#### Reste à prélever ce mois")
            st.metric("Tous les comptes", euros(remaining_total))
            if remaining_monthly_debits.empty:
                st.caption("Aucun compte mensualisé enregistré.")
            else:
                for remaining in remaining_monthly_debits.itertuples():
                    st.caption(
                        f"**{remaining.banque} — {remaining.compte_bancaire}** : "
                        f"{euros(float(remaining.reste_a_prelever))}"
                    )
            st.caption(
                "Déduit uniquement du solde total pour calculer le prévisionnel."
            )

        total_balance, forecast_total_balance = analytics.total_and_forecast_balances(
            month_balance, previous_month_balance, remaining_total
        )
        total_balance_column, forecast_balance_column = st.columns(2)
        with total_balance_column:
            display_monthly_balance(
                total_balance, "Solde total (mois + mois précédent)"
            )
        with forecast_balance_column:
            display_monthly_balance(
                forecast_total_balance,
                "Solde total prévisionnel (solde total − reste à prélever)",
            )

        if not month_expenses.empty:
            pie_data, expense_ranking = monthly_expense_visual_data(month_expenses)
            category_order = pie_data["categorie_illustree"].tolist()
            palette = [
                "#2563eb", "#f97316", "#16a34a", "#9333ea",
                "#e11d48", "#0891b2", "#ca8a04", "#94a3b8",
            ]
            arcs = (
                alt.Chart(pie_data)
                .mark_arc(innerRadius=90, outerRadius=175, cornerRadius=5, padAngle=0.015)
                .encode(
                    theta=alt.Theta("montant:Q", title="Montant"),
                    color=alt.Color(
                        "categorie_illustree:N",
                        title="Catégories principales",
                        sort=category_order,
                        scale=alt.Scale(range=palette[: len(category_order)]),
                    ),
                    order=alt.Order("montant:Q", sort="descending"),
                    tooltip=[
                        alt.Tooltip("categorie_illustree:N", title="Catégorie"),
                        alt.Tooltip("montant:Q", title="Dépenses", format=".2f"),
                        alt.Tooltip("part:Q", title="Part", format=".1f"),
                    ],
                )
            )
            center_data = pd.DataFrame(
                {"titre": ["DÉPENSES"], "total": [euros(total_month_expenses)]}
            )
            center_title = alt.Chart(center_data).mark_text(
                fontSize=13, fontWeight=600, color="#64748b", dy=-10
            ).encode(text="titre:N")
            center_total = alt.Chart(center_data).mark_text(
                fontSize=19, fontWeight=700, color="#1e293b", dy=14
            ).encode(text="total:N")
            pie = (arcs + center_title + center_total).properties(
                title={
                    "text": f"Répartition des dépenses — {selected_month}",
                    "subtitle": "Les 7 catégories principales sont mises en avant",
                },
                height=440,
            )
            st.altair_chart(pie, use_container_width=True)

            st.markdown("#### Catégories les plus importantes")
            st.caption(
                "Classement décroissant de toutes les catégories ; la barre représente "
                "leur part dans les dépenses du mois."
            )
            st.dataframe(
                expense_ranking[["rang", "illustration", "categorie", "montant", "part"]],
                use_container_width=True,
                hide_index=True,
                height=full_dataframe_height(len(expense_ranking)),
                row_height=35,
                column_config={
                    "rang": st.column_config.NumberColumn("Rang", format="%d"),
                    "illustration": "Image",
                    "categorie": "Catégorie",
                    "montant": st.column_config.NumberColumn("Dépenses", format="%.2f €"),
                    "part": st.column_config.ProgressColumn(
                        "Part du mois", format="%.1f %%", min_value=0.0, max_value=100.0
                    ),
                },
            )

with page_transactions:
    st.subheader(f"Transactions filtrées ({len(filtered)})")
    display_columns = [
        "date", "date_originale", "banque", "compte", "libelle_originale", "libelle_transforme",
        "montant", "categorie_effective", "sous_categorie_effective", "categorie_exclue",
        "type_mouvement", "commentaire",
    ]
    transaction_table = filtered.reset_index(drop=True)
    table_event = st.dataframe(
        transaction_table[display_columns],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="transactions_table",
        column_config={
            "date": st.column_config.DatetimeColumn("Date effective", format="DD/MM/YYYY HH:mm"),
            "date_originale": st.column_config.DatetimeColumn(
                "Date bancaire originale", format="DD/MM/YYYY HH:mm"
            ),
            "banque": "Banque", "compte": "Compte",
            "libelle_originale": "Libellé original", "libelle_transforme": "Libellé transformé",
            "montant": st.column_config.NumberColumn("Montant", format="%.2f €"),
            "categorie_effective": "Catégorie", "sous_categorie_effective": "Sous-catégorie",
            "categorie_exclue": st.column_config.CheckboxColumn("Exclue des statistiques"),
            "type_mouvement": "Type de mouvement", "commentaire": "Commentaire",
        },
    )
    selected_rows = table_event.selection.rows
    table_selected_id = analytics.selected_transaction_id(
        transaction_table, selected_rows
    )
    if table_selected_id is not None:
        if st.session_state.get("last_table_selected_transaction_id") != table_selected_id:
            st.session_state["selected_transaction_id"] = table_selected_id
            st.session_state["last_table_selected_transaction_id"] = table_selected_id

    st.caption(
        "Sélectionnez une ligne du tableau pour ouvrir directement cette transaction "
        "dans le formulaire de modification."
    )
    st.divider()
    st.subheader("Modifier une transaction")
    if filtered.empty:
        st.info("Aucune transaction ne correspond aux filtres.")
    else:
        options = filtered["id"].astype("int64").tolist()
        by_id = filtered.set_index("id")
        if st.session_state.get("selected_transaction_id") not in options:
            st.session_state["selected_transaction_id"] = options[0]
        selected_id = st.selectbox(
            "Transaction",
            options,
            key="selected_transaction_id",
            format_func=lambda tx_id: (
                f"{by_id.loc[tx_id, 'date']:%d/%m/%Y} — "
                f"{by_id.loc[tx_id, 'montant']:.2f} € — "
                f"{str(by_id.loc[tx_id, 'libelle_originale'])[:80]}"
            ),
        )
        row = by_id.loc[selected_id]
        active_categories = sorted(
            (r for r in categories.itertuples() if r.actif == 1),
            key=lambda r: alphabetical_key(r.nom),
        )
        category_map = {int(r.id): str(r.nom) for r in active_categories}
        active_subcategories = subcategories.loc[subcategories["actif"].eq(1)].copy()
        category_options = [0] + list(category_map)
        current_cat = int(row["id_categorie_forcee"]) if pd.notna(row["id_categorie_forcee"]) else 0
        current_sub = int(row["id_sous_categorie_forcee"]) if pd.notna(row["id_sous_categorie_forcee"]) else 0
        st.caption(
            f"Valeur calculée : {row['categorie'] or '—'} / {row['sous_categorie'] or '—'}"
        )
        col1, col2 = st.columns(2)
        category_key = f"edit_transaction_category_{selected_id}"
        subcategory_key = f"edit_transaction_subcategory_{selected_id}"
        forced_cat = col1.selectbox(
            "Catégorie forcée", category_options,
            index=category_options.index(current_cat),
            format_func=lambda x: "— Aucune —" if x == 0 else category_map[x],
            key=category_key,
            help="Le choix d’une catégorie filtre immédiatement les sous-catégories.",
        )
        matching_subcategories = sorted(
            active_subcategories.loc[
                active_subcategories["id_categorie"].eq(forced_cat)
            ].itertuples(),
            key=lambda r: alphabetical_key(r.nom),
        )
        subcategory_map = {
            int(r.id): str(r.nom) for r in matching_subcategories
        }
        subcategory_options = [0] + list(subcategory_map)
        if subcategory_key not in st.session_state:
            st.session_state[subcategory_key] = (
                current_sub if current_sub in subcategory_options else 0
            )
        elif st.session_state[subcategory_key] not in subcategory_options:
            st.session_state[subcategory_key] = 0
        forced_sub = col2.selectbox(
            "Sous-catégorie forcée", subcategory_options,
            format_func=lambda x: "— Aucune —" if x == 0 else subcategory_map[x],
            key=subcategory_key,
            disabled=forced_cat == 0,
            help=(
                "Seules les sous-catégories de la catégorie sélectionnée sont proposées."
                if forced_cat != 0 else "Sélectionnez d’abord une catégorie."
            ),
        )
        original_date = row["date_originale"].date()
        effective_date = row["date"].date()
        use_original_date = st.checkbox(
            "Utiliser la date bancaire originale",
            value=pd.isna(row["date_forcee"]),
            key=f"edit_transaction_original_date_{selected_id}",
            help="Décochez pour décaler cette transaction dans le suivi, les filtres et les statistiques.",
        )
        forced_date_value = st.date_input(
            "Date effective forcée",
            value=effective_date,
            disabled=use_original_date,
            key=f"edit_transaction_forced_date_{selected_id}",
        )
        st.caption(f"Date bancaire originale conservée : {original_date:%d/%m/%Y}")
        movement = st.text_input(
            "Type de mouvement", value=row["type_mouvement"] or "",
            key=f"edit_transaction_movement_{selected_id}",
        )
        comment = st.text_area(
            "Commentaire", value=row["commentaire"] or "",
            key=f"edit_transaction_comment_{selected_id}",
        )
        save = st.button(
            "Enregistrer", type="primary", key=f"save_transaction_{selected_id}"
        )
        if save:
            try:
                db.update_transaction(
                    int(selected_id), optional_int(forced_cat), optional_int(forced_sub),
                    movement, comment, None if use_original_date else forced_date_value,
                )
                clear_cache()
                st.success("Transaction enregistrée.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

with page_monthly_debits:
    st.subheader(f"Prélèvements mensualisés ({len(all_monthly_debits)})")
    st.caption(
        "Ces prélèvements déjà autorisés servent à prévoir les montants à venir. "
        "Toutes les données sont modifiables, sauf l’identifiant."
    )
    monthly_debit_display = all_monthly_debits[
        [
            "nom", "mensualite", "methode_paiment", "jourDePrelevement",
            "ancienneMensualite", "categorie", "sous_categorie", "banque",
            "compteBancaire",
        ]
    ].copy()
    st.dataframe(
        monthly_debit_display,
        use_container_width=True,
        hide_index=True,
        height=full_dataframe_height(len(monthly_debit_display)),
        column_config={
            "nom": "Nom",
            "mensualite": st.column_config.NumberColumn("Mensualité", format="%.2f €"),
            "methode_paiment": "Méthode de paiement",
            "jourDePrelevement": st.column_config.NumberColumn(
                "Jour de prélèvement", format="%d"
            ),
            "ancienneMensualite": st.column_config.NumberColumn(
                "Ancienne mensualité", format="%.2f €"
            ),
            "categorie": "Catégorie",
            "sous_categorie": "Sous-catégorie",
            "banque": "Banque",
            "compteBancaire": "Compte bancaire",
        },
    )

    monthly_categories = sorted(
        (r for r in categories.itertuples() if int(r.actif) == 1),
        key=lambda r: alphabetical_key(r.nom),
    )
    monthly_category_map = {int(r.id): str(r.nom) for r in monthly_categories}
    monthly_category_options = [0] + list(monthly_category_map)
    monthly_active_subcategories = subcategories.loc[subcategories["actif"].eq(1)].copy()

    edit_monthly_tab, create_monthly_tab, delete_monthly_tab = st.tabs(
        ["Modifier", "Créer", "Supprimer"]
    )

    if all_monthly_debits.empty:
        with edit_monthly_tab:
            st.info("Aucune mensualité à modifier.")
        with delete_monthly_tab:
            st.info("Aucune mensualité à supprimer.")
    else:
        monthly_names = {
            int(r.id): f"{r.nom} — {euros(float(r.mensualite or 0))}"
            for r in all_monthly_debits.itertuples()
        }
        selected_monthly_id = st.selectbox(
            "Mensualité sélectionnée",
            list(monthly_names),
            format_func=monthly_names.get,
            key="selected_monthly_debit_id",
        )
        selected_monthly = all_monthly_debits.set_index("id").loc[selected_monthly_id]

        with edit_monthly_tab:
            current_category = (
                int(selected_monthly["id_categorie"])
                if pd.notna(selected_monthly["id_categorie"])
                and int(selected_monthly["id_categorie"]) in monthly_category_options
                else 0
            )
            edit_monthly_category_key = f"edit_monthly_category_{selected_monthly_id}"
            edit_monthly_subcategory_key = f"edit_monthly_subcategory_{selected_monthly_id}"
            edit_ref_left, edit_ref_right = st.columns(2)
            edit_monthly_category = edit_ref_left.selectbox(
                "Catégorie",
                monthly_category_options,
                index=monthly_category_options.index(current_category),
                format_func=lambda item: (
                    "— Aucune —" if item == 0 else monthly_category_map[item]
                ),
                key=edit_monthly_category_key,
            )
            edit_matching_monthly_subcategories = sorted(
                monthly_active_subcategories.loc[
                    monthly_active_subcategories["id_categorie"].eq(edit_monthly_category)
                ].itertuples(),
                key=lambda r: alphabetical_key(r.nom),
            )
            edit_monthly_subcategory_map = {
                int(r.id): str(r.nom) for r in edit_matching_monthly_subcategories
            }
            edit_monthly_subcategory_options = [0] + list(edit_monthly_subcategory_map)
            current_subcategory = (
                int(selected_monthly["id_sous_categorie"])
                if pd.notna(selected_monthly["id_sous_categorie"])
                and int(selected_monthly["id_sous_categorie"])
                in edit_monthly_subcategory_options
                else 0
            )
            if edit_monthly_subcategory_key not in st.session_state:
                st.session_state[edit_monthly_subcategory_key] = current_subcategory
            elif st.session_state[edit_monthly_subcategory_key] not in edit_monthly_subcategory_options:
                st.session_state[edit_monthly_subcategory_key] = 0
            edit_monthly_subcategory = edit_ref_right.selectbox(
                "Sous-catégorie",
                edit_monthly_subcategory_options,
                format_func=lambda item: (
                    "— Aucune —" if item == 0 else edit_monthly_subcategory_map[item]
                ),
                key=edit_monthly_subcategory_key,
                disabled=edit_monthly_category == 0,
            )
            with st.form(f"edit_monthly_debit_{selected_monthly_id}"):
                edit_left, edit_right = st.columns(2)
                edit_monthly_name = edit_left.text_input(
                    "Nom *", value=str(selected_monthly["nom"] or "")
                )
                edit_monthly_amount = edit_right.number_input(
                    "Mensualité *", min_value=0.0,
                    value=float(selected_monthly["mensualite"] or 0), step=0.01,
                )
                edit_payment_method = edit_left.text_input(
                    "Méthode de paiement",
                    value=optional_text(selected_monthly["methode_paiment"]),
                )
                edit_debit_day = edit_right.number_input(
                    "Jour de prélèvement *", min_value=1, max_value=31,
                    value=max(1, min(31, int(selected_monthly["jourDePrelevement"] or 1))),
                    step=1,
                )
                old_amount = selected_monthly["ancienneMensualite"]
                edit_old_monthly_amount = edit_left.number_input(
                    "Ancienne mensualité", min_value=0.0,
                    value=float(old_amount) if pd.notna(old_amount) else None,
                    step=0.01,
                )
                edit_bank = edit_right.text_input(
                    "Banque", value=optional_text(selected_monthly["banque"])
                )
                edit_bank_account = st.text_input(
                    "Compte bancaire",
                    value=optional_text(selected_monthly["compteBancaire"]),
                )
                save_monthly_debit = st.form_submit_button("Enregistrer", type="primary")
            if save_monthly_debit:
                try:
                    db.update_monthly_debit(
                        int(selected_monthly_id), edit_monthly_name,
                        float(edit_monthly_amount), edit_payment_method,
                        int(edit_debit_day),
                        float(edit_old_monthly_amount)
                        if edit_old_monthly_amount is not None else None,
                        optional_int(edit_monthly_category),
                        optional_int(edit_monthly_subcategory),
                        edit_bank, edit_bank_account,
                    )
                    clear_cache()
                    st.success("Mensualité enregistrée.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        with delete_monthly_tab:
            st.warning(
                f"La mensualité « {selected_monthly['nom']} » sera supprimée définitivement."
            )
            with st.form(f"delete_monthly_debit_{selected_monthly_id}"):
                confirm_monthly_delete = st.checkbox(
                    "Je confirme la suppression définitive de cette mensualité."
                )
                delete_monthly_submitted = st.form_submit_button("Supprimer")
            if delete_monthly_submitted:
                if not confirm_monthly_delete:
                    st.error("Cochez la confirmation avant de supprimer la mensualité.")
                else:
                    try:
                        db.delete_monthly_debit(int(selected_monthly_id))
                        clear_cache()
                        st.success("Mensualité supprimée.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

    with create_monthly_tab:
        create_monthly_ref_left, create_monthly_ref_right = st.columns(2)
        create_monthly_category = create_monthly_ref_left.selectbox(
            "Catégorie",
            monthly_category_options,
            format_func=lambda item: (
                "— Aucune —" if item == 0 else monthly_category_map[item]
            ),
            key="create_monthly_category",
        )
        create_matching_monthly_subcategories = sorted(
            monthly_active_subcategories.loc[
                monthly_active_subcategories["id_categorie"].eq(create_monthly_category)
            ].itertuples(),
            key=lambda r: alphabetical_key(r.nom),
        )
        create_monthly_subcategory_map = {
            int(r.id): str(r.nom) for r in create_matching_monthly_subcategories
        }
        create_monthly_subcategory_options = [0] + list(create_monthly_subcategory_map)
        if st.session_state.get("create_monthly_subcategory", 0) not in create_monthly_subcategory_options:
            st.session_state["create_monthly_subcategory"] = 0
        create_monthly_subcategory = create_monthly_ref_right.selectbox(
            "Sous-catégorie",
            create_monthly_subcategory_options,
            format_func=lambda item: (
                "— Aucune —" if item == 0 else create_monthly_subcategory_map[item]
            ),
            key="create_monthly_subcategory",
            disabled=create_monthly_category == 0,
        )
        with st.form("create_monthly_debit", clear_on_submit=True):
            create_left, create_right = st.columns(2)
            create_monthly_name = create_left.text_input("Nom *")
            create_monthly_amount = create_right.number_input(
                "Mensualité *", min_value=0.0, value=0.0, step=0.01
            )
            create_payment_method = create_left.text_input("Méthode de paiement")
            create_debit_day = create_right.number_input(
                "Jour de prélèvement *", min_value=1, max_value=31, value=1, step=1
            )
            create_old_monthly_amount = create_left.number_input(
                "Ancienne mensualité", min_value=0.0, value=None, step=0.01
            )
            create_bank = create_right.text_input("Banque")
            create_bank_account = st.text_input("Compte bancaire")
            create_monthly_submitted = st.form_submit_button("Créer", type="primary")
        if create_monthly_submitted:
            try:
                new_monthly_id = db.create_monthly_debit(
                    create_monthly_name, float(create_monthly_amount),
                    create_payment_method, int(create_debit_day),
                    float(create_old_monthly_amount)
                    if create_old_monthly_amount is not None else None,
                    optional_int(create_monthly_category),
                    optional_int(create_monthly_subcategory),
                    create_bank, create_bank_account,
                )
                clear_cache()
                st.success(f"Mensualité {new_monthly_id} créée.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


with page_follow_up:
    st.subheader("Suivi du transfert vers Trade Republic")
    follow_up = db.monthly_follow_up()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Mensualités Trade Republic", euros(follow_up["trade_republic_total"]))
    m2.metric("Mensualités des amortissements", euros(follow_up["amortization_total"]))
    m3.metric("Surplus souhaité", euros(follow_up["desired_surplus"]))
    m4.metric("Solde du mois précédent", euros(previous_month_balance))

    with st.form("desired_amortization_surplus"):
        desired_surplus = st.number_input(
            "Surplus souhaité lors d’une mensualité globale",
            min_value=0.0,
            value=float(follow_up["desired_surplus"]),
            step=0.01,
            help="Cette valeur est enregistrée dans la base et préremplit la mensualité globale.",
        )
        save_desired_surplus = st.form_submit_button("Enregistrer le surplus")
    if save_desired_surplus:
        try:
            db.update_desired_amortization_surplus(float(desired_surplus))
            clear_cache()
            st.success("Surplus souhaité enregistré.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    with st.form("previous_month_balance"):
        entered_previous_month_balance = st.number_input(
            "Solde du mois précédent",
            value=float(previous_month_balance),
            step=0.01,
            help="Cette valeur est enregistrée dans la base et affichée dans le tableau de bord.",
        )
        save_previous_month_balance = st.form_submit_button(
            "Enregistrer le solde du mois précédent"
        )
    if save_previous_month_balance:
        try:
            db.update_previous_month_balance(float(entered_previous_month_balance))
            clear_cache()
            st.success("Solde du mois précédent enregistré.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    projected_transfer = round(
        follow_up["trade_republic_total"]
        + follow_up["amortization_total"]
        + float(desired_surplus),
        2,
    )
    st.markdown("### Somme à transférer mensuellement vers Trade Republic")
    st.metric("Trade Republic + amortissements + surplus", euros(projected_transfer))
    st.caption(
        "Ce montant dépend uniquement des mensualités Trade Republic, des amortissements "
        "et du surplus souhaité."
    )

    st.markdown("### Minimum montant Trade Republic")
    st.metric(
        "Mensualités Trade Republic + soldes des amortissements + amortissement manuel",
        euros(follow_up["minimum_trade_republic"]),
    )
    st.caption(
        f"{euros(follow_up['trade_republic_total'])} + "
        f"{euros(follow_up['amortization_balances_total'])} + "
        f"{euros(follow_up['manual_amortization_balance'])}."
    )

    st.divider()
    st.subheader("Reste à prélever ce mois — tous les comptes")
    st.caption(
        "Information indépendante du transfert vers Trade Republic. Une mensualité prévue "
        "aujourd’hui est considérée comme restant à prélever."
    )
    remaining_total = float(remaining_monthly_debits["reste_a_prelever"].sum())
    st.metric("Reste total à prélever", euros(remaining_total))
    if remaining_monthly_debits.empty:
        st.info("Aucun prélèvement mensualisé enregistré.")
    else:
        remaining_display = remaining_monthly_debits.rename(
            columns={
                "banque": "Banque",
                "compte_bancaire": "Compte bancaire",
                "nombre_mensualites": "Nombre de mensualités",
                "total_mensuel": "Total mensuel",
                "reste_a_prelever": "Reste à prélever",
            }
        )
        st.dataframe(
            remaining_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Nombre de mensualités": st.column_config.NumberColumn(format="%d"),
                "Total mensuel": st.column_config.NumberColumn(format="%.2f €"),
                "Reste à prélever": st.column_config.NumberColumn(format="%.2f €"),
            },
        )


with page_loans:
    st.subheader(f"Emprunts en cours ({len(all_loans)})")
    st.caption(
        "Un emprunt est considéré en cours tant que son restant à rembourser est supérieur à 0 €."
    )
    if all_loans.empty:
        st.info("Aucun emprunt en cours.")
    else:
        loan_display = all_loans[
            [
                "nom", "montantEmprunte", "restantARembourse",
                "avancement_pourcentage", "date_fin_emprunt_affichee",
            ]
        ].copy()
        loan_display["nom"] = [
            str(row.nom) if pd.notna(row.nom) and str(row.nom).strip()
            else f"Emprunt #{int(row.id)}"
            for row in all_loans.itertuples()
        ]
        st.dataframe(
            loan_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "nom": "Nom",
                "montantEmprunte": st.column_config.NumberColumn(
                    "Montant emprunté", format="%.2f €"
                ),
                "restantARembourse": st.column_config.NumberColumn(
                    "Restant à rembourser", format="%.2f €"
                ),
                "avancement_pourcentage": st.column_config.NumberColumn(
                    "Avancement du remboursement", format="%.2f %%"
                ),
                "date_fin_emprunt_affichee": st.column_config.DateColumn(
                    "Date de fin", format="DD/MM/YYYY"
                ),
            },
        )

        loan_names = {
            int(row.id): (
                str(row.nom) if pd.notna(row.nom) and str(row.nom).strip()
                else f"Emprunt #{int(row.id)}"
            )
            for row in all_loans.itertuples()
        }
        selected_loan_id = st.selectbox(
            "Emprunt à mettre à jour",
            options=list(loan_names),
            format_func=loan_names.get,
            key="selected_loan_id",
        )
        selected_loan = all_loans.set_index("id").loc[selected_loan_id]
        with st.form(f"update_loan_{selected_loan_id}"):
            updated_remaining_balance = st.number_input(
                "Restant à rembourser",
                min_value=0.0,
                max_value=float(selected_loan["montantEmprunte"]),
                value=float(selected_loan["restantARembourse"]),
                step=0.01,
            )
            save_loan = st.form_submit_button("Enregistrer", type="primary")
        if save_loan:
            try:
                db.update_loan_remaining_balance(
                    int(selected_loan_id), float(updated_remaining_balance)
                )
                clear_cache()
                st.success("Restant à rembourser enregistré.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


with page_amortizations:
    active_amortization_categories = sorted(
        (r for r in categories.itertuples() if int(r.actif) == 1),
        key=lambda r: alphabetical_key(r.nom),
    )
    active_category_map = {
        int(r.id): str(r.nom) for r in active_amortization_categories
    }
    active_amortization_subcategories = subcategories.loc[
        subcategories["actif"].eq(1)
    ].copy()
    amortization_category_options = [0] + list(active_category_map)
    account_choices = db.load_account_choices()
    st.subheader(f"Amortissements ({len(all_amortizations)})")
    if all_amortizations.empty:
        st.info("Aucun amortissement n’est présent dans la base.")
    else:
        amortization_display = all_amortizations[
            [
                "nom", "solde", "objectif", "avancement_pourcentage",
                "progression_pourcentage", "mois", "mois_restant",
                "mensualite", "mensualite_ajustee", "categorie", "sous_categorie",
                "date_cible_affichee", "date_dernier_paiement_affichee", "commentaire",
            ]
        ]
        styled_amortizations = (
            amortization_display.style
            .map(percentage_color, subset=["progression_pourcentage"])
            .map(
                completed_financial_progress_color,
                subset=["avancement_pourcentage"],
            )
        )
        st.dataframe(
            styled_amortizations,
            use_container_width=True,
            hide_index=True,
            column_config={
                "nom": "Nom",
                "solde": st.column_config.NumberColumn("Solde", format="%.2f €"),
                "objectif": st.column_config.NumberColumn("Objectif", format="%.2f €"),
                "avancement_pourcentage": st.column_config.NumberColumn(
                    "Avancement financier", format="%.2f %%"
                ),
                "progression_pourcentage": st.column_config.NumberColumn(
                    "Progression des mensualités", format="%.2f %%",
                    help="100 % signifie que les mensualités suivent le rythme attendu.",
                ),
                "mois": "Nombre de mois",
                "mois_restant": "Mois restants",
                "mensualite": st.column_config.NumberColumn("Mensualité", format="%.2f €"),
                "mensualite_ajustee": st.column_config.NumberColumn(
                    "Mensualité ajustée", format="%.2f €"
                ),
                "categorie": "Catégorie des transactions",
                "sous_categorie": "Sous-catégorie des transactions",
                "date_cible_affichee": st.column_config.DatetimeColumn(
                    "Date cible", format="DD/MM/YYYY"
                ),
                "date_dernier_paiement_affichee": st.column_config.DatetimeColumn(
                    "Dernier paiement effectif", format="DD/MM/YYYY"
                ),
                "commentaire": "Commentaire",
            },
        )
        manual_account = db.load_manual_amortization_account()
        account_metric, account_editor = st.columns([1, 2])
        account_metric.metric(
            "Solde amortissement manuel", euros(float(manual_account["solde"]))
        )
        with account_editor.form("edit_manual_amortization_account"):
            manual_balance = st.number_input(
                "Modifier le solde du compte amortissementManuel",
                min_value=0.0,
                value=float(manual_account["solde"]),
                step=0.01,
                help="Cette modification n’a aucun impact sur les amortissements ou les transactions.",
            )
            save_manual_balance = st.form_submit_button("Enregistrer le solde")
        if save_manual_balance:
            try:
                db.update_manual_amortization_balance(float(manual_balance))
                clear_cache()
                st.success("Solde du compte amortissementManuel enregistré.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        amortization_names = {
            int(r.id): f"{r.nom} — {euros(float(r.solde or 0))} / {euros(float(r.objectif or 0))}"
            for r in all_amortizations.itertuples()
        }
        selected_amortization_id = st.selectbox(
            "Amortissement à modifier ou à transférer comme revenu",
            list(amortization_names),
            format_func=amortization_names.get,
            key="selected_amortization_id",
        )
        selected_amortization = all_amortizations.set_index("id").loc[selected_amortization_id]

        edit_amortization_tab, create_amortization_tab, contribution_tab, withdrawal_tab = st.tabs(
            [
                "Modifier", "Créer", "Enregistrer les mensualités globales",
                "Transférer comme revenu",
            ]
        )
        with edit_amortization_tab:
            target_value = (
                selected_amortization["date_cible_affichee"].date()
                if pd.notna(selected_amortization["date_cible_affichee"])
                else None
            )
            last_payment_value = (
                selected_amortization["date_dernier_paiement_affichee"].date()
                if pd.notna(selected_amortization["date_dernier_paiement_affichee"])
                else None
            )
            current_amortization_category = (
                int(selected_amortization["id_categorie"])
                if pd.notna(selected_amortization["id_categorie"])
                and int(selected_amortization["id_categorie"]) in amortization_category_options
                else 0
            )
            edit_category_key = f"edit_amortization_category_{selected_amortization_id}"
            edit_subcategory_key = f"edit_amortization_subcategory_{selected_amortization_id}"
            edit_reference_left, edit_reference_right = st.columns(2)
            edit_amortization_category = edit_reference_left.selectbox(
                "Catégorie des transactions",
                amortization_category_options,
                index=amortization_category_options.index(current_amortization_category),
                format_func=lambda item: (
                    "— Aucune —" if item == 0 else active_category_map[item]
                ),
                key=edit_category_key,
            )
            edit_matching_subcategories = sorted(
                active_amortization_subcategories.loc[
                    active_amortization_subcategories["id_categorie"].eq(
                        edit_amortization_category
                    )
                ].itertuples(),
                key=lambda r: alphabetical_key(r.nom),
            )
            edit_subcategory_map = {
                int(r.id): str(r.nom) for r in edit_matching_subcategories
            }
            edit_subcategory_options = [0] + list(edit_subcategory_map)
            current_amortization_subcategory = (
                int(selected_amortization["id_sous_categorie"])
                if pd.notna(selected_amortization["id_sous_categorie"])
                and int(selected_amortization["id_sous_categorie"])
                in edit_subcategory_options
                else 0
            )
            if edit_subcategory_key not in st.session_state:
                st.session_state[edit_subcategory_key] = current_amortization_subcategory
            elif st.session_state[edit_subcategory_key] not in edit_subcategory_options:
                st.session_state[edit_subcategory_key] = 0
            edit_amortization_subcategory = edit_reference_right.selectbox(
                "Sous-catégorie des transactions",
                edit_subcategory_options,
                format_func=lambda item: (
                    "— Aucune —" if item == 0 else edit_subcategory_map[item]
                ),
                key=edit_subcategory_key,
                disabled=edit_amortization_category == 0,
            )
            with st.form(f"edit_amortization_{selected_amortization_id}"):
                edit_left, edit_right = st.columns(2)
                amortization_name = edit_left.text_input(
                    "Nom *", value=str(selected_amortization["nom"] or "")
                )
                amortization_balance = edit_right.number_input(
                    "Solde *", min_value=0.0,
                    value=float(selected_amortization["solde"] or 0), step=0.01
                )
                amortization_objective = edit_left.number_input(
                    "Objectif *", min_value=0.01,
                    value=float(selected_amortization["objectif"] or 0.01), step=0.01
                )
                old_objective_value = selected_amortization["ancien_objectif"]
                amortization_old_objective = edit_right.number_input(
                    "Ancien objectif", min_value=0.0,
                    value=float(old_objective_value) if pd.notna(old_objective_value) else 0.0,
                    step=0.01,
                )
                amortization_months = edit_left.number_input(
                    "Nombre de mois *", min_value=1,
                    value=max(1, int(selected_amortization["mois"] or 1)), step=1
                )
                amortization_monthly_payment = edit_right.number_input(
                    "Mensualité *", min_value=0.0,
                    value=float(selected_amortization["mensualite"] or 0), step=0.01
                )
                amortization_target = edit_left.date_input(
                    "Date cible", value=target_value
                )
                amortization_last_payment = edit_right.date_input(
                    "Date du dernier paiement effectif",
                    value=last_payment_value,
                    help="Cette date n’est jamais modifiée lors de l’enregistrement d’une mensualité.",
                )
                amortization_comment = st.text_area(
                    "Commentaire", value=str(selected_amortization["commentaire"] or "")
                )
                save_amortization = st.form_submit_button("Enregistrer", type="primary")
            if save_amortization:
                try:
                    db.update_amortization(
                        int(selected_amortization_id), amortization_name,
                        float(amortization_balance), float(amortization_objective),
                        float(amortization_old_objective), int(amortization_months),
                        float(amortization_monthly_payment), amortization_target,
                        amortization_last_payment, amortization_comment,
                        category_id=(
                            int(edit_amortization_category)
                            if edit_amortization_category else None
                        ),
                        subcategory_id=(
                            int(edit_amortization_subcategory)
                            if edit_amortization_subcategory else None
                        ),
                    )
                    clear_cache()
                    st.success("Amortissement enregistré et indicateurs recalculés.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        with create_amortization_tab:
            st.caption(
                "L’association choisie préremplira la catégorie de la transaction "
                "créée pour cet amortissement lors d’une mensualité globale."
            )
            create_reference_left, create_reference_right = st.columns(2)
            create_amortization_category = create_reference_left.selectbox(
                "Catégorie des transactions *",
                amortization_category_options,
                format_func=lambda item: (
                    "— Aucune —" if item == 0 else active_category_map[item]
                ),
                key="create_amortization_category",
            )
            create_matching_subcategories = sorted(
                active_amortization_subcategories.loc[
                    active_amortization_subcategories["id_categorie"].eq(
                        create_amortization_category
                    )
                ].itertuples(),
                key=lambda r: alphabetical_key(r.nom),
            )
            create_subcategory_map = {
                int(r.id): str(r.nom) for r in create_matching_subcategories
            }
            create_subcategory_options = [0] + list(create_subcategory_map)
            if st.session_state.get("create_amortization_subcategory", 0) not in create_subcategory_options:
                st.session_state["create_amortization_subcategory"] = 0
            create_amortization_subcategory = create_reference_right.selectbox(
                "Sous-catégorie des transactions",
                create_subcategory_options,
                format_func=lambda item: (
                    "— Aucune —" if item == 0 else create_subcategory_map[item]
                ),
                key="create_amortization_subcategory",
                disabled=create_amortization_category == 0,
            )
            with st.form("create_amortization_form", clear_on_submit=True):
                create_left, create_right = st.columns(2)
                create_name = create_left.text_input("Nom *")
                create_balance = create_right.number_input(
                    "Solde actuel *", min_value=0.0, value=0.0, step=0.01
                )
                create_objective = create_left.number_input(
                    "Objectif *", min_value=0.01, value=100.0, step=0.01
                )
                create_old_objective = create_right.number_input(
                    "Ancien objectif", min_value=0.0, value=0.0, step=0.01
                )
                create_months = create_left.number_input(
                    "Nombre de mois *", min_value=1, value=12, step=1
                )
                create_monthly_payment = create_right.number_input(
                    "Mensualité *", min_value=0.0, value=0.0, step=0.01
                )
                create_target = create_left.date_input(
                    "Date cible", value=date.today()
                )
                create_last_payment = create_right.date_input(
                    "Date du dernier paiement effectif", value=None
                )
                create_comment = st.text_area("Commentaire")
                create_submitted = st.form_submit_button("Créer", type="primary")
            if create_submitted:
                try:
                    new_amortization_id = db.create_amortization(
                        create_name,
                        float(create_balance),
                        float(create_objective),
                        float(create_old_objective) if create_old_objective else None,
                        int(create_months),
                        float(create_monthly_payment),
                        create_target,
                        create_last_payment,
                        create_comment,
                        int(create_amortization_category) if create_amortization_category else None,
                        int(create_amortization_subcategory) if create_amortization_subcategory else None,
                    )
                    clear_cache()
                    st.success(f"Amortissement {new_amortization_id} créé.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        active_subcategory_map = {
            int(r.id): f"{r.categorie} › {r.nom}"
            for r in active_amortization_subcategories.itertuples()
        }
        amortization_subcategory_options = [0] + list(active_subcategory_map)

        with contribution_tab:
            total_monthly_payments = db.total_amortization_monthly_payments()
            desired_surplus = db.load_desired_amortization_surplus()
            suggested_global_amount = round(total_monthly_payments + desired_surplus, 2)
            st.metric("Somme des mensualités à répartir", euros(total_monthly_payments))
            st.metric("Surplus souhaité enregistré", euros(desired_surplus))
            st.caption(
                "Crée une transaction négative par amortissement pour sa mensualité. "
                "L’éventuel surplus crée une transaction Épargne et est versé sur "
                "amortissementManuel. Chaque transaction utilise l’association de son "
                "amortissement ; les choix ci-dessous servent à l’Épargne et de repli "
                "si aucune association n’est définie. La somme des transactions correspond "
                "exactement à la somme globale saisie. Les dates de dernier paiement restent inchangées."
            )
            with st.form("global_amortization_contribution", clear_on_submit=True):
                contribution_date = st.date_input("Date *", value=date.today(), key="contribution_date")
                contribution_account = st.selectbox(
                    "Banque et compte *", account_choices,
                    format_func=lambda item: f"{item[0]} — {item[1]}",
                    key="contribution_account",
                )
                contribution_amount = st.number_input(
                    "Somme globale versée *",
                    min_value=total_monthly_payments,
                    value=suggested_global_amount,
                    step=0.01,
                    help=(
                        "Le montant prérempli correspond à la somme des mensualités "
                        "d’amortissement et du surplus souhaité enregistré dans Suivi."
                    ),
                )
                st.caption(
                    f"Surplus vers amortissementManuel : "
                    f"{euros(max(0.0, float(contribution_amount) - total_monthly_payments))}"
                )
                contribution_label = st.text_input(
                    "Libellé *", value="Mensualités globales des amortissements"
                )
                contribution_category = st.selectbox(
                    "Catégorie de repli et de l’Épargne", amortization_category_options,
                    format_func=lambda item: "— Aucune —" if item == 0 else active_category_map[item],
                    key="contribution_category",
                )
                contribution_subcategory = st.selectbox(
                    "Sous-catégorie de repli et de l’Épargne", amortization_subcategory_options,
                    format_func=lambda item: "— Aucune —" if item == 0 else active_subcategory_map[item],
                    key="contribution_subcategory",
                )
                contribution_comment = st.text_area("Commentaire", key="contribution_comment")
                create_contribution = st.form_submit_button("Enregistrer les mensualités", type="primary")
            if create_contribution:
                try:
                    transaction_ids, distributed, surplus = db.create_global_amortization_contribution(
                        float(contribution_amount), contribution_date,
                        contribution_account[0], contribution_account[1], contribution_label,
                        optional_int(contribution_category),
                        optional_int(contribution_subcategory), contribution_comment,
                    )
                    clear_cache()
                    st.success(
                        f"Mensualités enregistrées : {euros(distributed)} répartis et "
                        f"{euros(surplus)} versés sur amortissementManuel. "
                        f"{len(transaction_ids)} transactions créées pour un total de "
                        f"{euros(float(contribution_amount))}."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        with withdrawal_tab:
            current_balance = float(selected_amortization["solde"] or 0)
            st.caption(
                "Crée une transaction positive et retire le même montant du solde de l’amortissement. "
                "Le transfert peut être partiel ou total."
            )
            if current_balance <= 0:
                st.info("Le solde de cet amortissement est nul : aucun transfert n’est possible.")
            else:
                with st.form(f"amortization_withdrawal_{selected_amortization_id}", clear_on_submit=True):
                    withdrawal_date = st.date_input("Date *", value=date.today(), key="withdrawal_date")
                    withdrawal_account = st.selectbox(
                        "Banque et compte *", account_choices,
                        format_func=lambda item: f"{item[0]} — {item[1]}",
                        key="withdrawal_account",
                    )
                    withdrawal_amount = st.number_input(
                        "Montant transféré *", min_value=0.01, max_value=current_balance,
                        value=current_balance, step=0.01
                    )
                    withdrawal_label = st.text_input(
                        "Libellé *", value=f"Restitution amortissement - {selected_amortization['nom']}"
                    )
                    withdrawal_category = st.selectbox(
                        "Catégorie", amortization_category_options,
                        format_func=lambda item: "— Aucune —" if item == 0 else active_category_map[item],
                        key="withdrawal_category",
                    )
                    withdrawal_subcategory = st.selectbox(
                        "Sous-catégorie", amortization_subcategory_options,
                        format_func=lambda item: "— Aucune —" if item == 0 else active_subcategory_map[item],
                        key="withdrawal_subcategory",
                    )
                    withdrawal_comment = st.text_area("Commentaire", key="withdrawal_comment")
                    create_withdrawal = st.form_submit_button("Créer le revenu", type="primary")
                if create_withdrawal:
                    try:
                        transaction_id = db.create_amortization_transaction(
                            int(selected_amortization_id), "withdrawal", float(withdrawal_amount),
                            withdrawal_date, withdrawal_account[0], withdrawal_account[1],
                            withdrawal_label, optional_int(withdrawal_category),
                            optional_int(withdrawal_subcategory), withdrawal_comment,
                        )
                        clear_cache()
                        st.success(f"Revenu enregistré. Transaction créée avec l’identifiant {transaction_id}.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

with page_rules:
    st.subheader("Créer un enregistrement")
    add_category, add_subcategory, add_label = st.tabs(
        ["Catégorie", "Sous-catégorie", "Règle de libellé"]
    )
    with add_category:
        with st.form("new_category", clear_on_submit=True):
            name = st.text_input("Nom *")
            priority = st.number_input("Priorité (0 = non renseignée)", min_value=0, step=1)
            active = st.checkbox("Active", value=True)
            excluded = st.checkbox(
                "Exclue des statistiques et graphiques",
                help="Exemple : transferts entre comptes internes.",
            )
            submitted = st.form_submit_button("Créer la catégorie", type="primary")
        if submitted:
            try:
                new_id = db.create_category(
                    name, optional_int(priority), active, excluded
                )
                clear_cache(); st.success(f"Catégorie créée avec l’identifiant {new_id}."); st.rerun()
            except Exception as exc: st.error(str(exc))
    with add_subcategory:
        category_map_all = {int(r.id): r.nom for r in categories.itertuples()}
        with st.form("new_subcategory", clear_on_submit=True):
            sub_name = st.text_input("Nom *")
            parent_category = st.selectbox(
                "Catégorie parente *", list(category_map_all), format_func=category_map_all.get
            )
            sub_priority = st.number_input("Priorité (0 = non renseignée)", min_value=0, step=1)
            sub_active = st.checkbox("Active", value=True)
            submitted_sub = st.form_submit_button("Créer la sous-catégorie", type="primary")
        if submitted_sub:
            try:
                new_id = db.create_subcategory(
                    sub_name, int(parent_category), optional_int(sub_priority), sub_active
                )
                clear_cache(); st.success(f"Sous-catégorie créée avec l’identifiant {new_id}."); st.rerun()
            except Exception as exc: st.error(str(exc))
    with add_label:
        sub_map_all = {int(r.id): f"{r.categorie} › {r.nom}" for r in subcategories.itertuples()}
        with st.form("new_label", clear_on_submit=True):
            pattern = st.text_input("Motif recherché *")
            transformed = st.text_input("Libellé transformé *")
            parent_sub = st.selectbox(
                "Sous-catégorie *", list(sub_map_all), format_func=sub_map_all.get
            )
            submitted_label = st.form_submit_button("Créer la règle", type="primary")
        if submitted_label:
            try:
                new_id = db.create_label(pattern, transformed, int(parent_sub))
                clear_cache(); st.success(f"Règle créée avec l’identifiant {new_id}."); st.rerun()
            except Exception as exc: st.error(str(exc))

    st.divider()
    st.subheader("Consulter et modifier les référentiels")
    ref_cat, ref_sub, ref_labels = st.tabs(
        [f"Catégories ({len(categories)})", f"Sous-catégories ({len(subcategories)})", f"Libellés ({len(labels)})"]
    )
    with ref_cat:
        st.dataframe(categories, use_container_width=True, hide_index=True)
        category_names = {int(r.id): r.nom for r in categories.itertuples()}
        category_to_rename = st.selectbox(
            "Catégorie à renommer",
            list(category_names),
            format_func=category_names.get,
            key="category_to_rename",
        )
        with st.form("rename_category"):
            renamed_category = st.text_input(
                "Nouveau nom de la catégorie *",
                value=category_names[category_to_rename],
                key=f"renamed_category_{category_to_rename}",
            )
            rename_category_submitted = st.form_submit_button(
                "Enregistrer le nouveau nom", type="primary"
            )
        if rename_category_submitted:
            try:
                db.rename_category(int(category_to_rename), renamed_category)
                clear_cache()
                st.success("Catégorie renommée.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with ref_sub:
        st.dataframe(subcategories, use_container_width=True, hide_index=True)
        subcategory_names = {
            int(r.id): f"{r.categorie} › {r.nom}" for r in subcategories.itertuples()
        }
        subcategory_raw_names = {int(r.id): r.nom for r in subcategories.itertuples()}
        subcategory_to_rename = st.selectbox(
            "Sous-catégorie à renommer",
            list(subcategory_names),
            format_func=subcategory_names.get,
            key="subcategory_to_rename",
        )
        with st.form("rename_subcategory"):
            renamed_subcategory = st.text_input(
                "Nouveau nom de la sous-catégorie *",
                value=subcategory_raw_names[subcategory_to_rename],
                key=f"renamed_subcategory_{subcategory_to_rename}",
            )
            rename_subcategory_submitted = st.form_submit_button(
                "Enregistrer le nouveau nom", type="primary"
            )
        if rename_subcategory_submitted:
            try:
                db.rename_subcategory(int(subcategory_to_rename), renamed_subcategory)
                clear_cache()
                st.success("Sous-catégorie renommée.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with ref_labels:
        st.dataframe(labels, use_container_width=True, hide_index=True)
        label_names = {
            int(r.id): f"{r.motif} → {r.libelle_transforme}"
            for r in labels.itertuples()
        }
        label_to_delete = st.selectbox(
            "Règle de libellé à supprimer",
            list(label_names),
            format_func=label_names.get,
            key="label_to_delete",
        )
        linked_transactions = db.label_transaction_count(int(label_to_delete))
        st.warning(
            f"Cette règle est liée à {linked_transactions} transaction(s). "
            "Les transactions seront conservées, mais dissociées de cette règle."
        )
        with st.form("delete_label"):
            delete_confirmation = st.checkbox(
                "Je confirme la suppression définitive de cette règle."
            )
            delete_label_submitted = st.form_submit_button("Supprimer la règle")
        if delete_label_submitted:
            if not delete_confirmation:
                st.error("Cochez la confirmation avant de supprimer la règle.")
            else:
                try:
                    detached = db.delete_label(int(label_to_delete))
                    clear_cache()
                    st.success(
                        f"Règle supprimée. {detached} transaction(s) conservée(s) "
                        "et dissociée(s)."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
