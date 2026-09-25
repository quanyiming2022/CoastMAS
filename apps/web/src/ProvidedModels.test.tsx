import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ProvidedModels from "./ProvidedModels";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("uses existing links and sends only the selected registered method", async () => {
  const sent: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url, options) => {
      if (options.method === "POST") {
        sent.push(JSON.parse(options.body));
        return new Response(
          JSON.stringify({
            error_code: "VERSION_CONFLICT",
            message: "already registered",
          }),
          { status: 409 },
        );
      }
      return new Response(
        JSON.stringify({
          available: true,
          reason: null,
          can_approve: false,
          can_register: true,
          models: [
            {
              method: "ppci_mcdc",
              name: "PPCI",
              license: "GPL-3",
              image: "sha256:test",
              id: "business:p:ppci_mcdc",
              registered: true,
            },
            {
              method: "ppr_ols",
              name: "pprRFA",
              license: "MIT",
              image: "sha256:test",
              id: "business:p:ppr_ols",
              registered: false,
            },
          ],
        }),
      );
    }),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <ProvidedModels projectId="p" model={null} onSaved={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(
    (await screen.findByRole("link", { name: "打开已登记模型" })).getAttribute(
      "href",
    ),
  ).toBe("/models/business%3Ap%3Appci_mcdc/edit");
  fireEvent.click(screen.getByRole("button", { name: "登记pprRFA" }));
  await screen.findByRole("alert");
  expect(sent).toEqual([{ project_id: "p", method: "ppr_ols" }]);
  expect(
    screen.queryByRole("button", { name: "批准此版本运行适配器" }),
  ).toBeNull();
});
