import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  ResearchHeader,
  researchSaveStatus,
  combineSaveStatus,
} from "./ResearchHeader";

describe("compact research header", () => {
  it("never claims saved before draft and workspace acknowledgements or during conflicts", () => {
    expect(researchSaveStatus(true, false, null, null)).toBe("正在恢复…");
    expect(researchSaveStatus(false, false, null, "saved")).toBe("正在恢复…");
    expect(researchSaveStatus(true, false, null, "unsaved")).toBe("尚未保存");
    expect(researchSaveStatus(true, true, null, "saved")).toBe("保存中…");
    expect(researchSaveStatus(true, false, null, "saving")).toBe("保存中…");
    expect(researchSaveStatus(true, true, null, "conflict")).toBe("保存冲突");
    expect(researchSaveStatus(true, false, new Error("offline"), "saved")).toBe(
      "保存失败",
    );
    expect(researchSaveStatus(true, false, null, "error")).toBe("保存失败");
    expect(researchSaveStatus(true, false, null, "saved")).toBe("已保存");
  });
  it("keeps the actual long title accessible and separate from execution", () => {
    const execute = vi.fn();
    const title = "珠江三角洲海岸带空间研究：不可省略的实际研究名称";
    render(
      <ResearchHeader
        title={title}
        status="已保存"
        canEdit={true}
        canExecute={true}
        onNew={vi.fn()}
        onExecute={execute}
        onRename={vi.fn()}
      />,
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(title);
    expect(
      screen.getByRole("button", { name: "查看或编辑研究名称" }),
    ).toHaveAttribute("title", title);
    expect(screen.getByRole("button", { name: "预检并执行" })).toBeEnabled();
    expect(execute).not.toHaveBeenCalled();
  });
});

it("view failures and conflicts override a saved scientific draft", () => {
  expect(combineSaveStatus("已保存", "保存失败")).toBe("保存失败");
  expect(combineSaveStatus("已保存", "保存冲突")).toBe("保存冲突");
  expect(combineSaveStatus("已保存", "保存中…")).toBe("保存中…");
  expect(combineSaveStatus("尚未保存", "已保存")).toBe("尚未保存");
});
