import assert from "node:assert/strict";
import { test } from "node:test";

import { DAILY_LIMIT, GUEST_DAILY_TOKENS, guestBlocked } from "../functions/_lib/robot.js";

test("訪客每天題數上限", () => {
  assert.equal(guestBlocked({ mine: DAILY_LIMIT - 1, tokens: 0 }), null);
  assert.match(guestBlocked({ mine: DAILY_LIMIT, tokens: 0 }), /每人每天最多 10 題/);
});

test("全體訪客 token 用完就停，額度留給站長；可用環境變數調整", () => {
  assert.match(guestBlocked({ mine: 0, tokens: GUEST_DAILY_TOKENS }), /留一些給站長/);
  assert.equal(guestBlocked({ mine: 0, tokens: GUEST_DAILY_TOKENS }, { ROBOT_DAILY_TOKENS: "200000" }), null);
});
