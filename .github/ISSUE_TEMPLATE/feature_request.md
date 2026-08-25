---
name: Feature request
about: Propose a capability or a change in behaviour
title: ''
labels: enhancement
assignees: ''
---

<!--
Check first whether this is already specified but unbuilt:
  - Stages 3 (score) and 4 (publish) are specified and pending.
  - Docs/README.md indexes the design record, the SRS, and the ADRs.
  - specs/ holds in-progress feature specifications.
If it is already specified, say so and link it rather than re-describing it.
-->

## Which area?

- [ ] **collect** — stage 1, boards and collection
- [ ] **normalise** — stage 2, fingerprinting and deduplication
- [ ] **score** — stage 3
- [ ] **publish** — stage 4
- [ ] **web** — the triage interface
- [ ] **reports**
- [ ] CLI / scheduler / packaging
- [ ] Documentation

## The problem

<!-- What is hard or impossible today? Describe the situation, not the solution.
     A feature request that opens with an implementation is hard to evaluate. -->

## The proposal

<!-- What should happen instead. -->

## Alternatives considered

<!-- Including doing nothing. If an existing setting or the UI nearly does this,
     say what falls short. -->

---

## Design impact

<!-- Answer these honestly; "I don't know" is a fine answer and we will work it
     out in the thread. They determine how much process this needs. -->

**Does it change the dependency direction?**
<!-- config ← everything; collect/normalise pure with no DB; pipeline the only
     writer; web never writes pipeline data. A change here needs an ADR. -->

- [ ] No
- [ ] Yes — and I understand this needs an ADR

**Does it need a schema change / migration?**

- [ ] No
- [ ] Yes

**Does it affect deduplication?**

- [ ] No
- [ ] Yes — and I have thought about the merge/split asymmetry below

<!-- If yes: a false merge conceals a posting; a false split merely repeats one.
     Which direction does this change push, and what stops it merging things
     that should stay separate? -->

**Does it send data off the machine?**
<!-- The project's core constraint is that nothing leaves the operator's
     hardware. A feature requiring a hosted API is a fundamental change and
     needs an ADR arguing for it explicitly. -->

- [ ] No
- [ ] Yes — and I understand this contradicts a core project constraint

**Does it need an ADR?**
<!-- See CONTRIBUTING.md, "Architecture Decision Records". -->

- [ ] No — behaviour-preserving, or a small addition
- [ ] Yes
- [ ] Not sure — please advise
