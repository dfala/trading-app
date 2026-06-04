import { NextResponse } from "next/server";

import { loadShadowHistory } from "@/lib/shadow-history";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  try {
    const payload = await loadShadowHistory();
    return NextResponse.json(payload);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Shadow history unavailable.";
    return NextResponse.json(
      { generated_at: new Date().toISOString(), source: "", models: [], error: message },
      { status: 500 },
    );
  }
}
