import json
from typing import Dict, List
from urllib.parse import urljoin

import requests

from src.parsers.types import TransactionType

from .models import Transaction


class FireflyClient:
    ASSET_ACCOUNT_TYPE_MAP = {
        TransactionType.EXPENSE: "expense",
        TransactionType.REFUND: "revenue",
        TransactionType.TRANSFER: "asset",
    }

    def __init__(self, base_url, token, auto_categories=None):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        # Alias ​​-> Canonical Account Name Mapping Cache
        self.alias_map: Dict[str, str] = {}
        # Reverse cache: account name -> alias list
        self.account_aliases: Dict[str, List[str]] = {}
        self.auto_categories = auto_categories
        self.build_alias_mapping()

    def _get(self, endpoint, **params):
        """Fetch all paginated results from a paginated API endpoint."""
        full_url = urljoin(self.base_url, f"/api/v1/{endpoint}")
        all_data = []
        page = params.get("page", 1)

        while True:
            params["page"] = page
            res = requests.get(full_url, headers=self.headers, params=params)
            res.raise_for_status()
            payload = res.json()

            # Collect data
            data = payload.get("data", [])
            all_data.extend(data)

            # Check pagination
            pagination = payload.get("meta", {}).get("pagination", {})
            current_page = pagination.get("current_page")
            total_pages = pagination.get("total_pages")

            # Stop if we're on the last page or pagination info is missing
            if not total_pages or current_page >= total_pages:
                break

            page += 1  # move to next page

        return all_data

    def _post(self, endpoint, payload):
        full_url = urljoin(self.base_url, f"/api/v1/{endpoint}")
        res = requests.post(full_url, headers=self.headers, json=payload)
        res.raise_for_status()

        return res.json()

    def _put(self, endpoint, payload):
        """PUT request to API."""
        full_url = urljoin(self.base_url, f"/api/v1/{endpoint}")
        res = requests.put(full_url, headers=self.headers, json=payload)
        res.raise_for_status()

        return res.json()

    def search_transactions(self, query, limit=100):
        return self._get("search/transactions", query=query, limit=limit)

    def search_accounts(self, query, field, type, limit=100):
        return self._get(
            "search/accounts",
            field=field,
            type=type,
            query=query,
            limit=limit,
        )

    def transaction_exists(self, external_id):
        data = self.search_transactions(f'external_id:"{external_id}"', limit=1)
        return len(data) >= 1

    def update_external_id(self, firefly_id: str, new_external_id: str, existing: dict):
        splits = existing.get("attributes", {}).get("transactions", [])
        if not splits:
            return
        split = splits[0]
        payload = {
            "transactions": [
                {
                    "type": split.get("type"),
                    "date": split.get("date"),
                    "amount": split.get("amount"),
                    "description": split.get("description", ""),
                    "source_name": split.get("source_name", ""),
                    "destination_name": split.get("destination_name", ""),
                    "currency_code": split.get("currency_code", "EUR"),
                    "external_id": new_external_id,
                }
            ]
        }
        self._put(f"transactions/{firefly_id}", payload)

    def get_accounts(self, type):
        """Get accounts by type (asset, expense, revenue)."""
        return self._get("accounts", type=type)

    def create_transaction(self, tx: Transaction) -> bool:
        """
        Creates a transaction, automatically managing account mapping.

        Args:
            tx: Transaction object with transaction data

        Returns:
            True if the transaction was created, False if it already exists
        """
        if self.transaction_exists(tx.id):
            return False

        # Determine the account name that should be mapped and created or updated based
        # on the transaction type
        account_name = tx.destination_account

        # For refunds, use the source account field
        # For transfers
        #
        # use the source account field if it's an inbound transfer (i.e. money is
        # coming into the account)
        if tx.is_income():
            account_name = tx.source_account
        # use the destination account field if it's an outbound transfer (i.e. money
        # is leaving the account)
        elif tx.is_transfer_out():
            account_name = tx.destination_account

        self._get_or_create_account(
            tx.account_mapping,
            account_name,
            self.ASSET_ACCOUNT_TYPE_MAP[tx.type],
            tx.enable_mapping,
        )

        transaction = tx.to_firefly_payload()
        payload = {"transactions": [transaction]}
        self._post("transactions", payload)

        return True

    # ------------------------- Create or update account ------------------------- #

    def _get_or_create_account(
        self,
        account_mapping: str,
        account_name: str,
        account_type,
        enable_mapping: bool,
    ) -> tuple[str, bool]:
        """
        Gets the ID of an existing account or creates one with mapping.

        Args:
            account_mapping:
                Raw name from the bank statement
            destination_account:
                Canonical name to use
            account_type:
                Account type

        Returns:
            Tuple (account_id, created) where created indicates whether the account was
            created
        """
        # Search for the account by canonical name
        accounts = self.search_accounts(account_name, field="name", type=account_type)
        existing_account = None

        for acc in accounts:
            if acc["attributes"]["name"] == account_name:
                existing_account = acc
                break

        if existing_account:
            if enable_mapping:
                # Account exists: update mapping if necessary
                self._update_account_aliases(
                    existing_account,
                    account_type,
                    account_mapping,
                    account_name,
                )
            return existing_account["id"], False
        else:
            # Account does not exist: create it with mapping
            return (
                self._create_account_with_alias(
                    account_name,
                    account_type,
                    account_mapping,
                    enable_mapping,
                ),
                True,
            )

    def _update_account_aliases(
        self, account: dict, account_type: str, raw_name: str, account_name: str
    ):
        """
        Update existing account aliases if necessary.

        Args:
            account: Account dictionary from Firefly
            raw_name: Raw name to add to aliases
            account_name: Canonical account name
        """
        account_id = account["id"]
        attrs = account["attributes"]
        current_notes = attrs.get("notes") or ""
        current_role = attrs.get("account_role")
        current_aliases = self._extract_aliases_from_notes(current_notes)

        # If raw_name is different from the canonical name and is not already in aliases
        if raw_name != account_name and raw_name not in current_aliases:
            # Add the new alias
            current_aliases.append(raw_name)
            new_notes = self._build_notes_with_aliases(current_aliases)

            # Update your account
            payload = {
                "name": account_name,
                "type": account_type,
                "notes": new_notes,
                "account_role": current_role,
            }
            self._put(f"accounts/{account_id}", payload)

            # Update local caches
            self.alias_map[raw_name] = account_name
            self.account_aliases[account_name] = current_aliases

    def _create_account_with_alias(
        self, account_name: str, account_type: str, raw_name: str, enable_mapping: bool
    ) -> str:
        """
        Create a new account with alias mapping.

        Args:
            destination_account: Canonical name for the account
            raw_name: Raw name to map

        Returns:
            New account ID
        """
        # If raw_name is different from canonical, add to aliases
        aliases = [raw_name] if raw_name != account_name and enable_mapping else []

        payload = {
            "name": account_name,
            "type": account_type,
            "notes": self._build_notes_with_aliases(aliases) if aliases else "",
        }

        response = self._post("accounts", payload)
        account_id = response["data"]["id"]

        # Update local caches
        if aliases:
            self.alias_map[raw_name] = account_name
            self.account_aliases[account_name] = aliases

        return account_id

    # ---------------------------------------------------------------------------- #

    # -------------------------- Expense account mapping ------------------------- #

    def build_alias_mapping(self):
        """
        Builds the alias -> canonical account name map.
        Reads the notes field of each expense account, searching for JSON like this:
        {"aliases": ["Cl4ud3**2452*", "Cl4ud3**8273*"]}

        Returns:
            Dict mapping alias (lowercase) -> canonical account name
        """
        for account_type in ["asset", "expense", "revenue"]:
            self.account_aliases[account_type] = {}
            self.alias_map[account_type] = {}
            accounts = self.get_accounts(account_type)

            for acc in accounts:
                attrs = acc["attributes"]
                name = attrs["name"]
                notes = attrs.get("notes") or ""

                aliases = self._extract_aliases_from_notes(notes)

                if aliases:
                    self.account_aliases[account_type][name] = aliases
                    for alias in aliases:
                        self.alias_map[account_type][alias] = name

        return self.alias_map

    def map_account(self, type: str, raw_name: str) -> str:
        """
        Maps a raw name to the canonical account name.

        Args:
            type: Account type
            raw_name: Raw name from the statement (e.g., "Cl4ud3**2452*")

        Returns:
            Canonical name if mapping exists, otherwise None
        """
        return self.alias_map[type].get(raw_name)

    def _extract_aliases_from_notes(self, notes: str) -> List[str]:
        """
        Extracts the list of aliases from the notes field.

        Args:
            notes: String that can contain JSON with the format {"aliases": [...]}

        Returns:
            List of aliases (strings)
        """
        if not notes:
            return []

        try:
            parsed = json.loads(notes)
            return parsed.get("aliases", [])
        except json.JSONDecodeError:
            return []

    def _build_notes_with_aliases(self, aliases: List[str]) -> str:
        """
        Constructs the notes field with the alias JSON.

        Args:
            aliases: List of alias strings

        Returns:
            Formatted JSON string
        """
        return json.dumps({"aliases": aliases}, ensure_ascii=False, indent=2)

    # ---------------------------------------------------------------------------- #
