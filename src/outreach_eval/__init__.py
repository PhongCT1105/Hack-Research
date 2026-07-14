"""outreach_eval — claim-level factuality evaluation of AI-generated professor
outreach emails (2x2 grounding x verification study).

Module map:
- schemas: Pydantic contracts for packets, claims, edits, and output records
- llm: provider-agnostic LLM client (anthropic | openai | mock)
- conditions: the 2x2 condition logic
- generate: writer stage (conditions A-D)
- verify: evidence-based verification stage (conditions C/D)
- extract_claims: claim inventory for annotation
- io_utils: JSONL + run-manifest logging
"""

__version__ = "0.1.0"
