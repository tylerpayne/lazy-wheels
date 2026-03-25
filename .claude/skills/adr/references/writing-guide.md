# Writing Good ADR Content

An ADR is an executive summary and a verdict, not a novel. It should be brief enough that people actually read it, assertive enough that the decision is clear, and honest enough that trade-offs are visible.

## Title

Name the decision, not the problem. Use a verb phrase that makes the outcome clear.

- Bad: "Database choice"
- Good: "Use PostgreSQL for persistent storage"

A reader should know what was decided from the title alone.

## Context and Problem Statement

State what forced the decision. What changed, broke, or became necessary? End with the question being answered. Two to three sentences — no more. If you need more, the scope is too broad; split into multiple ADRs.

Use domain vocabulary and reference specific requirements, constraints, or incidents. Don't manufacture false urgency — if there's no real forcing function, question whether you need the ADR yet.

## Decision Drivers

These are the constraints and forces that shaped the decision — not a wishlist of nice-to-haves. Each driver should actually discriminate between the options. If a driver is equally true for all options, it doesn't belong here.

Prioritize operational qualities (observability, maintainability, ability to react) over speculative long-term goals ("future scalability for workloads we don't have").

## Considered Options

Include only options that were genuinely considered — at least two. Each option should be a real contender that a reasonable person might pick.

**Anti-pattern: Dummy Alternative.** Don't pad with strawmen to make the chosen option look better. If you can't articulate a genuine upside of an alternative, it shouldn't be listed.

**Anti-pattern: Sprint.** Don't consider only one option and rush to a conclusion. Search for alternatives — check existing projects, community practices, or ask colleagues. Report on the search even if you end up where you started.

## Decision Outcome

Lead with which option was chosen and why in one sentence. The "because" clause should reference specific decision drivers — this closes the loop between the problem and the solution.

**State your confidence level.** It's fine to say "we believe this is the right choice given current information but plan to revisit after X." Honesty about uncertainty is more useful than false confidence.

### Consequences

Be honest about trade-offs. Every decision has downsides; listing only positives signals that the analysis was shallow.

**Anti-pattern: Fairy Tale.** "We chose X because it does X" is circular. The justification must explain why X's properties matter for _this_ project's constraints.

**Anti-pattern: Free Lunch.** Ignoring difficult or long-term consequences. If you chose an event-driven architecture for decoupling, acknowledge the schema coupling and operational complexity it introduces.

The "Bad" consequences are the most valuable part — they tell future readers what to watch for and when to revisit the decision.

## Comparing Options

Use a **comparison table** with shared features as rows and options as columns. This forces you to evaluate each option against the same criteria, making the reasoning transparent and comparable.

Don't write separate pro/con lists per option — they become disconnected lists where the reader can't tell how options relate to each other.

```markdown
| Feature | Option A | Option B | Option C |
|---|---|---|---|
| Criterion 1 | How A does on this | How B does | How C does |
| Criterion 2 | ... | ... | ... |
```

The rows should map back to your decision drivers. If a criterion doesn't relate to a driver, question whether it matters.

**Anti-pattern: Pseudo-accuracy.** Don't use quantitative weighted scoring (e.g., "4x vendor independence + 3x licensing / 2 = 7.3") — the numbers are fabricated precision that obscure subjective judgment. Use the table to make qualitative trade-offs visible, not to hide them behind arithmetic.

## Staging Decisions

When no simple answer exists, decide in stages: short-term compromise, mid-term solution, and long-term vision. Document the current stage and plan to revisit. This is better than deferring the decision entirely or pretending the short-term choice is permanent.

## Style

- **Write for the future reader who wasn't in the room.** They need to understand _why_, not just _what_. The code shows what was built; the ADR explains why this path was chosen over the alternatives.
- **Be concrete.** "Better performance" means nothing. "Reduces cold-start latency from 3s to 200ms" means everything.
- **Be brief.** Size the ADR to the decision. Sometimes a few sentences suffice. More complex problems may need a page. Multi-page ADRs are a smell — move detail design to a separate document.
- **Be assertive and factual.** An ADR is a verdict, not a blog post. No sarcasm, no vendor bashing, no sales language. Avoid exaggerations — check every adjective and adverb for whether it can be backed with evidence.
- **One decision per ADR.** If you find yourself writing "and we also decided...", stop and create a second ADR.
- **Don't fabricate trade-offs.** If there are no real downsides, say so — but be suspicious.
- **Omit optional sections that add no signal.** The "More Information" section is optional — skip it if there's nothing to add.
- **Acknowledge bias.** If personal experience or team familiarity influenced the decision, say so. "The team has deep experience with X" is a legitimate factor — but it should be stated, not hidden.
