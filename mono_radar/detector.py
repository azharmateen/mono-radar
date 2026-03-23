"""Workspace detector: find packages from various monorepo configurations."""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Package:
    """A package/workspace member in the monorepo."""

    name: str
    path: str  # Relative to monorepo root
    pkg_type: str  # npm, cargo, go, python, pnpm
    dependencies: list[str] = field(default_factory=list)
    dev_dependencies: list[str] = field(default_factory=list)
    version: str = ""


def detect_workspaces(root: str = ".") -> list[Package]:
    """Auto-detect all workspace packages in a monorepo.

    Checks for:
    - package.json workspaces (npm/yarn)
    - pnpm-workspace.yaml
    - Cargo.toml [workspace]
    - go.work
    - Python pyproject.toml with name
    """
    root_path = Path(root).resolve()
    packages: list[Package] = []

    # npm/yarn workspaces
    packages.extend(_detect_npm_workspaces(root_path))

    # pnpm workspaces
    packages.extend(_detect_pnpm_workspaces(root_path))

    # Cargo workspaces
    packages.extend(_detect_cargo_workspaces(root_path))

    # Go workspaces
    packages.extend(_detect_go_workspaces(root_path))

    # Python packages (fallback scan)
    packages.extend(_detect_python_packages(root_path))

    # Deduplicate by path
    seen = set()
    unique = []
    for pkg in packages:
        if pkg.path not in seen:
            seen.add(pkg.path)
            unique.append(pkg)

    return unique


def _resolve_globs(root: Path, patterns: list[str]) -> list[Path]:
    """Resolve glob patterns relative to root."""
    results = []
    for pattern in patterns:
        # Handle "packages/*" style patterns
        for match in sorted(root.glob(pattern)):
            if match.is_dir():
                results.append(match)
    return results


def _detect_npm_workspaces(root: Path) -> list[Package]:
    """Detect npm/yarn workspace packages."""
    pkg_json = root / "package.json"
    if not pkg_json.exists():
        return []

    with open(pkg_json) as f:
        data = json.load(f)

    workspace_globs = data.get("workspaces", [])
    # Yarn uses {"packages": [...]} format
    if isinstance(workspace_globs, dict):
        workspace_globs = workspace_globs.get("packages", [])

    if not workspace_globs:
        return []

    packages = []
    dirs = _resolve_globs(root, workspace_globs)

    for d in dirs:
        child_pkg = d / "package.json"
        if child_pkg.exists():
            with open(child_pkg) as f:
                child_data = json.load(f)
            name = child_data.get("name", d.name)
            deps = list(child_data.get("dependencies", {}).keys())
            dev_deps = list(child_data.get("devDependencies", {}).keys())
            packages.append(
                Package(
                    name=name,
                    path=str(d.relative_to(root)),
                    pkg_type="npm",
                    dependencies=deps,
                    dev_dependencies=dev_deps,
                    version=child_data.get("version", ""),
                )
            )

    return packages


def _detect_pnpm_workspaces(root: Path) -> list[Package]:
    """Detect pnpm workspace packages."""
    ws_file = root / "pnpm-workspace.yaml"
    if not ws_file.exists():
        return []

    with open(ws_file) as f:
        data = yaml.safe_load(f)

    patterns = data.get("packages", [])
    if not patterns:
        return []

    packages = []
    dirs = _resolve_globs(root, patterns)

    for d in dirs:
        child_pkg = d / "package.json"
        if child_pkg.exists():
            with open(child_pkg) as f:
                child_data = json.load(f)
            name = child_data.get("name", d.name)
            deps = list(child_data.get("dependencies", {}).keys())
            dev_deps = list(child_data.get("devDependencies", {}).keys())
            packages.append(
                Package(
                    name=name,
                    path=str(d.relative_to(root)),
                    pkg_type="pnpm",
                    dependencies=deps,
                    dev_dependencies=dev_deps,
                    version=child_data.get("version", ""),
                )
            )

    return packages


def _detect_cargo_workspaces(root: Path) -> list[Package]:
    """Detect Cargo workspace members."""
    cargo_toml = root / "Cargo.toml"
    if not cargo_toml.exists():
        return []

    content = cargo_toml.read_text()

    # Simple TOML parsing for workspace members
    members = []
    in_workspace = False
    in_members = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "[workspace]":
            in_workspace = True
            continue
        if in_workspace and stripped.startswith("members"):
            in_members = True
            # Parse inline array
            match = re.search(r'\[([^\]]*)\]', stripped)
            if match:
                items = match.group(1)
                members = [s.strip().strip('"').strip("'") for s in items.split(",") if s.strip()]
                in_members = False
            continue
        if in_members:
            if stripped == "]":
                in_members = False
                continue
            member = stripped.strip('",').strip("',").strip()
            if member:
                members.append(member)
        if in_workspace and stripped.startswith("[") and stripped != "[workspace]":
            in_workspace = False

    packages = []
    for pattern in members:
        for d in _resolve_globs(root, [pattern]):
            member_toml = d / "Cargo.toml"
            if member_toml.exists():
                member_content = member_toml.read_text()
                name = d.name
                # Extract package name
                name_match = re.search(r'name\s*=\s*"([^"]+)"', member_content)
                if name_match:
                    name = name_match.group(1)

                # Extract dependencies
                deps = []
                in_deps = False
                for mline in member_content.splitlines():
                    ms = mline.strip()
                    if ms == "[dependencies]":
                        in_deps = True
                        continue
                    if in_deps:
                        if ms.startswith("["):
                            in_deps = False
                            continue
                        if "=" in ms:
                            dep_name = ms.split("=")[0].strip()
                            deps.append(dep_name)

                packages.append(
                    Package(
                        name=name,
                        path=str(d.relative_to(root)),
                        pkg_type="cargo",
                        dependencies=deps,
                    )
                )

    return packages


def _detect_go_workspaces(root: Path) -> list[Package]:
    """Detect Go workspace modules from go.work."""
    go_work = root / "go.work"
    if not go_work.exists():
        return []

    packages = []
    content = go_work.read_text()

    # Parse "use" directives
    in_use = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("use ("):
            in_use = True
            continue
        if stripped == "use" and not in_use:
            in_use = True
            continue
        if in_use:
            if stripped == ")":
                in_use = False
                continue
            mod_path = stripped.strip()
            if mod_path:
                full_path = root / mod_path
                go_mod = full_path / "go.mod"
                if go_mod.exists():
                    # Extract module name
                    mod_content = go_mod.read_text()
                    name = mod_path
                    for mline in mod_content.splitlines():
                        if mline.startswith("module "):
                            name = mline.split("module ", 1)[1].strip()
                            break

                    # Extract dependencies from go.mod require block
                    deps = []
                    in_require = False
                    for mline in mod_content.splitlines():
                        ms = mline.strip()
                        if ms.startswith("require ("):
                            in_require = True
                            continue
                        if in_require:
                            if ms == ")":
                                in_require = False
                                continue
                            parts = ms.split()
                            if parts:
                                deps.append(parts[0])

                    packages.append(
                        Package(
                            name=name,
                            path=mod_path,
                            pkg_type="go",
                            dependencies=deps,
                        )
                    )

    return packages


def _detect_python_packages(root: Path) -> list[Package]:
    """Scan for Python packages with pyproject.toml or setup.py."""
    packages = []

    for pyproj in root.rglob("pyproject.toml"):
        # Skip nested venvs and build dirs
        rel = pyproj.relative_to(root)
        parts = rel.parts
        if any(p in parts for p in ("venv", ".venv", "env", "node_modules", ".git", "build", "dist")):
            continue
        # Skip root pyproject.toml if it's not a package itself
        if len(parts) < 2:
            continue

        try:
            content = pyproj.read_text()
            # Simple TOML parsing for name
            name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
            if name_match:
                name = name_match.group(1)
                pkg_dir = str(pyproj.parent.relative_to(root))

                # Extract dependencies
                deps = []
                dep_match = re.search(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
                if dep_match:
                    dep_block = dep_match.group(1)
                    for dep_line in dep_block.splitlines():
                        dep_clean = dep_line.strip().strip('",').strip("',")
                        if dep_clean:
                            # Extract package name (before version specifier)
                            dep_name = re.split(r'[>=<!\[]', dep_clean)[0].strip()
                            if dep_name:
                                deps.append(dep_name)

                packages.append(
                    Package(
                        name=name,
                        path=pkg_dir,
                        pkg_type="python",
                        dependencies=deps,
                    )
                )
        except Exception:
            continue

    return packages


def map_file_to_package(filepath: str, packages: list[Package]) -> Optional[Package]:
    """Map a file path to its owning package."""
    # Normalize path
    filepath = filepath.replace("\\", "/")
    best_match: Optional[Package] = None
    best_depth = -1

    for pkg in packages:
        pkg_path = pkg.path.replace("\\", "/")
        if filepath.startswith(pkg_path + "/") or filepath == pkg_path:
            depth = pkg_path.count("/")
            if depth > best_depth:
                best_depth = depth
                best_match = pkg

    return best_match
