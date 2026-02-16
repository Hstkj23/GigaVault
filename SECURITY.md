# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.4.x   | :white_check_mark: |
| 0.3.x   | :white_check_mark: |
| < 0.3   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in SpawnAgent, please report it responsibly.

**Do NOT open a public issue for security vulnerabilities.**

Instead, please email security concerns to the maintainers directly or use
GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
feature on this repository.

### What to include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **Acknowledgment:** Within 48 hours
- **Initial assessment:** Within 5 business days
- **Fix timeline:** Depends on severity; critical issues targeted within 7 days

## Security Best Practices

When using SpawnAgent:

1. **Never commit API keys** — Use environment variables or `.env` files
2. **Use read-only RPC endpoints** — SpawnAgent only reads chain state
3. **Restrict webhook URLs** — Validate alert destination endpoints
4. **Run with minimal privileges** — The Docker image runs as non-root by default
5. **Keep dependencies updated** — Run `pip audit` or `safety check` regularly
