import { expect, it } from "vitest";
import { freshSource, prepareSourceRevision } from "./source-editor";
import { contract } from "./contracts";
it("does not fabricate file identities or scientific coverage for a source template", () => {
  const draft = freshSource();
  expect(draft.output.crs).toBeNull();
  expect(draft.output.time_start).toBeNull();
  expect(draft.output).not.toHaveProperty("checksum");
  expect(draft.output).not.toHaveProperty("uri");
  expect(contract("DataSourceSpec").safeParse(draft).success).toBe(false);
});
it("pins source identity and increments the stored version", () => {
  const base = {
    ...freshSource(),
    name: "Source",
    connector_id: "approved",
    version: 3,
  };
  base.output = {
    ...base.output,
    name: "Data",
    source: "survey",
    license: "CC0",
  };
  const revision = prepareSourceRevision(
    { ...base, id: "spoof", version: 500 },
    base,
  );
  expect(revision.id).toBe(base.id);
  expect(revision.version).toBe(4);
});
