import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { DataTable, Panel } from "./components";
afterEach(cleanup);
it("keeps table semantics, selection handlers and accessible scrolling", () => {
  const onChange = vi.fn();
  render(
    <DataTable aria-label="实际观测" data-testid="observations">
      <thead>
        <tr>
          <th>选择</th>
          <th>数值</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>
            <input aria-label="选择观测" type="checkbox" onChange={onChange} />
          </td>
          <td className="numeric">0</td>
        </tr>
      </tbody>
    </DataTable>,
  );
  expect(screen.getByRole("table", { name: "实际观测" })).toHaveAttribute(
    "data-testid",
    "observations",
  );
  expect(screen.getByRole("region")).toHaveAttribute("tabindex", "0");
  fireEvent.click(screen.getByRole("checkbox"));
  expect(onChange).toHaveBeenCalledOnce();
  expect(screen.getByRole("cell", { name: "0" })).toBeInTheDocument();
});
it("keeps disabled actions and panel content in document order", () => {
  render(
    <Panel title="记录" actions={<button disabled>新建</button>}>
      <p>内容</p>
    </Panel>,
  );
  expect(screen.getByRole("button")).toBeDisabled();
  expect(
    screen
      .getByRole("heading")
      .compareDocumentPosition(screen.getByText("内容")) &
      Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
});
