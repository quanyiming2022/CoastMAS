import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { APIError } from "./api";
import { ErrorNotice } from "./shared";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
test("error summary remains visible; diagnostics retain code but exclude password fields", () => {
  render(
    <ErrorNotice
      error={
        new APIError(
          422,
          "原名SHA指标的单位不相容",
          {
            detail: [{ loc: ["body", "password"], input: "do-not-show" }],
            password: "do-not-show",
            reason: "m versus s",
          },
          "UNIT_CONFLICT",
        )
      }
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "原名SHA指标的单位不相容",
  );
  fireEvent.click(screen.getByText("错误详情"));
  expect(screen.getByText("UNIT_CONFLICT")).toBeVisible();
  expect(screen.queryByText(/do-not-show/)).toBeNull();
  expect(screen.getByText(/m versus s/)).toBeVisible();
});
test("network errors remain failures, with accessible retry reason", () => {
  render(<ErrorNotice error={new TypeError("Failed to fetch")} />);
  expect(screen.getByRole("alert")).toHaveTextContent("连接失败");
});
