"""Transaction model for Firefly III."""

import hashlib
from datetime import datetime

from pytz import timezone

from src.parsers.types import TransactionType, TransferType


class Transaction:
    """Template for a bank transaction."""

    def __init__(
        self,
        date,
        description,
        source_account,
        dest_account,
        account_mapping,
        total,
        enable_mapping=True,
        type: TransactionType = TransactionType.EXPENSE,
        transfer_type=None,
        id=None,
        state=None,
        card=None,
        category=None,
        tags=None,
        notes=None,
    ):
        self.date = date
        self.description = description
        self.source_account = source_account
        self.destination_account = dest_account
        self.account_mapping = account_mapping
        self.total = total
        self.enable_mapping = enable_mapping
        self.type = type
        self.transfer_type = transfer_type
        self.category_name = category or ""
        self.tags = tags or []
        self.notes = notes or ""
        self.state = state or ""
        self.card = card
        self.id = id or self._generate_id()

    def is_transfer(self) -> bool:
        return self.type == TransactionType.TRANSFER

    def is_refund(self) -> bool:
        """True if it's a refund."""
        return self.type == TransactionType.REFUND

    def is_transfer_in(self) -> bool:
        """True if it's an inbound transfer."""
        return self.is_transfer() and self.transfer_type == TransferType.IN

    def is_transfer_out(self) -> bool:
        """True if it's an outbound transfer."""
        return self.is_transfer() and self.transfer_type == TransferType.OUT

    def is_income(self) -> bool:
        """True if it's a refund or money coming in via transfer."""
        if self.is_refund():
            return True
        if self.is_transfer_in():
            return True
        return False

    def is_expense(self) -> bool:
        """True if it's an expense or money going out via transfer."""
        if self.type is TransactionType.EXPENSE:
            return True
        if self.is_transfer_out():
            return True
        return False

    def _format_date(self, date_str):
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.replace(tzinfo=timezone("UTC")).isoformat()
            except ValueError:
                continue
        raise ValueError(f"Unable to parse date: {date_str}")

    def _generate_id(self):
        raw = f"{self.date}|{self.account_mapping.strip().lower()}|{self.total:.2f}"
        uid = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        return uid

    def to_firefly_payload(self):
        return {
            "type": self.type.value,
            "date": self._format_date(self.date),
            "amount": self.total,
            "description": self.description,
            "source_name": self.source_account,
            "destination_name": self.destination_account,
            "category_name": self.category_name,
            "tags": self.tags,
            "currency_code": "EUR",
            "currency_name": "Euro",
            "currency_symbol": "€",
            "currency_decimal_places": 2,
            "external_id": self.id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict):
        """Create a Transaction instance from a JSON/dict object."""
        return cls(
            type=TransactionType(data.get("type")),
            transfer_type=(
                TransferType(data["transfer_type"])
                if data.get("transfer_type")
                else None
            ),
            date=data.get("date"),
            source_account=data.get("source_account", ""),
            description=data.get("description", ""),
            dest_account=data.get("destination_account", ""),
            account_mapping=data.get("account_mapping", ""),
            enable_mapping=data.get("enable_mapping", True),
            total=float(data.get("total", 0)),
            category=data.get("category_name"),
            tags=data.get("tags") or [],
            notes=data.get("notes", ""),
            state=data.get("state"),
            card=data.get("card"),
            id=data.get("id"),
        )

    def to_json(self):
        return {
            "id": self.id,
            "date": self.date,
            "description": self.description,
            "source_account": self.source_account,
            "destination_account": self.destination_account,
            "account_mapping": self.account_mapping,
            "enable_mapping": self.enable_mapping,
            "total": self.total,
            "type": self.type,
            "transfer_type": self.transfer_type,
            "category_name": self.category_name,
            "tags": self.tags,
            "notes": self.notes,
            "state": self.state,
            "card": self.card,
        }
