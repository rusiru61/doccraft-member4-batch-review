from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class ScoreWeights:
    ocr: float
    ai: float
    validation: float


def default_weights() -> ScoreWeights:
    return ScoreWeights(settings.weight_ocr, settings.weight_ai, settings.weight_validation)


def _check_range(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1, got {value}")


def calculate_reliability_score(
    ocr_confidence: float | None,
    ai_confidence: float | None,
    validation_passed: bool,
    weights: ScoreWeights | None = None,
) -> float:
    """Weighted reliability score between 0 and 1.

    OCR and AI confidence are both optional. A missing one is left out and the
    remaining weights are rescaled, so the score stays on the same 0-1 scale.
    """
    weights = weights or default_weights()
    parts = [(weights.validation, 1.0 if validation_passed else 0.0)]
    if ai_confidence is not None:
        _check_range("ai_confidence", ai_confidence)
        parts.append((weights.ai, ai_confidence))
    if ocr_confidence is not None:
        _check_range("ocr_confidence", ocr_confidence)
        parts.append((weights.ocr, ocr_confidence))

    total_weight = sum(w for w, _ in parts)
    score = sum(w * v for w, v in parts) / total_weight
    return round(score, 4)