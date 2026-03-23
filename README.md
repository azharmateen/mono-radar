# mono-radar

**Monorepo change-impact analyzer: find what to test, build, and deploy from a diff.**

Point mono-radar at your monorepo. It detects every package, builds the dependency graph, and tells you exactly which packages are affected by your changes -- directly and transitively. Generate CI matrices, build orders, and dependency visualizations.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

---

## Why mono-radar?

- **Auto-detects workspaces** -- npm/yarn, pnpm, Cargo, Go work, Python pyproject.toml.
- **Transitive impact analysis** -- Change `shared-utils`? See every downstream package that needs rebuilding.
- **CI matrix generation** -- Output GitHub Actions matrix JSON or GitLab CI config for only affected packages.
- **Build ordering** -- Parallelizable build layers respecting dependency order.
- **Cycle detection** -- Find circular dependencies before they break your build.
- **Visualization** -- DOT/Graphviz, Mermaid, or ASCII dependency graphs with impact highlighting.

## Quick Start

```bash
pip install mono-radar

# Detect packages in your monorepo
mono-radar detect

# See what's affected by recent changes
mono-radar impact

# Compare against a specific branch
mono-radar impact --base origin/main --head HEAD

# Generate GitHub Actions matrix
mono-radar matrix --format github

# Visualize dependencies
mono-radar visualize --format ascii
mono-radar visualize --format dot -o deps.dot
dot -Tsvg deps.dot -o deps.svg
```

## CI Integration

### GitHub Actions
```yaml
jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.radar.outputs.matrix }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - run: pip install mono-radar
      - id: radar
        run: echo "matrix=$(mono-radar matrix -f github -b origin/main)" >> $GITHUB_OUTPUT

  build:
    needs: detect
    strategy:
      matrix: ${{ fromJson(needs.detect.outputs.matrix) }}
    runs-on: ubuntu-latest
    steps:
      - run: echo "Building ${{ matrix.package }} at ${{ matrix.path }}"
```

### From a file list
```bash
git diff --name-only origin/main | mono-radar impact --files -
mono-radar matrix --files changed.txt --format names
```

## Features

### Workspace Detection
| Ecosystem | Config File | Detected |
|-----------|------------|----------|
| npm/yarn | `package.json` workspaces | Package name, deps, devDeps |
| pnpm | `pnpm-workspace.yaml` | Package name, deps, devDeps |
| Cargo | `Cargo.toml` [workspace] | Crate name, deps |
| Go | `go.work` | Module name, deps |
| Python | `pyproject.toml` | Package name, deps |

### Impact Analysis
```
Changed files -> Owning packages -> Dependency graph traversal -> All affected packages
```

### Visualization
```bash
# ASCII (terminal)
mono-radar visualize

# Graphviz DOT
mono-radar visualize -f dot -o graph.dot

# Mermaid (for GitHub/GitLab markdown)
mono-radar visualize -f mermaid -o graph.md
```

## License

MIT
