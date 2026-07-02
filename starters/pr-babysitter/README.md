# PR Babysitter Starter

This starter produces a read-only health report for open pull requests.

1. Set `GITHUB_TOKEN` to a fine-grained token with Pull Requests and Checks
   read permissions.
2. Set `integrations.github.repository` in `loop.yaml`.
3. Change `enabled` to `true`.
4. Run `loop-engine run --config loop.yaml`.

The handler never merges, comments, requests reviewers, or modifies branches.
