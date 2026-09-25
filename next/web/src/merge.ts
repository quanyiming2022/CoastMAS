import type { Draft } from "./draft";
export type Choice = "local" | "remote";
export type Conflict = {
  path: string;
  base: unknown;
  local: unknown;
  remote: unknown;
};
function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function ordered(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(ordered);
  if (object(value))
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, ordered(value[key])]),
    );
  return value;
}
export const equalDraftValue = (left: unknown, right: unknown) =>
  JSON.stringify(ordered(left)) === JSON.stringify(ordered(right));
export function mergeDrafts(
  base: Draft,
  local: Draft,
  remote: Draft,
  choices: Record<string, Choice> = {},
) {
  const conflicts: Conflict[] = [];
  function merge(
    previous: unknown,
    mine: unknown,
    theirs: unknown,
    path: string,
  ): unknown {
    if (equalDraftValue(mine, previous)) return theirs;
    if (equalDraftValue(theirs, previous) || equalDraftValue(mine, theirs))
      return mine;
    // Unit/bound/role and method assumptions are coupled. Never merge a scientific
    // group field-by-field simply because two edits touched different JSON keys.
    const atomic = ["/options", "/mapping", "/selection"].includes(path);
    if (!atomic && object(previous) && object(mine) && object(theirs)) {
      const result: Record<string, unknown> = {};
      for (const key of new Set([
        ...Object.keys(previous),
        ...Object.keys(mine),
        ...Object.keys(theirs),
      ])) {
        const value = merge(
          previous[key],
          mine[key],
          theirs[key],
          path + "/" + key.replaceAll("~", "~0").replaceAll("/", "~1"),
        );
        if (value !== undefined) result[key] = value;
      }
      return result;
    }
    if (choices[path]) return choices[path] === "local" ? mine : theirs;
    conflicts.push({ path, base: previous, local: mine, remote: theirs });
    return mine;
  }
  return { draft: merge(base, local, remote, "") as Draft, conflicts };
}
