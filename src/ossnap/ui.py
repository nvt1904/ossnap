from contextlib import contextmanager

from rich.console import Console
from rich.rule import Rule
from rich.table import Table, box
from rich.tree import Tree

console = Console()

_INDENT = "  "


def banner(cmd: str) -> None:
    console.print(f"\n[bold cyan]ossnap[/] [bold white]{cmd}[/]")
    console.print(Rule(style="cyan dim"))
    console.print()


def header(msg: str) -> None:
    console.print()
    console.print(Rule(f"[bold]{msg}[/]", style="dim", align="left"))


def success(msg: str) -> None:
    console.print(f"{_INDENT}[bold green]✓[/] {msg}")


def error(msg: str) -> None:
    console.print(f"{_INDENT}[bold red]✗[/] {msg}")


def warn(msg: str) -> None:
    console.print(f"{_INDENT}[bold yellow]⚠[/]  {msg}")


def info(msg: str) -> None:
    console.print(f"{_INDENT}[dim]{msg}[/]")


@contextmanager
def status_spinner(msg: str):
    with console.status(f"[dim]{msg}[/]") as s:
        yield s


def print_snapshot_tree(
    repo_results: list[tuple[str, list[str]]],
    ssh_result: dict,
) -> None:
    tree = Tree("[dim]snapshot/[/]")

    # SSH branch
    ssh_branch = tree.add("[bold cyan]ssh/[/]")
    for name in ("config", "authorized_keys"):
        if ssh_result.get(name):
            ssh_branch.add(f"[green]{name}[/] [dim]· encrypted[/]")
    if ssh_result.get("known_hosts"):
        ssh_branch.add("[dim]known_hosts · plain text[/]")
    if ssh_result.get("keys"):
        keys_branch = ssh_branch.add("[bold cyan]keys/[/]")
        for key in ssh_result.get("keys", []):
            keys_branch.add(f"[green]{key}[/] [dim]· encrypted[/]")

    # Repos branch
    with_envs = [(p, files) for p, files in repo_results if files]
    no_envs_count = sum(1 for _, files in repo_results if not files)

    if with_envs or no_envs_count:
        repos_branch = tree.add("[bold cyan]repos/envs/[/]")
        for rel_path, env_files in with_envs:
            repo_branch = repos_branch.add(f"[white]{rel_path}[/]")
            for f in env_files:
                repo_branch.add(f"[green]{f}[/] [dim]· encrypted[/]")
        if no_envs_count:
            repos_branch.add(f"[dim]+ {no_envs_count} repos with no env files[/]")

    console.print(tree)


def print_table(title: str, rows: list[tuple], headers: list[str]) -> None:
    table = Table(
        title=f"[bold]{title}[/]",
        show_header=True,
        box=box.ROUNDED,
        border_style="dim",
        header_style="bold cyan",
        title_justify="left",
    )
    for h in headers:
        table.add_column(h)
    for row in rows:
        table.add_row(*[str(c) for c in row])
    console.print()
    console.print(table)
