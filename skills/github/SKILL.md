---
name: github
description: "GitHub operations via gh CLI. Use when: managing PRs, issues, repos, releases. NOT for: general git commands."
metadata:
  openclaw:
    emoji: "🐙"
    requires:
      bins: ["gh"]
user-invocable: true
---

# GitHub CLI Operations

You have access to the `gh` CLI tool for GitHub operations. Use the `exec` tool to run gh commands.

## Common Operations

### Pull Requests
```bash
gh pr list                          # List open PRs
gh pr view <number>                 # View PR details
gh pr create --title "..." --body "..."  # Create PR
gh pr checkout <number>             # Check out a PR locally
gh pr merge <number>                # Merge a PR
gh pr review <number> --approve     # Approve a PR
```

### Issues
```bash
gh issue list                       # List open issues
gh issue view <number>              # View issue details
gh issue create --title "..." --body "..."  # Create issue
gh issue close <number>             # Close issue
```

### Repository
```bash
gh repo view                        # View current repo info
gh repo clone <owner/repo>          # Clone a repo
gh release list                     # List releases
gh release create <tag> --title "..." --notes "..."  # Create release
```

### Search
```bash
gh search repos <query>             # Search repositories
gh search issues <query>            # Search issues
gh search prs <query>               # Search PRs
```

## Tips
- Always check `gh auth status` first if commands fail
- Use `--json` flag for structured output: `gh pr list --json number,title,url`
- Use `--jq` for filtering: `gh pr list --json title --jq '.[].title'`
