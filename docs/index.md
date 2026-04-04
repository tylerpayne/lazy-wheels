---
layout: home

hero:
  name: uv-release
  tagline: <span>Release management for <a href="https://github.com/astral-sh/uv">uv</a> workspaces. Bump, build, and release only what changed. You manage major/minor versions, uvr manages the rest.</span>
  actions:
    - theme: brand
      text: Get Started
      link: /user-guide/01-setup
    - theme: alt
      text: Go Under the Hood
      link: /under-the-hood/

features:
  - title: 🔄 Bump
    details: "<code class=\"brand-code\">uvr bump</code><br>You own major and minor versions. uvr manages patch bumps, dev suffixes, and pre-release cycles. Dependency pins update automatically."
    link: /user-guide/03-bumping
  - title: 🔨 Build
    details: "<code class=\"brand-code\">uvr build</code><br>Cross-platform build matrix with topologically-sorted parallel builds. Change detection rebuilds only what's needed."
    link: /user-guide/04-building
  - title: 📦 Release
    details: "<code class=\"brand-code\">uvr release</code><br>One GitHub release per package with auto-generated notes. Plan locally, execute on CI. Install wheels directly from releases."
    link: /user-guide/05-releasing
  - title: 🤖 Claude
    details: "<code class=\"brand-code\">/release</code><br>Ship with the /release skill. Claude reads your workspace, runs uvr, and handles the entire release flow interactively."
    link: /user-guide/01-setup
---

## Quick Start

Install uv-release and scaffold your first workflow:

```bash
uv add --dev uv-release
uvr workflow init
```

Check what would be released:

```bash
uvr release --dry-run
```

Release changed packages — generates a plan, prompts for confirmation, and dispatches to GitHub Actions:

```bash
uvr release
```

That's it. One CLI, one workflow file, one command to ship. See the [setup guide](/user-guide/01-setup) for the full walkthrough.
