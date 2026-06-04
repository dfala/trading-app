import { proxyBackend } from "@/lib/backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const params = new URLSearchParams();
  const modelKey = url.searchParams.get("model_key") ?? "";
  const universeId = url.searchParams.get("universe_id");
  params.set("model_key", modelKey);
  if (universeId) {
    params.set("universe_id", universeId);
  }
  return proxyBackend(`/api/model-performance?${params.toString()}`);
}
