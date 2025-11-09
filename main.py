import json
import os
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

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
            f"\n[green]✓[/green] Auto-detected from config: [bold]{behavior.name}[/bold]"
        )
        console.print(f"  [dim]{behavior.description}[/dim]")

        # Show prepaid-specific info
        if isinstance(behavior, PrepaidCardBehavior):
            console.print(
                f"  [dim]Fallback: {'transfer' if behavior.positive_is_transfer else 'refund'}[/dim]"
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
            "[yellow]Hint:[/yellow] Copy config/config.example.yaml to config/config.yaml"
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
                f"[yellow]Transaction {tx_dict['id']} has no description. Skipping...[/yellow]"
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
                f"[yellow]Transaction {tx.id} already exists in Firefly. Skipping...[/yellow]"
            )


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
    console.print("  [red][P][/red]arse   - Parse bank statement")
    console.print("  [red][C][/red]reate  - Create transactions")

    action = Prompt.ask(
        "\nChoose action",
        choices=["parse", "p", "create", "c"],
        default="parse",
        show_choices=False,
        case_sensitive=False,
    )

    # Map short forms to full names
    action_map = {"p": "parse", "c": "create"}
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


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}")
        import traceback

        console.print("[dim]" + traceback.format_exc() + "[/dim]")
