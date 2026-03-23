"""Impact analyzer: map git diff to affected packages and their dependents."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .detector import Package, map_file_to_package
from .graph import DependencyGraph


@dataclass
class ImpactReport:
    """Analysis of what is affected by a set of changes."""

    changed_files: list[str]
    directly_changed: set[str]  # Package names with changed files
    transitively_affected: set[str]  # All downstream dependents
    all_affected: set[str]  # Union of direct + transitive
    file_to_package: dict[str, str]  # file -> package name
    unowned_files: list[str]  # Files not belonging to any package

    @property
    def total_affected(self) -> int:
        return len(self.all_affected)

    def summary(self) -> dict:
        return {
            "changed_files": len(self.changed_files),
            "directly_changed_packages": sorted(self.directly_changed),
            "transitively_affected_packages": sorted(
                self.transitively_affected - self.directly_changed
            ),
            "all_affected_packages": sorted(self.all_affected),
            "total_affected": self.total_affected,
            "unowned_files": len(self.unowned_files),
        }


def get_changed_files(
    base_ref: str = "HEAD~1",
    head_ref: str = "HEAD",
    root: str = ".",
) -> list[str]:
    """Get list of changed files from git diff.

    Args:
        base_ref: Base git ref (default: previous commit)
        head_ref: Head git ref (default: current commit)
        root: Repository root directory

    Returns:
        List of changed file paths relative to root
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref, head_ref],
            capture_output=True,
            text=True,
            cwd=root,
        )
        if result.returncode != 0:
            # Try against staged changes
            result = subprocess.run(
                ["git", "diff", "--name-only", "--cached"],
                capture_output=True,
                text=True,
                cwd=root,
            )
        if result.returncode != 0:
            # Try uncommitted changes
            result = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True,
                text=True,
                cwd=root,
            )

        files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        return files
    except FileNotFoundError:
        return []


def get_changed_files_from_text(diff_text: str) -> list[str]:
    """Parse file list from diff output or plain text (one file per line)."""
    files = []
    for line in diff_text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Handle git diff --name-status format (M\tfile)
        if "\t" in line:
            parts = line.split("\t")
            if len(parts) >= 2:
                files.append(parts[-1])
                continue
        files.append(line)
    return files


def analyze_impact(
    changed_files: list[str],
    packages: list[Package],
    dep_graph: DependencyGraph,
) -> ImpactReport:
    """Analyze the impact of changed files on the monorepo.

    Args:
        changed_files: List of changed file paths
        packages: Detected workspace packages
        dep_graph: Built dependency graph

    Returns:
        ImpactReport with direct and transitive impact analysis
    """
    directly_changed: set[str] = set()
    file_to_pkg: dict[str, str] = {}
    unowned: list[str] = []

    for filepath in changed_files:
        pkg = map_file_to_package(filepath, packages)
        if pkg:
            directly_changed.add(pkg.name)
            file_to_pkg[filepath] = pkg.name
        else:
            unowned.append(filepath)

    # Find all transitive dependents
    transitively_affected: set[str] = set()
    for pkg_name in directly_changed:
        dependents = dep_graph.dependents_of(pkg_name)
        transitively_affected.update(dependents)

    all_affected = directly_changed | transitively_affected

    return ImpactReport(
        changed_files=changed_files,
        directly_changed=directly_changed,
        transitively_affected=transitively_affected,
        all_affected=all_affected,
        file_to_package=file_to_pkg,
        unowned_files=unowned,
    )


def analyze_from_git(
    packages: list[Package],
    dep_graph: DependencyGraph,
    base_ref: str = "HEAD~1",
    head_ref: str = "HEAD",
    root: str = ".",
) -> ImpactReport:
    """Full analysis: get git diff and analyze impact."""
    changed = get_changed_files(base_ref, head_ref, root)
    return analyze_impact(changed, packages, dep_graph)
