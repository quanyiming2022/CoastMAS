import { test, expect, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { CatalogDock, dockBounds } from "./CatalogDock";
test("dock bounds retain map room and never use screen scaling", () => {
  expect(dockBounds(844)).toEqual({ min: 220, max: 580, initial: 295 });
  expect(dockBounds(480).max).toBe(216);
});
test("keyboard splitter reports actual height, expands/restores and closes without changing children", () => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  const height = vi.fn(),
    maximize = vi.fn(),
    close = vi.fn();
  const { rerender } = render(
    <CatalogDock
      open
      maximized={false}
      height={300}
      title="资料目录"
      onHeight={height}
      onMaximize={maximize}
      onClose={close}
    >
      <input aria-label="保留筛选" defaultValue="coast" />
    </CatalogDock>,
  );
  const bar = screen.getByRole("separator", { name: "调整目录高度" });
  fireEvent.keyDown(bar, { key: "ArrowUp" });
  expect(height).toHaveBeenCalledWith(324);
  fireEvent.keyDown(bar, { key: "ArrowDown" });
  expect(height).toHaveBeenCalledWith(276);
  fireEvent.keyDown(bar, { key: "Enter" });
  expect(maximize).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(bar, { key: "Escape" });
  expect(close).toHaveBeenCalledTimes(1);
  rerender(
    <CatalogDock
      open
      maximized
      height={300}
      title="资料目录"
      onHeight={height}
      onMaximize={maximize}
      onClose={close}
    >
      <input aria-label="保留筛选" defaultValue="coast" />
    </CatalogDock>,
  );
  expect(screen.getByLabelText("保留筛选")).toHaveValue("coast");
  expect(bar).toHaveAttribute("aria-valuenow", "300");
  cleanup();
  vi.unstubAllGlobals();
});
