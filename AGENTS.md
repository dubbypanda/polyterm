# Project Agent Rules

These instructions apply to all work in this repository.

## Architecture Rule: No Monoliths

- Do not introduce monolithic files, modules, or command handlers.
- Prefer small, focused modules with clear single responsibilities.
- Keep features easy to edit, add, remove, and test in isolation.
- Split large changes into composable units (API layer, core logic, CLI/TUI wiring, tests).
- Favor explicit interfaces between modules over tightly coupled cross-module logic.
- When extending functionality, add or modify the smallest relevant module instead of expanding a central "god" file.

## Change Quality Gate

Before finalizing substantial changes, verify:

- The code path can be understood without reading unrelated modules.
- A future contributor can replace/remove a feature without broad refactors.
- Tests are scoped to behavior of the touched module(s), not accidental implementation details.
