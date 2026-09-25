import { afterEach, expect, test, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as network from "./api";
import { taskSchema } from "./draft";
import { ResearchStepPanel } from "./ResearchStepPanel";
import {
  ConfigurationIssues,
  useConfigurationReview,
} from "./ConfigurationReview";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
const task = taskSchema.parse({
  id: "t",
  project_id: "p",
  revision: 1,
  updated: 1,
  draft: {
    title: "原名SHA缺口",
    purpose: "assessment",
    selection: [],
    mapping: [],
    options: {},
  },
});
function Harness({ value = task }: { value?: typeof task }) {
  const review = useConfigurationReview(value);
  return <ConfigurationIssues review={review} onAction={vi.fn()} />;
}
function wrapper() {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        {children}
      </QueryClientProvider>
    );
  };
}
test("UX02 empty sources contain one real add action, no run explanations or scope", () => {
  const add = vi.fn();
  render(
    <ResearchStepPanel
      step="sources"
      scope="draft"
      task={task}
      assets={[]}
      onScope={vi.fn()}
      onAdd={add}
    />,
    { wrapper: wrapper() },
  );
  expect(screen.getByText("尚未添加输入资料")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "添加资料" }));
  expect(add).toHaveBeenCalledOnce();
  expect(screen.queryByRole("combobox")).toBeNull();
  expect(
    screen.queryByText(/运行产物|最大化配置表|检查草稿缺口|修改只保存/),
  ).toBeNull();
});
test("UX07–10 no-input no request, nonempty read-only versioned request; failure never ready", async () => {
  const mock = vi
    .spyOn(network, "api")
    .mockRejectedValue(new Error("connection interrupted"));
  const { rerender } = render(<Harness />, { wrapper: wrapper() });
  await new Promise((r) => setTimeout(r, 350));
  expect(mock).not.toHaveBeenCalled();
  const withInput = {
    ...task,
    draft: { ...task.draft, selection: [{ asset_id: "a", revision: 1 }] },
  };
  rerender(<Harness value={withInput} />);
  await screen.findByText("检查未完成");
  expect(mock.mock.calls[0]?.[0]).toBe(
    "/tasks/t/configuration-review?revision=1",
  );
  expect(screen.queryByText(/通过|就绪/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重新检查" }));
  await waitFor(() => expect(mock).toHaveBeenCalledTimes(2));
});
test("UX10 late response and UX16 unrelated or duplicate issues do not pollute next task", async () => {
  let resolve!: (v: unknown) => void;
  const issue = {
    id: "same",
    code: "UNIT_REQUIRED",
    message: "指标“原名SHA缺口”单位未确定",
    steps: ["indicators"],
    action: "bindings",
  };
  vi.spyOn(network, "api").mockImplementation((path) =>
    path.includes("/t/")
      ? new Promise((r) => {
          resolve = r;
        })
      : Promise.resolve({
          task_id: "other",
          revision: 1,
          scope: "saved_metadata",
          execution_checked: false,
          issues: [],
        }),
  );
  const selected = {
    ...task,
    draft: { ...task.draft, selection: [{ asset_id: "a", revision: 1 }] },
  };
  const { rerender } = render(<Harness value={selected} />, {
    wrapper: wrapper(),
  });
  await waitFor(() => expect(resolve).toBeTypeOf("function"));
  rerender(<Harness value={{ ...selected, id: "other" }} />);
  resolve({
    task_id: "t",
    revision: 1,
    scope: "saved_metadata",
    execution_checked: false,
    issues: [issue, issue],
  });
  await waitFor(() => expect(screen.queryByText(issue.message)).toBeNull());
});
