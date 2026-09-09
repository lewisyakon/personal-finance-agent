from pathlib import Path

import pytest


@pytest.fixture
def sample_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "datasets" / "sanitized_samples"

