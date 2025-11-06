import warnings

import openpyxl

from src.firefly.models import Transaction

from .base import BaseParser
from .types import TransactionType

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")


class NexiParser(BaseParser):
    def parse(self, file_path, skip_already_imported=True):
        """
        Parse the Excel file of transactions.

        Args:
            file_path: Path to the Excel file
            skip_already_imported: If True, skips transactions already imported
        """
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb.active
        card_info = ws["B8"].value

        transactions = []
        for row in ws.iter_rows(min_row=11):
            date = row[2].value  # Column C
            raw_dest_account = row[5].value  # Column F
            state = row[6].value  # Column G
            total = row[9].value  # Column J

            # Determine the transaction type, normalize the amount, and map the
            # destination. account
            tx_type, total = self.classify_transaction(total, raw_dest_account)
            dest_mapped = self.map_destination(raw_dest_account)

            # For deposit and transfer, source and destination must be reversed
            if tx_type in [
                TransactionType.REFUND.value,
                TransactionType.TRANSFER.value,
            ]:
                # Money coming IN to the asset account
                asset_account = dest_mapped
                destination_account = self.asset_account
            else:
                # Withdrawal: money leaving the asset account
                asset_account = self.asset_account
                destination_account = dest_mapped

            tx = Transaction(
                date=date,
                description="",
                dest_account=destination_account,
                raw_dest_account=raw_dest_account,
                total=total,
                type=tx_type,
                state=state,
                card=card_info,
                asset_account=asset_account,
            )

            if skip_already_imported:
                if self.firefly_client.transaction_exists(tx.id):
                    continue

            transactions.append(tx)

        return transactions
