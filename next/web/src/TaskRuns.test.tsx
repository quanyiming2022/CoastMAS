import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as network from "./api";
import { TaskRuns } from "./TaskRuns";
const row = (id: string, status = "cancelled") => ({
  id,
  task_id: "task",
  status,
  created: 1,
  draft_revision: 2,
  cancel_requested: false,
  error: null,
});
function mount(canEdit: boolean) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <TaskRuns taskId="task" draftRevision={3} canEdit={canEdit} />
    </QueryClientProvider>,
  );
  return client;
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
describe("run history actions", () => {
  it("pages actual history without writing a draft, including for read-only users", async () => {
    const api = vi
      .spyOn(network, "api")
      .mockImplementation(async (path, schema) => {
        if (path.includes("offset=25"))
          return schema.parse({
            items: [row("last")],
            total: 26,
            limit: 25,
            offset: 25,
          });
        return schema.parse({
          items: Array.from({ length: 25 }, (_, i) => row("job-" + i)),
          total: 26,
          limit: 25,
          offset: 0,
        });
      });
    const client = mount(false);
    fireEvent.click(await screen.findByText("全部运行记录（26 次）"));
    expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    await screen.findByText("第2/2页 · 共26次");
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /查看任务版本/ })).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: "取消此运行" }),
    ).not.toBeInTheDocument();
    expect(api.mock.calls.every((call) => !call[2]?.method)).toBe(true);
    client.clear();
  });
  it("requests cancellation and refreshes status rather than claiming success locally", async () => {
    let cancelled = false;
    const api = vi
      .spyOn(network, "api")
      .mockImplementation(async (path, schema, options) => {
        if (path.endsWith("/cancel")) {
          expect(options?.method).toBe("POST");
          cancelled = true;
          return schema.parse({ ...row("one"), cancel_requested: true });
        }
        return schema.parse({
          items: [row("one", cancelled ? "cancelled" : "queued")],
          total: 1,
          limit: 25,
          offset: 0,
        });
      });
    const client = mount(true);
    fireEvent.click(await screen.findByRole("button", { name: "取消此运行" }));
    await screen.findByText("运行已取消");
    await waitFor(() =>
      expect(
        api.mock.calls.some((call) => call[0] === "/jobs/one/cancel"),
      ).toBe(true),
    );
    client.clear();
  });
});
