import { readFile, writeFile } from 'node:fs/promises';
import { compile } from 'json-schema-to-typescript';
const schema = JSON.parse(await readFile(new URL('../contracts.schema.json', import.meta.url), 'utf8'));
// The compiler accepts draft-07 tuple items; validation keeps the original 2020-12 schema.
function compilerSchema(value) {
  if (Array.isArray(value)) return value.map(compilerSchema);
  if (value === null || typeof value !== 'object') return value;
  const converted = Object.fromEntries(Object.entries(value).map(([key, child]) => [key, compilerSchema(child)]));
  if (Array.isArray(value.prefixItems)) {
    converted.items = compilerSchema(value.prefixItems);
    converted.additionalItems = value.items === undefined ? true : compilerSchema(value.items);
    delete converted.prefixItems;
  }
  return converted;
}
const result = await compile(compilerSchema(schema), 'CoastMASContracts', {
  bannerComment: '/* Generated from Python public contracts. Do not edit manually. */',
  additionalProperties: false,
  style: { singleQuote: true, semi: true, tabWidth: 2 },
});
const target = new URL('../src/generated/contracts.ts', import.meta.url);
if (process.argv.includes('--check')) {
  if (await readFile(target, 'utf8') !== result) throw new Error('Generated TypeScript contracts are stale');
} else await writeFile(target, result);
