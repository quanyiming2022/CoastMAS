import { expect, it } from "vitest";
import { freshModel, prepareModelRevision } from "./model-editor";
import type { ModelSpec } from "./generated/contracts";

it("new metadata requires explicit identity and scale declarations before registration", () => {
  const draft = freshModel("owner", "2026-09-21T00:00:00Z");
  expect(draft.runtime_type).toBe("metadata");
  expect(draft.execution_status).toBe("NOT_EXECUTABLE");
  expect(draft.spatial_scale.unit).toBe("");
  expect(() =>
    prepareModelRevision(draft, null, "2026-09-21T00:00:01Z"),
  ).toThrow();
});
it("editing fixes the source identity and version, preserves zero and resets execution approval", () => {
  const source: ModelSpec = {
    ...freshModel("owner", "2026-09-21T00:00:00Z"),
    name: "Model",
    license: "MIT",
    display_name: "Model",
    spatial_scale: { unit: "m", minimum: null, maximum: null },
    temporal_scale: { unit: "s", minimum: null, maximum: null },
    runtime_type: "python",
    validation_status: "VALIDATED",
    execution_status: "EXECUTABLE",
    parameters: [
      {
        name: "threshold",
        unit: "m",
        minimum: 0,
        maximum: 10,
        default: 0,
        required: true,
      },
    ],
  };
  const edited = prepareModelRevision(
    { ...source, id: "spoof", version: 99 },
    source,
    "2026-09-21T00:00:02Z",
  );
  expect(edited.id).toBe(source.id);
  expect(edited.version).toBe(2);
  expect(edited.parameters[0]!.default).toBe(0);
  expect(edited.validation_status).toBe("UNVALIDATED");
  expect(edited.execution_status).toBe("NOT_EXECUTABLE");
  expect(source.validation_status).toBe("VALIDATED");
});
