import json
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests


class FireflyClient:
    def __init__(self, base_url, token):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        # Alias ​​-> Canonical Account Name Mapping Cache
        self.alias_map: Dict[str, str] = {}
        # Reverse cache: account name -> alias list
        self.account_aliases: Dict[str, List[str]] = {}

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

    def search_accounts(self, query, field, type="expense", limit=100):
        return self._get(
            "search/accounts",
            field=field,
            type=type,
            query=query,
            limit=limit,
        )

    def transaction_exists(self, external_id):
        data = self.search_transactions(f'external_id:"{external_id}"', limit=1)
        return len(data) == 1

    def get_accounts(self, type="expense"):
        return self._get("accounts", type=type)

    def create_transaction(self, tx):
        """
        Creates a transaction, automatically managing account mapping.

        Args:
            tx: Transaction object with transaction data

        Returns:
            Response from Firefly API
        """
        # Get or create an auto-mapping account
        destination_id, created = self.get_or_create_account(
            tx.raw_destination_account,
            tx.destination_account,
        )

        transaction = tx.to_firefly_payload()
        # transaction.pop("destination_name")  # Use ID, safer
        transaction["destination_id"] = destination_id

        payload = {"transactions": [transaction]}
        return self._post("transactions", payload)

    # ------------------------- Create or update account ------------------------- #

    def get_or_create_account(
        self, raw_name: str, destination_account: Optional[str] = None
    ) -> tuple[str, bool]:
        """
        Gets the ID of an existing account or creates one with mapping.

        Args:
            raw_name:
                Raw name from the bank statement
            destination_account:
                Canonical name to use (optional, otherwise use raw_name)

        Returns:
            Tuple (account_id, created) where created indicates whether the account was
            created
        """
        # Determine the canonical name
        if not destination_account:
            destination_account = self.map_destination(raw_name)

        # Search for the account by canonical name
        accounts = self.search_accounts(destination_account, field="name")
        existing_account = None

        for acc in accounts:
            if acc["attributes"]["name"] == destination_account:
                existing_account = acc
                break

        if existing_account:
            # Account exists: update mapping if necessary
            self._update_account_aliases(
                existing_account, raw_name, destination_account
            )
            return existing_account["id"], False
        else:
            # Account does not exist: create it with mapping
            return self._create_account_with_alias(destination_account, raw_name), True

    def _update_account_aliases(
        self, account: dict, raw_name: str, destination_account: str
    ):
        """
        Update existing account aliases if necessary.

        Args:
            account: Account dictionary from Firefly
            raw_name: Raw name to add to aliases
            destination_account: Canonical account name
        """
        account_id = account["id"]
        attrs = account["attributes"]
        current_notes = attrs.get("notes") or ""
        current_aliases = self._extract_aliases_from_notes(current_notes)

        # If raw_name is different from the canonical name and is not already in aliases
        if raw_name != destination_account and raw_name not in current_aliases:
            # Add the new alias
            current_aliases.append(raw_name)
            new_notes = self._build_notes_with_aliases(current_aliases)

            # Update your account
            payload = {
                "name": destination_account,
                "type": "expense",
                "notes": new_notes,
            }
            self._put(f"accounts/{account_id}", payload)

            # Update local caches
            self.alias_map[raw_name] = destination_account
            self.account_aliases[destination_account] = current_aliases

    def _create_account_with_alias(
        self, destination_account: str, raw_name: str
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
        aliases = [raw_name] if raw_name != destination_account else []

        payload = {
            "name": destination_account,
            "type": "expense",
            "notes": self._build_notes_with_aliases(aliases) if aliases else "",
        }

        response = self._post("accounts", payload)
        account_id = response["data"]["id"]

        # Update local caches
        if aliases:
            self.alias_map[raw_name] = destination_account
            self.account_aliases[destination_account] = aliases

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
        accounts = self.get_accounts()
        self.alias_map = {}
        self.account_aliases = {}

        for acc in accounts:
            attrs = acc["attributes"]
            name = attrs["name"]
            notes = attrs.get("notes") or ""

            # Extract aliases from JSON in Notes
            aliases = self._extract_aliases_from_notes(notes)

            # Populate both maps
            if aliases:
                self.account_aliases[name] = aliases
                for alias in aliases:
                    self.alias_map[alias] = name

        return self.alias_map

    def map_destination(self, raw_name: str) -> str:
        """
        Maps a raw name to the canonical account name.

        Args:
            raw_name: Raw name from the statement (e.g., "Cl4ud3**2452*")

        Returns:
            Canonical name if mapping exists, otherwise raw_name
        """
        return self.alias_map.get(raw_name, raw_name)

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
