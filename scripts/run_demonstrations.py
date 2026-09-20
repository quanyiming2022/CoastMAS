"""Reproduce the scientific file calculations; not UI/E2E acceptance."""

import json
from datetime import UTC, datetime
from pathlib import Path

from coastmas.domain.samples import generate_samples
from coastmas.domain.scenarios import run_assessment_scenarios, run_screening_scenario

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    data = ROOT / "sample-data"
    if not (data / "manifest.json").exists():
        generate_samples(data)
    output = ROOT / "artifacts" / "research" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    for name, results in {
        "scenario-a": run_screening_scenario(data, increment=0.5),
        "scenarios-b-c": run_assessment_scenarios(data),
    }.items():
        (output / (name + ".json")).write_text(
            json.dumps(results, indent=2, allow_nan=False) + "\n"
        )
    print(
        json.dumps(
            {
                "scope": "scientific file calculations",
                "artifacts": str(output.relative_to(ROOT)),
                "e2e_acceptance": "NOT_RUN",
                "external_llm": "NOT_RUN",
            }
        )
    )


if __name__ == "__main__":
    main()
