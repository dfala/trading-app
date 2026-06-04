import { afterEach, describe, expect, it, vi } from "vitest";

import { POST as postControl } from "@/app/api/control/route";
import { GET as getHealth } from "@/app/api/health/route";
import { GET as getModelPerformance } from "@/app/api/model-performance/route";
import { GET as getSnapshot } from "@/app/api/snapshot/route";

describe("Next.js backend proxy routes", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    delete process.env.TRADING_APP_BACKEND_URL;
  });

  it("proxies snapshot requests to the Python backend without caching", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await getSnapshot();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      URL,
      RequestInit,
    ];

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ ok: true });
    expect(String(url)).toBe("http://127.0.0.1:8765/api/snapshot");
    expect(init).toMatchObject({
      method: "GET",
      cache: "no-store",
    });
  });

  it("proxies health requests using the configured backend URL", async () => {
    process.env.TRADING_APP_BACKEND_URL = "http://127.0.0.1:9999/";
    const fetchMock = vi.fn(async () => Response.json({ status: "healthy" }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await getHealth();
    const [url] = fetchMock.mock.calls[0] as unknown as [URL, RequestInit];

    expect(response.status).toBe(200);
    expect(String(url)).toBe("http://127.0.0.1:9999/api/health");
  });

  it("proxies model performance requests with model and universe parameters", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({ model_key: "test_strategy:v1" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const request = new Request(
      "http://localhost/api/model-performance?model_key=test_strategy%3Av1&universe_id=semis",
    );

    const response = await getModelPerformance(request);
    const [url] = fetchMock.mock.calls[0] as unknown as [URL, RequestInit];

    expect(response.status).toBe(200);
    expect(String(url)).toBe(
      "http://127.0.0.1:8765/api/model-performance?model_key=test_strategy%3Av1&universe_id=semis",
    );
  });

  it("proxies operator controls as JSON POST requests", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({ status: "accepted", message: "Control action accepted." }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const request = new Request("http://localhost/api/control", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "pause_runtime" }),
    });

    const response = await postControl(request);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      URL,
      RequestInit,
    ];

    expect(response.status).toBe(200);
    expect(String(url)).toBe("http://127.0.0.1:8765/api/control");
    expect(init).toMatchObject({
      method: "POST",
      cache: "no-store",
      body: JSON.stringify({ action: "pause_runtime" }),
    });
  });

  it("returns a 502 response when the Python backend is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("connect ECONNREFUSED");
      }),
    );

    const response = await getSnapshot();
    const payload = await response.json();

    expect(response.status).toBe(502);
    expect(payload.error).toBe("Python trading backend unavailable");
  });
});
