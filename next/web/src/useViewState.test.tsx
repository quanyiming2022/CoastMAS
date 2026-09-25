import { afterEach, expect, test, vi } from "vitest";
import { cleanup, renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as network from "./api";
import { useViewState } from "./useViewState";
const initial = {
  asset_id: "source",
  band: 1,
  camera: null,
  opacity: 0.9,
  visible: true,
};
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const hook = renderHook(() => useViewState("/tasks/task/view-state"), {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
  return { ...hook, client };
}
test("saved means acknowledged; lost acknowledgment recovers the same state", async () => {
  let state: unknown = null;
  let revision = 0;
  vi.spyOn(network, "api").mockImplementation(
    async (_path, schema, options) => {
      if (options?.method === "PUT") {
        const body = JSON.parse(String(options.body));
        expect(body.expected_revision).toBe(revision);
        state = body.state;
        revision++;
        throw new TypeError("response lost");
      }
      return schema.parse({ state, revision });
    },
  );
  const { result, client } = mount();
  await waitFor(() => expect(result.current.ready).toBe(true));
  await act(async () => {
    await result.current.save(initial);
  });
  expect(result.current.active).toEqual(initial);
  expect(result.current.error).toBeNull();
  expect(result.current.saving).toBe(false);
  expect(
    client.getQueryData(["personal-view", "/tasks/task/view-state"]),
  ).toEqual({ state: initial, revision: 1 });
  client.clear();
});
test("concurrent server change keeps local view and blocks silent further overwrites", async () => {
  let revision = 0;
  const api = vi
    .spyOn(network, "api")
    .mockImplementation(async (_path, schema, options) => {
      if (options?.method === "PUT") {
        revision = 1;
        throw new network.APIError(409, "conflict", null);
      }
      return schema.parse({
        revision,
        state: revision ? { ...initial, band: 2 } : null,
      });
    });
  const { result, client } = mount();
  await waitFor(() => expect(result.current.ready).toBe(true));
  await act(async () => {
    await result.current.save(initial).catch(() => {});
  });
  expect(result.current.active?.band).toBe(1);
  expect(result.current.error).toBeTruthy();
  await act(async () => {
    await result.current.save({ ...initial, opacity: 0.4 }).catch(() => {});
  });
  expect(
    api.mock.calls.filter((call) => call[2]?.method === "PUT"),
  ).toHaveLength(1);
  await act(async () => {
    await result.current.restore();
  });
  expect(result.current.active?.band).toBe(2);
  expect(result.current.error).toBeNull();
  client.clear();
});
