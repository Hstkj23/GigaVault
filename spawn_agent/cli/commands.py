"""
Command-line interface for SpawnAgent.

Provides commands for wallet monitoring, fund flow tracing,
and agent management from the terminal.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

import click

from spawn_agent import __version__


@click.group()
@click.version_option(version=__version__, prog_name="spawn-agent")
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    default=None,
    help="Path to configuration file.",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output.")
@click.pass_context
def cli(ctx: click.Context, config: Optional[str], verbose: bool) -> None:
    """SpawnAgent — Real-time on-chain intelligence platform."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["verbose"] = verbose


@cli.command()
@click.argument("address")
@click.option("--label", "-l", default=None, help="Label for this address.")
@click.option(
    "--alert",
    "-a",
    multiple=True,
    type=click.Choice(["telegram", "discord", "webhook"]),
    help="Alert channels to enable.",
)
@click.option(
    "--threshold",
    "-t",
    default=10.0,
    help="Large transfer threshold in ETH.",
)
@click.pass_context
def watch(
    ctx: click.Context,
    address: str,
    label: Optional[str],
    alert: tuple,
    threshold: float,
) -> None:
    """Monitor a wallet or contract address for on-chain activity."""
    from spawn_agent import SpawnAgent

    config_path = ctx.obj.get("config")

    if config_path:
        agent = SpawnAgent.from_config(config_path)
    else:
        rpc_url = _get_rpc_url()
        agent = SpawnAgent.create(rpc_url=rpc_url)

    agent.watch(
        address,
        label=label,
        options={"large_transfer_threshold": str(threshold)},
    )

    click.echo(f"Monitoring {label or address}...")
    click.echo(f"Alert channels: {', '.join(alert) if alert else 'stdout'}")

    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        click.echo("\nStopping...")


@cli.command()
@click.argument("address")
@click.option("--depth", "-d", default=3, help="Maximum trace depth (hops).")
@click.option(
    "--direction",
    type=click.Choice(["forward", "backward"]),
    default="forward",
    help="Trace direction.",
)
@click.option(
    "--min-value",
    default=0.0,
    help="Minimum value in ETH to include.",
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "tree", "csv"]),
    default="tree",
    help="Output format.",
)
@click.pass_context
def trace(
    ctx: click.Context,
    address: str,
    depth: int,
    direction: str,
    min_value: float,
    output: str,
) -> None:
    """Trace fund flows from an address."""
    import json as json_lib

    from spawn_agent.analysis.graph import WalletGraph
    from spawn_agent.providers.rpc import RPCProvider

    click.echo(f"Tracing {direction} from {address} (depth={depth})...")

    async def run_trace():
        rpc_url = _get_rpc_url(ctx.obj.get("config"))
        provider = RPCProvider(url=rpc_url)
        await provider.connect()

        graph = WalletGraph()

        # Fetch transactions and build graph
        current_block = await provider.get_block_number()
        lookback = 1000  # blocks
        start_block = max(0, current_block - lookback)

        txs = await provider.get_transactions(
            address=address,
            from_block=start_block,
            to_block=current_block,
        )

        for tx in txs:
            graph.add_transaction(tx)

        # Perform trace
        if direction == "forward":
            result = graph.trace_forward(
                address, max_depth=depth, min_value_wei=int(min_value * 1e18)
            )
        else:
            result = graph.trace_backward(
                address, max_depth=depth, min_value_wei=int(min_value * 1e18)
            )

        await provider.close()
        return result

    result = asyncio.run(run_trace())

    if output == "json":
        import json as json_mod

        click.echo(json_mod.dumps(result, indent=2))
    elif output == "csv":
        _print_csv(result)
    else:
        _print_tree(result)


@cli.command()
@click.option("--file", "-f", type=click.Path(exists=True), help="File with addresses.")
@click.option("--port", "-p", default=8420, help="Dashboard port.")
@click.pass_context
def serve(ctx: click.Context, file: Optional[str], port: int) -> None:
    """Start the monitoring dashboard server."""
    click.echo(f"Starting SpawnAgent dashboard on port {port}...")
    click.echo("Dashboard: http://localhost:{port}")

    # TODO: Implement web dashboard
    click.echo("Web dashboard is under development. Use 'watch' for CLI monitoring.")


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show the status of the running agent."""
    click.echo(f"SpawnAgent v{__version__}")
    click.echo("Status: No running agent found")
    click.echo("Use 'spawn-agent watch <address>' to start monitoring")


def _get_rpc_url(config_path: Optional[str] = None) -> str:
    """Resolve the RPC URL from config or environment."""
    import os

    url = os.environ.get("SPAWN_AGENT_RPC_URL", os.environ.get("ETH_RPC_URL"))

    if not url:
        click.echo(
            "Error: No RPC URL configured. Set SPAWN_AGENT_RPC_URL "
            "environment variable or use --config.",
            err=True,
        )
        sys.exit(1)

    return url


def _print_tree(node: dict, prefix: str = "", is_last: bool = True) -> None:
    """Print a trace result as an ASCII tree."""
    connector = "└── " if is_last else "├── "
    addr = node.get("address", "?")[:42]
    label = node.get("label", "")
    value = node.get("total_value_wei", 0)
    value_eth = value / 1e18 if value else 0

    if label and label != addr[:10]:
        display = f"{addr} ({label})"
    else:
        display = addr

    if value_eth > 0:
        display += f"  [{value_eth:.4f} ETH]"

    if node.get("cycle"):
        display += " ↻ cycle"

    click.echo(f"{prefix}{connector}{display}")

    children = node.get("children", [])
    for i, child in enumerate(children):
        extension = "    " if is_last else "│   "
        _print_tree(child, prefix + extension, i == len(children) - 1)


def _print_csv(node: dict, depth: int = 0) -> None:
    """Print trace results as CSV."""
    if depth == 0:
        click.echo("depth,address,value_wei,tx_count")

    addr = node.get("address", "")
    value = node.get("total_value_wei", 0)
    tx_count = node.get("tx_count", 0)
    click.echo(f"{depth},{addr},{value},{tx_count}")

    for child in node.get("children", []):
        _print_csv(child, depth + 1)


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
