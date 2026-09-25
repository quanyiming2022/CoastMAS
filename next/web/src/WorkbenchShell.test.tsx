import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { WorkbenchShell } from "./WorkbenchShell";

describe("professional shell", () => {
  it("keeps editable content mounted while navigation opens and closes", () => {
    render(
      <MemoryRouter>
        <WorkbenchShell
          projectControl={
            <select aria-label="当前项目">
              <option>海岸</option>
            </select>
          }
          project="p"
          email="long-account@example.test"
          canManage={false}
          onSignOut={async () => {}}
        >
          <input aria-label="未完成字段" defaultValue="" />
        </WorkbenchShell>
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText("未完成字段"), {
      target: { value: "保留输入" },
    });
    expect(screen.getByRole("button", { name: "收起导航" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "收起导航" }));
    fireEvent.click(screen.getByRole("button", { name: "展开导航" }));
    expect(screen.getByLabelText("未完成字段")).toHaveValue("保留输入");
    expect(
      screen.queryByRole("link", { name: "用户与权限" }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByLabelText("当前项目")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "工作台" })).toHaveAttribute(
      "href",
      "/research?project=p",
    );
  });
});
