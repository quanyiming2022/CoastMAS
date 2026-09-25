import { createContext, useContext, type ReactNode } from "react";
export {taskFlows} from "./taskFlows";
import {taskFlows} from "./taskFlows";
export const researchSteps = taskFlows.assessment;
export type ResearchStep = (typeof taskFlows)[keyof typeof taskFlows][number]["id"] | "normalization" | "spatialization";
export type ResearchPanel =
  | { kind: "step"; step: ResearchStep; scope: "draft" | "run" }
  | { kind: "details" | "pixel" | "style"; owner: string };
export type PanelController = {
  reportViewSave?: (owner: string, status: string) => void;
  active: ResearchPanel | null;
  host: HTMLElement | null;
  open: (panel: ResearchPanel, trigger?: HTMLElement | null) => void;
  close: () => void;
};
const ResearchPanelContext = createContext<PanelController | null>(null);
export const useResearchPanel = () => useContext(ResearchPanelContext);
export function ResearchPanelProvider({
  value,
  children,
}: {
  value: PanelController;
  children: ReactNode;
}) {
  return (
    <ResearchPanelContext.Provider value={value}>
      {children}
    </ResearchPanelContext.Provider>
  );
}
