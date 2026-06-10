import { NextResponse } from "next/server";

import { loadLiveSandboxHistory } from "@/lib/live-sandbox-history";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  try {
    const payload = await loadLiveSandboxHistory();
    return NextResponse.json(payload);
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : "Live sandbox history unavailable.";
    return NextResponse.json(
      {
        generated_at: new Date().toISOString(),
        source: "",
        points: [],
        error: message,
      },
      { status: 500 },
    );
  }
}
