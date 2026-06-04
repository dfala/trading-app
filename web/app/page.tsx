import { DashboardClient } from "@/components/dashboard-client";
import { backendBaseUrl } from "@/lib/backend";
import type { DashboardSnapshot } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function Page() {
  const initialSnapshot = await loadInitialSnapshot();
  return <DashboardClient initialSnapshot={initialSnapshot} />;
}

async function loadInitialSnapshot(): Promise<DashboardSnapshot | undefined> {
  try {
    const response = await fetch(`${backendBaseUrl()}/api/snapshot`, {
      cache: "no-store",
      headers: {
        accept: "application/json",
      },
    });
    if (!response.ok) {
      return undefined;
    }
    return (await response.json()) as DashboardSnapshot;
  } catch {
    return undefined;
  }
}
