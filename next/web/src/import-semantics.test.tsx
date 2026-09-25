import { afterEach, expect, test, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  fireEvent,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CatalogUpload } from "./CatalogUpload";
import { formatBytes } from "./formatBytes";
import * as network from "./api";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
test("research import shows the actual picker inside exactly one application dialog", async () => {
  const request = vi.spyOn(network, "api").mockResolvedValue([]);
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <div role="dialog" aria-label="添加研究资料">
        <CatalogUpload inline project="p" disabled={false} onAsset={vi.fn()} />
      </div>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(request).toHaveBeenCalled());
  expect(screen.getAllByRole("dialog")).toHaveLength(1);
  expect(screen.getByLabelText("选择并导入资料")).toBeVisible();
  expect(screen.queryByRole("button", { name: "导入资料" })).toBeNull();
  fireEvent.change(screen.getByLabelText("选择并导入资料"), {
    target: { files: [] },
  });
  expect(
    request.mock.calls.every((c) => !c[2]?.method || c[2].method === "GET"),
  ).toBe(true);
});
test("byte progress does not round a 93 byte attachment to zero MiB", () => {
  expect(formatBytes(93)).toBe("93 B");
  expect(formatBytes(0)).toBe("0 B");
  expect(formatBytes(419430400)).toBe("400.00 MiB");
});
