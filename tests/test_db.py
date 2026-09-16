import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

import analytics
import db
from pandas.testing import assert_frame_equal

SOURCE = Path(__file__).resolve().parents[1] / "data" / "budget.db"


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "budget.db"
        shutil.copy2(SOURCE, self.path)
        os.environ["BUDGET_DB_PATH"] = str(self.path)

    def tearDown(self):
        os.environ.pop("BUDGET_DB_PATH", None)
        self.tmp.cleanup()

    def test_integrity_and_expected_rows(self):
        self.assertEqual(db.verify_database(), [])
        self.assertEqual(len(db.load_transactions()), 400)
        self.assertEqual(len(db.load_categories()), 19)
        self.assertEqual(len(db.load_subcategories()), 34)
        self.assertEqual(len(db.load_labels()), 40)
        self.assertEqual(len(db.load_amortizations()), 20)
        self.assertEqual(len(db.load_monthly_debits()), 18)
        self.assertEqual(len(db.load_current_loans()), 2)
        self.assertEqual(db.total_amortization_monthly_payments(), 341.18)
        self.assertEqual(db.load_manual_amortization_account()["solde"], 127.49)

    def test_transaction_update_is_persistent(self):
        tx_id = int(db.load_transactions().iloc[0]["id"])
        db.update_transaction(tx_id, 1, 1, "Virement", "Test")
        with sqlite3.connect(self.path) as con:
            actual = con.execute(
                "SELECT id_categorie_forcee,id_sous_categorie_forcee,type_mouvement,commentaire "
                "FROM transactions WHERE id=?", (tx_id,)
            ).fetchone()
        self.assertEqual(actual, (1, 1, "Virement", "Test"))

    def test_forced_date_becomes_effective_and_original_date_is_preserved(self):
        original = db.load_transactions().loc[lambda frame: frame["categorie_exclue"] == 0].iloc[0]
        tx_id = int(original["id"])
        original_date = original["date_originale"]
        db.update_transaction(
            tx_id,
            int(original["id_categorie_forcee"]) if __import__("pandas").notna(original["id_categorie_forcee"]) else None,
            int(original["id_sous_categorie_forcee"]) if __import__("pandas").notna(original["id_sous_categorie_forcee"]) else None,
            original["type_mouvement"], original["commentaire"], date(2025, 1, 15),
        )
        updated = db.load_transactions().set_index("id").loc[tx_id]
        self.assertEqual(updated["date_originale"], original_date)
        self.assertEqual(updated["date_forcee"].date(), date(2025, 1, 15))
        self.assertEqual(updated["date"].date(), date(2025, 1, 15))
        one_transaction = db.load_transactions().loc[lambda frame: frame["id"] == tx_id]
        aggregate = (
            analytics.monthly_category_incomes(one_transaction)
            if float(updated["montant"]) > 0
            else analytics.monthly_category_expenses(one_transaction)
        )
        self.assertEqual(aggregate.iloc[0]["mois"], "2025-01")

    def test_forced_date_can_be_cleared(self):
        tx_id = int(db.load_transactions().iloc[0]["id"])
        db.update_transaction(tx_id, None, None, None, None, date(2025, 2, 10))
        db.update_transaction(tx_id, None, None, None, None, None)
        updated = db.load_transactions().set_index("id").loc[tx_id]
        self.assertTrue(__import__("pandas").isna(updated["date_forcee"]))
        self.assertEqual(updated["date"], updated["date_originale"])
        with sqlite3.connect(self.path) as con:
            stored = con.execute(
                "SELECT dateTimestamp_forcee FROM transactions WHERE id=?", (tx_id,)
            ).fetchone()[0]
        self.assertIsNone(stored)

    def test_loads_monthly_progression_percentage(self):
        amortization = db.load_amortizations().set_index("id").loc[1]
        self.assertEqual(float(amortization["progression_pourcentage"]), 91.67)

    def test_amortization_associations_can_be_updated_and_loaded(self):
        db.update_amortization(
            1, "Impôts fonciers", 100.0, 1200.0, None, 12, 100.0,
            date(2027, 9, 11), None, "Association de test",
            category_id=2, subcategory_id=2,
        )
        amortization = db.load_amortizations().set_index("id").loc[1]
        self.assertEqual(int(amortization["id_categorie"]), 2)
        self.assertEqual(amortization["categorie"], "Courses Alimentaires et entretien")
        self.assertEqual(int(amortization["id_sous_categorie"]), 2)
        self.assertEqual(amortization["sous_categorie"], "SuperMarché")

    def test_create_amortization_with_associations(self):
        amortization_id = db.create_amortization(
            "Nouvel amortissement", 25.0, 300.0, None, 12, 25.0,
            date(2027, 9, 11), None, "Création de test", 3, 4,
        )
        amortization = db.load_amortizations().set_index("id").loc[amortization_id]
        self.assertEqual(amortization["nom"], "Nouvel amortissement")
        self.assertEqual(int(amortization["id_categorie"]), 3)
        self.assertEqual(int(amortization["id_sous_categorie"]), 4)
        self.assertEqual(amortization["categorie"], "Deplacement")
        self.assertEqual(amortization["sous_categorie"], "Peage")

    def test_amortization_rejects_incompatible_subcategory(self):
        with self.assertRaisesRegex(ValueError, "n’appartient pas"):
            db.update_amortization(
                1, "Invalide", 10.0, 100.0, None, 12, 10.0,
                None, None, None, category_id=2, subcategory_id=1,
            )
        with self.assertRaisesRegex(ValueError, "n’appartient pas"):
            db.create_amortization(
                "Invalide", 10.0, 100.0, None, 12, 10.0,
                None, None, None, 2, 1,
            )

    def test_create_reference_chain(self):
        category_id = db.create_category("Test catégorie", 9, True)
        subcategory_id = db.create_subcategory("Test sous-catégorie", category_id, 9, True)
        label_id = db.create_label("TEST MOTIF", "TEST LIBELLÉ", subcategory_id)
        self.assertGreater(category_id, 0)
        self.assertGreater(subcategory_id, 0)
        self.assertGreater(label_id, 0)
        self.assertEqual(len(db.load_categories()), 20)
        self.assertEqual(len(db.load_subcategories()), 35)
        self.assertEqual(len(db.load_labels()), 41)

    def test_rename_category_and_subcategory_preserves_relations(self):
        with sqlite3.connect(self.path) as con:
            category_links_before = con.execute(
                "SELECT COUNT(*) FROM transactions WHERE id_categorie=1 OR id_categorie_forcee=1"
            ).fetchone()[0]
            subcategory_links_before = con.execute(
                "SELECT COUNT(*) FROM transactions "
                "WHERE id_sous_categorie=1 OR id_sous_categorie_forcee=1"
            ).fetchone()[0]
        db.rename_category(1, "Habitation")
        db.rename_subcategory(1, "Crédit logement")
        with sqlite3.connect(self.path) as con:
            self.assertEqual(
                con.execute("SELECT nom FROM categories WHERE id=1").fetchone()[0],
                "Habitation",
            )
            self.assertEqual(
                con.execute("SELECT nom FROM sous_categorie WHERE id=1").fetchone()[0],
                "Crédit logement",
            )
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM transactions "
                    "WHERE id_categorie=1 OR id_categorie_forcee=1"
                ).fetchone()[0],
                category_links_before,
            )
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM transactions "
                    "WHERE id_sous_categorie=1 OR id_sous_categorie_forcee=1"
                ).fetchone()[0],
                subcategory_links_before,
            )

    def test_rename_rejects_existing_names(self):
        with self.assertRaisesRegex(ValueError, "autre catégorie"):
            db.rename_category(1, "Transfert")
        with self.assertRaisesRegex(ValueError, "autre sous-catégorie"):
            db.rename_subcategory(2, "Boulangerie")

    def test_delete_label_keeps_transactions_and_unlinks_them(self):
        label_id = 11
        transaction_count_before = len(db.load_transactions())
        linked = db.label_transaction_count(label_id)
        self.assertEqual(linked, 6)
        detached = db.delete_label(label_id)
        self.assertEqual(detached, linked)
        self.assertEqual(len(db.load_transactions()), transaction_count_before)
        with sqlite3.connect(self.path) as con:
            self.assertIsNone(
                con.execute("SELECT id FROM libelles WHERE id=?", (label_id,)).fetchone()
            )
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM transactions WHERE id_libelle_transforme=?",
                    (label_id,),
                ).fetchone()[0],
                0,
            )
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_rejects_incoherent_category_and_subcategory(self):
        tx_id = int(db.load_transactions().iloc[0]["id"])
        with self.assertRaisesRegex(ValueError, "n’appartient pas"):
            db.update_transaction(tx_id, 2, 1, None, None)

    def test_foreign_keys_are_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with db.connection() as con:
                con.execute(
                    "INSERT INTO libelles(motif,libelle_transforme,id_sous_categorie) VALUES (?,?,?)",
                    ("INVALID", "INVALID", 999999999),
                )

    def test_real_transfer_category_is_fully_excluded_from_analytics(self):
        tx = db.load_transactions()
        transfers = tx.loc[tx["categorie_effective"] == "Transfert"]
        self.assertEqual(len(transfers), 18)
        self.assertTrue(transfers["categorie_exclue"].astype(int).eq(1).all())
        included = analytics.included_transactions(tx)
        self.assertEqual(len(included), 382)
        self.assertFalse(included["categorie_effective"].eq("Transfert").any())
        monthly = analytics.monthly_category_expenses(tx)
        monthly_incomes = analytics.monthly_category_incomes(tx)
        self.assertFalse(monthly["categorie"].eq("Transfert").any())
        self.assertFalse(monthly_incomes["categorie"].eq("Transfert").any())

    def test_excluded_category_is_ignored_by_analytics_but_kept_in_transactions(self):
        baseline = analytics.included_transactions(db.load_transactions())
        category_id = db.create_category("Transferts internes", 1, True, True)
        created = db.load_categories().loc[lambda frame: frame["id"] == category_id].iloc[0]
        self.assertEqual(int(created["exclu"]), 1)
        tx = db.load_transactions()
        non_excluded = tx.loc[tx["categorie_exclue"].fillna(0).astype(int).ne(1)]
        tx_id = int(non_excluded.iloc[0]["id"])
        second_tx_id = int(non_excluded.iloc[1]["id"])
        with db.connection() as con:
            # La catégorie forcée exclue prime sur la catégorie calculée non exclue.
            con.execute(
                "UPDATE transactions SET id_categorie=1, id_categorie_forcee=? WHERE id=?",
                (category_id, tx_id),
            )
            # Et une catégorie forcée non exclue prime sur une calculée exclue.
            con.execute(
                "UPDATE transactions SET id_categorie=?, id_categorie_forcee=1 WHERE id=?",
                (category_id, second_tx_id),
            )
        refreshed = db.load_transactions()
        self.assertEqual(len(refreshed), 400)
        selected = refreshed.loc[refreshed["id"] == tx_id].iloc[0]
        second = refreshed.loc[refreshed["id"] == second_tx_id].iloc[0]
        self.assertEqual(int(selected["categorie_exclue"]), 1)
        self.assertEqual(int(second["categorie_exclue"]), 0)
        included = analytics.included_transactions(refreshed)
        self.assertEqual(len(included), len(baseline) - 1)
        self.assertNotIn(tx_id, included["id"].tolist())
        self.assertIn(second_tx_id, included["id"].tolist())

    def test_update_amortization_recalculates_both_progress_percentages(self):
        db.update_amortization(
            1, "Impôts fonciers", 750.0, 1500.0, 1400.0, 12, 125.0,
            date(2027, 9, 11), date(2026, 10, 9), "Réserve foncière",
            reference_date=date(2026, 9, 11),
        )
        amortization = db.load_amortizations().set_index("id").loc[1]
        self.assertEqual(amortization["nom"], "Impôts fonciers")
        self.assertEqual(float(amortization["avancement_pourcentage"]), 50.0)
        self.assertEqual(int(amortization["mois_restant"]), 12)
        self.assertEqual(float(amortization["mensualite_ajustee"]), 125.0)
        self.assertEqual(float(amortization["progression_pourcentage"]), 150.0)
        self.assertEqual(
            amortization["date_dernier_paiement_affichee"].date(), date(2026, 10, 9)
        )

    def test_adjusted_monthly_payment_is_zero_when_objective_is_reached(self):
        db.update_amortization(
            1, "Impôts fonciers", 1500.0, 1500.0, 1400.0, 12, 125.0,
            date(2027, 9, 11), None, None,
            reference_date=date(2026, 9, 11),
        )
        amortization = db.load_amortizations().set_index("id").loc[1]
        self.assertEqual(float(amortization["avancement_pourcentage"]), 100.0)
        self.assertEqual(float(amortization["mensualite_ajustee"]), 0.0)
        self.assertEqual(float(amortization["progression_pourcentage"]), 100.0)

    def test_cent_allocation_uses_adjusted_monthly_weights_exactly(self):
        self.assertEqual(
            db._allocate_cents_by_weights(100.0, [0.0, 1.0, 3.0]),
            [0.0, 25.0, 75.0],
        )
        self.assertEqual(
            db._allocate_cents_by_weights(1.0, [1.0, 1.0, 1.0]),
            [0.34, 0.33, 0.33],
        )

    def test_global_contribution_distributes_all_monthlies_and_surplus(self):
        before = db.load_amortizations().set_index("id")
        dates_before = before["date_dernier_paiement"].to_dict()
        manual_before = float(db.load_manual_amortization_account()["solde"])
        transaction_ids, distributed, surplus = db.create_global_amortization_contribution(
            400.0, date(2026, 9, 15), "La Banque Postale", "compte courant",
            "Mensualités globales test", 4, 5, "Test versement global",
        )
        self.assertEqual(distributed, 341.18)
        self.assertEqual(surplus, 58.82)
        after = db.load_amortizations().set_index("id")
        expected_distributions = db._allocate_cents_by_weights(
            float(before["mensualite"].sum()),
            before["mensualite_ajustee"].astype(float).tolist(),
        )
        expected_by_id = dict(zip(before.index, expected_distributions))
        for amortization_id, row in before.iterrows():
            self.assertAlmostEqual(
                float(after.loc[amortization_id, "solde"]),
                float(row["solde"]) + expected_by_id[amortization_id],
                places=2,
            )
            self.assertEqual(
                int(after.loc[amortization_id, "date_dernier_paiement"]),
                int(dates_before[amortization_id]),
            )
            adjusted = float(after.loc[amortization_id, "mensualite_ajustee"])
            expected_monthly_progress = round(
                (
                    int(after.loc[amortization_id, "mois_restant"]) * adjusted
                    + float(after.loc[amortization_id, "solde"])
                )
                / float(after.loc[amortization_id, "objectif"])
                * 100,
                2,
            )
            self.assertEqual(
                float(after.loc[amortization_id, "progression_pourcentage"]),
                expected_monthly_progress,
            )
        self.assertAlmostEqual(
            float(db.load_manual_amortization_account()["solde"]),
            manual_before + 58.82,
            places=2,
        )
        positive_distributions = sum(value > 0 for value in expected_distributions)
        self.assertEqual(len(transaction_ids), positive_distributions + 1)
        with sqlite3.connect(self.path) as con:
            transactions = con.execute(
                f"SELECT libelle_originale, montant, type_mouvement FROM transactions "
                f"WHERE id IN ({','.join('?' for _ in transaction_ids)}) ORDER BY id",
                transaction_ids,
            ).fetchall()
        self.assertEqual(len(transactions), positive_distributions + 1)
        self.assertAlmostEqual(sum(float(row[1]) for row in transactions), -400.0, places=2)
        self.assertEqual(
            sum(row[2] == "Amortissement - mensualité" for row in transactions),
            positive_distributions,
        )
        self.assertEqual(transactions[-1][0], "Mensualités globales test — Épargne")
        self.assertEqual(transactions[-1][1:], (-58.82, "Amortissement - épargne"))
        with sqlite3.connect(self.path) as con:
            surplus_references = con.execute(
                "SELECT id_categorie_forcee,id_sous_categorie_forcee "
                "FROM transactions WHERE id=?", (transaction_ids[-1],)
            ).fetchone()
        self.assertEqual(surplus_references, (4, 5))
        transaction_by_name = {
            transaction[0].split(" — ")[-1]: transaction for transaction in transactions[:-1]
        }
        for amortization_id, amortization in before.iterrows():
            expected = expected_by_id[amortization_id]
            if expected > 0:
                transaction = transaction_by_name[str(amortization["nom"])]
                self.assertAlmostEqual(transaction[1], -expected, places=2)
            else:
                self.assertNotIn(str(amortization["nom"]), transaction_by_name)
        self.assertEqual(len(db.load_transactions()), 400 + positive_distributions + 1)

    def test_global_contribution_at_exact_total_has_no_surplus(self):
        manual_before = float(db.load_manual_amortization_account()["solde"])
        transactions_before = len(db.load_transactions())
        amortizations_before = db.load_amortizations()
        positive_adjusted = int((amortizations_before["mensualite_ajustee"] > 0).sum())
        transaction_ids, distributed, surplus = db.create_global_amortization_contribution(
            341.18, date(2026, 9, 15), "La Banque Postale", "compte courant",
            "Mensualités exactes", None, None, None,
        )
        self.assertEqual(len(transaction_ids), positive_adjusted)
        self.assertTrue(all(transaction_id > 0 for transaction_id in transaction_ids))
        self.assertEqual(distributed, 341.18)
        self.assertEqual(surplus, 0.0)
        self.assertEqual(
            len(db.load_transactions()), transactions_before + positive_adjusted
        )
        with sqlite3.connect(self.path) as con:
            created_total = con.execute(
                f"SELECT SUM(montant) FROM transactions WHERE id IN "
                f"({','.join('?' for _ in transaction_ids)})",
                transaction_ids,
            ).fetchone()[0]
        self.assertAlmostEqual(float(created_total), -341.18, places=2)
        self.assertEqual(
            float(db.load_manual_amortization_account()["solde"]), manual_before
        )

    def test_global_contribution_below_total_is_rejected_atomically(self):
        balances_before = db.load_amortizations()[["id", "solde"]].to_dict("records")
        manual_before = db.load_manual_amortization_account()["solde"]
        transactions_before = len(db.load_transactions())
        with self.assertRaisesRegex(ValueError, "au moins égal"):
            db.create_global_amortization_contribution(
                341.17, date(2026, 9, 15), "La Banque Postale", "compte courant",
                "Montant insuffisant", None, None, None,
            )
        self.assertEqual(
            db.load_amortizations()[["id", "solde"]].to_dict("records"),
            balances_before,
        )
        self.assertEqual(db.load_manual_amortization_account()["solde"], manual_before)
        self.assertEqual(len(db.load_transactions()), transactions_before)

    def test_global_contribution_uses_each_association_and_fallback(self):
        with db.connection() as con:
            con.execute(
                "UPDATE amortissement SET id_categorie=1,id_sous_categorie=1 WHERE id=1"
            )
            con.execute(
                "UPDATE amortissement SET id_categorie=NULL,id_sous_categorie=NULL WHERE id<>1"
            )
        transaction_ids, _, surplus = db.create_global_amortization_contribution(
            341.18, date(2026, 9, 15), "La Banque Postale", "compte courant",
            "Associations test", 2, 2, None,
        )
        self.assertEqual(surplus, 0.0)
        with sqlite3.connect(self.path) as con:
            created = con.execute(
                f"SELECT libelle_originale,id_categorie_forcee,id_sous_categorie_forcee "
                f"FROM transactions WHERE id IN ({','.join('?' for _ in transaction_ids)})",
                transaction_ids,
            ).fetchall()
        first_name = db.load_amortizations().set_index("id").loc[1, "nom"]
        first = next(row for row in created if row[0].endswith(f"— {first_name}"))
        self.assertEqual(first[1:], (1, 1))
        fallback_rows = [row for row in created if row != first]
        self.assertTrue(all(row[1:] == (2, 2) for row in fallback_rows))

    def test_invalid_stored_association_rolls_back_global_contribution(self):
        balances_before = db.load_amortizations()[["id", "solde"]].to_dict("records")
        transactions_before = len(db.load_transactions())
        # Simule une référence invalide introduite par un outil externe ayant
        # désactivé les clés étrangères ; l’application doit encore la détecter.
        with sqlite3.connect(self.path) as con:
            con.execute("PRAGMA foreign_keys=OFF")
            con.execute(
                "UPDATE amortissement SET id_categorie=999999,id_sous_categorie=NULL WHERE id=2"
            )
        with self.assertRaisesRegex(ValueError, "n’existe pas ou est inactive"):
            db.create_global_amortization_contribution(
                341.18, date(2026, 9, 15), "La Banque Postale", "compte courant",
                "Association invalide", 2, 2, None,
            )
        self.assertEqual(len(db.load_transactions()), transactions_before)
        self.assertEqual(
            db.load_amortizations()[["id", "solde"]].to_dict("records"),
            balances_before,
        )

    def test_manual_account_balance_is_independently_editable(self):
        amortizations_before = db.load_amortizations()
        transactions_before = len(db.load_transactions())
        db.update_manual_amortization_balance(222.22)
        self.assertEqual(db.load_manual_amortization_account()["solde"], 222.22)
        assert_frame_equal(db.load_amortizations(), amortizations_before)
        self.assertEqual(len(db.load_transactions()), transactions_before)

    def test_partial_amortization_withdrawal_creates_income_and_reduces_balance(self):
        balance_before = float(db.load_amortizations().set_index("id").loc[1, "solde"])
        transaction_id = db.create_amortization_transaction(
            1, "withdrawal", 50.0, date(2026, 9, 16),
            "La Banque Postale", "compte courant", "Restitution test",
            4, 5, "Test revenu",
        )
        with sqlite3.connect(self.path) as con:
            amount = con.execute(
                "SELECT montant FROM transactions WHERE id=?", (transaction_id,)
            ).fetchone()[0]
            balance_after = con.execute(
                "SELECT solde FROM amortissement WHERE id=1"
            ).fetchone()[0]
        self.assertEqual(amount, 50.0)
        self.assertAlmostEqual(balance_after, balance_before - 50.0, places=2)

    def test_withdrawal_over_balance_is_rejected_atomically(self):
        balance_before = float(db.load_amortizations().set_index("id").loc[1, "solde"])
        count_before = len(db.load_transactions())
        with self.assertRaisesRegex(ValueError, "dépasser le solde"):
            db.create_amortization_transaction(
                1, "withdrawal", balance_before + 0.01, date(2026, 9, 16),
                "La Banque Postale", "compte courant", "Impossible",
                None, None, None,
            )
        self.assertEqual(len(db.load_transactions()), count_before)
        self.assertEqual(
            float(db.load_amortizations().set_index("id").loc[1, "solde"]),
            balance_before,
        )

    def test_monthly_debit_crud_preserves_identifier_and_all_fields(self):
        monthly_id = db.create_monthly_debit(
            "Test abonnement", 12.34, "Carte", 7, 11.11,
            1, 1, "Trade Republic", "Compte espèces",
        )
        self.assertGreater(monthly_id, 0)
        created = db.load_monthly_debits().set_index("id").loc[monthly_id]
        self.assertEqual(created["nom"], "Test abonnement")
        self.assertEqual(float(created["mensualite"]), 12.34)
        self.assertEqual(created["methode_paiment"], "Carte")
        self.assertEqual(int(created["jourDePrelevement"]), 7)
        self.assertEqual(float(created["ancienneMensualite"]), 11.11)
        self.assertEqual(int(created["id_categorie"]), 1)
        self.assertEqual(int(created["id_sous_categorie"]), 1)
        self.assertEqual(created["banque"], "Trade Republic")
        self.assertEqual(created["compteBancaire"], "Compte espèces")

        db.update_monthly_debit(
            monthly_id, "Test modifié", 45.67, "Prélèvement", 29, 40.0,
            2, 2, "Autre banque", "Compte courant",
        )
        updated = db.load_monthly_debits().set_index("id").loc[monthly_id]
        self.assertEqual(int(updated.name), monthly_id)
        self.assertEqual(updated["nom"], "Test modifié")
        self.assertEqual(float(updated["mensualite"]), 45.67)
        self.assertEqual(updated["methode_paiment"], "Prélèvement")
        self.assertEqual(int(updated["jourDePrelevement"]), 29)
        self.assertEqual(float(updated["ancienneMensualite"]), 40.0)
        self.assertEqual(int(updated["id_categorie"]), 2)
        self.assertEqual(int(updated["id_sous_categorie"]), 2)
        self.assertEqual(updated["banque"], "Autre banque")
        self.assertEqual(updated["compteBancaire"], "Compte courant")

        db.delete_monthly_debit(monthly_id)
        self.assertNotIn(monthly_id, db.load_monthly_debits()["id"].tolist())

    def test_monthly_debit_validation_is_atomic(self):
        count_before = len(db.load_monthly_debits())
        with self.assertRaisesRegex(ValueError, "compris entre 1 et 31"):
            db.create_monthly_debit(
                "Jour invalide", 10.0, None, 32, None, None, None, None, None
            )
        with self.assertRaisesRegex(ValueError, "n’appartient pas"):
            db.create_monthly_debit(
                "Association invalide", 10.0, None, 10, None,
                1, 2, None, None,
            )
        self.assertEqual(len(db.load_monthly_debits()), count_before)

    def test_monthly_follow_up_and_persistent_surplus(self):
        initial = db.monthly_follow_up(date(2026, 9, 12))
        self.assertEqual(initial["trade_republic_total"], 623.78)
        self.assertNotIn("trade_republic_remaining", initial)
        self.assertEqual(initial["amortization_total"], 341.18)
        self.assertEqual(initial["amortization_balances_total"], 3056.68)
        self.assertEqual(initial["manual_amortization_balance"], 127.49)
        self.assertEqual(initial["minimum_trade_republic"], 3807.95)
        self.assertEqual(
            initial["minimum_trade_republic"],
            initial["trade_republic_total"]
            + initial["amortization_balances_total"]
            + initial["manual_amortization_balance"],
        )
        self.assertEqual(initial["desired_surplus"], 60.29)
        self.assertEqual(initial["monthly_transfer"], 1025.25)
        self.assertEqual(
            initial["monthly_transfer"],
            initial["trade_republic_total"]
            + initial["amortization_total"]
            + initial["desired_surplus"],
        )

        db.update_desired_amortization_surplus(58.82)
        self.assertEqual(db.load_desired_amortization_surplus(), 58.82)
        updated = db.monthly_follow_up(date(2026, 9, 12))
        self.assertEqual(updated["desired_surplus"], 58.82)
        self.assertEqual(updated["monthly_transfer"], 1023.78)
        with sqlite3.connect(self.path) as con:
            stored = con.execute(
                "SELECT valeur_reelle FROM budgetbibis_settings WHERE cle=?",
                ("surplus_mensualite_amortissement",),
            ).fetchone()[0]
        self.assertEqual(stored, 58.82)

    def test_remaining_monthly_debits_include_every_account_without_affecting_transfer(self):
        remaining = db.monthly_debits_remaining(date(2026, 9, 12))
        self.assertEqual(len(remaining), 2)
        by_account = {
            (row.banque, row.compte_bancaire): row
            for row in remaining.itertuples(index=False)
        }
        postal = by_account[("La Banque Postale", "compte courant")]
        self.assertEqual(int(postal.nombre_mensualites), 4)
        self.assertEqual(float(postal.total_mensuel), 915.29)
        self.assertEqual(float(postal.reste_a_prelever), 0.0)
        trade = by_account[("Trade Republic", "Default")]
        self.assertEqual(int(trade.nombre_mensualites), 14)
        self.assertEqual(float(trade.total_mensuel), 623.78)
        self.assertEqual(float(trade.reste_a_prelever), 224.72)
        self.assertEqual(float(remaining["reste_a_prelever"].sum()), 224.72)
        self.assertEqual(
            db.monthly_follow_up(date(2026, 9, 12))["monthly_transfer"],
            1025.25,
        )

    def test_current_loans_progress_and_remaining_balance_update(self):
        loans = db.load_current_loans().set_index("id")
        self.assertEqual(len(loans), 2)
        self.assertEqual(float(loans.loc[1, "montantEmprunte"]), 188413.0)
        self.assertEqual(float(loans.loc[1, "restantARembourse"]), 156922.9)
        self.assertEqual(float(loans.loc[1, "avancement_pourcentage"]), 16.71)
        self.assertEqual(float(loans.loc[2, "avancement_pourcentage"]), 28.36)

        db.update_loan_remaining_balance(1, 150000.0)
        updated = db.load_current_loans().set_index("id").loc[1]
        self.assertEqual(float(updated["restantARembourse"]), 150000.0)
        self.assertEqual(float(updated["avancement_pourcentage"]), 20.39)

        db.update_loan_remaining_balance(1, 0.0)
        self.assertNotIn(1, db.load_current_loans()["id"].tolist())

    def test_loan_remaining_balance_validation_is_atomic(self):
        before = float(db.load_current_loans().set_index("id").loc[1, "restantARembourse"])
        with self.assertRaisesRegex(ValueError, "positif ou nul"):
            db.update_loan_remaining_balance(1, -0.01)
        with self.assertRaisesRegex(ValueError, "dépasser le montant emprunté"):
            db.update_loan_remaining_balance(1, 188413.01)
        after = float(db.load_current_loans().set_index("id").loc[1, "restantARembourse"])
        self.assertEqual(after, before)

    def test_previous_month_balance_is_persistent_and_accepts_negative_values(self):
        self.assertEqual(db.load_previous_month_balance(), 0.0)
        db.update_previous_month_balance(-123.45)
        self.assertEqual(db.load_previous_month_balance(), -123.45)
        with sqlite3.connect(self.path) as con:
            stored = con.execute(
                "SELECT valeur_reelle FROM budgetbibis_settings WHERE cle=?",
                ("solde_mois_precedent",),
            ).fetchone()[0]
        self.assertEqual(stored, -123.45)

    def test_monthly_category_expenses_excludes_marked_categories(self):
        tx = db.load_transactions().head(2).copy()
        tx["date"] = __import__("pandas").to_datetime(["2026-09-01", "2026-09-02"])
        tx["montant"] = [-100.0, -40.0]
        tx["categorie_effective"] = ["Courses", "Transfert"]
        tx["categorie_exclue"] = [0, 1]
        result = analytics.monthly_category_expenses(tx)
        self.assertEqual(result.to_dict("records"), [
            {"mois": "2026-09", "categorie": "Courses", "montant": 100.0}
        ])

    def test_monthly_category_incomes_keeps_only_positive_non_excluded_amounts(self):
        tx = db.load_transactions().head(4).copy()
        tx["date"] = __import__("pandas").to_datetime(
            ["2026-08-01", "2026-09-01", "2026-09-02", "2026-09-03"]
        )
        tx["montant"] = [500.0, 1200.0, -50.0, 400.0]
        tx["categorie_effective"] = ["Salaire", "Salaire", "Courses", "Transfert"]
        tx["categorie_exclue"] = [0, 0, 0, 1]
        result = analytics.monthly_category_incomes(tx)
        self.assertEqual(result.to_dict("records"), [
            {"mois": "2026-08", "categorie": "Salaire", "montant": 500.0},
            {"mois": "2026-09", "categorie": "Salaire", "montant": 1200.0},
        ])

    def test_monthly_categories_are_net_between_income_and_expense(self):
        tx = db.load_transactions().head(6).copy()
        tx["date"] = __import__("pandas").to_datetime(["2026-09-01"] * 6)
        tx["montant"] = [11.19, -3.16, 5.0, -12.0, 4.0, -4.0]
        tx["categorie_effective"] = [
            "Intérêts et Dividendes", "Intérêts et Dividendes",
            "Courses", "Courses", "Catégorie nulle", "Catégorie nulle",
        ]
        tx["categorie_exclue"] = [0] * 6

        incomes = analytics.monthly_category_incomes(tx)
        expenses = analytics.monthly_category_expenses(tx)

        self.assertEqual(incomes.to_dict("records"), [
            {
                "mois": "2026-09",
                "categorie": "Intérêts et Dividendes",
                "montant": 8.03,
            }
        ])
        self.assertEqual(expenses.to_dict("records"), [
            {"mois": "2026-09", "categorie": "Courses", "montant": 7.0}
        ])
        self.assertFalse(incomes["categorie"].isin(expenses["categorie"]).any())
        self.assertNotIn("Catégorie nulle", incomes["categorie"].tolist())
        self.assertNotIn("Catégorie nulle", expenses["categorie"].tolist())

    def test_total_and_forecast_balances_subtracts_remaining_debits(self):
        total, forecast = analytics.total_and_forecast_balances(
            month_balance=1000.10,
            previous_month_balance=-100.05,
            remaining_debits=224.72,
        )
        self.assertEqual(total, 900.05)
        self.assertEqual(forecast, 675.33)


if __name__ == "__main__": 
    unittest.main()
