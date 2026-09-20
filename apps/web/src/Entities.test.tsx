import { afterEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WorkspaceProvider } from "./workspace";
import Entities from "./Entities";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("does not reset the user's historical selection when a delayed map refresh completes", async () => {
  const initial = {
    id: "entity-test",
    name: "Original",
    version: 1,
    type: "management_unit",
    management_unit_id: "U1",
    crs: "EPSG:4326",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [117, 31],
          [118, 31],
          [118, 32],
          [117, 31],
        ],
      ],
    },
    valid_from: "2020-01-01T00:00:00Z",
    valid_to: null,
    properties: {},
  };
  let current = { ...initial };
  let finishMap: () => void = () => {
    throw new Error("Map request has not started");
  };
  const deferredMap = new Promise<void>((resolve) => {
    finishMap = resolve;
  });
  const json = (value: unknown) => new Response(JSON.stringify(value));
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      if (input.endsWith("/projects"))
        return json([{ id: "project", name: "Project", owner_id: "user" }]);
      if (input.includes("/entities/spatial?")) {
        if (current.version === 2) await deferredMap;
        return json({
          type: "FeatureCollection",
          features: [],
          has_more: false,
          offset: 0,
        });
      }
      if (input.includes("/entities?"))
        return json([
          {
            id: current.id,
            name: current.name,
            version: current.version,
            enabled: true,
            published: false,
            summary: {},
          },
        ]);
      if (input.includes("/entities/entity-test")) {
        if (init?.method === "PUT")
          current = { ...initial, name: "Revised", version: 2 };
        const spec = input.endsWith("?version=1") ? initial : current;
        return json({ spec, version: spec.version, checksum: "a".repeat(64) });
      }
      throw new Error("Unexpected request " + input);
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <WorkspaceProvider>
        <Entities />
      </WorkspaceProvider>
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Original · v1" }));
  await waitFor(() =>
    expect(screen.getByLabelText("实体名称")).toHaveValue("Original"),
  );
  fireEvent.change(screen.getByLabelText("实体名称"), {
    target: { value: "Revised" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存实体版本" }));
  await screen.findByRole("button", { name: "Revised · v2" });
  fireEvent.change(screen.getByLabelText("读取版本"), {
    target: { value: "1" },
  });
  await waitFor(() =>
    expect(screen.getByLabelText("实体名称")).toHaveValue("Original"),
  );
  await act(async () => {
    finishMap();
    await deferredMap;
  });
  await waitFor(() => expect(client.isMutating()).toBe(0));
  expect(screen.getByLabelText("读取版本")).toHaveValue(1);
  expect(screen.getByLabelText("实体名称")).toHaveValue("Original");
});
