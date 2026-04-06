---
layout: home

hero:
  name: uvr
  tagline: <span>Footgun-free release management for <a href="https://github.com/astral-sh/uv">uv</a> workspaces.</span>
  actions:
    - theme: brand
      text: Get Started
      link: /user-guide/01-getting-started
    - theme: alt
      text: Go Under the Hood
      link: /under-the-hood/architecture

features:
  - title: 🏗️ Scaffold
    details: "<code class=\"brand-code\">uvr workflow init</code><br>Generate a complete release workflow in one command. Runner matrices, PyPI publishing, and hooks built in."
    link: /user-guide/01-getting-started#scaffold-the-release-workflow
  - title: ⬆️ Bump
    details: "<code class=\"brand-code\">uvr bump</code><br>Bump versions without breaking internal dependencies. Downstream pins update automatically."
    link: /user-guide/04-versions
  - title: 🚀 Release
    details: "<code class=\"brand-code\">uvr release</code><br>Release with confidence. Catch errors before dispatch, only rebuild what changed, and recover from failures without starting over."
    link: /user-guide/02-releasing
  - title: 🤖 Claude
    details: "<code class=\"brand-code\">/release</code><br>Ship interactively. Claude handles branching, release notes, dispatch, and failure recovery."
    link: /user-guide/03-claude
---

## Quick Start

Install uv-release and scaffold your first workflow:

```bash
pip install uv-release
uvr workflow init
```

Check what would be released:

```bash
uvr release --dry-run
```

Release changed packages. Generates a plan, prompts for confirmation, and dispatches to GitHub Actions.

```bash
uvr release
```

That's it. One CLI, one workflow file, one command to ship. See the [setup guide](/user-guide/01-getting-started) for the full walkthrough.
