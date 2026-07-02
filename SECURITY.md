# Security Policy

## Supported Versions

| Version | Supported          |
|---------|-------------------|
| 0.4.x   | :white_check_mark: |
| 0.3.x   | :x:                |
| < 0.3   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability, please:

1. **Do NOT** open a public issue
2. Email security@loop-engineering.dev with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will respond within 48 hours and work with you to address the issue.

## Security Best Practices

When using Loop Engineering:

1. **Budget Caps**: Always set budget limits
2. **Checkpoints**: Use conservative checkpoint presets for sensitive operations
3. **Gates**: Enable security gates
4. **Secrets**: Never commit API keys
5. **Scope**: Limit file system access

## Security Features

Loop Engineering includes:

- Budget enforcement (prevent token blowout)
- Human checkpoints (prevent unauthorized actions)
- Deterministic gates (catch issues before LLM calls)
- Worktree isolation (prevent unauthorized file access)
