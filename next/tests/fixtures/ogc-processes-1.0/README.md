# OGC Processes 1.0 official schema fixtures

Downloaded read-only from https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/schemas/ . `sources.json` records each original URL and SHA-256; no original schema was patched. JSON Schema validation is offline. Only the implemented qualified-JSON input and document/reference asynchronous subset is claimed; passing these tests is not full Core conformance or OGC certification.

The published primitive input union overlaps `number`/`integer` and string/byte. The implemented process therefore describes a typed task-reference object and uses the standard qualified object representation. The test does not weaken the official union or relabel invalid primitive requests as compliant.
