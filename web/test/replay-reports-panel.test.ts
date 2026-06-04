import { describe, expect, it } from "vitest";

import { reportMatchesSearchForTest } from "@/components/replay-reports-panel";
import type { ReplayReportSummary } from "@/lib/types";

describe("ReplayReportsPanel search", () => {
  it("matches report file names when users type spaces instead of separators", () => {
    const report: ReplayReportSummary = {
      id: "replay-discovery-20260601-sip-risk-managed-semis.md",
      title: "Replay Discovery Report",
      fileName: "replay-discovery-20260601-sip-risk-managed-semis.md",
      relativePath: "replay-discovery-20260601-sip-risk-managed-semis.md",
      kind: "comparison",
      updatedAt: "2026-06-01T19:19:00Z",
      sizeBytes: 123,
      tags: ["Comparison", "SIP"],
    };

    expect(reportMatchesSearchForTest(report, "risk-managed semis")).toBe(true);
    expect(reportMatchesSearchForTest(report, "risk managed semis")).toBe(true);
  });
});
