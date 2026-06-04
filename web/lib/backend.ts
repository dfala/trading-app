const DEFAULT_BACKEND_URL = "http://127.0.0.1:8765";

type ProxyInit = {
  method?: "GET" | "POST";
  body?: BodyInit | null;
  headers?: HeadersInit;
};

export function backendBaseUrl(): string {
  const configured = process.env.TRADING_APP_BACKEND_URL ?? DEFAULT_BACKEND_URL;
  return configured.replace(/\/+$/, "");
}

export async function proxyBackend(path: string, init: ProxyInit = {}) {
  const url = new URL(path, backendBaseUrl());
  const method = init.method ?? "GET";
  const headers = new Headers(init.headers);

  if (!headers.has("accept")) {
    headers.set("accept", "application/json");
  }

  try {
    const upstream = await fetch(url, {
      method,
      body: init.body,
      headers,
      cache: "no-store",
    });
    return responseFromUpstream(upstream);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown backend error";
    return Response.json(
      {
        error: "Python trading backend unavailable",
        detail: message,
        backend_url: backendBaseUrl(),
      },
      {
        status: 502,
        headers: noStoreHeaders(),
      },
    );
  }
}

async function responseFromUpstream(upstream: Response) {
  const headers = noStoreHeaders();
  const contentType = upstream.headers.get("content-type");

  if (contentType) {
    headers.set("content-type", contentType);
  }

  return new Response(await upstream.arrayBuffer(), {
    status: upstream.status,
    statusText: upstream.statusText,
    headers,
  });
}

function noStoreHeaders() {
  return new Headers({
    "cache-control": "no-store",
  });
}
