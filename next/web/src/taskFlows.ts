import type {TaskRecord} from "./draft";
export const taskTypes = [
  {id:"assessment",label:"评价 · Assessment"},
  {id:"simulation",label:"模拟 · Simulation"},
  {id:"planning",label:"规划 · Planning"},
  {id:"comparison",label:"比较 · Comparison"},
] as const;
export type TaskType=(typeof taskTypes)[number]["id"];
const flow = <const T extends readonly (readonly [string,string,string])[]>(rows:T)=>rows.map(([id,title,label])=>({id:id as T[number][0],title,label}));
export const taskFlows = {
  assessment:flow([["sources","数据","数据"],["spatial","准备与对齐","对齐"],["indicators","指标","指标"],["weights","权重与评价","权评"],["synthesis","综合计算","综合"],["classification","分级","分级"],["spacetime","时空分析","时空"],["validation","成果","成果"]]),
  simulation:flow([["sources","数据","数据"],["spatial","准备与对齐","对齐"],["state-variables","状态变量","变量"],["model","模型","模型"],["scenario","情景条件","情景"],["simulation-run","模拟运行","模拟"],["scenario-analysis","情景分析","分析"],["validation","成果","成果"]]),
  planning:flow([["sources","数据","数据"],["spatial","准备与对齐","对齐"],["diagnosis","现状诊断","诊断"],["objectives","规划目标","目标"],["constraints","约束与决策变量","约束"],["optimization","方案生成与优化","优化"],["plan-comparison","方案评价与比较","比选"],["validation","规划成果","成果"]]),
  comparison:flow([["compare-inputs","选择方案","方案"],["compare-basis","统一比较口径","口径"],["compare-indicators","评价指标","指标"],["compare-statistics","统计分析","统计"],["compare-spatial","空间差异","差异"],["tradeoffs","权衡分析","权衡"],["sensitivity","敏感性分析","敏感"],["validation","比较成果","成果"]]),
};
export function taskType(task?:TaskRecord):TaskType {
  const type=task?.draft.options.task_type;
  if(taskTypes.some(x=>x.id===type))return type as TaskType;
  if(task?.draft.purpose==="optimization")return "planning";
  if(task?.draft.purpose==="comparison")return "comparison";
  if(task?.draft.purpose==="simulation")return "simulation";
  return "assessment";
}
