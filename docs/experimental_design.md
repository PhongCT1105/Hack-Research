# Experimental Design

## 2×2 Factorial Conditions

| Condition | Writer receives evidence | Post-generation verification | Purpose |
|-----------|--------------------------|------------------------------|---------|
| **A** | No | No | Closed-book baseline |
| **B** | Yes | No | Effect of grounding during writing |
| **C** | No | Yes | Effect of correction after ungrounded writing |
| **D** | Yes | Yes | Combined safeguards |

The factorial design (vs. a three-condition design) isolates the **main effects** of
grounding and verification plus their **interaction** — it answers whether verification
can rescue ungrounded writing, whether grounding alone does most of the work, and
whether grounding makes verification more useful.

**The single most informative comparison is B vs C:**
- B beats C → evidence during generation matters more than repair after the fact.
- C beats B on errors but loses sharply on supported specificity → strong factuality–personalization trade-off result.
- D dominates both → evidence for complementarity.

## Generation Protocol

For each professor, generate emails per condition with **independent seeds** and
**identical output constraints**:

- Pilot: 12 professors × 4 conditions × 2 seeds = **96 emails**.
- The writing prompt is IDENTICAL across conditions except for the presence/absence of
  the evidence packet block.
- Model, temperature, output word limit, instructions, and sampling settings are held
  constant across conditions (see `config/config.yaml`).
- Scenario: a student writes to the professor expressing research interest (fixed
  persona defined in `prompts/writer_v1.md`; constant across all runs).

## Verification Protocol (Conditions C and D)

The verifier receives the evidence packet and the draft, then follows a
RARR/FLEEK-style **minimal-edit philosophy** — not free rewriting:

1. Extract research-related atomic claims from the draft.
2. Check each claim against the evidence packet.
3. **Preserve** supported claims (and their specificity) verbatim where possible.
4. **Soften** overstatements to what the evidence warrants.
5. **Remove or generalize** unsupported/contradicted claims.
6. Log every edit: type (delete / soften / rewrite / keep), original span, new span, reason.

Original and verified emails are stored separately; verifier edits are fully logged
(`VerifierEdit` records in the output schema).

## Controls and Confound Management

| Control | Rule |
|---|---|
| Prompt constancy | Only the evidence block differs between A/C and B/D writer prompts |
| Output budget | Same `max_tokens` and stated word limit in all conditions |
| Seeds | Independent seeds per generation; recorded in run manifest |
| Model roles | Different model families for writer / verifier / auto-evaluator when possible |
| Length confound (optional, subset) | Length-matched placebo context in condition A/C if resources allow |

## Pilot → Freeze Workflow

1. Dataset owner delivers first 2 professor packets (CS-01, PSY-01).
2. Pipeline runs the pilot: 2 professors × 4 conditions × 2 seeds = **16 emails**.
3. Whole team reviews against the checkpoint questions:
   - Does the evidence packet contain enough information?
   - Are research claims being split into atomic units correctly?
   - Are the four conditions meaningfully different?
   - Is the verifier deleting too much specific content?
   - Can human annotators apply the rubric consistently?
4. Fix issues, record decisions in `docs/decision_log.md`.
5. **FREEZE:** prompts, evidence schema, output schema, annotation rubric.
6. Scale to the full 96-email run. After freeze: bug fixes only, no method changes.
