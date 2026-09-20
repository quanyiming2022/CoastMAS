import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { ApiError, request } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "coastmas_csrf=; Max-Age=0; path=/";
});

describe("API transport boundaries", () => {
  it("validates successful data instead of trusting its declared type", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response('{"count":"wrong"}')),
    );
    await expect(
      request("/dashboard", z.object({ count: z.number() })),
    ).rejects.toMatchObject({ code: "RESPONSE_CONTRACT" });
  });
  it("sends CSRF for mutations and never retries a failed write", async () => {
    document.cookie = "coastmas_csrf=test-token; path=/";
    const fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error_code: "VERSION_CONFLICT",
          message: "Changed",
          request_id: "trace-1",
        }),
        { status: 409 },
      ),
    );
    vi.stubGlobal("fetch", fetch);
    await expect(
      request("/models/id", z.unknown(), {
        method: "PUT",
        body: { expected_version: 1 },
      }),
    ).rejects.toMatchObject({ code: "VERSION_CONFLICT", requestId: "trace-1" });
    expect(fetch).toHaveBeenCalledTimes(1);
    const headers = fetch.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.get("X-CSRF-Token")).toBe("test-token");
  });
  it("reports network and malformed error responses explicitly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(
      request("/projects", z.array(z.unknown())),
    ).rejects.toBeInstanceOf(ApiError);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("bad gateway", { status: 502 })),
    );
    await expect(
      request("/projects", z.array(z.unknown())),
    ).rejects.toMatchObject({ code: "HTTP_502" });
  });
  it("allows only same-origin API paths", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(
      request("//external.invalid", z.unknown()),
    ).rejects.toMatchObject({ code: "INVALID_PATH" });
    expect(fetch).not.toHaveBeenCalled();
  });
});
