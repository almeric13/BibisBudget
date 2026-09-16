from __future__ import annotations

import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

import pandas as pd

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "budget.db"


def database_path() -> Path:
    return Path(os.environ.get("BUDGET_DB_PATH", DEFAULT_DB_PATH)).expanduser().resolve()


def database_signature() -> tuple[str, int, int]:
    """Clé de cache variant dès que le fichier SQLite est remplacé ou modifié."""
    path = database_path()
    stat = path.stat()
    return str(path), stat.st_size, stat.st_mtime_ns


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    path = database_path()
    if not path.exists():
        raise FileNotFoundError(f"Base SQLite introuvable : {path}")
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 10000")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def verify_database() -> list[str]:
    expected = {
        "transactions", "libelles", "sous_categorie", "categories",
        "amortissement", "comptes", "prelevementMensualise", "emprunts",
    }
    with connection() as con:
        found = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        missing = sorted(expected - found)
        if missing:
            raise RuntimeError("Tables manquantes : " + ", ".join(missing))
        category_columns = {
            row[1] for row in con.execute("PRAGMA table_info(categories)")
        }
        if "exclu" not in category_columns:
            raise RuntimeError(
                "La colonne categories.exclu est absente de la base de données."
            )
        amortization_columns = {
            row[1] for row in con.execute("PRAGMA table_info(amortissement)")
        }
        missing_amortization_columns = {
            "id_categorie", "id_sous_categorie"
        } - amortization_columns
        if missing_amortization_columns:
            raise RuntimeError(
                "Colonnes absentes de la table amortissement : "
                + ", ".join(sorted(missing_amortization_columns))
            )
        monthly_debit_columns = {
            row[1] for row in con.execute("PRAGMA table_info(prelevementMensualise)")
        }
        expected_monthly_debit_columns = {
            "id", "nom", "mensualite", "methode_paiment", "jourDePrelevement",
            "ancienneMensualite", "id_categorie", "id_sous_categorie", "banque",
            "compteBancaire",
        }
        missing_monthly_debit_columns = (
            expected_monthly_debit_columns - monthly_debit_columns
        )
        if missing_monthly_debit_columns:
            raise RuntimeError(
                "Colonnes absentes de la table prelevementMensualise : "
                + ", ".join(sorted(missing_monthly_debit_columns))
            )
        loan_columns = {
            row[1] for row in con.execute("PRAGMA table_info(emprunts)")
        }
        expected_loan_columns = {
            "id", "nom", "montantEmprunte", "restantARembourse", "dateFinEmprunt",
        }
        missing_loan_columns = expected_loan_columns - loan_columns
        if missing_loan_columns:
            raise RuntimeError(
                "Colonnes absentes de la table emprunts : "
                + ", ".join(sorted(missing_loan_columns))
            )
        transaction_columns = {
            row[1] for row in con.execute("PRAGMA table_info(transactions)")
        }
        if "dateTimestamp_forcee" not in transaction_columns:
            raise RuntimeError(
                "La colonne transactions.dateTimestamp_forcee est absente de la base."
            )
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Échec du contrôle d’intégrité : {integrity}")
        return [" / ".join(map(str, row)) for row in con.execute("PRAGMA foreign_key_check")]


def load_transactions() -> pd.DataFrame:
    sql = """
        SELECT
            t.id,
            t.dateTimestamp,
            t.dateTimestamp_forcee,
            t.compte,
            t.banque,
            t.libelle_originale,
            t.id_libelle_transforme,
            l.libelle_transforme,
            t.montant,
            t.id_categorie,
            c.nom AS categorie,
            t.id_categorie_forcee,
            cf.nom AS categorie_forcee,
            CASE
                WHEN t.id_categorie_forcee IS NOT NULL THEN COALESCE(cf.exclu, 0)
                ELSE COALESCE(c.exclu, 0)
            END AS categorie_exclue,
            t.id_sous_categorie,
            sc.nom AS sous_categorie,
            t.id_sous_categorie_forcee,
            scf.nom AS sous_categorie_forcee,
            t.type_mouvement,
            t.commentaire
        FROM transactions t
        LEFT JOIN libelles l ON l.id = t.id_libelle_transforme
        LEFT JOIN categories c ON c.id = t.id_categorie
        LEFT JOIN categories cf ON cf.id = t.id_categorie_forcee
        LEFT JOIN sous_categorie sc ON sc.id = t.id_sous_categorie
        LEFT JOIN sous_categorie scf ON scf.id = t.id_sous_categorie_forcee
        ORDER BY COALESCE(t.dateTimestamp_forcee, t.dateTimestamp) DESC, t.id DESC
    """
    with connection() as con:
        df = pd.read_sql_query(sql, con)
    df["date_originale"] = (
        pd.to_datetime(df["dateTimestamp"], unit="ms", utc=True, errors="coerce")
        .dt.tz_convert("Europe/Paris")
        .dt.tz_localize(None)
    )
    df["date_forcee"] = (
        pd.to_datetime(df["dateTimestamp_forcee"], unit="ms", utc=True, errors="coerce")
        .dt.tz_convert("Europe/Paris")
        .dt.tz_localize(None)
    )
    df["date"] = df["date_forcee"].fillna(df["date_originale"])
    df["categorie_effective"] = df["categorie_forcee"].fillna(df["categorie"])
    df["sous_categorie_effective"] = df["sous_categorie_forcee"].fillna(
        df["sous_categorie"]
    )
    return df


def load_categories(active_only: bool = False) -> pd.DataFrame:
    where = "WHERE actif = 1" if active_only else ""
    with connection() as con:
        return pd.read_sql_query(
            f"SELECT id, priorite, nom, actif, COALESCE(exclu, 0) AS exclu "
            f"FROM categories {where} "
            "ORDER BY COALESCE(priorite, 999999), nom",
            con,
        )


def load_subcategories(active_only: bool = False) -> pd.DataFrame:
    where = "WHERE sc.actif = 1 AND c.actif = 1" if active_only else ""
    sql = f"""
        SELECT sc.id, sc.nom, sc.priorite, sc.actif, sc.id_categorie,
               c.nom AS categorie
        FROM sous_categorie sc
        JOIN categories c ON c.id = sc.id_categorie
        {where}
        ORDER BY c.nom, CAST(sc.priorite AS INTEGER), sc.nom
    """
    with connection() as con:
        return pd.read_sql_query(sql, con)


def load_labels() -> pd.DataFrame:
    sql = """
        SELECT l.id, l.motif, l.libelle_transforme, l.id_sous_categorie,
               sc.nom AS sous_categorie, c.nom AS categorie
        FROM libelles l
        JOIN sous_categorie sc ON sc.id = l.id_sous_categorie
        JOIN categories c ON c.id = sc.id_categorie
        ORDER BY l.motif
    """
    with connection() as con:
        return pd.read_sql_query(sql, con)


def load_amortizations() -> pd.DataFrame:
    with connection() as con:
        df = pd.read_sql_query(
            '''SELECT a.id, a.nom, a.solde, a."Objectif" AS objectif,
                      a."Ancien_objectif" AS ancien_objectif,
                      a."AvancementPourcentage" AS avancement_pourcentage,
                      a."Mois" AS mois, a."Mois_restant" AS mois_restant,
                      a.mensualite, a.mensualite_ajustee, a.date_cible,
                      a."Progession_pourcentage" AS progression_pourcentage,
                      a."dateDernierPaiment" AS date_dernier_paiement,
                      a.commentaire, a.id_categorie, c.nom AS categorie,
                      a.id_sous_categorie, sc.nom AS sous_categorie
               FROM amortissement a
               LEFT JOIN categories c ON c.id=a.id_categorie
               LEFT JOIN sous_categorie sc ON sc.id=a.id_sous_categorie
               ORDER BY a.nom, a.id''',
            con,
        )
    for source, target in (
        ("date_cible", "date_cible_affichee"),
        ("date_dernier_paiement", "date_dernier_paiement_affichee"),
    ):
        df[target] = (
            pd.to_datetime(df[source], unit="ms", utc=True, errors="coerce")
            .dt.tz_convert("Europe/Paris")
            .dt.tz_localize(None)
        )
    return df


def load_monthly_debits() -> pd.DataFrame:
    """Charge les prélèvements mensualisés et leurs libellés de référence."""
    with connection() as con:
        return pd.read_sql_query(
            '''SELECT p.id, p.nom, p.mensualite,
                      p.methode_paiment, p.jourDePrelevement,
                      p.ancienneMensualite, p.id_categorie,
                      c.nom AS categorie, p.id_sous_categorie,
                      sc.nom AS sous_categorie, p.banque, p.compteBancaire
               FROM prelevementMensualise p
               LEFT JOIN categories c ON c.id=p.id_categorie
               LEFT JOIN sous_categorie sc ON sc.id=p.id_sous_categorie
               ORDER BY lower(p.nom), p.id''',
            con,
        )


def _normalize_monthly_debit(
    name: str,
    monthly_amount: float,
    payment_method: str | None,
    debit_day: int,
    old_monthly_amount: float | None,
    bank: str | None,
    bank_account: str | None,
) -> tuple[str, float, str | None, int, float | None, str | None, str | None]:
    name = name.strip()
    if not name:
        raise ValueError("Le nom de la mensualité est obligatoire.")
    monthly_amount = round(float(monthly_amount), 2)
    if monthly_amount < 0:
        raise ValueError("La mensualité ne peut pas être négative.")
    debit_day = int(debit_day)
    if not 1 <= debit_day <= 31:
        raise ValueError("Le jour de prélèvement doit être compris entre 1 et 31.")
    if old_monthly_amount is not None:
        old_monthly_amount = round(float(old_monthly_amount), 2)
        if old_monthly_amount < 0:
            raise ValueError("L’ancienne mensualité ne peut pas être négative.")

    def optional_text(value: str | None) -> str | None:
        value = value.strip() if isinstance(value, str) else ""
        return value or None

    return (
        name, monthly_amount, optional_text(payment_method), debit_day,
        old_monthly_amount, optional_text(bank), optional_text(bank_account),
    )


def create_monthly_debit(
    name: str,
    monthly_amount: float,
    payment_method: str | None,
    debit_day: int,
    old_monthly_amount: float | None,
    category_id: int | None,
    subcategory_id: int | None,
    bank: str | None,
    bank_account: str | None,
) -> int:
    values = _normalize_monthly_debit(
        name, monthly_amount, payment_method, debit_day,
        old_monthly_amount, bank, bank_account,
    )
    with connection() as con:
        category_id, subcategory_id = _validate_transaction_references(
            con, category_id, subcategory_id
        )
        cur = con.execute(
            '''INSERT INTO prelevementMensualise(
                   nom, mensualite, methode_paiment, jourDePrelevement,
                   ancienneMensualite, id_categorie, id_sous_categorie,
                   banque, compteBancaire
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (*values[:5], category_id, subcategory_id, *values[5:]),
        )
        return int(cur.lastrowid)


def update_monthly_debit(
    monthly_debit_id: int,
    name: str,
    monthly_amount: float,
    payment_method: str | None,
    debit_day: int,
    old_monthly_amount: float | None,
    category_id: int | None,
    subcategory_id: int | None,
    bank: str | None,
    bank_account: str | None,
) -> None:
    values = _normalize_monthly_debit(
        name, monthly_amount, payment_method, debit_day,
        old_monthly_amount, bank, bank_account,
    )
    with connection() as con:
        category_id, subcategory_id = _validate_transaction_references(
            con, category_id, subcategory_id
        )
        cur = con.execute(
            '''UPDATE prelevementMensualise
               SET nom=?, mensualite=?, methode_paiment=?, jourDePrelevement=?,
                   ancienneMensualite=?, id_categorie=?, id_sous_categorie=?,
                   banque=?, compteBancaire=?
               WHERE id=?''',
            (*values[:5], category_id, subcategory_id, *values[5:], monthly_debit_id),
        )
        if cur.rowcount != 1:
            raise ValueError("Mensualité introuvable.")


def delete_monthly_debit(monthly_debit_id: int) -> None:
    with connection() as con:
        cur = con.execute(
            "DELETE FROM prelevementMensualise WHERE id=?", (monthly_debit_id,)
        )
        if cur.rowcount != 1:
            raise ValueError("Mensualité introuvable.")


def _ensure_settings_table(con: sqlite3.Connection) -> None:
    con.execute(
        '''CREATE TABLE IF NOT EXISTS budgetbibis_settings (
               cle TEXT PRIMARY KEY,
               valeur_reelle REAL NOT NULL
           )'''
    )


def load_desired_amortization_surplus() -> float:
    with connection() as con:
        _ensure_settings_table(con)
        row = con.execute(
            "SELECT valeur_reelle FROM budgetbibis_settings WHERE cle=?",
            ("surplus_mensualite_amortissement",),
        ).fetchone()
        return round(float(row[0]), 2) if row is not None else 0.0


def update_desired_amortization_surplus(amount: float) -> None:
    amount = round(float(amount), 2)
    if amount < 0:
        raise ValueError("Le surplus souhaité ne peut pas être négatif.")
    with connection() as con:
        _ensure_settings_table(con)
        con.execute(
            '''INSERT INTO budgetbibis_settings(cle, valeur_reelle)
               VALUES (?, ?)
               ON CONFLICT(cle) DO UPDATE SET valeur_reelle=excluded.valeur_reelle''',
            ("surplus_mensualite_amortissement", amount),
        )


def load_previous_month_balance() -> float:
    with connection() as con:
        _ensure_settings_table(con)
        row = con.execute(
            "SELECT valeur_reelle FROM budgetbibis_settings WHERE cle=?",
            ("solde_mois_precedent",),
        ).fetchone()
        return round(float(row[0]), 2) if row is not None else 0.0


def update_previous_month_balance(amount: float) -> None:
    amount = round(float(amount), 2)
    if not math.isfinite(amount):
        raise ValueError("Le solde du mois précédent doit être un nombre valide.")
    with connection() as con:
        _ensure_settings_table(con)
        con.execute(
            '''INSERT INTO budgetbibis_settings(cle, valeur_reelle)
               VALUES (?, ?)
               ON CONFLICT(cle) DO UPDATE SET valeur_reelle=excluded.valeur_reelle''',
            ("solde_mois_precedent", amount),
        )


def monthly_debits_remaining(reference_date: date | None = None) -> pd.DataFrame:
    """Retourne les prélèvements restant à venir, séparément pour chaque compte."""
    reference_date = reference_date or datetime.now(ZoneInfo("Europe/Paris")).date()
    with connection() as con:
        frame = pd.read_sql_query(
            '''SELECT
                   COALESCE(NULLIF(trim(banque), ''), 'Banque non renseignée') AS banque,
                   COALESCE(NULLIF(trim(compteBancaire), ''), 'Compte non renseigné')
                       AS compte_bancaire,
                   COUNT(*) AS nombre_mensualites,
                   ROUND(SUM(COALESCE(mensualite, 0)), 2) AS total_mensuel,
                   ROUND(SUM(
                       CASE WHEN jourDePrelevement >= ?
                            THEN COALESCE(mensualite, 0) ELSE 0 END
                   ), 2) AS reste_a_prelever
               FROM prelevementMensualise
               GROUP BY
                   COALESCE(NULLIF(trim(banque), ''), 'Banque non renseignée'),
                   COALESCE(NULLIF(trim(compteBancaire), ''), 'Compte non renseigné')
               ORDER BY lower(banque), lower(compte_bancaire)''',
            con,
            params=(reference_date.day,),
        )
    return frame


def monthly_follow_up(reference_date: date | None = None) -> dict[str, float]:
    """Calcule le transfert mensuel vers Trade Republic, hors suivi des prélèvements."""
    with connection() as con:
        trade_total = round(sum(
            round(float(row[0]), 2)
            for row in con.execute(
                '''SELECT COALESCE(mensualite, 0)
                   FROM prelevementMensualise
                   WHERE lower(trim(COALESCE(banque, '')))='trade republic' ''',
            )
        ), 2)
        amortization_total = round(sum(
            round(float(row[0]), 2)
            for row in con.execute(
                "SELECT COALESCE(mensualite, 0) FROM amortissement"
            )
        ), 2)
        amortization_balances_total = round(sum(
            round(float(row[0]), 2)
            for row in con.execute(
                "SELECT COALESCE(solde, 0) FROM amortissement"
            )
        ), 2)
        manual_balance_rows = con.execute(
            """SELECT COALESCE(solde, 0) FROM comptes
               WHERE lower(nom)=lower('amortissementManuel')"""
        ).fetchall()
        if len(manual_balance_rows) != 1:
            raise RuntimeError(
                "Le compte amortissementManuel doit exister en un seul exemplaire."
            )
        manual_amortization_balance = round(
            float(manual_balance_rows[0][0]), 2
        )
        _ensure_settings_table(con)
        surplus_row = con.execute(
            "SELECT valeur_reelle FROM budgetbibis_settings WHERE cle=?",
            ("surplus_mensualite_amortissement",),
        ).fetchone()
    surplus = round(float(surplus_row[0]), 2) if surplus_row is not None else 0.0
    return {
        "trade_republic_total": trade_total,
        "amortization_total": amortization_total,
        "amortization_balances_total": amortization_balances_total,
        "manual_amortization_balance": manual_amortization_balance,
        "minimum_trade_republic": round(
            trade_total + amortization_balances_total + manual_amortization_balance,
            2,
        ),
        "desired_surplus": surplus,
        "monthly_transfer": round(trade_total + amortization_total + surplus, 2),
    }


def load_current_loans() -> pd.DataFrame:
    """Charge les emprunts dont le capital restant à rembourser est positif."""
    with connection() as con:
        frame = pd.read_sql_query(
            '''SELECT id, nom, montantEmprunte, restantARembourse, dateFinEmprunt
               FROM emprunts
               WHERE COALESCE(restantARembourse, 0) > 0
               ORDER BY lower(COALESCE(nom, '')), id''',
            con,
        )
    borrowed = pd.to_numeric(frame["montantEmprunte"], errors="coerce").fillna(0.0)
    remaining = pd.to_numeric(frame["restantARembourse"], errors="coerce").fillna(0.0)
    frame["avancement_pourcentage"] = (
        ((borrowed - remaining) / borrowed * 100)
        .where(borrowed > 0, 0.0)
        .clip(lower=0.0, upper=100.0)
        .round(2)
    )
    frame["date_fin_emprunt_affichee"] = (
        pd.to_datetime(frame["dateFinEmprunt"], unit="ms", utc=True, errors="coerce")
        .dt.tz_convert("Europe/Paris")
        .dt.tz_localize(None)
    )
    return frame


def update_loan_remaining_balance(loan_id: int, remaining_balance: float) -> None:
    remaining_balance = round(float(remaining_balance), 2)
    if not math.isfinite(remaining_balance) or remaining_balance < 0:
        raise ValueError("Le restant à rembourser doit être un montant positif ou nul.")
    with connection() as con:
        row = con.execute(
            "SELECT montantEmprunte FROM emprunts WHERE id=?", (loan_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Emprunt introuvable.")
        borrowed_amount = float(row[0] or 0)
        if remaining_balance > borrowed_amount:
            raise ValueError(
                "Le restant à rembourser ne peut pas dépasser le montant emprunté."
            )
        con.execute(
            "UPDATE emprunts SET restantARembourse=? WHERE id=?",
            (remaining_balance, loan_id),
        )


def load_account_choices() -> list[tuple[str, str]]:
    with connection() as con:
        return [
            (str(row[0]), str(row[1]))
            for row in con.execute(
                """SELECT DISTINCT banque, compte FROM transactions
                   WHERE banque IS NOT NULL AND compte IS NOT NULL
                   ORDER BY banque, compte"""
            )
        ]


def load_manual_amortization_account() -> dict[str, int | str | float]:
    with connection() as con:
        row = con.execute(
            """SELECT id, nom, COALESCE(solde, 0) AS solde
               FROM comptes WHERE lower(nom)=lower('amortissementManuel')"""
        ).fetchone()
        if row is None:
            raise RuntimeError(
                "Le compte amortissementManuel est absent de la table comptes."
            )
        return {"id": int(row[0]), "nom": str(row[1]), "solde": float(row[2])}


def update_manual_amortization_balance(balance: float) -> None:
    balance = round(float(balance), 2)
    if balance < 0:
        raise ValueError("Le solde du compte manuel ne peut pas être négatif.")
    with connection() as con:
        cur = con.execute(
            """UPDATE comptes SET solde=?
               WHERE lower(nom)=lower('amortissementManuel')""",
            (balance,),
        )
        if cur.rowcount != 1:
            raise RuntimeError(
                "Le compte amortissementManuel est absent ou n’est pas unique."
            )


def update_transaction(
    transaction_id: int,
    category_id: int | None,
    subcategory_id: int | None,
    movement_type: str | None,
    comment: str | None,
    forced_date: date | None = None,
) -> None:
    movement_type = (
        movement_type.strip()
        if isinstance(movement_type, str) and movement_type.strip()
        else None
    )
    comment = comment.strip() if isinstance(comment, str) and comment.strip() else None
    with connection() as con:
        if subcategory_id is not None:
            row = con.execute(
                "SELECT id_categorie FROM sous_categorie WHERE id = ? AND actif = 1",
                (subcategory_id,),
            ).fetchone()
            if row is None:
                raise ValueError("La sous-catégorie sélectionnée n’existe pas ou est inactive.")
            inferred_category = int(row[0])
            if category_id is None:
                category_id = inferred_category
            elif category_id != inferred_category:
                raise ValueError("La sous-catégorie n’appartient pas à la catégorie sélectionnée.")
        if category_id is not None:
            exists = con.execute(
                "SELECT 1 FROM categories WHERE id = ? AND actif = 1", (category_id,)
            ).fetchone()
            if exists is None:
                raise ValueError("La catégorie sélectionnée n’existe pas ou est inactive.")
        cur = con.execute(
            """
            UPDATE transactions
            SET id_categorie_forcee = ?, id_sous_categorie_forcee = ?,
                type_mouvement = ?, commentaire = ?, dateTimestamp_forcee = ?
            WHERE id = ?
            """,
            (
                category_id, subcategory_id, movement_type, comment,
                _date_to_timestamp_ms(forced_date), transaction_id,
            ),
        )
        if cur.rowcount != 1:
            raise ValueError("Transaction introuvable.")


def create_category(
    name: str, priority: int | None, active: bool, excluded: bool = False
) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Le nom de la catégorie est obligatoire.")
    with connection() as con:
        if con.execute("SELECT 1 FROM categories WHERE lower(nom)=lower(?)", (name,)).fetchone():
            raise ValueError("Une catégorie portant ce nom existe déjà.")
        cur = con.execute(
            "INSERT INTO categories(priorite, nom, actif, exclu) VALUES (?, ?, ?, ?)",
            (priority, name, int(active), int(excluded)),
        )
        return int(cur.lastrowid)


def rename_category(category_id: int, name: str) -> None:
    name = name.strip()
    if not name:
        raise ValueError("Le nom de la catégorie est obligatoire.")
    with connection() as con:
        if con.execute(
            "SELECT 1 FROM categories WHERE lower(nom)=lower(?) AND id<>?",
            (name, category_id),
        ).fetchone():
            raise ValueError("Une autre catégorie portant ce nom existe déjà.")
        cur = con.execute(
            "UPDATE categories SET nom=? WHERE id=?", (name, category_id)
        )
        if cur.rowcount != 1:
            raise ValueError("Catégorie introuvable.")


def create_subcategory(
    name: str, category_id: int, priority: int | None, active: bool
) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Le nom de la sous-catégorie est obligatoire.")
    with connection() as con:
        if con.execute(
            "SELECT 1 FROM sous_categorie WHERE lower(nom)=lower(?) AND id_categorie=?",
            (name, category_id),
        ).fetchone():
            raise ValueError("Cette sous-catégorie existe déjà dans cette catégorie.")
        cur = con.execute(
            """INSERT INTO sous_categorie(nom, priorite, actif, id_categorie)
               VALUES (?, ?, ?, ?)""",
            (name, priority, int(active), category_id),
        )
        return int(cur.lastrowid)


def rename_subcategory(subcategory_id: int, name: str) -> None:
    name = name.strip()
    if not name:
        raise ValueError("Le nom de la sous-catégorie est obligatoire.")
    with connection() as con:
        row = con.execute(
            "SELECT id_categorie FROM sous_categorie WHERE id=?", (subcategory_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Sous-catégorie introuvable.")
        if con.execute(
            """SELECT 1 FROM sous_categorie
               WHERE lower(nom)=lower(?) AND id_categorie=? AND id<>?""",
            (name, int(row[0]), subcategory_id),
        ).fetchone():
            raise ValueError(
                "Une autre sous-catégorie portant ce nom existe déjà dans cette catégorie."
            )
        con.execute(
            "UPDATE sous_categorie SET nom=? WHERE id=?", (name, subcategory_id)
        )


def create_label(pattern: str, transformed_label: str, subcategory_id: int) -> int:
    pattern, transformed_label = pattern.strip(), transformed_label.strip()
    if not pattern or not transformed_label:
        raise ValueError("Le motif et le libellé transformé sont obligatoires.")
    with connection() as con:
        if con.execute("SELECT 1 FROM libelles WHERE lower(motif)=lower(?)", (pattern,)).fetchone():
            raise ValueError("Une règle portant ce motif existe déjà.")
        cur = con.execute(
            """INSERT INTO libelles(motif, libelle_transforme, id_sous_categorie)
               VALUES (?, ?, ?)""",
            (pattern, transformed_label, subcategory_id),
        )
        return int(cur.lastrowid)


def label_transaction_count(label_id: int) -> int:
    with connection() as con:
        if con.execute("SELECT 1 FROM libelles WHERE id=?", (label_id,)).fetchone() is None:
            raise ValueError("Règle de libellé introuvable.")
        return int(
            con.execute(
                "SELECT COUNT(*) FROM transactions WHERE id_libelle_transforme=?",
                (label_id,),
            ).fetchone()[0]
        )


def delete_label(label_id: int) -> int:
    """Supprime une règle en conservant et en dissociant ses transactions."""
    with connection() as con:
        if con.execute("SELECT 1 FROM libelles WHERE id=?", (label_id,)).fetchone() is None:
            raise ValueError("Règle de libellé introuvable.")
        detached = con.execute(
            "UPDATE transactions SET id_libelle_transforme=NULL "
            "WHERE id_libelle_transforme=?",
            (label_id,),
        ).rowcount
        cur = con.execute("DELETE FROM libelles WHERE id=?", (label_id,))
        if cur.rowcount != 1:
            raise ValueError("La règle de libellé n’a pas pu être supprimée.")
        return int(detached)


def _date_to_timestamp_ms(value: date | None) -> int | None:
    if value is None:
        return None
    local = datetime(value.year, value.month, value.day, tzinfo=ZoneInfo("Europe/Paris"))
    return int(local.timestamp() * 1000)


def _timestamp_ms_to_date(value: int | float | None) -> date | None:
    if value is None:
        return None
    return datetime.fromtimestamp(float(value) / 1000, ZoneInfo("Europe/Paris")).date()


def _remaining_months(target: date | None, reference: date) -> int:
    if target is None or target < reference:
        return 0
    months = (target.year - reference.year) * 12 + target.month - reference.month
    return max(0, months + int(target.day > reference.day))


def _calculated_amortization_values(
    balance: float,
    objective: float,
    monthly_payment: float,
    target_date: date | None,
    reference_date: date,
) -> tuple[float, int, float, float]:
    financial_progress = (
        round(balance / objective * 100, 2) if objective > 0 else 0.0
    )
    remaining_months = _remaining_months(target_date, reference_date)
    adjusted = (
        0.0
        if financial_progress >= 100.0
        else round(float(monthly_payment), 2)
    )
    monthly_progress = (
        round(((remaining_months * adjusted) + balance) / objective * 100, 2)
        if objective > 0
        else 0.0
    )
    return financial_progress, remaining_months, adjusted, monthly_progress


def update_amortization(
    amortization_id: int,
    name: str,
    balance: float,
    objective: float,
    old_objective: float | None,
    months: int,
    monthly_payment: float,
    target_date: date | None,
    last_payment_date: date | None,
    comment: str | None,
    reference_date: date | None = None,
    category_id: int | None = None,
    subcategory_id: int | None = None,
) -> None:
    name = name.strip()
    if not name:
        raise ValueError("Le nom de l’amortissement est obligatoire.")
    if balance < 0 or objective <= 0 or months <= 0 or monthly_payment < 0:
        raise ValueError("Le solde et la mensualité doivent être positifs, et l’objectif et le nombre de mois supérieurs à zéro.")
    reference_date = reference_date or date.today()
    progress, remaining_months, adjusted, monthly_progress = (
        _calculated_amortization_values(
            float(balance),
            float(objective),
            float(monthly_payment),
            target_date,
            reference_date,
        )
    )
    with connection() as con:
        category_id, subcategory_id = _validate_transaction_references(
            con, category_id, subcategory_id
        )
        cur = con.execute(
            '''UPDATE amortissement
               SET nom=?, solde=?, "Objectif"=?, "Ancien_objectif"=?,
                   "AvancementPourcentage"=?, "Mois"=?, "Mois_restant"=?,
                   mensualite=?, mensualite_ajustee=?, date_cible=?,
                   "Progession_pourcentage"=?, "dateDernierPaiment"=?, commentaire=?,
                   id_categorie=?, id_sous_categorie=?
               WHERE id=?''',
            (
                name, round(float(balance), 2), round(float(objective), 2),
                None if old_objective is None else round(float(old_objective), 2),
                progress, int(months), remaining_months, round(float(monthly_payment), 2),
                adjusted, _date_to_timestamp_ms(target_date), monthly_progress,
                _date_to_timestamp_ms(last_payment_date),
                comment.strip() if comment and comment.strip() else None,
                category_id, subcategory_id, amortization_id,
            ),
        )
        if cur.rowcount != 1:
            raise ValueError("Amortissement introuvable.")


def _validate_transaction_references(
    con: sqlite3.Connection, category_id: int | None, subcategory_id: int | None
) -> tuple[int | None, int | None]:
    if subcategory_id is not None:
        row = con.execute(
            "SELECT id_categorie FROM sous_categorie WHERE id=? AND actif=1",
            (subcategory_id,),
        ).fetchone()
        if row is None:
            raise ValueError("La sous-catégorie sélectionnée n’existe pas ou est inactive.")
        parent_id = int(row[0])
        if category_id is None:
            category_id = parent_id
        elif category_id != parent_id:
            raise ValueError("La sous-catégorie n’appartient pas à la catégorie sélectionnée.")
    if category_id is not None and con.execute(
        "SELECT 1 FROM categories WHERE id=? AND actif=1", (category_id,)
    ).fetchone() is None:
        raise ValueError("La catégorie sélectionnée n’existe pas ou est inactive.")
    return category_id, subcategory_id


def create_amortization(
    name: str,
    balance: float,
    objective: float,
    old_objective: float | None,
    months: int,
    monthly_payment: float,
    target_date: date | None,
    last_payment_date: date | None,
    comment: str | None,
    category_id: int | None,
    subcategory_id: int | None,
    reference_date: date | None = None,
) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Le nom de l’amortissement est obligatoire.")
    if balance < 0 or objective <= 0 or months <= 0 or monthly_payment < 0:
        raise ValueError(
            "Le solde et la mensualité doivent être positifs, et l’objectif "
            "et le nombre de mois supérieurs à zéro."
        )
    reference_date = reference_date or date.today()
    progress, remaining_months, adjusted, monthly_progress = (
        _calculated_amortization_values(
            float(balance),
            float(objective),
            float(monthly_payment),
            target_date,
            reference_date,
        )
    )
    with connection() as con:
        category_id, subcategory_id = _validate_transaction_references(
            con, category_id, subcategory_id
        )
        cur = con.execute(
            '''INSERT INTO amortissement(
                   nom, solde, "Objectif", "Ancien_objectif",
                   "AvancementPourcentage", "Mois", "Mois_restant",
                   mensualite, mensualite_ajustee, date_cible,
                   "Progession_pourcentage", "dateDernierPaiment", commentaire,
                   id_categorie, id_sous_categorie
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                name, round(float(balance), 2), round(float(objective), 2),
                None if old_objective is None else round(float(old_objective), 2),
                progress, int(months), remaining_months,
                round(float(monthly_payment), 2), adjusted,
                _date_to_timestamp_ms(target_date), monthly_progress,
                _date_to_timestamp_ms(last_payment_date),
                comment.strip() if comment and comment.strip() else None,
                category_id, subcategory_id,
            ),
        )
        return int(cur.lastrowid)


def total_amortization_monthly_payments() -> float:
    with connection() as con:
        monthly_payments = con.execute(
            "SELECT COALESCE(mensualite, 0) FROM amortissement ORDER BY id"
        ).fetchall()
    return round(sum(round(float(row[0]), 2) for row in monthly_payments), 2)


def _allocate_cents_by_weights(total: float, weights: list[float]) -> list[float]:
    """Répartit exactement un total au centime selon des poids positifs."""
    total_cents = int(round(float(total) * 100))
    normalized = [max(0.0, float(weight)) for weight in weights]
    weight_total = sum(normalized)
    if total_cents <= 0 or weight_total <= 0:
        return [0.0 for _ in normalized]

    raw_allocations = [total_cents * weight / weight_total for weight in normalized]
    allocated_cents = [math.floor(value) for value in raw_allocations]
    remaining_cents = total_cents - sum(allocated_cents)
    priority = sorted(
        range(len(normalized)),
        key=lambda index: (raw_allocations[index] - allocated_cents[index], -index),
        reverse=True,
    )
    for index in priority[:remaining_cents]:
        allocated_cents[index] += 1
    return [cents / 100 for cents in allocated_cents]


def create_global_amortization_contribution(
    amount: float,
    transaction_date: date,
    bank: str,
    account: str,
    label: str,
    category_id: int | None,
    subcategory_id: int | None,
    comment: str | None,
) -> tuple[list[int], float, float]:
    """Crée une transaction par amortissement et une autre pour le surplus."""
    amount = round(float(amount), 2)
    bank, account, label = bank.strip(), account.strip(), label.strip()
    if amount <= 0:
        raise ValueError("Le montant doit être strictement positif.")
    if not bank or not account or not label:
        raise ValueError("La banque, le compte et le libellé sont obligatoires.")

    with connection() as con:
        amortizations = con.execute(
            '''SELECT id, nom, COALESCE(solde, 0), COALESCE("Objectif", 0),
                      date_cible, COALESCE(mensualite, 0),
                      id_categorie, id_sous_categorie,
                      COALESCE(mensualite_ajustee, 0)
               FROM amortissement ORDER BY id'''
        ).fetchall()
        if not amortizations:
            raise ValueError("Aucun amortissement n’est présent dans la base.")
        normal_monthly_amounts = [round(float(row[5]), 2) for row in amortizations]
        total_monthly = round(sum(normal_monthly_amounts), 2)
        adjusted_monthly_weights = [round(float(row[8]), 2) for row in amortizations]
        distributed_amounts = _allocate_cents_by_weights(
            total_monthly, adjusted_monthly_weights
        )
        if amount < total_monthly:
            raise ValueError(
                f"Le montant doit être au moins égal à la somme des mensualités "
                f"({total_monthly:.2f} €)."
            )
        manual_account = con.execute(
            """SELECT id, COALESCE(solde, 0) FROM comptes
               WHERE lower(nom)=lower('amortissementManuel')"""
        ).fetchall()
        if len(manual_account) != 1:
            raise RuntimeError(
                "Le compte amortissementManuel doit exister en un seul exemplaire."
            )
        category_id, subcategory_id = _validate_transaction_references(
            con, category_id, subcategory_id
        )
        timestamp = _date_to_timestamp_ms(transaction_date)
        normalized_comment = comment.strip() if comment and comment.strip() else None
        transaction_ids: list[int] = []
        for row, distributed_amount in zip(amortizations, distributed_amounts):
            if distributed_amount <= 0:
                continue
            amortization_id = int(row[0])
            amortization_name = str(row[1] or f"Amortissement {amortization_id}")
            stored_category_id, stored_subcategory_id = _validate_transaction_references(
                con,
                int(row[6]) if row[6] is not None else None,
                int(row[7]) if row[7] is not None else None,
            )
            transaction_category_id = (
                stored_category_id
                if stored_category_id is not None or stored_subcategory_id is not None
                else category_id
            )
            transaction_subcategory_id = (
                stored_subcategory_id
                if stored_category_id is not None or stored_subcategory_id is not None
                else subcategory_id
            )
            cur = con.execute(
                '''INSERT INTO transactions(
                       dateTimestamp, compte, banque, libelle_originale, montant,
                       id_categorie_forcee, id_sous_categorie_forcee,
                       type_mouvement, commentaire
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    timestamp, account, bank, f"{label} — {amortization_name}",
                    -distributed_amount, transaction_category_id,
                    transaction_subcategory_id, "Amortissement - mensualité",
                    normalized_comment,
                ),
            )
            transaction_ids.append(int(cur.lastrowid))
            new_balance = round(float(row[2]) + distributed_amount, 2)
            progress, remaining_months, adjusted, monthly_progress = (
                _calculated_amortization_values(
                    new_balance,
                    float(row[3]),
                    float(row[5]),
                    _timestamp_ms_to_date(row[4]),
                    transaction_date,
                )
            )
            con.execute(
                '''UPDATE amortissement
                   SET solde=?, "AvancementPourcentage"=?, "Mois_restant"=?,
                       mensualite_ajustee=?, "Progession_pourcentage"=?
                   WHERE id=?''',
                (
                    new_balance, progress, remaining_months, adjusted,
                    monthly_progress, amortization_id,
                ),
            )
        surplus = round(amount - total_monthly, 2)
        if surplus:
            surplus_transaction = con.execute(
                '''INSERT INTO transactions(
                       dateTimestamp, compte, banque, libelle_originale, montant,
                       id_categorie_forcee, id_sous_categorie_forcee,
                       type_mouvement, commentaire
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    timestamp, account, bank, f"{label} — Épargne", -surplus,
                    category_id, subcategory_id, "Amortissement - épargne",
                    normalized_comment,
                ),
            )
            transaction_ids.append(int(surplus_transaction.lastrowid))
            con.execute(
                "UPDATE comptes SET solde=? WHERE id=?",
                (round(float(manual_account[0][1]) + surplus, 2), int(manual_account[0][0])),
            )
        return transaction_ids, total_monthly, surplus


def create_amortization_transaction(
    amortization_id: int,
    operation: str,
    amount: float,
    transaction_date: date,
    bank: str,
    account: str,
    label: str,
    category_id: int | None,
    subcategory_id: int | None,
    comment: str | None,
) -> int:
    """Crée une transaction et ajuste le solde dans une seule transaction SQLite."""
    if operation not in {"contribution", "withdrawal"}:
        raise ValueError("Type d’opération d’amortissement invalide.")
    amount = round(float(amount), 2)
    if amount <= 0:
        raise ValueError("Le montant doit être strictement positif.")
    bank, account, label = bank.strip(), account.strip(), label.strip()
    if not bank or not account or not label:
        raise ValueError("La banque, le compte et le libellé sont obligatoires.")

    with connection() as con:
        amortization = con.execute(
            '''SELECT solde, "Objectif", date_cible, COALESCE(mensualite, 0)
               FROM amortissement WHERE id=?''',
            (amortization_id,),
        ).fetchone()
        if amortization is None:
            raise ValueError("Amortissement introuvable.")
        current_balance = float(amortization[0] or 0)
        if operation == "withdrawal" and amount > current_balance:
            raise ValueError("Le montant transféré ne peut pas dépasser le solde de l’amortissement.")
        category_id, subcategory_id = _validate_transaction_references(
            con, category_id, subcategory_id
        )
        signed_amount = -amount if operation == "contribution" else amount
        movement_type = (
            "Amortissement - mensualité"
            if operation == "contribution"
            else "Amortissement - restitution"
        )
        cur = con.execute(
            '''INSERT INTO transactions(
                   dateTimestamp, compte, banque, libelle_originale, montant,
                   id_categorie_forcee, id_sous_categorie_forcee,
                   type_mouvement, commentaire
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                _date_to_timestamp_ms(transaction_date), account, bank, label,
                signed_amount, category_id, subcategory_id, movement_type,
                comment.strip() if comment and comment.strip() else None,
            ),
        )
        new_balance = current_balance + amount if operation == "contribution" else current_balance - amount
        progress, remaining_months, adjusted, monthly_progress = (
            _calculated_amortization_values(
                new_balance,
                float(amortization[1] or 0),
                float(amortization[3] or 0),
                _timestamp_ms_to_date(amortization[2]),
                transaction_date,
            )
        )
        con.execute(
            '''UPDATE amortissement
               SET solde=?, "AvancementPourcentage"=?, "Mois_restant"=?,
                   mensualite_ajustee=?, "Progession_pourcentage"=?
               WHERE id=?''',
            (
                round(new_balance, 2), progress, remaining_months, adjusted,
                monthly_progress, amortization_id,
            ),
        )
        return int(cur.lastrowid)
