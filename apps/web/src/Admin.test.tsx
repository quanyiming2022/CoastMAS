import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Admin from "./Admin";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("restores an archived project through the authorized API and keeps history visible", async () => {
  let archived = true;
  const operations: { method?: string; body?: BodyInit | null }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/projects/p/archive")) {
        operations.push({ method: init?.method, body: init?.body });
        archived = false;
        return new Response(
          JSON.stringify({
            id: "p",
            name: "历史项目",
            owner_id: "u",
            archived,
          }),
        );
      }
      if (url.includes("/projects?"))
        return new Response(
          JSON.stringify([
            { id: "p", name: "历史项目", owner_id: "u", archived },
          ]),
        );
      if (url.includes("/admin/users"))
        return new Response(
          JSON.stringify([
            {
              id: "u",
              email: "admin@test.local",
              active: true,
              is_admin: true,
            },
          ]),
        );
      return new Response("[]");
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <Admin userId="u" />
    </QueryClientProvider>,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "恢复项目 历史项目" }),
  );
  await screen.findByRole("button", { name: "归档项目 历史项目" });
  await waitFor(() =>
    expect(operations).toEqual([
      { method: "POST", body: JSON.stringify({ archived: false }) },
    ]),
  );
  expect(
    screen.getByRole("cell", { name: /^历史项目$/ }),
  ).toBeTruthy();
});
