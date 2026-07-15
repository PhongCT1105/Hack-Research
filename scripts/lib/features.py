"""Deterministic lexical features for paper-complexity scoring."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence
import unicodedata


PAPER_FEATURES_VERSION = "paper-features-v1"

# Tuples keep matching and serialized audit output stable across Python processes. These
# controlled indicators are deliberately compact: they are benchmark heuristics, not a
# discipline-independent scientific ontology.
CONTROLLED_KEYWORDS = MappingProxyType(
    {
        "technical_vocabulary": (
            "algorithm",
            "accuracy",
            "bayesian",
            "benchmark",
            "benchmarks",
            "classification",
            "cohort",
            "cohorts",
            "corpus",
            "corpora",
            "dataset",
            "datasets",
            "embedding",
            "experiment",
            "experiments",
            "hypothesis",
            "inference",
            "intervention",
            "model",
            "models",
            "neural network",
            "optimization",
            "participant",
            "participants",
            "population",
            "populations",
            "randomized trial",
            "regression",
            "simulation",
            "statistical",
            "survey",
            "surveys",
        ),
        "method": (
            "algorithm",
            "analysis",
            "bayesian",
            "case study",
            "experiment",
            "experiments",
            "interview",
            "interviews",
            "method",
            "methods",
            "model",
            "models",
            "neural network",
            "qualitative",
            "quantitative",
            "randomized trial",
            "randomised trial",
            "regression",
            "simulation",
            "survey",
            "surveys",
        ),
        "dataset_or_population": (
            "benchmark",
            "benchmarks",
            "cohort",
            "cohorts",
            "corpus",
            "corpora",
            "database",
            "databases",
            "dataset",
            "datasets",
            "patient",
            "patients",
            "participant",
            "participants",
            "population",
            "populations",
            "respondent",
            "respondents",
            "sample",
            "samples",
            "student",
            "students",
        ),
        "result_or_experiment": (
            "accuracy",
            "effect",
            "effects",
            "evidence",
            "experiment",
            "experiments",
            "finding",
            "findings",
            "improved",
            "outcome",
            "outcomes",
            "result",
            "results",
            "significant",
            "significantly",
        ),
        "research_objective": (
            "aim",
            "aims",
            "evaluate",
            "evaluates",
            "examine",
            "examines",
            "hypothesize",
            "hypothesise",
            "investigate",
            "investigates",
            "objective",
            "we propose",
            "we study",
            "we test",
        ),
        "qualification_or_hedging": (
            "although",
            "appear",
            "appears",
            "approximately",
            "could",
            "however",
            "likely",
            "limitation",
            "limitations",
            "limited",
            "may",
            "might",
            "perhaps",
            "possible",
            "possibly",
            "suggest",
            "suggests",
        ),
    }
)

_WORD_RE = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", re.UNICODE)
_SENTENCE_RE = re.compile(r"[.!?]+(?:[\"'’”)}\]]+)?(?=\s|$)", re.UNICODE)
_VOWEL_GROUP_RE = re.compile(r"[aeiouy]+")


@dataclass(frozen=True)
class ComplexityComponents:
    """Normalized weighted components plus unweighted diagnostic components."""

    technical_vocabulary_density: float | None
    method_count: float | None
    dataset_or_population_count: float | None
    result_or_experiment_count: float | None
    interdisciplinary_breadth: float | None
    readability_difficulty: float | None
    research_objective_count: float | None
    qualification_hedging_density: float | None

    @property
    def dataset_population_count(self) -> float | None:
        """Schema-compatible alias for the documented component name."""

        return self.dataset_or_population_count

    @property
    def result_experiment_count(self) -> float | None:
        """Schema-compatible alias for the documented component name."""

        return self.result_or_experiment_count


@dataclass(frozen=True)
class PaperFeatures:
    """Raw, auditable lexical measurements for one paper text."""

    available: bool
    word_count: int | None
    sentence_count: int | None
    syllable_count: int | None
    technical_vocabulary_count: int | None
    technical_vocabulary_density: float | None
    method_count: int | None
    dataset_or_population_count: int | None
    result_or_experiment_count: int | None
    interdisciplinary_breadth: int | None
    readability_difficulty: float | None
    research_objective_count: int | None
    qualification_hedging_count: int | None
    qualification_hedging_density: float | None
    method_indicators: tuple[str, ...] = ()
    dataset_or_population_indicators: tuple[str, ...] = ()
    result_or_experiment_indicators: tuple[str, ...] = ()
    research_objective_indicators: tuple[str, ...] = ()
    qualification_hedging_indicators: tuple[str, ...] = ()


def extract_paper_features(
    text: str | None, topics: Sequence[Mapping[str, Any]] | None
) -> PaperFeatures:
    """Extract deterministic counts and densities without external NLP dependencies."""

    if text is None or not text.strip():
        return PaperFeatures(
            available=False,
            word_count=None,
            sentence_count=None,
            syllable_count=None,
            technical_vocabulary_count=None,
            technical_vocabulary_density=None,
            method_count=None,
            dataset_or_population_count=None,
            result_or_experiment_count=None,
            interdisciplinary_breadth=None,
            readability_difficulty=None,
            research_objective_count=None,
            qualification_hedging_count=None,
            qualification_hedging_density=None,
        )

    normalized_text = unicodedata.normalize("NFKC", text).casefold()
    tokens = tuple(_WORD_RE.findall(normalized_text))
    if not tokens:
        return extract_paper_features(None, topics)

    sentence_count = max(1, len(_SENTENCE_RE.findall(normalized_text)))
    syllable_count = sum(_syllable_count(token) for token in tokens)
    technical_vocabulary_count = _keyword_occurrence_count(
        tokens, CONTROLLED_KEYWORDS["technical_vocabulary"]
    )
    method_indicators = _matched_indicators(tokens, CONTROLLED_KEYWORDS["method"])
    dataset_indicators = _matched_indicators(tokens, CONTROLLED_KEYWORDS["dataset_or_population"])
    result_indicators = _matched_indicators(tokens, CONTROLLED_KEYWORDS["result_or_experiment"])
    objective_indicators = _matched_indicators(tokens, CONTROLLED_KEYWORDS["research_objective"])
    hedging_indicators = _matched_indicators(
        tokens, CONTROLLED_KEYWORDS["qualification_or_hedging"]
    )
    word_count = len(tokens)
    hedging_count = _keyword_occurrence_count(
        tokens, CONTROLLED_KEYWORDS["qualification_or_hedging"]
    )

    return PaperFeatures(
        available=True,
        word_count=word_count,
        sentence_count=sentence_count,
        syllable_count=syllable_count,
        technical_vocabulary_count=technical_vocabulary_count,
        technical_vocabulary_density=100.0 * technical_vocabulary_count / word_count,
        method_count=len(method_indicators),
        dataset_or_population_count=len(dataset_indicators),
        result_or_experiment_count=len(result_indicators),
        interdisciplinary_breadth=_topic_breadth(topics),
        readability_difficulty=_flesch_kincaid_grade(word_count, sentence_count, syllable_count),
        research_objective_count=len(objective_indicators),
        qualification_hedging_count=hedging_count,
        qualification_hedging_density=100.0 * hedging_count / word_count,
        method_indicators=method_indicators,
        dataset_or_population_indicators=dataset_indicators,
        result_or_experiment_indicators=result_indicators,
        research_objective_indicators=objective_indicators,
        qualification_hedging_indicators=hedging_indicators,
    )


def percentile_rank(
    value: float | int | None, values: Sequence[float | int | None]
) -> float | None:
    """Return a 0-100 midrank percentile, assigning tied values the same rank."""

    if value is None:
        return None
    numeric_value = _finite_number(value, "value")
    numeric_values = [
        _finite_number(candidate, "values") for candidate in values if candidate is not None
    ]
    if not numeric_values:
        return None
    below = sum(candidate < numeric_value for candidate in numeric_values)
    equal = sum(candidate == numeric_value for candidate in numeric_values)
    return 100.0 * (below + 0.5 * equal) / len(numeric_values)


def score_paper_complexity(components: ComplexityComponents) -> float | None:
    """Apply the documented v1 weights; diagnostics and popularity are unweighted."""

    weighted = (
        (components.technical_vocabulary_density, 0.25),
        (components.method_count, 0.20),
        (components.dataset_or_population_count, 0.15),
        (components.result_or_experiment_count, 0.15),
        (components.interdisciplinary_breadth, 0.15),
        (components.readability_difficulty, 0.10),
    )
    if any(value is None for value, _ in weighted):
        return None
    return sum(_score_component(value) * weight for value, weight in weighted)


def _score_component(value: float | None) -> float:
    assert value is not None
    numeric = _finite_number(value, "complexity component")
    if not 0.0 <= numeric <= 100.0:
        raise ValueError("normalized complexity components must be between 0 and 100")
    return numeric


def _finite_number(value: float | int, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must contain only numeric values")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{label} must contain only finite values")
    return numeric


def _matched_indicators(tokens: tuple[str, ...], indicators: Sequence[str]) -> tuple[str, ...]:
    return tuple(indicator for indicator in indicators if _phrase_count(tokens, indicator) > 0)


def _keyword_occurrence_count(tokens: tuple[str, ...], indicators: Sequence[str]) -> int:
    return sum(_phrase_count(tokens, indicator) for indicator in indicators)


def _phrase_count(tokens: tuple[str, ...], phrase: str) -> int:
    phrase_tokens = tuple(_WORD_RE.findall(phrase.casefold()))
    width = len(phrase_tokens)
    if width == 0 or width > len(tokens):
        return 0
    return sum(
        tokens[index : index + width] == phrase_tokens for index in range(len(tokens) - width + 1)
    )


def _syllable_count(token: str) -> int:
    ascii_token = "".join(
        character
        for character in unicodedata.normalize("NFKD", token)
        if not unicodedata.combining(character)
    )
    letters = "".join(character for character in ascii_token if character.isalpha()).casefold()
    if not letters:
        return 1
    groups = len(_VOWEL_GROUP_RE.findall(letters))
    if letters.endswith("e") and not letters.endswith(("le", "ye")) and groups > 1:
        groups -= 1
    return max(1, groups)


def _flesch_kincaid_grade(words: int, sentences: int, syllables: int) -> float:
    grade = 0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59
    return max(0.0, grade)


def _topic_breadth(topics: Sequence[Mapping[str, Any]] | None) -> int:
    if not topics:
        return 0
    for key in ("domain", "field", "topic_id", "topic", "display_name"):
        values = {
            normalized
            for topic in topics
            if isinstance(topic, Mapping)
            and (normalized := _topic_value(topic.get(key))) is not None
        }
        if values:
            return len(values)
    return 0


def _topic_value(value: Any) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("display_name") or value.get("name") or value.get("id")
    if not isinstance(value, str) or not value.strip():
        return None
    return unicodedata.normalize("NFKC", value).strip().casefold()
