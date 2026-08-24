---
name: Bug report
about: Something behaves differently from what the documentation or design says
title: ''
labels: bug
assignees: ''
---

<!--
Before filing: if this is a SECURITY issue, do not open an issue.
See SECURITY.md — report privately through GitHub Security Advisories.

Please do not paste your CV, real posting data, or the contents of .env.
Redact employer names if they identify you or someone else.
-->

## Which stage?

<!-- Tick one. If you are not sure, describe the symptom and leave them blank. -->

- [ ] **collect** — stage 1, querying boards via JobSpy
- [ ] **normalise** — stage 2, fingerprinting and deduplication
- [ ] **score** — stage 3 *(not yet implemented)*
- [ ] **publish** — stage 4 *(not yet implemented)*
- [ ] **web** — the triage interface
- [ ] **scheduler** / CLI / packaging
- [ ] **migrations** — schema or Alembic
- [ ] Documentation

## What happened

<!-- The observed behaviour. -->

## What you expected

<!-- And, if you can, what says it should behave that way — a design section,
     an ADR, the SRS, or the development guide. -->

## Reproduction

```
# The exact command, from app/
```

Steps:

1.
2.
3.

## Deduplication bugs only

<!-- Skip this section unless the bug is a wrong merge or a wrong split.
     This is the highest-value information you can give us. -->

- **Merged but shouldn't have** (a posting is being concealed — higher severity):

  | | Posting A | Posting B |
  |---|---|---|
  | Title | | |
  | Employer | | |
  | Location | | |
  | Source board | | |

- **Split but should have merged** (a duplicate is showing twice):

  <!-- Same table shape. -->

**Are these real captured strings from a board, or examples you typed?**
<!-- Real ones are much more useful — they become OBSERVED test fixtures. -->

## Logs / traceback

<details>
<summary>Output</summary>

```
```

</details>

## Environment

- OS:
- Python (`uv run python -V`):
- Running via: <!-- docker compose / host-side uv run -->
- Commit or branch:
- Board(s) involved: <!-- indeed / linkedin -->
