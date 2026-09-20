import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import App from "./App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/dashboard"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
it("logs in from an expired session and renders server counts", async () => {
  let loggedIn = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      if (input.endsWith("/auth/me"))
        return new Response(
          JSON.stringify(
            loggedIn
              ? { user_id: "user", email: "user@test.local", is_admin: false }
              : {
                  error_code: "AUTHENTICATION_ERROR",
                  message: "Login required",
                },
          ),
          { status: loggedIn ? 200 : 401 },
        );
      if (input.endsWith("/auth/login")) {
        expect(init?.method).toBe("POST");
        loggedIn = true;
        return new Response(
          JSON.stringify({ user_id: "user", csrf_token: "test" }),
        );
      }
      if (input.endsWith("/projects"))
        return new Response(
          JSON.stringify([
            { id: "project", name: "测试项目", owner_id: "user" },
          ]),
        );
      if (input.includes("/dashboard?"))
        return new Response(
          JSON.stringify({
            counts: {
              models: 37,
              scenes: 3,
              executable_models: 8,
              workflows: 5,
              data_assets: 11,
              results: 2,
            },
            run_states: {},
            recent_runs: [],
            provider_configured: false,
          }),
        );
      throw new Error("Unexpected request: " + input);
    }),
  );
  mount();
  fireEvent.change(await screen.findByLabelText("邮箱"), {
    target: { value: "user@test.local" },
  });
  fireEvent.change(screen.getByLabelText("密码"), {
    target: { value: "test-only-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "登录" }));
  expect(await screen.findByText("37")).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "当前项目" })).toHaveValue(
    "project",
  );
});
it("does not turn a server failure into an empty successful dashboard", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error_code: "INTERNAL_ERROR",
          message: "Service unavailable",
          request_id: "trace-7",
        }),
        { status: 500 },
      ),
    ),
  );
  mount();
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Service unavailable"),
  );
  expect(screen.getByRole("alert")).toHaveTextContent("trace-7");
  expect(screen.queryByText("尚无运行记录。")).not.toBeInTheDocument();
});

it("expires a session on protected 401 and never reuses the previous account project cache", async () => {
  let identity: "A" | "B" | null = "A";
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      if (input.endsWith("/auth/me"))
        return new Response(
          JSON.stringify(
            identity
              ? {
                  user_id: identity,
                  email: identity + "@test.local",
                  is_admin: false,
                }
              : { error_code: "AUTHENTICATION_ERROR", message: "Expired" },
          ),
          { status: identity ? 200 : 401 },
        );
      if (input.endsWith("/auth/login")) {
        identity = "B";
        return new Response(
          JSON.stringify({ user_id: "B", csrf_token: "new-test-token" }),
        );
      }
      if (input.endsWith("/projects"))
        return new Response(
          JSON.stringify([
            {
              id: "project-" + identity,
              name: "Private project " + identity,
              owner_id: identity,
            },
          ]),
        );
      if (input.includes("/dashboard?"))
        return new Response(
          JSON.stringify({
            counts: { models: 37 },
            run_states: {},
            recent_runs: [],
            provider_configured: false,
          }),
        );
      if (input.includes("/models?")) {
        if (identity === "A") {
          identity = null;
          return new Response(
            JSON.stringify({
              error_code: "AUTHENTICATION_ERROR",
              message: "Expired",
            }),
            { status: 401 },
          );
        }
        expect(input).toContain("project_id=project-B");
        return new Response("[]");
      }
      throw new Error("Unexpected request: " + input);
    }),
  );
  mount();
  await screen.findByText("37");
  fireEvent.click(screen.getByRole("link", { name: "模型中心" }));
  fireEvent.change(await screen.findByLabelText("邮箱"), {
    target: { value: "B@test.local" },
  });
  fireEvent.change(screen.getByLabelText("密码"), {
    target: { value: "test-only-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "登录" }));
  await waitFor(() =>
    expect(screen.getByRole("combobox", { name: "当前项目" })).toHaveValue(
      "project-B",
    ),
  );
  expect(screen.queryByText("Private project A")).not.toBeInTheDocument();
});
