# Contributing to Loop Engineering

Thank you for your interest in contributing to Loop Engineering! This document provides guidelines for contributing to the project.

## Development Setup

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/chillum-codeX/loop-engineering.git
   cd loop-engineering
   ```

3. Install in development mode:
   ```bash
   pip install -e ".[dev]"
   ```

4. Run tests:
   ```bash
   pytest tests/
   ```

## Code Standards

- **Python**: Follow PEP 8
- **Line length**: 100 characters max
- **Formatting**: Use black
- **Imports**: Use isort
- **Types**: Add type hints for new code

## Pull Request Process

1. Create a branch for your feature:
   ```bash
   git checkout -b feature/my-feature
   ```

2. Make your changes and add tests

3. Run the test suite:
   ```bash
   pytest tests/ -v
   ```

4. Format your code:
   ```bash
   black loop_engine/ tests/
   isort loop_engine/ tests/
   ```

5. Commit with a clear message:
   ```bash
   git commit -m "Add feature: description"
   ```

6. Push and create a PR:
   ```bash
   git push origin feature/my-feature
   ```

## Adding New Patterns

To add a new pattern:

1. Create `docs/patterns/my-pattern.md`
2. Add a starter template to `starters/my-pattern/`
3. Update the pattern index in `docs/patterns/README.md`
4. Add cost estimates to the CLI

Pattern template:
```markdown
# My Pattern

## When
Trigger conditions

## Read
Inputs needed

## Judge
Success criteria

## Output
Deliverables

## Stop
Boundaries
```

## Testing

- Add tests for new features
- Maintain >80% coverage
- Test both success and failure cases

## Documentation

- Update README.md if needed
- Add docstrings to new functions
- Update API reference docs

## Code of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Questions?

- [GitHub Discussions](https://github.com/chillum-codeX/loop-engineering/discussions)
- [GitHub Issues](https://github.com/chillum-codeX/loop-engineering/issues)

Thank you for contributing!
