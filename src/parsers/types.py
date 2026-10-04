"""Types and configurations for bank transaction parsers."""

from enum import Enum
from dataclasses import dataclass, field
from typing import List


class TransactionType(Enum):
    """Transaction types."""

    EXPENSE = "withdrawal"
    REFUND = "deposit"
    TRANSFER = "transfer"


class TransferType(Enum):
    """Transfer types."""

    IN = "in"
    OUT = "out"


class CardType(Enum):
    """Card type enumeration."""

    STANDARD = "standard"
    PREPAID = "prepaid"

    # @classmethod
    # def list_options(cls):
    #     """Returns a list of options for the menu."""
    #     return [(i, card_type) for i, card_type in enumerate(cls, 1)]


@dataclass
class StandardCardBehavior:
    """
    Standard credit card behavior.

    Characteristics:
    - All amounts are positive
    - All transactions are expenses

    Example:
        €50.00 "Amazon" → withdrawal €50
        €25.00 "Netflix" → withdrawal €25
    """

    name: str = "Standard Credit Card"
    description: str = "All amounts positive, all expenses"
    type: CardType = CardType.STANDARD
    all_positive: bool = True
    completed_states: List[str] = field(default_factory=list)
    skip_states: List[str] = field(default_factory=list)
    parser: str = None


@dataclass
class PrepaidCardBehavior:
    """
    Prepaid card behavior with keyword-based detection.

    Characteristics:

    - Mixed positive and negative amounts
    - Uses keywords to identify transfers/recharges (regardless of sign!)
    - Falls back to sign-based detection when no keywords match

    Detection Logic (Priority Order):

    1. **Keywords First**: If merchant name contains transfer keyword → transfer
       - This works for BOTH negative and positive amounts
       - Example: "-€210.00 Revolut**3060*" with keyword "revolut" → transfer

    2. **Sign-based Fallback** (only if no keyword matches):
       - Negative amount → expense (withdrawal)
       - Positive amount → depends on positive_is_transfer:
         * True: treat as transfer
         * False: treat as deposit (refund)

    Why Keywords Override Sign:
    ---------------------------

    Some cards show recharges as negative (money leaving another account).
    Keywords let you mark these as transfers regardless of the sign.

    Examples (keywords=["revolut", "recharge"], positive_is_transfer=False):

        Case 1: Keyword match overrides negative sign
        -€210.00 "Revolut**3060*" → transfer (keyword "revolut" found)

        Case 2: No keyword, negative = expense
        -€50.00 "Amazon" → withdrawal (no keyword, negative)

        Case 3: No keyword, positive = uses fallback
        +€15.00 "Amazon" → deposit (no keyword, positive_is_transfer=False)

        Case 4: Keyword match with positive
        +€100.00 "Recharge card" → transfer (keyword "Recharge" found)

    Attributes:
        name: Human-readable name
        description: Brief description
        positive_is_transfer: Fallback for positive amounts without keywords
                             True = transfer, False = refund
        transfer_specs: List of keywords to identify transfers (case-insensitive)
    """

    name: str = "Prepaid Card"
    description: str = "Negative=expenses, Positive=keyword-based detection"
    type: CardType = CardType.PREPAID
    all_positive: bool = False
    positive_is_transfer: bool = False
    transfer_specs: List[str] = field(default_factory=list)
    completed_states: List[str] = field(default_factory=list)
    skip_states: List[str] = field(default_factory=list)
    parser: str = None

    def __post_init__(self):
        """Set default values and type for transfer_specs direction."""
        for spec in self.transfer_specs:
            if "direction" not in spec:
                spec["direction"] = TransferType.IN
            elif not isinstance(spec["direction"], TransferType):
                spec["direction"] = TransferType(spec["direction"].lower())
