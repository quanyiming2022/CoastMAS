import { readFile, writeFile } from 'node:fs/promises';
import { compile } from 'json-schema-to-typescript';
const schema = JSON.parse(await readFile(new URL('../contracts.schema.json', import.meta.url), 'utf8'));
const result = await compile(schema, 'CoastMASContracts', {
  bannerComment: '/* Generated from Python public contracts. Do not edit manually. */',
  additionalProperties: false,
  style: { singleQuote: true, semi: true, tabWidth: 2 },
});
const target = new URL('../src/generated/contracts.ts', import.meta.url);
if (process.argv.includes('--check')) {
  if (await readFile(target, 'utf8') !== result) throw new Error('Generated TypeScript contracts are stale');
} else await writeFile(target, result);
