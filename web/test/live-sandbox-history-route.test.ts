import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { GET as getLiveSandboxHistory } from "@/app/api/live-sandbox-history/route";
import { liveSandboxJournalPath } from "@/lib/live-sandbox-history";

describe("live sandbox history route", () => {
  let dir: string | undefined;

  afterEach(async () => {
    delete process.env.TRADING_APP_LIVE_SANDBOX_JOURNAL;
    if (dir) {
      await rm(dir, { force: true, recursive: true });
      dir = undefined;
    }
  });

  it("pivots the cycle journal into a sorted equity series", async () => {
    dir = await mkdtemp(path.join(tmpdir(), "live-sandbox-"));
    const journal = path.join(dir, "live-sandbox-cycles.jsonl");
    process.env.TRADING_APP_LIVE_SANDBOX_JOURNAL = journal;
    await writeFile(
      journal,
      [
        JSON.stringify({
          as_of: "2026-06-08T16:06:38Z",
          sandbox_equity: "100",
          cap_deployed: "0",
          sandbox_cash: "100",
        }),
        "not valid json", // malformed line is skipped, not fatal
        JSON.stringify({
          as_of: "2026-06-08T22:35:34Z",
          sandbox_equity: "99.85",
          cap_deployed: "99.35",
          sandbox_cash: "0.50",
        }),
        // out-of-order line is sorted back into place
        JSON.stringify({
          as_of: "2026-06-08T20:00:00Z",
          sandbox_equity: "99.9",
          cap_deployed: "99.4",
          sandbox_cash: "0.5",
        }),
        "",
      ].join("\n"),
    );

    const response = await getLiveSandboxHistory();
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.points).toHaveLength(3);
    expect(payload.points.map((point: { as_of: string }) => point.as_of)).toEqual([
      "2026-06-08T16:06:38Z",
      "2026-06-08T20:00:00Z",
      "2026-06-08T22:35:34Z",
    ]);
    expect(payload.points[2]).toMatchObject({
      equity: 99.85,
      deployed: 99.35,
      cash: 0.5,
    });
  });

  it("dedupes records that share a timestamp, keeping the last", async () => {
    dir = await mkdtemp(path.join(tmpdir(), "live-sandbox-"));
    const journal = path.join(dir, "live-sandbox-cycles.jsonl");
    process.env.TRADING_APP_LIVE_SANDBOX_JOURNAL = journal;
    await writeFile(
      journal,
      [
        JSON.stringify({ as_of: "2026-06-08T20:00:00Z", sandbox_equity: "99.9" }),
        JSON.stringify({ as_of: "2026-06-08T20:00:00Z", sandbox_equity: "99.95" }),
      ].join("\n"),
    );

    const response = await getLiveSandboxHistory();
    const payload = await response.json();

    expect(payload.points).toHaveLength(1);
    expect(payload.points[0].equity).toBe(99.95);
  });

  it("returns an empty series when the journal is missing", async () => {
    dir = await mkdtemp(path.join(tmpdir(), "live-sandbox-"));
    process.env.TRADING_APP_LIVE_SANDBOX_JOURNAL = path.join(dir, "missing.jsonl");

    const response = await getLiveSandboxHistory();
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.points).toEqual([]);
  });

  it("defaults the journal under the app data directory", () => {
    expect(liveSandboxJournalPath()).toBe(
      path.join(
        process.cwd(),
        "data",
        "runtime",
        "journal",
        "live-sandbox-cycles.jsonl",
      ),
    );
  });
});
