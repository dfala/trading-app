import { NextResponse } from "next/server";

import {
  chooseDefaultReplayReport,
  listReplayReports,
  readReplayReport,
} from "@/lib/replay-reports";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const requestedId = url.searchParams.get("id");
    const reports = await listReplayReports();
    const selectedReport = requestedId
      ? reports.find((report) => report.id === requestedId)
      : chooseDefaultReplayReport(reports);

    if (requestedId && !selectedReport) {
      return NextResponse.json(
        {
          reports,
          error: "Replay report not found.",
        },
        { status: 404 },
      );
    }

    const content = selectedReport
      ? await readReplayReport(selectedReport.id)
      : "";

    return NextResponse.json({
      reports,
      selectedId: selectedReport?.id,
      selectedReport,
      content,
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Replay reports unavailable.";
    return NextResponse.json({ reports: [], error: message }, { status: 500 });
  }
}
