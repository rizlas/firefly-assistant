import json
from abc import ABC, abstractmethod
from typing import Union

from src.firefly.models import Transaction
from src.firefly.client import FireflyClient

from .types import (
    PrepaidCardBehavior,
    StandardCardBehavior,
    TransactionType,
    TransferType,
)


class BaseParser(ABC):
    def __init__(
        self,
        asset_account,
        firefly_client,
        card_behavior: Union[StandardCardBehavior, PrepaidCardBehavior],
    ):
        """
        Args:
            asset_account: Asset account from which transactions originate
            firefly_client: Firefly API client
            card_type: CardType enum that defines the behavior
        """
        self.firefly_client: FireflyClient = firefly_client
        self.asset_account = asset_account
        self.behavior = card_behavior

    @abstractmethod
    def parse(self, file_path) -> list[Transaction]:
        """
        Parse transactions from file.

        Args:
            file_path: Path to file to parse

        Returns:
            List of Transaction objects
        """
        pass

    def export_to_json(self, transactions, output_path):
        """Export transactions to JSON file.

        Args:
            transactions: List of Transaction objects
            output_path: Path where to save JSON file
        """
        data = [t.to_json() for t in transactions]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def classify_transaction(
        self, amount: float, raw_account: str
    ) -> tuple[str, float]:
        """
        Classify transaction based on amount sign and card type.

        Args:
            amount: Raw amount from Excel (with sign)
            raw_account: Raw merchant name or raw transfer account name

        Returns:
            Tuple of (transaction_type, final_amount)
            - transaction_type: "withdrawal", "deposit", or "transfer"
            - transfer_type: "in" or "out" if any
            - final_amount: Absolute amount (always positive for Firefly)
        """
        final_amount = abs(amount)

        if self.behavior.all_positive:
            # Standard card: all positive, all expenses
            return TransactionType.EXPENSE, None, final_amount
        else:
            # Prepaid card: check keywords FIRST (before sign)
            # This handles cases where recharges appear as negative
            contains, direction = self._check_transfer_specs(raw_account)
            if contains:
                return TransactionType.TRANSFER, direction, final_amount

            # No keyword match: use sign to determine type
            if amount < 0:
                # Negative without keyword = expense
                return TransactionType.EXPENSE, None, final_amount
            else:
                positive_amounts_type = TransactionType.REFUND
                # Positive without keyword = use fallback
                # positive_is_transfer: Fallback for positive amounts without keywords
                #      True = transfer, False = refund
                if self.behavior.positive_is_transfer:
                    positive_amounts_type = TransactionType.TRANSFER

                return positive_amounts_type, TransferType.IN, final_amount

    def _check_transfer_specs(self, raw_account: str) -> bool:
        """
        Check if merchant name contains any transfer keyword.

        Args:
            raw_account: Raw merchant name or raw transfer account name

        Returns:
            True and direction if any keyword matches
        """
        if not self.behavior.transfer_specs:
            return False, None

        for spec in self.behavior.transfer_specs:
            if spec["keyword"].lower() in raw_account.lower():
                return True, spec["direction"]

        return False, None
