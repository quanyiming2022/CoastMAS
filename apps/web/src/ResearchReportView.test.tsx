import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import ResearchReportView from "./ResearchReportView";
import type { ResearchReport } from "./generated/contracts";

afterEach(cleanup);
it("shows blocked local trials and unknown metrics without claiming success or zero corrections", () => {
  const report: ResearchReport = {
    status: "BLOCKED",
    elapsed_seconds: 0.5,
    methodology: "frozen-catalog-planning-v1",
    executes_candidates: false,
    trials: [
      {
        workflow: null,
        trace_id: null,
        proposal: null,
        observation: {
          case_id: "local-case",
          repetition: 1,
          experiment: "B",
          origin: "LOCAL",
          status: "BLOCKED",
          latency_seconds: null,
          candidate_present: null,
          workflow_valid: null,
          constraint_violated: null,
          manual_corrections: null,
          provider_requests: 0,
          usage: null,
          diagnostics: ["PROVIDER_NOT_CONFIGURED"],
        },
      },
    ],
    metrics: [
      {
        experiment: "B",
        origin: "LOCAL",
        total: 1,
        evaluated: 0,
        blocked: 1,
        failed: 0,
        evaluation_completion_rate: 0,
        workflow_validity_rate: null,
        constraint_observations: 0,
        constraint_violation_rate: null,
        manual_observations: 0,
        manual_correction_count: null,
        latency_observations: 0,
        mean_latency_seconds: null,
        provider_requests: 0,
        usage_observations: 0,
        total_tokens: null,
      },
    ],
  };
  render(<ResearchReportView report={report} />);
  expect(screen.getByText("全部阻塞")).toBeTruthy();
  expect(screen.getAllByText("本地提供方").length).toBeGreaterThan(0);
  expect(screen.getAllByText("未观测").length).toBeGreaterThan(3);
  expect(screen.getByText("PROVIDER_NOT_CONFIGURED")).toBeTruthy();
  expect(screen.queryByText("100.0%")).toBeNull();
});
