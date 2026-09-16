import unittest

import pandas as pd

import analytics


class TransactionFilterTests(unittest.TestCase):
    def test_uncategorized_requires_both_categories_to_be_missing(self):
        transactions = pd.DataFrame(
            {
                "categorie": [None, "Courses", None, "", "   ", "Courses"],
                "categorie_forcee": [None, None, "Loisirs", "", None, "Loisirs"],
            }
        )

        self.assertEqual(
            analytics.uncategorized_mask(transactions).tolist(),
            [True, False, False, True, True, False],
        )

    def test_stale_table_selection_is_ignored_after_filtered_row_disappears(self):
        remaining_transactions = pd.DataFrame({"id": [102]})

        self.assertIsNone(
            analytics.selected_transaction_id(remaining_transactions, [1])
        )
        self.assertEqual(
            analytics.selected_transaction_id(remaining_transactions, [0]),
            102,
        )
        self.assertIsNone(
            analytics.selected_transaction_id(remaining_transactions.iloc[0:0], [0])
        )


if __name__ == "__main__":
    unittest.main()
