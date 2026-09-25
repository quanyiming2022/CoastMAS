import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useCatalogSearch } from "./catalogSearch";
afterEach(() => vi.useRealTimers());
describe("catalog search", () => {
  it("waits for IME completion and debounces, while Enter applies immediately", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useCatalogSearch());
    act(() => result.current.compose(true));
    act(() => result.current.change("海"));
    act(() => vi.advanceTimersByTime(500));
    expect(result.current.query).toBe("");
    act(() => result.current.compose(false));
    act(() => vi.advanceTimersByTime(300));
    expect(result.current.query).toBe("海");
    act(() => result.current.change("海岸"));
    act(() => result.current.submit());
    expect(result.current.query).toBe("海岸");
  });
});
