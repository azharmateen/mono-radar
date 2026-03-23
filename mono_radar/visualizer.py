"""Generate DOT/Graphviz visualization of dependency graph."""

from typing import Optional

from .graph import DependencyGraph
from .impact import ImpactReport


# Color scheme
COLORS = {
    "direct_changed": "#ff6b6b",  # Red - directly changed
    "transitive": "#ffd93d",  # Yellow - transitively affected
    "unaffected": "#6bcb77",  # Green - not affected
    "edge_normal": "#888888",
    "edge_affected": "#ff6b6b",
    "bg": "#1a1a2e",
    "text": "#ffffff",
}

PKG_TYPE_SHAPES = {
    "npm": "box",
    "pnpm": "box",
    "cargo": "hexagon",
    "go": "diamond",
    "python": "ellipse",
}


def generate_dot(
    dep_graph: DependencyGraph,
    report: Optional[ImpactReport] = None,
    title: str = "Dependency Graph",
    show_types: bool = True,
) -> str:
    """Generate DOT format string for Graphviz visualization.

    Args:
        dep_graph: The dependency graph
        report: Optional impact report (to highlight affected nodes)
        title: Graph title
        show_types: Show package types as node shapes

    Returns:
        DOT format string
    """
    lines = [
        "digraph mono_radar {",
        f'  label="{title}";',
        "  labelloc=t;",
        "  fontsize=20;",
        f'  bgcolor="{COLORS["bg"]}";',
        f'  fontcolor="{COLORS["text"]}";',
        "  rankdir=LR;",
        "  node [style=filled, fontsize=12];",
        "  edge [color=\"#555555\"];",
        "",
    ]

    directly_changed = report.directly_changed if report else set()
    all_affected = report.all_affected if report else set()

    # Nodes
    for name, pkg in sorted(dep_graph.packages.items()):
        shape = PKG_TYPE_SHAPES.get(pkg.pkg_type, "ellipse") if show_types else "ellipse"

        if name in directly_changed:
            color = COLORS["direct_changed"]
            font_color = "#000000"
        elif name in all_affected:
            color = COLORS["transitive"]
            font_color = "#000000"
        else:
            color = COLORS["unaffected"]
            font_color = "#000000"

        label = name
        if show_types:
            label = f"{name}\\n({pkg.pkg_type})"

        safe_name = _safe_id(name)
        lines.append(
            f'  {safe_name} [label="{label}", shape={shape}, '
            f'fillcolor="{color}", fontcolor="{font_color}"];'
        )

    lines.append("")

    # Edges
    for u, v in dep_graph.graph.edges():
        safe_u = _safe_id(u)
        safe_v = _safe_id(v)
        edge_color = COLORS["edge_normal"]
        penwidth = "1.0"

        if report and (u in all_affected and v in all_affected):
            edge_color = COLORS["edge_affected"]
            penwidth = "2.0"

        lines.append(f'  {safe_u} -> {safe_v} [color="{edge_color}", penwidth={penwidth}];')

    lines.append("")

    # Legend
    if report:
        lines.extend([
            "  subgraph cluster_legend {",
            '    label="Legend";',
            f'    fontcolor="{COLORS["text"]}";',
            '    style=dashed;',
            f'    color="{COLORS["text"]}";',
            f'    legend_direct [label="Directly Changed", fillcolor="{COLORS["direct_changed"]}", shape=box];',
            f'    legend_transitive [label="Transitively Affected", fillcolor="{COLORS["transitive"]}", shape=box];',
            f'    legend_safe [label="Not Affected", fillcolor="{COLORS["unaffected"]}", shape=box];',
            "    legend_direct -> legend_transitive -> legend_safe [style=invis];",
            "  }",
        ])

    lines.append("}")
    return "\n".join(lines)


def generate_mermaid(
    dep_graph: DependencyGraph,
    report: Optional[ImpactReport] = None,
) -> str:
    """Generate Mermaid diagram syntax."""
    lines = ["graph LR"]

    directly_changed = report.directly_changed if report else set()
    all_affected = report.all_affected if report else set()

    # Define nodes with styling
    for name in sorted(dep_graph.packages.keys()):
        safe = _safe_id(name)
        if name in directly_changed:
            lines.append(f"  {safe}[{name}]:::changed")
        elif name in all_affected:
            lines.append(f"  {safe}[{name}]:::affected")
        else:
            lines.append(f"  {safe}[{name}]:::normal")

    lines.append("")

    # Edges
    for u, v in dep_graph.graph.edges():
        lines.append(f"  {_safe_id(u)} --> {_safe_id(v)}")

    # Styling
    lines.extend([
        "",
        "  classDef changed fill:#ff6b6b,stroke:#333,color:#000",
        "  classDef affected fill:#ffd93d,stroke:#333,color:#000",
        "  classDef normal fill:#6bcb77,stroke:#333,color:#000",
    ])

    return "\n".join(lines)


def generate_ascii(
    dep_graph: DependencyGraph,
    report: Optional[ImpactReport] = None,
) -> str:
    """Generate a simple ASCII representation of the graph."""
    lines = []
    directly_changed = report.directly_changed if report else set()
    all_affected = report.all_affected if report else set()

    for name in sorted(dep_graph.packages.keys()):
        marker = " "
        if name in directly_changed:
            marker = "!"
        elif name in all_affected:
            marker = "~"

        deps = dep_graph.direct_dependents(name)
        dep_str = ""
        if deps:
            dep_str = " -> " + ", ".join(sorted(deps))

        lines.append(f"  [{marker}] {name}{dep_str}")

    header = "Dependency Graph (! = directly changed, ~ = transitively affected)"
    return f"{header}\n{'=' * len(header)}\n" + "\n".join(lines)


def _safe_id(name: str) -> str:
    """Convert package name to safe DOT/Mermaid identifier."""
    return name.replace("-", "_").replace("@", "").replace("/", "__").replace(".", "_")
