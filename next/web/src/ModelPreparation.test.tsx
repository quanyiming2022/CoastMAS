import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { ModelPreparation } from "./ModelPreparation";

afterEach(cleanup);
describe("model intent controls", () => {
  it("keeps unknown standardization unselected and preserves numeric zero seed", () => {
    const change = vi.fn();
    render(
      <ModelPreparation
        purpose="cluster"
        options={{ seed: 0 }}
        change={change}
      />,
    );
    expect(
      (screen.getByLabelText("标准化规则") as HTMLSelectElement).value,
    ).toBe("");
    expect((screen.getByLabelText("随机种子") as HTMLInputElement).value).toBe(
      "0",
    );
    fireEvent.change(screen.getByLabelText("标准化规则"), {
      target: { value: "false" },
    });
    expect(change).toHaveBeenCalledWith("standardize", false);
  });
  it("separates regression terms from cluster count", () => {
    render(
      <ModelPreparation purpose="regression" options={{}} change={() => {}} />,
    );
    expect(screen.getByLabelText("投影项数")).toBeTruthy();
    expect(screen.queryByLabelText("聚类数量")).toBeNull();
  });
});
