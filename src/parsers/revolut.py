import csv
from datetime import datetime
from src.firefly.models import Transaction
from .base import BaseParser
from .types import TransactionType, TransferType

COL_TYPE = 0
COL_DATE = 2  # Started Date
COL_DESCRIPTION = 4
COL_AMOUNT = 5
COL_STATE = 8


class RevolutParser(BaseParser):
    def parse(self, file_path, skip_already_imported=True):
        transactions = []

        with open(file_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # Skip header

            rows = []
            completed = {s.lower() for s in self.behavior.completed_states}

            for row in reader:
                if len(row) < 9:
                    continue
                state = row[COL_STATE].strip()
                if state.lower() not in completed:
                    continue
                rows.append(row)

        # Sort by Started Date descending (most recent first)
        rows.sort(key=lambda r: r[COL_DATE], reverse=True)

        for row in rows:
            raw_type = row[COL_TYPE].strip()
            date_str = row[COL_DATE].strip()
            merchant = row[COL_DESCRIPTION].strip()
            state = row[COL_STATE].strip()

            try:
                amount = float(row[COL_AMOUNT].replace(",", "."))
            except ValueError:
                continue

            date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").strftime(
                "%d/%m/%Y %H:%M:%S"
            )

            raw_account = f"{raw_type} {merchant}"
            tx_type, transfer_type, amount = self.classify_transaction(
                amount, raw_account
            )

            asset_account = self.asset_account
            mapped_account = self.firefly_client.map_account(
                self.firefly_client.ASSET_ACCOUNT_TYPE_MAP[tx_type], merchant
            )
            destination_account = mapped_account or merchant

            if tx_type in [TransactionType.REFUND, TransactionType.TRANSFER]:
                if (
                    tx_type is TransactionType.REFUND
                    or transfer_type == TransferType.IN
                ):
                    asset_account = destination_account
                    destination_account = self.asset_account

            category = self.auto_categorize(destination_account)

            tx = Transaction(
                date=date,
                description="",
                source_account=asset_account,
                dest_account=destination_account,
                account_mapping=merchant,
                total=amount,
                type=tx_type.value,
                transfer_type=transfer_type.value if transfer_type else None,
                state=state,
                card=None,
                category=category,
            )

            if skip_already_imported:
                if self.firefly_client.transaction_exists(tx.id):
                    continue

            transactions.append(tx)

        return transactions
