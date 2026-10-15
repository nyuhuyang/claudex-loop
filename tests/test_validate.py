import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import validate  # noqa: E402


class PlanCheckboxTest(unittest.TestCase):
    def test_every_actionable_item_must_be_a_checkbox(self):
        plan = """# Plan
## Decisions
- plain bullet is fine here
## Acceptance Criteria
- [ ] boxed
1. numbered criterion
## Verification
```bash
- not a list item inside a fence
```
### Live
- [x] done
  - nested plain sub-step
## Progress Checklist
- [ ] step
## Risks
- plain again
"""
        errors = validate.plan_checkbox_errors(plan)
        self.assertEqual(len(errors), 2, errors)
        self.assertIn("line 6", errors[0])
        self.assertIn("line 13", errors[1])

    def test_fully_boxed_plan_passes(self):
        self.assertEqual(validate.plan_checkbox_errors(
            "## Progress Checklist\n- [ ] a\n  - [x] b\n## Notes\n- c\n"), [])


if __name__ == "__main__":
    unittest.main()
