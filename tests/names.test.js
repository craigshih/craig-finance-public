import assert from "node:assert/strict";
import { test } from "node:test";

import { cleanName } from "../functions/_lib/market.js";

test("股名去掉官方的「*」標記", () => {
  assert.equal(cleanName("國巨*"), "國巨");
  assert.equal(cleanName("91APP*-KY"), "91APP-KY");
  assert.equal(cleanName("台積電"), "台積電");
  assert.equal(cleanName(null), null);
});
