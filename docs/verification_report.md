# Verification Report (Workstream 1 checks)

Automated checks run 2026-07-18 to support Phong's D004/D013 verification. These are
existence + attribution checks; a human spot-check that each OpenAlex author is the
*intended* individual is still worthwhile, but the mechanical checks below all pass.

## 1. Packet attribution (12/12 OK)

For each professor, every paper in the evidence packet was confirmed to be attributed to
the sampled OpenAlex author (packet `provenance.source_url` work IDs ⊆ the author's works,
looked up live via the OpenAlex API using the private identity map).

| Professor | Packet papers | Attributed to author |
|---|---|---|
| CS-01 … CS-04 | 8 each | 8/8 ✅ |
| PSY-01 … PSY-04 | 8 each | 8/8 ✅ |
| BIO-01 … BIO-04 | 8 each | 8/8 ✅ |

No misattributed papers. Packets remain **provisional** pending a human identity check.

## 2. Reference verification (13/13 resolve)

Every reference cited in `paper/FINAL_paper.md` resolves on arXiv (HTTP 200) with a title
matching its use:

| # | Ref | arXiv | Status |
|---|-----|-------|--------|
| 1 | Panza | 2407.10994 | ✅ |
| 2 | AuPEL | 2310.11593 | ✅ |
| 3 | Bulk-email field experiment | 2302.11156 | ✅ |
| 4 | When Personalization Misleads | 2601.11000 | ✅ |
| 5 | FActScore | 2305.14251 | ✅ |
| 6 | SciFact | 2004.14974 | ✅ |
| 7 | SciFact-Open | 2210.13777 | ✅ |
| 8 | RARR | 2210.08726 | ✅ |
| 9 | FLEEK | 2310.17119 | ✅ |
| 10 | SciFix | 2305.14707 | ✅ |
| 11 | AGREE | 2311.09533 | ✅ |
| 12 | ScholarCopilot | 2504.00824 | ✅ |
| 13 | OpenAlex | 2205.01833 | ✅ |

Author lists in the reference section are still best confirmed by hand before submission,
but all IDs and titles are valid.
