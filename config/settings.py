"""Centralized configuration management."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from src.parsers.types import StandardCardBehavior, PrepaidCardBehavior, TransactionType

import yaml

# from src.parsers.types import


@dataclass
class FireflyConfig:
    """Firefly III configuration."""

    url: str
    token: str
    timeout: int = 30
    max_retries: int = 3


@dataclass
class PathsConfig:
    """Paths configuration."""

    inputs: Path
    outputs: Path


@dataclass
class ParserConfig:
    """Parser configuration."""

    skip_already_imported: bool = True
    date_format: str = "%Y-%m-%d"


@dataclass
class CardMapping:
    """
    Card mapping configuration.

    For STANDARD cards:
        - Only card_type needed

    For PREPAID cards:
        - card_type: "PREPAID"
        - positive_is_transfer: True/False (default False)
        - transfer_specs: list of keywords (default [])
    """

    asset_account: str
    card_type: str  # "STANDARD" or "PREPAID"
    description: str = ""
    parser: str = None
    completed_states: List[str] = None
    # PREPAID only fields
    positive_is_transfer: bool = False
    transfer_specs: List[dict] = None

    def __post_init__(self):
        if self.transfer_specs is None:
            self.transfer_specs = []
        if self.completed_states is None:
            self.completed_states = []
        if self.parser is None:
            raise ValueError(
                f"Missing 'parser' field for card mapping '{self.asset_account}'. "
                f"Please set it in config.yaml (e.g. parser: nexi)"
            )

    def to_behavior(self) -> Union[StandardCardBehavior, PrepaidCardBehavior]:
        """
        Convert mapping to behavior object.

        Returns:
            StandardCardBehavior or PrepaidCardBehavior
        """
        if self.card_type.upper() == "STANDARD":
            return StandardCardBehavior(
                parser=self.parser,
                completed_states=self.completed_states,
            )
        elif self.card_type.upper() == "PREPAID":
            return PrepaidCardBehavior(
                positive_is_transfer=self.positive_is_transfer,
                transfer_specs=self.transfer_specs,
                parser=self.parser,
                completed_states=self.completed_states,
            )
        else:
            raise ValueError(
                f"Unknown card_type: {self.card_type}. Must be STANDARD or PREPAID"
            )


@dataclass
class RecurrenceTransactionConfig:
    """Recurrence transactions configuration."""

    description: str
    type: TransactionType
    source_account: str
    destination_account: str
    category: str
    amount: float
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class Config:
    """Main configuration class."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to config.yaml. If None, uses default path.
        """
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"

        self.config_path = config_path
        self._raw_config = self._load_yaml()

        # Load sections
        self.firefly = self._load_firefly()
        self.paths = self._load_paths()
        self.parser = self._load_parser()
        self.card_mappings = self._load_card_mappings()
        self.recurrences = self._load_recurrences()
        self.auto_categories = self._load_auto_categories()

        self._ensure_directories()

    def _load_yaml(self) -> Dict[str, Any]:
        """Load YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {self.config_path}\n"
                f"Please create it from config.example.yaml"
            )

        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _load_firefly(self) -> FireflyConfig:
        """Load Firefly configuration."""
        firefly = self._raw_config.get("firefly", {})
        return FireflyConfig(
            url=firefly.get("url", "http://localhost:8080"),
            token=firefly.get("token", ""),
            timeout=firefly.get("timeout", 30),
            max_retries=firefly.get("max_retries", 3),
        )

    def _load_paths(self) -> PathsConfig:
        """Load paths configuration."""
        paths = self._raw_config.get("paths", {})
        base_dir = self.config_path.parent.parent

        return PathsConfig(
            inputs=base_dir / paths.get("inputs", "data/inputs"),
            outputs=base_dir / paths.get("outputs", "data/outputs"),
        )

    def _load_parser(self) -> ParserConfig:
        """Load parser configuration."""
        parser = self._raw_config.get("parser", {})
        return ParserConfig(
            skip_already_imported=parser.get("skip_already_imported", True),
            date_format=parser.get("date_format", "%Y-%m-%d"),
        )

    def _load_card_mappings(self) -> List[CardMapping]:
        """Load card mappings."""
        mappings = self._raw_config.get("card_mappings", [])
        return [
            CardMapping(
                asset_account=m["asset_account"],
                card_type=m["card_type"],
                description=m.get("description", ""),
                parser=m["parser"],
                completed_states=m.get("completed_states", []),
                positive_is_transfer=m.get("positive_is_transfer", False),
                transfer_specs=m.get("transfer_specs", []),
            )
            for m in mappings
        ]

    def _load_recurrences(self) -> List[RecurrenceTransactionConfig]:
        """Load recurrence transactions configuration."""
        recurrences = self._raw_config.get("recurring_transactions", [])
        return [
            RecurrenceTransactionConfig(
                description=r["description"],
                type=TransactionType(r["type"]),
                source_account=r.get("source_account"),
                destination_account=r.get("destination_account"),
                category=r.get("category"),
                amount=r.get("amount"),
                tags=r.get("tags"),
            )
            for r in recurrences
        ]

    def _load_auto_categories(self) -> Dict[str, Any]:
        """Load auto categories configuration."""
        auto_categories = self._raw_config.get("auto_categories", {})
        return {
            "enabled": auto_categories.get("enabled", False),
            "rules": auto_categories.get("rules", []),
        }

    def _ensure_directories(self):
        """Create necessary directories."""
        self.paths.inputs.mkdir(parents=True, exist_ok=True)
        self.paths.outputs.mkdir(parents=True, exist_ok=True)

    def get_card_mapping(self, asset_account: str) -> Optional[CardMapping]:
        """
        Get card mapping for asset account.

        Args:
            asset_account: Asset account name

        Returns:
            CardMapping or None
        """
        for mapping in self.card_mappings:
            if mapping.asset_account.lower() == asset_account.lower():
                return mapping
        return None
