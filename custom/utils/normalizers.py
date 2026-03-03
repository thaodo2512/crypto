"""Signal normalization utilities.

See docs/sub-specs/SS-01.md §Normalizers
"""

import numpy as np


def z_score(value: float, mean: float, std: float) -> float:
    """Compute z-score. Returns 0.0 when std is 0 to avoid division by zero.

    See docs/sub-specs/SS-01.md §Normalizers
    """
    if std == 0:
        return 0.0
    return (value - mean) / std


def clip_score(
    score: float, min_val: float = -1.0, max_val: float = 1.0
) -> float:
    """Clip score to [min_val, max_val] using numpy.clip().

    See docs/sub-specs/SS-01.md §Normalizers
    """
    return float(np.clip(score, min_val, max_val))


def normalize_range(value: float, min_val: float, max_val: float) -> float:
    """Map value from [min_val, max_val] to [-1.0, +1.0]. Midpoint maps to 0.

    Returns 0.0 when min_val == max_val to avoid division by zero.

    See docs/sub-specs/SS-01.md §Normalizers
    """
    if max_val == min_val:
        return 0.0
    return 2.0 * (value - min_val) / (max_val - min_val) - 1.0
