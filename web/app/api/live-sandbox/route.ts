import { proxyBackend } from "@/lib/backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  return proxyBackend("/api/live-sandbox");
}
