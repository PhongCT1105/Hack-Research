# Expanded Benchmark Design

## Purpose and relationship to the experiment

This benchmark supports the existing 2 x 2 experiment on recipient-focused hallucinations in AI-generated professor outreach. It is designed to test whether a writer misrepresents a professor's research and whether two safeguards reduce those errors:

| Condition | Writer receives evidence | Post-generation verification |
|---|---:|---:|
| A | No | No |
| B | Yes | No |
| C | No | Yes |
| D | Yes | Yes |

The benchmark must measure both factual accuracy and useful personalization. A system does not succeed merely by deleting research-specific content.

### Dataset stages

The stages are cumulative, not replacements for one another.

**Pilot (preserved):** 12 professors, 3 broad domains, 4 conditions, 2 generations per condition, and 96 emails. Before the 96-email run, the existing design uses a 2-professor x 4-condition x 2-seed = 16-email checkpoint. The pilot validates evidence sufficiency, atomic claim extraction, annotation consistency, prompt behavior, verifier over-deletion, and output schemas. After sign-off, the prompt, runtime evidence schema, output schema, and annotation rubric are frozen as described in `docs/experimental_design.md`.

**Expanded benchmark (`benchmark-v1`):** approximately 100 professors, around 8 selected papers per professor, 2 focal papers per professor, and 2-4 selected passages per focal paper. At target size this yields about 800 selected paper records, 200 focal papers, and 400-800 full-text evidence passages. The expanded collection schemas in `schemas/` are versioned collection contracts; they do not silently retrofit the pilot.

## Design principles

1. Sample intentionally across risk-relevant dimensions rather than convenience, fame, or citation rank.
2. Store each construct separately. Visibility, popularity, complexity, breadth, coherence, synthesis difficulty, and evidence completeness are not interchangeable.
3. Treat automated scores as reproducible screening features, not objective measures of scholarly merit.
4. Require human review for faculty status, identity, focal evidence, topic coherence, and final synthesis-difficulty labels.
5. Use evidence-relative factuality. A claim absent from the packet is not automatically false in the world.
6. Keep source, transformed, selected, generated, annotation, and identity data in separate stages.

## Target population and primary margins

The final sample is selected from a larger verified pool by constrained stratified sampling. Exact matching of every intersection is neither required nor statistically realistic; the sampler minimizes deviation from all target margins while enforcing hard quality gates.

| Dimension | Target |
|---|---|
| Domain | 20 in each of 5 domains |
| Career stage | 35 early, 35 mid, 30 senior |
| Visibility | 35 lower, 35 medium, 30 higher |
| Research breadth | 30 narrow, 40 moderate, 30 broad |
| Aggregate paper complexity | 30 low, 40 medium, 30 high |
| Cross-paper synthesis difficulty | 30 low, 40 medium, 30 high |

The five domains are:

1. Computer science and engineering
2. Biomedical science and public health
3. Psychology and cognitive science
4. Physical and mathematical sciences
5. Social sciences, humanities, or interdisciplinary research

Each professor record stores the reviewed `domain`, `field`, `subfield`, `primary_topics`, and OpenAlex Topic IDs. OpenAlex Topics make the hierarchy reproducible, but a collector must correct obvious topic-classification errors and record the correction without altering raw API responses.

## Construct definitions

All continuous features are retained even when a tier is assigned. Unless stated otherwise, normalization occurs within a defensible comparison stratum, normally broad field and career stage for researcher metrics and broad field plus publication-year band for paper metrics. If a stratum is too small, pool upward to domain and record the fallback.

### Researcher visibility

**Question:** How likely is a model to have encountered the professor or their work?

Inputs include total citation count, h-index, works count, field-normalized citation percentile, and optional public-profile indicators recorded as separate features. The operational score is the mean of available percentile-ranked core inputs; missing components are not imputed silently, and `visibility_components_available` records the denominator.

Suggested sampling bands are lower (approximately 10th-40th percentile), medium (40th-75th), and higher (75th-95th). Avoid the extreme top 1-5%. Percentiles must be field- and career-normalized rather than based on universal citation cutoffs.

**Sources:** OpenAlex metrics and topic hierarchy; optional public profile indicators from documented public pages. **Human review:** verify the comparison stratum and investigate implausible outliers. **Limitation:** visibility is only a proxy for possible model familiarity or training-data exposure.

### Paper popularity

**Question:** How visible or influential is one paper, and how likely is model familiarity?

Store raw citation count, OpenAlex `cited_by_count`, field-normalized citation percentile, and year-normalized citation percentile. Popularity informs the two influential-paper slots and subgroup analysis. It is not paper complexity and is not a merit score.

Within each professor packet, target 3 recent papers, 2 influential papers, 2 topic- or method-diversifying papers, and 1 randomly selected eligible paper. One paper may satisfy multiple rationales, but every selected record has one primary `selection_reason` and any secondary reasons.

### Research breadth

**Question:** How widely do the selected papers span topics and subfields?

Store unique topic, subfield, and field counts; topic entropy; topic-cluster distribution; and a score. The v1 screening score is:

```text
0.35 * normalized topic entropy
+ 0.25 * normalized unique topic count
+ 0.20 * normalized unique subfield count
+ 0.10 * normalized unique field count
+ 0.10 * normalized topic-cluster balance
```

Assign narrow/moderate/broad tiers by candidate-pool percentiles chosen to approximate the 30/40/30 target. **Example:** eight papers in one NLP cluster may be narrow even if they use several datasets; papers spread across NLP, human-computer interaction, and education may be broad. **Limitation:** topic taxonomies can split or merge concepts unevenly across disciplines.

### Topic coherence

**Question:** Do the papers support a shared research agenda?

Store this separately from breadth. Automated aids include mean pairwise embedding similarity, within-cluster similarity, between-cluster distance, and cluster count. The final categorical label is human-reviewed:

- `high`: papers strongly support one shared agenda;
- `medium`: papers form multiple related clusters;
- `low`: papers form several weakly connected clusters.

The numeric `topic_coherence_score` runs from 0 (weak coherence) to 1 (strong coherence). A broad portfolio can still be coherent, and a narrow-looking topic assignment can hide low conceptual coherence. Low coherence may increase false cross-paper synthesis.

### Method diversity

**Question:** How many major method families and how balanced a mix appear across selected papers?

Use controlled tags such as theoretical analysis, deep learning, statistical modeling, simulation, randomized experiment, observational study, clinical study, survey research, qualitative interviews, and mixed methods. Store the tags, count, entropy, score, and tier.

```text
method_diversity_score =
  0.50 * normalized distinct method-family count
  + 0.50 * normalized method-family entropy
```

Assign low/medium/high tiers within the verified pool, aiming for a balanced mix. Human reviewers confirm method tags for focal papers and ambiguous abstracts.

### Paper complexity

**Question:** How difficult is the scientific content to describe precisely from the available text?

Complexity is an operational benchmark heuristic, not scientific merit, quality, impact, or popularity. Compute each component on a 0-100 normalized scale within field and publication-year bands, then use:

```text
paper_complexity_score =
  0.25 * technical_vocabulary_density
  + 0.20 * method_count
  + 0.15 * dataset_or_population_count
  + 0.15 * result_or_experiment_count
  + 0.15 * interdisciplinary_breadth
  + 0.10 * readability_difficulty
```

Also store distinct research-objective count and qualification/hedging density as diagnostic components. They are retained for analysis but are not weighted in v1 because the requested composite already sums to 100%. Complexity tiers are low/medium/high using candidate-pool percentiles that support the 30/40/30 professor-level target. The professor-level score is the mean score across the eight selected papers; retain the distribution so one complex focal paper is not hidden by an average.

Examples the benchmark must preserve include popular but technically simple, popular and technically complex, less cited but technically complex, and less cited and less complex papers.

### Cross-paper synthesis difficulty

**Question:** How difficult is it to summarize the portfolio without unsupported unification or overgeneralization?

The v1 automated screening score is:

```text
0.15 * topic_entropy
+ 0.15 * mean_semantic_distance
+ 0.10 * topic_cluster_count
+ 0.10 * method_diversity
+ 0.10 * dataset_or_population_diversity
+ 0.10 * temporal_research_evolution
+ 0.10 * cross_domain_breadth
+ 0.20 * inverse_topic_coherence
```

All inputs are normalized to 0-1 and stored individually. Provisional bands are low `[0, 0.33)`, medium `[0.33, 0.67)`, and high `[0.67, 1]`; candidate-pool percentile cut points may replace them if the raw distribution collapses, but the chosen cut points and version must be recorded.

- `low`: one clear topic and method family;
- `medium`: two or three related clusters;
- `high`: several topics, methods, time periods, or applications requiring careful qualification.

A human reviews the paper list, cluster summary, temporal trajectory, and proposed tier. The final label records reviewer, review date, and whether it differs from the automated tier. This is the central difficulty dimension, but it must not absorb the separate breadth, coherence, method, complexity, visibility, or evidence-completeness scores.

### Evidence completeness and ambiguity

**Question:** Can the packet fairly adjudicate likely outreach claims?

Evidence completeness measures coverage of the selected portfolio: usable abstracts, verified authorship, focal full text, passage coverage across objective/method/result/limitations, and provenance. Evidence ambiguity records conflicting metadata, vague source wording, or passage-level uncertainty. Neither is a property of the professor's research difficulty.

## Career stage

Prefer the official faculty title and faculty page. Store `faculty_title` independently from `career_stage`.

When official evidence does not establish a stage, use years since the first credible publication:

```text
academic_age_years = collection_year - first_publication_year
early: 0-8 publication years
mid: 9-18 publication years
senior: 19+ publication years
```

Set `career_stage_source` to `official_faculty_page` or `estimated_from_first_publication_year`. The fallback is an estimate, not verified academic rank. Career interruptions and field-specific publication norms are known limitations.

## Secondary dimensions

Collect, but do not force exact balance for: institution and OpenAlex/ROR IDs; institution type, country, region, and research visibility; faculty-page and publication language; collaboration complexity, average author count, unique collaborator count, and multi-institution rate; temporal publication span and research evolution; dataset/population diversity; paper popularity distribution; open-access availability; evidence completeness; and evidence ambiguity.

Do not infer sensitive demographic traits from names, photos, language, or location.

## Candidate and final paper selection

Build a 20-30-paper eligible pool per verified professor. For every candidate, compute recency, field/year citation percentile, topic cluster, method indicators, complexity components, open-access and abstract/full-text availability, representativeness, and diversity contribution.

Select approximately eight papers with a deterministic algorithm and human review:

1. Three most suitable recent papers, balancing recency with usable evidence.
2. Two influential papers by normalized popularity, not raw citations alone.
3. Two papers maximizing marginal topic or method coverage.
4. One uniformly random paper from remaining eligible works using the recorded seed.

Resolve duplicate slot assignments by moving to the next eligible paper in that slot. Two selected papers become focal papers, preferring legal full text, clear methods and results, topic representation, and low ownership ambiguity. Each focal paper contributes 2-4 short passages from objective/introduction, methods, results, and discussion/limitations as available.

## Constrained professor sampling

### Hard eligibility constraints

Every final professor must have:

- a confirmed current faculty or research role and official page;
- at least 8 eligible papers and 6 usable abstracts;
- 2 focal papers with usable legal full-text evidence;
- verified authorship for all selected papers;
- no unresolved OpenAlex author merge/split or material affiliation conflict;
- traceable sources for every evidence item.

### Objective

Let each target margin cell have target `t_j`, achieved count `a_j`, and importance weight `w_j`. Among hard-eligible candidates, select 100 records minimizing:

```text
sum_j w_j * abs(a_j - t_j) / max(t_j, 1)
```

Domain cells are hard targets when enough eligible candidates exist. Career, visibility, breadth, complexity, and synthesis cells are soft targets with equal default weights. Add a small penalty for geographic/institutional concentration and for selecting many candidates from the same institution. Use deterministic tie-breaking by seeded random rank, then professor ID. Record the seed, algorithm version, candidate-pool version, target and achieved distributions, all exclusions, and reasons.

No candidate is chosen because they are easy for a model to recognize. Extreme top-visibility researchers are excluded unless needed for a documented coverage reason.

## Evidence packets and experiment joins

Each final internal packet contains an anonymous professor ID; reviewed domain/field/subfield; verified profile summary; career and visibility metadata; separate benchmark-dimension scores; eight selected paper records; two focal-paper IDs; selected passages; provenance and reconciliation notes; and evidence completeness/ambiguity fields. The real identity mapping remains only in `data/private/professor_identity_map.csv`.

Generated emails join to the benchmark through:

```text
professor_id, condition, seed, writer_model, verifier_model,
prompt_version, evidence_packet_version, dataset_version
```

Atomic claims join through:

```text
email_id, professor_id, condition, claim_id, claim_type,
factuality_label, evidence_source_ids
```

Main factuality metrics are Severe Error Rate, unsupported-claim rate, contradiction rate, overstatement rate, and percentage of emails with at least one severe error. The existing project definition is preserved:

```text
Severe Error Rate = (unsupported + contradicted claims) / all judged factual claims
```

The main personalization metric is:

```text
Supported Personalization Density =
  supported research-specific claims / email words * 100
```

Verifier-preservation metrics include supported claims preserved, claims deleted, softened, or rewritten, edit distance, email-length change, and supported-specificity change.

## Analysis supported

The benchmark supports subgroup and interaction analyses including:

- whether hallucination rates vary by domain;
- whether lower-visibility professors produce more closed-book errors;
- whether grounding helps more for technically complex papers;
- whether verification helps more for high-synthesis-difficulty portfolios;
- whether broad, low-coherence portfolios produce more false cross-paper synthesis;
- whether method, result, impact, novelty, collaboration, and authorship claims respond differently;
- whether a verifier preserves supported specificity or mainly deletes specific content;
- whether paper popularity improves closed-book accuracy through possible model familiarity;
- whether research evolution increases incorrect statements about a professor's current agenda.

These are observational benchmark moderators. Correlations involving citation counts, institution type, location, visibility, or other metadata do not establish causality.

## Reproducibility and human review

For every collection release, preserve the configuration, seed, source retrieval dates, raw-response checksums, code version, algorithm versions, candidate-pool version, exclusions, target/achieved margins, and reviewer decisions. Raw data are append-only. Any correction produces a new transformed/final version with a changelog entry.

Human review is mandatory for faculty verification, author merge/split assessment, material metadata conflicts, focal-paper/passages, obvious topic errors, final topic coherence, final synthesis difficulty, and the first 10-professor go/no-go gate.
