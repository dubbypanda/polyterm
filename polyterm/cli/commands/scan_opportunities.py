"""Agent-native market opportunity scan command."""

import click
from rich.console import Console
from rich.table import Table

from ...agent.contracts import envelope
from ...core.scanner import MarketOpportunityScanner
from ...utils.json_output import print_json


@click.command("scan-opportunities")
@click.option("--query", "-q", default="", help="Market search query; empty scans the active market feed.")
@click.option("--limit", default=20, help="Maximum opportunities to return.")
@click.option("--min-volume", type=float, default=1000, help="Minimum 24h volume signal threshold.")
@click.option("--min-liquidity", type=float, default=0, help="Minimum liquidity signal threshold.")
@click.option("--max-archive-age-hours", type=int, default=24, help="Freshness threshold for local archive evidence.")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table")
def scan_opportunities(query, limit, min_volume, min_liquidity, max_archive_age_hours, output_format):
    """Scan active markets for research-worthy opportunities."""
    scanner = MarketOpportunityScanner()
    result = scanner.scan(
        query=query,
        limit=limit,
        min_volume=min_volume,
        min_liquidity=min_liquidity,
        max_archive_age_hours=max_archive_age_hours,
    )

    if output_format == "json":
        print_json(envelope(result, meta={"tool": "scan.opportunities"}))
        return

    console = Console()
    table = Table(title="Market Opportunities")
    table.add_column("Score", justify="right")
    table.add_column("Market")
    table.add_column("Price", justify="right")
    table.add_column("24h", justify="right")
    table.add_column("Volume", justify="right")
    table.add_column("Signals")

    for item in result["opportunities"]:
        table.add_row(
            f"{item['score']:.1f}",
            item["title"][:56],
            f"{item['probability']:.0%}",
            f"{item['change_24h']:+.1f}%",
            f"${item['volume_24h']:,.0f}",
            ", ".join(item["signals"][:4]),
        )

    if result["opportunities"]:
        console.print(table)
    else:
        console.print("[yellow]No ranked opportunities found.[/yellow]")
    console.print(f"[dim]Quality flags: {', '.join(result['quality_flags'])}[/dim]")
