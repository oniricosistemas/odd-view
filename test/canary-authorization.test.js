import assert from "node:assert/strict";
import test from "node:test";

import { canReadArtifact } from "../src/canary-authorization.js";

test("canary authorization only allows the artifact owner", () => {
  assert.equal(canReadArtifact("owner-1", "owner-1"), true);
  assert.equal(canReadArtifact("owner-1", "owner-2"), false);
  assert.equal(canReadArtifact("owner-1", ""), false);
});
