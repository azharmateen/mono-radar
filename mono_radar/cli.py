"""Click CLI for mono-radar: detect, impact, graph, matrix, visualize."""

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree

from .detector import detect_workspaces
from .graph import build_dependency_graph
from .impact import (
    analyze_impact,
    analyze_from_git,
    get_changed_files,
    get_changed_files_from_text,
)
from .matrix import (
    generate_github_actions_matrix,
    generate_plain_list,
    generate_build_order,
    generate_gitlab_ci,
)
from .visualizer import generate_dot, generate_mermaid, generate_ascii

console = Console()


@click.group()
@click.version_option(package_name="mono-radar")
@click.option("--root", "-r", default=".", help="Monorepo root directory")
@click.pass_context
def cli(ctx, root):
    """mono-radar - Monorepo change-impact analyzer."""
    ctx.ensure_object(dict)
    ctx.obj["root"] = root


@cli.command()
@click.pass_context
def detect(ctx):
    """Detect workspace packages in the monorepo."""
    root = ctx.obj["root"]
    packages = detect_workspaces(root)

    if not packages:
        console.print("[yellow]No workspace packages detected.[/yellow]")
        console.print("[dim]Supported: npm/yarn workspaces, pnpm-workspace.yaml, Cargo.toml, go.work, Python pyproject.toml[/dim]")
        return

    table = Table(title=f"Detected Packages ({len(packages)})")
    table.add_column("Name", style="cyan")
    table.add_column("Path", style="dim")
    table.add_column("Type", style="green")
    table.add_column("Deps", justify="right")
    table.add_column("Version", style="yellow")

    for pkg in packages:
        table.add_row(
            pkg.name,
            pkg.path,
            pkg.pkg_type,
            str(len(pkg.dependencies)),
            pkg.version or "-",
        )
    console.print(table)


@cli.command()
@click.option("--base", "-b", default="HEAD~1", help="Base git ref")
@click.option("--head", "-h", "head_ref", default="HEAD", help="Head git ref")
@click.option("--files", "-f", help="File with changed paths (one per line), or - for stdin")
@click.option("--json-output", "-j", "json_out", is_flag=True, help="Output as JSON")
@click.pass_context
def impact(ctx, base, head_ref, files, json_out):
    """Analyze impact of changes on the monorepo."""
    root = ctx.obj["root"]
    packages = detect_workspaces(root)

    if not packages:
        console.print("[yellow]No packages detected. Nothing to analyze.[/yellow]")
        return

    dep_graph = build_dependency_graph(packages)

    # Get changed files
    if files:
        if files == "-":
            text = sys.stdin.read()
        else:
            text = Path(files).read_text()
        changed = get_changed_files_from_text(text)
    else:
        changed = get_changed_files(base, head_ref, root)

    if not changed:
        console.print("[yellow]No changed files detected.[/yellow]")
        return

    report = analyze_impact(changed, packages, dep_graph)

    if json_out:
        click.echo(json.dumps(report.summary(), indent=2))
        return

    # Rich output
    console.print(Panel(
        f"Changed files: [bold]{len(changed)}[/bold]\n"
        f"Directly changed packages: [bold red]{len(report.directly_changed)}[/bold red]\n"
        f"Transitively affected: [bold yellow]{len(report.transitively_affected - report.directly_changed)}[/bold yellow]\n"
        f"Total affected: [bold]{report.total_affected}[/bold]\n"
        f"Unowned files: [dim]{len(report.unowned_files)}[/dim]",
        title="Impact Analysis",
    ))

    if report.directly_changed:
        console.print("\n[bold red]Directly changed:[/bold red]")
        for name in sorted(report.directly_changed):
            pkg = dep_graph.packages.get(name)
            path = pkg.path if pkg else "?"
            console.print(f"  [red]![/red] {name} ({path})")

    transitive_only = report.transitively_affected - report.directly_changed
    if transitive_only:
        console.print("\n[bold yellow]Transitively affected:[/bold yellow]")
        for name in sorted(transitive_only):
            pkg = dep_graph.packages.get(name)
            path = pkg.path if pkg else "?"
            console.print(f"  [yellow]~[/yellow] {name} ({path})")

    if report.unowned_files:
        console.print(f"\n[dim]Unowned files ({len(report.unowned_files)}):[/dim]")
        for f in report.unowned_files[:10]:
            console.print(f"  [dim]{f}[/dim]")
        if len(report.unowned_files) > 10:
            console.print(f"  [dim]... and {len(report.unowned_files) - 10} more[/dim]")


@cli.command()
@click.option("--json-output", "-j", "json_out", is_flag=True, help="Output as JSON")
@click.pass_context
def graph(ctx, json_out):
    """Show the dependency graph and statistics."""
    root = ctx.obj["root"]
    packages = detect_workspaces(root)

    if not packages:
        console.print("[yellow]No packages detected.[/yellow]")
        return

    dep_graph = build_dependency_graph(packages)
    stats = dep_graph.stats()

    if json_out:
        edges = [{"from": u, "to": v} for u, v in dep_graph.graph.edges()]
        click.echo(json.dumps({
            "packages": [{"name": p.name, "path": p.path, "type": p.pkg_type} for p in packages],
            "edges": edges,
            "stats": stats,
        }, indent=2))
        return

    console.print(Panel(
        f"Packages: [bold]{stats['total_packages']}[/bold]\n"
        f"Dependencies: [bold]{stats['total_edges']}[/bold]\n"
        f"Has cycles: [bold {'red' if stats['has_cycles'] else 'green'}]{stats['has_cycles']}[/bold]\n"
        f"Leaf packages: {len(stats['leaf_packages'])}\n"
        f"Root packages: {len(stats['root_packages'])}",
        title="Dependency Graph",
    ))

    if stats["cycles"]:
        console.print("\n[red bold]Cycles detected:[/red bold]")
        for cycle in stats["cycles"]:
            console.print(f"  {' -> '.join(cycle)} -> {cycle[0]}")

    # Show tree view
    tree = Tree("[bold]Dependency Tree[/bold]")
    for name in sorted(stats.get("root_packages", [])):
        _add_tree_node(tree, name, dep_graph, set())
    console.print(tree)


def _add_tree_node(tree_node, name: str, dep_graph, visited: set):
    """Recursively add nodes to rich Tree."""
    if name in visited:
        tree_node.add(f"[dim]{name} (circular)[/dim]")
        return
    visited.add(name)

    dependents = dep_graph.direct_dependents(name)
    if dependents:
        branch = tree_node.add(f"[cyan]{name}[/cyan]")
        for dep in sorted(dependents):
            _add_tree_node(branch, dep, dep_graph, visited.copy())
    else:
        tree_node.add(f"[green]{name}[/green]")


@cli.command()
@click.option("--base", "-b", default="HEAD~1", help="Base git ref")
@click.option("--head", "-h", "head_ref", default="HEAD", help="Head git ref")
@click.option("--format", "-f", "fmt", type=click.Choice(["github", "gitlab", "names", "paths", "json"]), default="github")
@click.option("--files", help="File with changed paths, or - for stdin")
@click.pass_context
def matrix(ctx, base, head_ref, fmt, files):
    """Generate CI matrix for affected packages."""
    root = ctx.obj["root"]
    packages = detect_workspaces(root)

    if not packages:
        return

    dep_graph = build_dependency_graph(packages)

    if files:
        text = sys.stdin.read() if files == "-" else Path(files).read_text()
        changed = get_changed_files_from_text(text)
    else:
        changed = get_changed_files(base, head_ref, root)

    report = analyze_impact(changed, packages, dep_graph)

    if fmt == "github":
        matrix_json = generate_github_actions_matrix(report, dep_graph)
        click.echo(json.dumps(matrix_json, indent=2))
    elif fmt == "gitlab":
        click.echo(generate_gitlab_ci(report, dep_graph))
    elif fmt in ("names", "paths", "json"):
        items = generate_plain_list(report, dep_graph, format=fmt)
        for item in items:
            click.echo(item)

    # Also show build order
    order = generate_build_order(report, dep_graph)
    if order and fmt not in ("gitlab",):
        console.print(f"\n[dim]Build order ({len(order)} layers):[/dim]")
        for i, layer in enumerate(order):
            console.print(f"  [dim]Layer {i}:[/dim] {', '.join(layer)}")


@cli.command()
@click.option("--format", "-f", "fmt", type=click.Choice(["dot", "mermaid", "ascii"]), default="ascii")
@click.option("--output", "-o", help="Output file path")
@click.option("--base", "-b", default="HEAD~1", help="Base git ref for highlighting")
@click.option("--head", "-h", "head_ref", default="HEAD", help="Head git ref")
@click.option("--no-impact", is_flag=True, help="Don't highlight impacted nodes")
@click.pass_context
def visualize(ctx, fmt, output, base, head_ref, no_impact):
    """Visualize the dependency graph."""
    root = ctx.obj["root"]
    packages = detect_workspaces(root)

    if not packages:
        console.print("[yellow]No packages detected.[/yellow]")
        return

    dep_graph = build_dependency_graph(packages)

    report = None
    if not no_impact:
        changed = get_changed_files(base, head_ref, root)
        if changed:
            report = analyze_impact(changed, packages, dep_graph)

    if fmt == "dot":
        result = generate_dot(dep_graph, report)
    elif fmt == "mermaid":
        result = generate_mermaid(dep_graph, report)
    else:
        result = generate_ascii(dep_graph, report)

    if output:
        Path(output).write_text(result)
        console.print(f"[green]Saved to {output}[/green]")

        if fmt == "dot":
            console.print(f"[dim]Render with: dot -Tsvg {output} -o graph.svg[/dim]")
    else:
        click.echo(result)


if __name__ == "__main__":
    cli()
