# Annotation Instructions

## Goal

Determine whether research-related claims in AI-generated professor outreach emails are supported by the provided evidence.

## Annotation Process

For each email:

1. Find sentences that describe the professor's research.
2. Split those sentences into smaller atomic claims.
3. Identify the claim type.
4. Compare the claim with the evidence packet.
5. Assign a label.

## Labels

### Supported
The evidence directly supports the claim.

Example:
"Professor A studies medical imaging calibration."
Evidence:
Professor A's papers discuss medical imaging calibration.

### Partially Supported
The general idea is correct, but the claim is broader than the evidence.

Example:
"Professor A works on healthcare AI."
Evidence only shows AI calibration for chest X-rays.

### Overstated
The claim is based on real evidence but exaggerates importance, certainty, or impact.

Example:
"Professor A pioneered trustworthy AI."
Evidence only shows publications in trustworthy AI.

### Unsupported
The evidence packet should contain this information if true, but no evidence exists.

Example:
"Professor A collaborated with NASA."

### Contradicted
The claim conflicts with the evidence.

Example:
"Professor A uses clinical trials."
Evidence shows only observational studies.

### Outside Evidence Scope
The evidence packet cannot verify the claim.

Example:
"Professor A is an excellent mentor."

### Subjective Praise
Personal opinions or compliments without factual research information.

Example:
"Your research is fascinating."
