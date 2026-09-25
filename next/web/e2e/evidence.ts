import { fileURLToPath } from "node:url";
import { join } from "node:path";
export const evidenceDirectory = process.env.COASTMAS_NEXT_EVIDENCE_DIR || fileURLToPath(
  new URL("../../artifacts/browser-evidence/", import.meta.url),
);
export const evidencePath = (name: string) => join(evidenceDirectory, name);
