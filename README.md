# Firefly-Assistant

Automated parser for bank statement Excel files with transaction classification and
Firefly III integration.

## ✨ Features

- 📊 **Parse Excel statements** - Automated import from bank Excel files
- 🏦 **Multi-card support** - Standard credit cards and prepaid cards
- 🔄 **Smart transfer detection** - Keyword-based classification with direction (in/out)
- 🏷️ **Auto-categorization** - Automatic category assignment based on merchant names
- 🔁 **Recurring transactions** - Quick entry for monthly bills and subscriptions
- 🗂️ **Alias management** - Automatic mapping of raw merchant names to clean names
- 💾 **JSON export** - Review transactions before importing to Firefly
- 🎨 **Beautiful CLI** - Rich terminal UI with colors and tables

## 🚀 Quick Start

### 1. Installation

```bash
# Clone repository
git clone <your-repo>
cd firefly-parser

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Copy example config
cp config/config.example.yaml config/config.yaml

# Edit with your settings
nano config/config.yaml
```

**Minimum required configuration:**
```yaml
firefly:
  url: "http://your-firefly-url:8080"
  token: "your_firefly_personal_access_token"
```

### 3. Usage

```bash
python main.py
```

```
Actions:
  [P]arse   - Parse bank statement
  [C]reate  - Create transactions from recurrences
  [M]anage  - Manage mappings

Choose action (parse): p
```

## 📖 Configuration Guide

### Firefly III Connection

```yaml
firefly:
  url: http://localhost:8080
  token: CHANGE_ME_your_personal_access_token_here
  timeout: 30          # API timeout in seconds
  max_retries: 3       # Number of retry attempts
```

**Getting your token:**
1. Go to Firefly III → Options → Profile
2. Create a new Personal Access Token
3. Copy and paste into config

### Directory Structure

```yaml
paths:
  inputs: data/inputs    # Place Excel files here
  outputs: data/outputs  # Parsed JSON files
```

### Parser Settings

```yaml
parser:
  skip_already_imported: true  # Skip transactions with existing external_id
```

## 🏦 Card Mappings

Associate your bank accounts with card types for automatic transaction classification.

### Standard Credit Card

All amounts are positive, all transactions are expenses.

```yaml
card_mappings:
  - asset_account: "My Credit Card"
    card_type: "STANDARD"
```

### Prepaid Card

Mixed signs with intelligent classification:
- **Negative amounts** = Expenses (withdrawals)
- **Positive amounts** = Classified using keywords

```yaml
card_mappings:
  - asset_account: "My Prepaid Card"
    card_type: "PREPAID"
    positive_is_transfer: false  # Fallback: refund if no keyword matches
    transfer_specs:
      # Money coming INTO the card (default direction: in)
      - keyword: "recharge"
      - keyword: "top up"
      - keyword: "bank transfer"

      # Money going OUT of the card (specify direction: out)
      - keyword: "transfer to revolut"
        direction: out
      - keyword: "payment to paypal"
        direction: out
```

### Transfer Direction Explained

| Direction | Money Flow | Account Swap | Example |
|-----------|------------|--------------|---------|
| `in` | Money INTO card | Yes (Bank → Card) | Bank recharge |
| `out` | Money OUT of card | No (Card → External) | Transfer to Revolut |

**Example scenarios:**

```yaml
# Scenario 1: Recharge from bank account
# Excel: -€200.00 "RECHARGE FROM MY BANK"
# Result: transfer_in (Bank → Prepaid Card)
- keyword: "recharge from"
  # direction: in is default

# Scenario 2: Transfer to external service
# Excel: -€50.00 "TRANSFER TO REVOLUT"
# Result: transfer_out (Prepaid Card → Revolut)
- keyword: "transfer to revolut"
  direction: out
```

## 🔁 Recurring Transactions

Define recurring transactions for quick manual entry (salary, rent, subscriptions).

```yaml
recurring_transactions:
  # Complete configuration
  - description: "Monthly Salary"
    source_account: "Employer Inc"
    destination_account: "My Bank Account"
    category: "Salary"
    amount: 2500.00
    date: "01/12/2024"
    tags: ["monthly", "income"]

  # Partial configuration - will prompt for missing fields
  - description: "Netflix Subscription"
    destination_account: "Netflix"
    category: "Entertainment"
    # Missing: source_account, amount, date
    # These will be asked interactively
```

**Usage:**
```bash
python main.py
# Choose: [C]reate

# For partial configs, you'll be prompted:
Source account: My Bank Account
Amount (€): 15.99
Transaction date (2024-11-10): ↵
```

## 🏷️ Auto-Categorization

Automatically assign categories based on merchant keywords.

```yaml
auto_categories:
  enabled: true
  rules:
    - category: "Groceries"
      keywords:
        - "esselunga"
        - "coop"
        - "carrefour"
        - "lidl"

    - category: "Transport"
      keywords:
        - "atm"
        - "trenitalia"
        - "uber"
        - "bolt"

    - category: "Entertainment"
      keywords:
        - "netflix"
        - "spotify"
        - "cinema"
```

**How it works:**
1. Transaction is parsed: `"ESSELUNGA MILANO"`
2. Matched against keywords (case-insensitive)
3. Category automatically assigned: `"Groceries"`
4. First match wins (order matters!)

**Matching logic:**
- Searches in both raw name (`"ESSELUNGA*123"`) and mapped name (`"Esselunga"`)
- Case-insensitive: `"NETFLIX"` matches `"netflix"`
- Partial match: `"esselunga"` matches `"ESSELUNGA MILANO"`

## 🗂️ Alias Management

The parser automatically manages merchant name aliases in Firefly III.

### How It Works

1. **First transaction** with `"AMAZON.IT*2X3Y4Z"`
   - Creates expense account: `"Amazon"`
   - Stores alias in notes: `{"aliases": ["AMAZON.IT*2X3Y4Z"]}`

2. **Second transaction** with `"AMAZON ITALIA"`
   - Finds existing account: `"Amazon"`
   - Adds new alias: `{"aliases": ["AMAZON.IT*2X3Y4Z", "AMAZON ITALIA"]}`

3. **Third transaction** with `"AMAZON.IT*2X3Y4Z"`
   - Alias already exists → Uses `"Amazon"` account

### Account Types

The parser creates different Firefly account types based on transaction:

| Transaction Type | Account Type | Example |
|-----------------|--------------|---------|
| Withdrawal | **Expense** | Amazon, Netflix |
| Deposit (refund) | **Revenue** | Amazon (refund) |
| Transfer IN | **Asset** | Bank Account |
| Transfer OUT | **Asset** | Revolut, PayPal |

## 📊 Transaction Flow

### Parsing Flow

```
1. Load Excel file
   ↓
2. For each row:
   - Extract amount, date, merchant
   - Classify transaction type (withdrawal/deposit/transfer)
   - Map merchant name (using aliases)
   - Auto-categorize (using keywords)
   ↓
3. Export to JSON
   ↓
4. Review in JSON file
   ↓
5. Import to Firefly (manual or future auto-import)
```

### Transaction Classification

**Standard Card:**
```
€50.00 "Amazon" → withdrawal
€25.00 "Netflix" → withdrawal
```

**Prepaid Card:**
```
-€50.00 "Amazon" → withdrawal
+€15.00 "Amazon" → deposit (refund, no keyword)
+€100.00 "RECHARGE POSTEPAY" → transfer_in (keyword: "recharge")
-€200.00 "TRANSFER TO REVOLUT" → transfer_out (keyword: "transfer to revolut", direction: out)
```

## 📁 Project Structure

```
firefly-parser/
├── config/
│   ├── config.yaml           # Your configuration
│   ├── config.example.yaml   # Template
│   └── settings.py           # Config loader
│
├── src/
│   ├── firefly/
│   │   ├── client.py         # Firefly API client
│   │   └── models.py         # Transaction model
│   │
│   ├── parsers/
│   │   ├── base.py           # Base parser
│   │   ├── nexi.py           # Nexi bank parser
│   │   └── types.py          # Card types and enums
│   │
│   └── utils/
│       └── ...
│
├── data/
│   ├── inputs/               # Place Excel files here
│   ├── outputs/              # Generated JSON files
│   └── backups/              # Automatic backups
│
├── scripts/
│   └── create_recurrence.py  # Recurrence transaction handler
│
├── main.py                   # Main entry point
└── README.md
```

## 🔧 Adding New Banks

To add support for a new bank:

1. Create parser in `src/parsers/yourbank.py`:

```python
from .base import BaseParser

class YourBankParser(BaseParser):
    def parse(self, file_path):
        # Your parsing logic
        # Read Excel/CSV
        # Create Transaction objects
        # Return list of transactions
        pass
```

2. Import in `src/parsers/__init__.py`
3. Use in main.py

## 🐛 Troubleshooting

### "Config file not found"
```bash
cp config/config.example.yaml config/config.yaml
# Then edit config.yaml
```

### "Firefly token not configured"
Edit `config/config.yaml` and set your Firefly III personal access token.

### Transactions not categorized
- Check `auto_categories.enabled: true`
- Verify keywords match merchant names (case-insensitive)
- Keywords search in both raw and mapped names

### Transfer direction wrong
- Review `transfer_specs` configuration
- `direction: in` = Money INTO card (swap accounts)
- `direction: out` = Money OUT of card (no swap)
- Default is `in` if not specified

## 📝 Example Workflow

### 1. First Time Setup

```bash
# 1. Configure
cp config/config.example.yaml config/config.yaml
nano config/config.yaml  # Add your Firefly token

# 2. Add your cards
card_mappings:
  - asset_account: "My Prepaid"
    card_type: "PREPAID"
    transfer_specs:
      - keyword: "ricarica"
```

### 2. Parse Bank Statement

```bash
# 1. Place Excel file in data/inputs/
cp ~/Downloads/movimenti_novembre.xlsx data/inputs/

# 2. Run parser
python main.py
> p  # Choose parse

# 3. Select file and card
> 1  # movimenti_novembre.xlsx
> 2  # My Prepaid

# 4. Review output
✓ Parsed 47 transactions
✓ Auto-categorized 42 transactions
✓ Exported to data/outputs/movimenti_novembre.json
```

### 3. Review JSON

```bash
cat data/outputs/movimenti_novembre.json
```

```json
[
  {
    "date": "2024-11-10",
    "type": "withdrawal",
    "source_account": "My Prepaid",
    "destination_account": "Amazon",
    "amount": 50.00,
    "category": "Shopping"
  },
  {
    "date": "2024-11-11",
    "type": "transfer_in",
    "source_account": "My Bank",
    "destination_account": "My Prepaid",
    "amount": 200.00
  }
]
```

### 4. Import to Firefly

*Future feature - currently manual import via Firefly UI*

## 🎯 Best Practices

1. **Review JSON before importing** - Check categories and mappings
2. **Add common merchants to config** - Save time with pre-defined aliases
3. **Use descriptive keywords** - Be specific to avoid false matches
4. **Order matters in rules** - Most specific rules first
5. **Backup regularly** - Keep copies of your config and data

## 🤝 Contributing

Contributions welcome! Please:
1. Follow existing code style
2. Add tests for new features
3. Update documentation

## 📄 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- [Firefly III](https://www.firefly-iii.org/) - Personal finance manager
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
- [PyYAML](https://pyyaml.org/) - YAML parsing

---

**Need help?** Open an issue or check existing documentation.
