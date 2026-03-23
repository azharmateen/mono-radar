"""Dependency graph builder using networkx."""

from dataclasses import dataclass
from typing import Optional

import networkx as nx

from .detector import Package


@dataclass
class DependencyGraph:
    """Directed dependency graph of monorepo packages."""

    graph: nx.DiGraph
    packages: dict[str, Package]  # name -> Package

    @property
    def package_names(self) -> list[str]:
        return list(self.packages.keys())

    def dependents_of(self, name: str) -> set[str]:
        """Get all packages that depend on `name` (direct + transitive)."""
        if name not in self.graph:
            return set()
        return set(nx.descendants(self.graph, name))

    def dependencies_of(self, name: str) -> set[str]:
        """Get all packages that `name` depends on (direct + transitive)."""
        if name not in self.graph:
            return set()
        return set(nx.ancestors(self.graph, name))

    def direct_dependents(self, name: str) -> set[str]:
        """Get direct dependents (one hop)."""
        if name not in self.graph:
            return set()
        return set(self.graph.successors(name))

    def direct_dependencies(self, name: str) -> set[str]:
        """Get direct dependencies (one hop)."""
        if name not in self.graph:
            return set()
        return set(self.graph.predecessors(name))

    def find_cycles(self) -> list[list[str]]:
        """Find all dependency cycles."""
        try:
            return list(nx.simple_cycles(self.graph))
        except nx.NetworkXError:
            return []

    def topological_order(self) -> list[str]:
        """Return packages in topological order (dependencies first).
        Returns empty list if graph has cycles.
        """
        try:
            return list(nx.topological_sort(self.graph))
        except nx.NetworkXUnfeasible:
            return []

    def subgraph(self, names: set[str]) -> "DependencyGraph":
        """Extract a subgraph containing only the given packages."""
        sub = self.graph.subgraph(names).copy()
        sub_packages = {n: self.packages[n] for n in names if n in self.packages}
        return DependencyGraph(graph=sub, packages=sub_packages)

    def stats(self) -> dict:
        """Get graph statistics."""
        return {
            "total_packages": len(self.packages),
            "total_edges": self.graph.number_of_edges(),
            "has_cycles": not nx.is_directed_acyclic_graph(self.graph),
            "cycles": self.find_cycles(),
            "leaf_packages": [n for n in self.graph.nodes() if self.graph.out_degree(n) == 0],
            "root_packages": [n for n in self.graph.nodes() if self.graph.in_degree(n) == 0],
        }


def build_dependency_graph(packages: list[Package]) -> DependencyGraph:
    """Build a directed dependency graph from detected packages.

    Edges go from dependency -> dependent (A -> B means B depends on A).
    This makes `descendants` of a changed node = all affected packages.
    """
    graph = nx.DiGraph()
    pkg_map = {pkg.name: pkg for pkg in packages}

    # Add all packages as nodes
    for pkg in packages:
        graph.add_node(pkg.name, path=pkg.path, type=pkg.pkg_type)

    # Add edges: dependency -> dependent
    for pkg in packages:
        all_deps = set(pkg.dependencies + pkg.dev_dependencies)
        for dep in all_deps:
            if dep in pkg_map:
                # Edge: dep -> pkg (dep is depended on by pkg)
                graph.add_edge(dep, pkg.name)

    return DependencyGraph(graph=graph, packages=pkg_map)


def build_reverse_graph(dep_graph: DependencyGraph) -> nx.DiGraph:
    """Build reverse graph (dependent -> dependency) for ancestor queries."""
    return dep_graph.graph.reverse(copy=True)
