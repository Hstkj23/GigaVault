# Contributing to SpawnAgent

Thank you for your interest in contributing to SpawnAgent! This document provides
guidelines and instructions for contributing.

## Development Setup

1. **Fork and clone** the repository
2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```
3. **Install in development mode:**
   ```bash
   pip install -e ".[dev]"
   ```
4. **Run tests to verify setup:**
   ```bash
   make test
   ```

## Development Workflow

1. Create a feature branch from `develop`:
   ```bash
   git checkout -b feature/your-feature develop
   ```
2. Make your changes
3. Add or update tests as needed
4. Run the full quality suite:
   ```bash
   make lint
   make test
   ```
5. Commit with a clear message:
   ```
   git commit -m "feat: add mempool anomaly scoring"
   ```
6. Push and open a Pull Request against `develop`

## Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation changes
- `test:` — Test changes
- `refactor:` — Code refactoring (no functionality change)
- `perf:` — Performance improvement
- `chore:` — Maintenance tasks

## Code Style

- **Formatter:** Black (line length 100)
- **Linter:** Ruff
- **Type checker:** mypy (strict mode)
- **Python:** 3.10+ (use modern type hints, no `Optional` — use `X | None`)

Run all checks with:
```bash
make lint
```

Auto-format with:
```bash
make format
```

## Testing

- All new features must include tests
- All bug fixes must include a regression test
- Minimum coverage target: 80%
- Use `pytest-asyncio` for async test functions
- Fixtures go in `tests/conftest.py`

```bash
make test         # Run tests
make test-cov     # Run tests with coverage report
```

## Architecture Guidelines

- **Async-first:** All I/O operations must be async
- **Supervision:** Long-running tasks must go through the supervisor tree
- **Events:** Cross-component communication uses the event system
- **Configuration:** All tunables must be configurable via YAML and env vars
- **Logging:** Use structured logging; no `print()` statements

## Pull Request Checklist

- [ ] Tests pass (`make test`)
- [ ] Linting passes (`make lint`)
- [ ] New features are documented
- [ ] CHANGELOG.md is updated for user-facing changes
- [ ] No sensitive data (API keys, addresses) in code

## Reporting Issues

- Use the [Bug Report](https://github.com/Hstkj23/GigaVault/issues/new?template=bug_report.md) template
- Use the [Feature Request](https://github.com/Hstkj23/GigaVault/issues/new?template=feature_request.md) template
- Check existing issues before creating duplicates

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
