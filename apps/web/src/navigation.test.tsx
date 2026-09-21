import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import Sidebar from "./Sidebar";
import {
  navigation,
  activeEntry,
  initialGroups,
  NAV_STORAGE_KEY,
} from "./navigation";

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
it("maps every existing route family once, with path-segment boundaries", () => {
  expect(new Set(navigation.map((item) => item.path)).size).toBe(
    navigation.length,
  );
  for (const [path, id] of [
    ["/models/a/edit", "models"],
    ["/models/decompose", "models"],
    ["/data-sources/new", "data"],
    ["/assessment-records/a", "assessments"],
    ["/results/compare", "results"],
    ["/scenes/a/workspace", "scenes"],
    ["/workflows/a/edit", "workflows"],
    ["/research/a", "research"],
    ["/admin", "admin"],
  ])
    expect(activeEntry(path!)?.id).toBe(id);
  expect(activeEntry("/models-other")).toBeUndefined();
  expect(activeEntry("/data-source")).toBeUndefined();
});
it("validates stored UI preferences and degrades on storage failure", () => {
  localStorage.setItem(
    NAV_STORAGE_KEY,
    JSON.stringify({
      data: false,
      models: false,
      results: true,
      assessment: false,
      token: "ignored",
    }),
  );
  expect(initialGroups("/research")).toEqual({
    data: false,
    models: false,
    results: true,
    assessment: false,
  });
  expect(initialGroups("/models/a").models).toBe(true);
  localStorage.setItem(NAV_STORAGE_KEY, "bad json");
  expect(initialGroups("/dashboard").data).toBe(true);
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  expect(initialGroups("/results/a").results).toBe(true);
});
function Harness({ admin = false }: { admin?: boolean }) {
  const navigate = useNavigate();
  return (
    <>
      <Sidebar
        email="long-account@example.test"
        isAdmin={admin}
        onLogout={() => {}}
        logoutPending={false}
      />
      <input aria-label="测试草稿" />
      <button onClick={() => navigate("/models/a/edit?version=2#inputs")}>
        直达模型
      </button>
    </>
  );
}
function mount(admin = false) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
  render(
    <MemoryRouter initialEntries={["/models/a"]}>
      <Harness admin={admin} />
    </MemoryRouter>,
  );
}
it("allows manual collapse, preserves content, opens the owning group on real navigation", () => {
  mount();
  const group = screen.getByRole("button", { name: "模型与编排" });
  fireEvent.change(screen.getByLabelText("测试草稿"), {
    target: { value: "do not reset" },
  });
  fireEvent.click(group);
  expect(group).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByLabelText("测试草稿")).toHaveValue("do not reset");
  expect(
    screen.queryByRole("link", { name: "模型中心" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "直达模型" }));
  expect(group).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("link", { name: "模型中心" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(document.querySelectorAll('[aria-current="page"]')).toHaveLength(1);
  expect(
    screen.queryByRole("link", { name: "系统管理" }),
  ).not.toBeInTheDocument();
});
it("uses only supplied authorization and remains usable if saving preferences fails", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("quota");
  });
  mount(true);
  expect(screen.getByRole("link", { name: "系统管理" })).toHaveAttribute(
    "href",
    "/admin",
  );
  fireEvent.click(screen.getByRole("button", { name: "模型与编排" }));
  expect(screen.getByRole("button", { name: "模型与编排" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
});

it("does not pull manual navigation scrolling back to the active item", () => {
  mount();
  const region = screen.getByRole("navigation", { name: "主导航" });
  const active = screen.getByRole("link", { name: "模型中心" });
  region.scrollTop = 100;
  vi.spyOn(region, "getBoundingClientRect").mockReturnValue(
    new DOMRect(0, 0, 200, 100),
  );
  vi.spyOn(active, "getBoundingClientRect").mockReturnValue(
    new DOMRect(0, -100, 200, 40),
  );
  fireEvent.click(screen.getByRole("button", { name: "场景与数据" }));
  expect(region.scrollTop).toBe(100);
});
