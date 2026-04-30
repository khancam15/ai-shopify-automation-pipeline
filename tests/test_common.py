from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from common import extract_checklist


def test_extract_checklist_parses_all_weeks() -> None:
    guide = """
## Week 1 - Setup
1. Create first listing
2. Add shop policies
Free Tool: Canva

## Week 2 - Expansion
- Draft 3 more listings
- Improve product photos

## Week 3 - Traffic
1. Create Pinterest board
2. Post Instagram reel

## Week 4 - Optimization
1. Review analytics
2. Update tags
"""
    result = extract_checklist(guide)

    assert len(result["week_1"]) == 2
    assert result["week_1"][0]["status"] == "pending"
    assert "Create first listing" in result["week_1"][0]["task"]
    assert len(result["week_2"]) == 2
    assert len(result["week_3"]) == 2
    assert len(result["week_4"]) == 2


def test_extract_checklist_raises_when_missing_weeks() -> None:
    guide = "No weekly sections available"

    try:
        extract_checklist(guide)
    except ValueError as exc:
        assert "No checklist tasks could be extracted" in str(exc)
    else:
        raise AssertionError("Expected extract_checklist to raise ValueError")
