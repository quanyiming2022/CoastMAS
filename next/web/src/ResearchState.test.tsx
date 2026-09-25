import { act, renderHook, waitFor, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, test, vi } from "vitest";
import type { ReactNode } from "react";
import * as network from "./api";
import { useResearchState, initialResearch } from "./useResearchState";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
test("directory browsing preserves the active research and cannot claim saved before acknowledgement", async () => {
  let value = {
    revision: 1,
    state: {
      ...initialResearch,
      active_task_id: "task-A",
      viewed_job_id: "run-A",
    },
  };
  let acknowledge: (() => void) | undefined;
  vi.spyOn(network, "api").mockImplementation(
    async (_path, schema, options) => {
      if (options?.method === "PUT") {
        const body = JSON.parse(String(options.body));
        expect(body.expected_revision).toBe(value.revision);
        await new Promise<void>((resolve) => {
          acknowledge = resolve;
        });
        value = { revision: value.revision + 1, state: body.state };
      }
      return schema.parse(value);
    },
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const { result } = renderHook(
    () => useResearchState("/projects/p/workspace-state"),
    {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    },
  );
  await waitFor(() => expect(result.current.ready).toBe(true));
  let pending: Promise<void>;
  act(() => {
    pending = result.current.save({
      ...result.current.active!,
      inspected_asset_id: "browse-only",
      panel: "methods",
    });
  });
  await waitFor(() => expect(acknowledge).toBeDefined());
  expect(result.current.saving).toBe(true);
  expect(result.current.active?.active_task_id).toBe("task-A");
  expect(result.current.active?.viewed_job_id).toBe("run-A");
  await act(async () => {
    acknowledge!();
    await pending;
  });
  expect(result.current.saving).toBe(false);
  expect(value.state.active_task_id).toBe("task-A");
  client.clear();
});
