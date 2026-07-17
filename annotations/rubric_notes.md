# Rubric Notes

These notes record clarification decisions made before pilot annotation. They are intended to improve consistency between annotators.

## 1. Unsupported vs Outside Evidence Scope

A missing piece of evidence does not automatically mean a claim is unsupported.

Use:

- Unsupported:
The claim is the type of information the evidence packet should contain, but no supporting evidence exists.

Example:
"Professor A created a new dataset for medical AI."
No paper/profile mentions this.

- Outside Evidence Scope:
The evidence packet cannot reasonably verify the claim.

Example:
"Professor A is an excellent mentor."
"Professor A is a generous colleague."

These should not enter the factuality denominator.

---

## 2. Partially Supported vs Overstated

These labels are related but different.

Partially Supported:
The central idea is correct, but the claim is broader than the evidence.

Example:
Evidence:
Professor studies calibration in medical imaging.

Claim:
"Professor studies trustworthy AI in healthcare."

The direction is correct, but the scope is wider.

Overstated:
The claim adds excessive certainty, importance, impact, or achievement.

Example:
Evidence:
A paper improves performance on one benchmark.

Claim:
"Professor A revolutionized AI reliability."

---

## 3. Contradicted Requires Direct Evidence

Do not use contradicted just because evidence is missing.

Contradicted requires the packet to show the opposite.

Example:

Evidence:
"The study uses observational data."

Claim:
"The study uses randomized controlled trials."

Label:
Contradicted.

---

## 4. Atomic Claims

Sentences containing multiple factual statements should be split.

Example:

"Your research develops NLP systems and you collaborate with Google."

Split into:

1. Professor develops NLP systems.
2. Professor collaborates with Google.

Each receives its own label.

---

## 5. Novelty Claims

Claims involving:

- first
- pioneered
- invented
- revolutionary
- groundbreaking
- unique

require explicit evidence.

A professor working in an area does not prove they pioneered it.

---

## 6. Causal Claims

Do not confuse correlation with causation.

Example:

Supported:
"The experiment increased retention."

Only if the study design supports causal inference.

Overstated:
"The model improves healthcare outcomes."

When the evidence only shows improved benchmark performance.

---

## 7. Cross-Paper Synthesis

Broad research themes require multiple supporting papers.

Example:

Supported:
"Across several papers, Professor A studies AI reliability in healthcare."

Only if multiple papers support this theme.

Overstated:
"Professor A developed a complete theory of trustworthy AI."

Based only on a few related papers.
