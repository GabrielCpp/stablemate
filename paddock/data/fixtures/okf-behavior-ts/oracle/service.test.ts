import assert from "node:assert/strict";
import { test } from "node:test";
import { dispatch } from "./service.ts";

type Case = {
  name: string;
  items: string[];
  sent: string[];
  limit: number;
  status: string;
  count: number;
  after: string[];
  error: string;
};

const cases: Case[] = [
  { name: "success", items: ["a", "b", "c"], sent: ["z"], limit: 2, status: "sent", count: 2, after: ["z", "a", "b"], error: "" },
  { name: "empty", items: [], sent: ["z"], limit: 2, status: "empty", count: 0, after: ["z"], error: "" },
  { name: "error", items: ["a"], sent: ["z"], limit: -1, status: "", count: 0, after: ["z"], error: "limit must be nonnegative" },
  { name: "empty-error", items: [], sent: ["z"], limit: -1, status: "", count: 0, after: ["z"], error: "limit must be nonnegative" },
  { name: "zero", items: ["a", "b"], sent: [], limit: 0, status: "sent", count: 0, after: [], error: "" },
  { name: "bounded", items: ["a", "b"], sent: [], limit: 5, status: "sent", count: 2, after: ["a", "b"], error: "" },
];

for (const tc of cases) {
  test(`dispatch contract/${tc.name}`, () => {
    const sent = [...tc.sent];
    if (tc.error) {
      assert.throws(() => dispatch(tc.items, sent, tc.limit), { name: "Error", message: tc.error });
    } else {
      const result = dispatch(tc.items, sent, tc.limit);
      assert.equal(result.status, tc.status);
      assert.equal(result.count, tc.count);
    }
    assert.deepEqual(sent, tc.after);
  });
}
