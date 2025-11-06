"""Transaction model for Firefly III."""

import hashlib
from datetime import datetime

from pytz import timezone


class Transaction:
    """Template for a bank transaction."""

    def __init__(
        self,
        date,
        description,
        asset_account,
        dest_account,
        raw_dest_account,
        total,
        type: str = "withdrawal",
        id=None,
        state=None,
        card=None,
        category=None,
        tags=None,
        notes=None,
    ):
        self.date = date
        self.description = description
        self.asset_account = asset_account
        self.destination_account = dest_account
        self.raw_destination_account = raw_dest_account
        self.total = total
        self.type = type
        self.category_name = category or ""
        self.tags = tags or []
        self.notes = notes or ""
        self.state = state or ""
        self.card = card
        self.id = id or self._generate_id()

    def is_expense(self):
        """Check if it's an expense."""
        return self.type == "withdrawal"

    def is_income(self):
        """Check if it is an income (refund/recharge)."""
        return self.type == "deposit"

    def _format_date(self, date_str):
        dt = datetime.strptime(date_str, "%d/%m/%Y")
        tz = timezone("Europe/Rome")
        return tz.localize(dt).isoformat()

    def _generate_id(self):
        raw = f"{self.date}|{self.raw_destination_account.strip().lower()}|{self.total:.2f}"
        uid = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        return uid

    def to_firefly_payload(self):
        return {
            "type": self.type,
            "date": self._format_date(self.date),
            "amount": self.total,
            "description": self.description,
            "source_name": self.asset_account,
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
            type=data.get("type"),
            date=data.get("date"),
            asset_account=data.get("asset_account", ""),
            description=data.get("description", ""),
            dest_account=data.get("destination_account", ""),
            raw_dest_account=data.get("raw_destination_account", ""),
            total=float(data.get("total", 0)),
            category=data.get("category_name"),
            tags=data.get("tags") or [],
            notes=data.get("notes", ""),
            state=data.get("state"),
            card=data.get("card"),
            id=data.get("id"),
        )
