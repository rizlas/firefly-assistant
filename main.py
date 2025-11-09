import json
import os
from datetime import datetime
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, FloatPrompt, Prompt
from rich.table import Table

from config.settings import Config
from src.firefly.client import FireflyClient
from src.firefly.models import Transaction
from src.parsers.nexi import NexiParser
from src.parsers.types import PrepaidCardBehavior, StandardCardBehavior

console = Console()


def choose_file(extension: str, prompt: str, path: Path) -> Path:
    """
    List files in directory with given extension.
    Ask user to pick one or enter a custom path.

    Args:
        extension: File extension to filter (e.g., ".xlsx")
        prompt: Prompt message for user
        path: Directory path to search in

    Returns:
        Path to selected file
    """
    files = [f for f in os.listdir(path) if f.lower().endswith(extension)]

    if files:
        console.print(f"\n[cyan]Available {extension.upper()} files:[/cyan]")
        for i, f in enumerate(files, start=1):
            console.print(f"  {i}. {f}")

        choice = Prompt.ask(
            prompt,
            choices=[str(i) for i in range(1, len(files) + 1)] + ["custom"],
            default="1",
        )

        if choice == "custom":
            custom_path = Prompt.ask("Enter full path")
            return Path(custom_path)

        return path / files[int(choice) - 1]
    else:
        console.print(f"[yellow]No {extension.upper()} files found in {path}[/yellow]")
        custom_path = Prompt.ask("Enter full path")
        return Path(custom_path)


def choose_account(accounts: list) -> str:
    """
    Display available accounts and let user choose one.

    Args:
        accounts: List of account dictionaries from Firefly API

    Returns:
        Name of selected account
    """
    console.print("\n[cyan]Available accounts:[/cyan]")
    for i, asset in enumerate(accounts, start=1):
        console.print(f"  {i}. {asset['attributes']['name']}")

    while True:
        choice = Prompt.ask(
            "Choose an asset",
            choices=[str(i) for i in range(1, len(accounts) + 1)],
            default="1",
        )

        idx = int(choice) - 1
        return accounts[idx]["attributes"]["name"]


def choose_card(asset_account: str, config: Config):
    """Get card type based on auto-detection or manual selection.

    Args:
        asset_account: Asset account name for auto-detection in card mappings

    Returns:
        StandardCardBehavior or PrepaidCardBehavior
    """

    # Try auto-detection from config
    card_mapping = config.get_card_mapping(asset_account)
    if card_mapping:
        behavior = card_mapping.to_behavior()

        console.print(
            "\n[green]✓[/green] Auto-detected from config: "
            f"[bold]{behavior.name}[/bold]"
        )
        console.print(f"  [dim]{behavior.description}[/dim]")

        # Show prepaid-specific info
        if isinstance(behavior, PrepaidCardBehavior):
            console.print(
                f"  [dim]Fallback: "
                f"{'transfer' if behavior.positive_is_transfer else 'refund'}[/dim]"
            )
            if behavior.transfer_specs:
                keywords_preview = ", ".join(
                    [spec["keyword"] for spec in behavior.transfer_specs[:3]]
                )
                if len(behavior.transfer_specs) > 3:
                    keywords_preview += "..."
                console.print(f"  [dim]Keywords: {keywords_preview}[/dim]")

        if Confirm.ask("Use this configuration?", default=True):
            return behavior

    # Manual selection
    console.print("\n[cyan]Select card type:[/cyan]")
    console.print("  1. [bold]Standard Credit Card[/bold]")
    console.print("     [dim]All amounts positive, all expenses[/dim]")
    console.print("  2. [bold]Prepaid Card[/bold]")
    console.print("     [dim]Negative=expenses, Positive=keyword-based[/dim]")

    choice = Prompt.ask("Card type", choices=["1", "2"], default="1")

    if choice == "1":
        return StandardCardBehavior()
    else:
        return PrepaidCardBehavior()


def load_config() -> Config | None:
    """Load and validate configuration.

    Returns:
        Config object if successful, None otherwise.
    """
    try:
        config = Config()
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print(
            "[yellow]Hint:[/yellow] Copy config/config.example.yaml "
            "to config/config.yaml"
        )
        return None

    # Verify Firefly token
    if not config.firefly.token:
        console.print("[red]⚠ Firefly token not configured![/red]")
        console.print(
            "Please edit [cyan]config/config.yaml[/cyan] and set your Firefly III token"
        )
        return None

    console.print(f"[dim]Firefly URL: {config.firefly.url}[/dim]\n")
    return config


def init_firefly_client(config: Config) -> FireflyClient | None:
    """Initialize Firefly III client.

    Args:
        config: Configuration object.

    Returns:
        FireflyClient if successful, None otherwise.
    """
    with console.status("[bold green]Connecting to Firefly III..."):
        try:
            return FireflyClient(
                base_url=config.firefly.url, token=config.firefly.token
            )
        except Exception as e:
            console.print(f"[red]Error connecting to Firefly:[/red] {e}")
            return None


def parse_transactions(config: Config, firefly: FireflyClient) -> None:
    """Parse bank statement and export to JSON.

    Args:
        config: Configuration object.
        firefly: Firefly III client.
    """
    # Select file
    console.print()
    file_path = choose_file(".xlsx", "Select file", config.paths.inputs)

    if not file_path.exists():
        console.print(f"[red]File not found:[/red] {file_path}")
        return

    # Get accounts from Firefly
    with console.status("[bold green]Fetching accounts..."):
        accounts = firefly.get_accounts("asset")

    # Select asset account
    asset_account = choose_account(accounts)

    # Select card type (with auto-detect)
    card = choose_card(asset_account, config)

    console.print(
        f"\n[green]✓[/green] Using: [bold]{card.name} ({card.type.value})[/bold]"
    )
    console.print(f"  [dim]{card.description}[/dim]")

    # Parse transactions
    with console.status(f"[bold green]Parsing {file_path.name}..."):
        parser = NexiParser(
            asset_account=asset_account, firefly_client=firefly, card_behavior=card
        )

        txs = parser.parse(
            file_path, skip_already_imported=config.parser.skip_already_imported
        )

    if not txs:
        console.print("[yellow]No transactions to process[/yellow]")
        return

    # Export to JSON
    out_filename = file_path.stem + ".json"
    out_path = config.paths.outputs / out_filename

    with console.status(f"[bold green]Exporting to {out_filename}..."):
        parser.export_to_json(txs, out_path)

    console.print(f"\n[green]✓[/green] Parsed [bold]{len(txs)}[/bold] transactions")
    console.print(f"[green]✓[/green] Exported to [cyan]{out_path}[/cyan]")


def create_transactions(config: Config, firefly: FireflyClient) -> None:
    """Create transactions in Firefly III from JSON file.

    Args:
        config: Configuration object.
        firefly: Firefly III client.
    """
    output_path = choose_file(".json", "Select JSON file", config.paths.outputs)

    if not os.path.exists(output_path):
        console.print(f"[red]File {output_path} not found.[/red]")
        return

    with open(output_path, "r", encoding="utf-8") as f:
        transactions = json.load(f)

    # Process each transaction
    for tx_dict in transactions:
        if not tx_dict["description"]:
            console.print(
                f"[yellow]Transaction {tx_dict['id']} has no description. "
                "Skipping...[/yellow]"
            )
            continue

        tx = Transaction.from_dict(tx_dict)

        if not tx.category_name:
            console.print(f"[yellow]Transaction {tx.id} has no category.[/yellow]")

        res = firefly.create_transaction(tx)

        if res:
            console.print(f"[green]✓[/green] Transaction {tx.id} created.")
        else:
            console.print(
                f"[yellow]Transaction {tx.id} already exists in Firefly. "
                "Skipping...[/yellow]"
            )


def complete_recurring_transaction(rec_tx):
    def ask_required(prompt_text):
        while True:
            value = Prompt.ask(prompt_text)
            if value.strip() == "":
                console.print(f"[red]{prompt_text} is required[/red]")
                continue
            return value

    # Date
    default_date = datetime.now().strftime("%d/%m/%Y")
    while True:
        rec_tx.date = Prompt.ask("Transaction date", default=default_date)
        try:
            datetime.strptime(rec_tx.date, "%d/%m/%Y")
            break
        except ValueError:
            console.print("[red]Invalid date format. Please use dd/mm/yyyy.[/red]")

    # Source account
    if rec_tx.source_account:
        console.print(f"Source account: [green]{rec_tx.source_account}[/green]")
    else:
        rec_tx.source_account = ask_required("Source account")

        # Destination account
    if rec_tx.destination_account:
        console.print(
            "Destination account: " f"[green]{rec_tx.destination_account}[/green]"
        )
    else:
        rec_tx.destination_account = ask_required("Destination account")

    # Amount (required, cannot be empty)
    if rec_tx.amount:
        console.print(f"Amount: [green]€{rec_tx.amount:.2f}[/green]")
    else:
        while True:
            try:
                amount = FloatPrompt.ask("Amount (€)", default=None)
                if amount is None or amount <= 0:
                    console.print("[red]Amount is required and must be > 0[/red]")
                    continue
                rec_tx.amount = amount
                break
            except Exception:
                console.print("[red]Invalid amount[/red]")

    # Category (optional)
    if rec_tx.category:
        console.print(f"Category: [green]{rec_tx.category}[/green]")
    else:
        rec_tx.category = Prompt.ask("Category (optional)", default="")

    # Tags (optional)
    if rec_tx.tags:
        console.print(f"Tags: [green]{', '.join(rec_tx.tags)}[/green]")
    else:
        tags_input = Prompt.ask("Tags (comma-separated, optional)", default="")
        rec_tx.tags = [tag.strip() for tag in tags_input.split(",")]


def _display_summary(transactions: list):
    """
    Display beautiful summary table of transactions to be created.

    Args:
        transactions: List of Transaction objects
    """
    console.print("\n")

    table = Table(
        title="[bold cyan]Transaction Summary[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )

    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")
    table.add_column("From", style="yellow")
    table.add_column("To", style="green")
    table.add_column("Type", style="blue")
    table.add_column("Amount", justify="right", style="bold green")
    table.add_column("Category", style="blue")
    table.add_column("Tags", style="blue")

    total = 0
    for tx in transactions:
        table.add_row(
            tx.date,
            tx.description,
            tx.source_account,
            tx.destination_account,
            tx.type.value,
            f"€{tx.amount:,.2f}",
            tx.category,
            ", ".join(tx.tags),
        )
        total += tx.amount

    table.add_section()
    table.add_row("", "", "", "[bold]Total[/bold]", f"[bold]€{total:,.2f}[/bold]", "")

    console.print(table)


def create_recurrence_transactions(config: Config, firefly: FireflyClient) -> None:
    """
    Create transactions from recurrence configurations.

    For each recurrence, prompts user for missing fields and creates transaction.

    Args:
        config: Configuration with recurrences list
        firefly: Firefly API client
    """

    if not config.recurrences:
        console.print(
            "[yellow]No recurrence configurations found in config.yaml[/yellow]"
        )
        return

    console.print(
        Panel.fit(
            f"[bold cyan]Found {len(config.recurrences)} recurrence(s)[/bold cyan]",
            border_style="cyan",
        )
    )

    recurring_transactions = []

    # Display menu
    console.print("\n[cyan]Available recurrences:[/cyan]")
    for i, rec_tx in enumerate(config.recurrences, start=1):
        console.print(f"  {i}. {rec_tx.description}")
    console.print(f"  {len(config.recurrences)+1}. All")

    # Prompt user
    while True:
        selected = Prompt.ask(
            "Select recurrence(s) to create (comma-separated numbers)", default="1"
        )

        try:
            # Parse comma-separated numbers
            selected_indices = [int(s.strip()) for s in selected.split(",")]

            # Validate numbers
            all_index = len(config.recurrences) + 1
            if any(idx < 1 or idx > all_index for idx in selected_indices):
                raise ValueError

            break
        except ValueError:
            console.print(
                "[red]Invalid selection. Enter numbers from the list, "
                "separated by commas.[/red]"
            )

    # Determine which transactions to process
    if all_index in selected_indices:  # "All" is the last option
        to_process = config.recurrences
    else:
        # Adjust to 0-based indices
        to_process = [config.recurrences[idx - 1] for idx in selected_indices]

    console.print(
        f"\n[green]✓[/green] Selected {len(to_process)} recurrence(s) to create."
    )

    # Complete selected transactions
    for rec_tx in to_process:
        complete_recurring_transaction(rec_tx)
        recurring_transactions.append(rec_tx)
        console.print("--" * 20)

    if recurring_transactions:
        _display_summary(recurring_transactions)

        # Confirm creation
        if Confirm.ask(
            "\n[bold]Create these transactions in Firefly?[/bold]", default=False
        ):
            for rec_tx in recurring_transactions:
                tx = Transaction(
                    date=rec_tx.date,
                    description=rec_tx.description,
                    source_account=rec_tx.source_account,
                    dest_account=rec_tx.destination_account,
                    account_mapping="",
                    total=rec_tx.amount,
                    enable_mapping=False,
                    type=rec_tx.type,
                    category=rec_tx.category,
                    tags=rec_tx.tags,
                )

            if not tx.category_name:
                console.print(f"[yellow]Transaction {tx.id} has no category.[/yellow]")

            res = firefly.create_transaction(tx)

            if res:
                console.print(
                    "[green]✓[/green] Recurrence transaction "
                    f"{tx.description} created."
                )
            else:
                console.print(
                    f"[red]Failed to create transaction {tx.description}[/red]"
                )
        else:
            console.print("[yellow]Cancelled[/yellow]")


def main():
    """Main application entry point."""
    console.print(
        Panel.fit(
            "[bold cyan]Firefly III Bank Transaction Parser[/bold cyan]",
            border_style="cyan",
        )
    )

    # Load configuration
    config = load_config()
    if not config:
        return

    # Main menu
    console.print("\n[cyan]Actions:[/cyan]\n")
    console.print("  [red][P][/red]arse         - Parse bank statement")
    console.print("  [red][C][/red]reate        - Create transactions")
    console.print("  [red][R][/red]ecurrence    - Create recurrences transaction")

    action = Prompt.ask(
        "\nChoose action",
        choices=["parse", "p", "create", "c", "recurrence", "r"],
        default="parse",
        show_choices=False,
        case_sensitive=False,
    )

    # Map short forms to full names
    action_map = {"p": "parse", "c": "create", "r": "recurrence"}
    action = action_map.get(action, action)

    # Initialize Firefly client
    firefly = init_firefly_client(config)
    if not firefly:
        return

    console.print(f"\n[green]✓[/green] Selected: [bold]{action}[/bold]")

    # Route to appropriate action
    if action == "parse":
        parse_transactions(config, firefly)
    elif action == "create":
        create_transactions(config, firefly)
    elif action == "recurrence":
        create_recurrence_transactions(config, firefly)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}")
        import traceback

        console.print("[dim]" + traceback.format_exc() + "[/dim]")
