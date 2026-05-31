import assert from "node:assert/strict";
import { test } from "node:test";

import { GRAPH_COLOR_GROUPS, buildColorGroups } from "../src/lib/graphColorGroups";

test("GRAPH_COLOR_GROUPS covers the ten entity tags", () => {
  const tags = GRAPH_COLOR_GROUPS.map(([tag]) => tag);
  assert.deepEqual(tags, [
    "person", "project", "skill", "organization", "publication",
    "role", "achievement", "event", "institution", "category",
  ]);
});

test("buildColorGroups preserves unmanaged groups and replaces managed ones", () => {
  const existing = [
    { query: "tag:#custom", color: { a: 1, rgb: 1 } },
    { query: "tag:#person", color: { a: 1, rgb: 999 } },
  ];
  const result = buildColorGroups(existing);
  const custom = result.find((g) => g.query === "tag:#custom");
  const person = result.filter((g) => g.query === "tag:#person");
  assert.ok(custom, "keeps custom group");
  assert.equal(person.length, 1, "exactly one person group");
  assert.equal(person[0].color.rgb, 0x4895ef, "person uses managed color");
});
