import {expect,test} from "vitest";
import {taskFlows,taskTypes} from "./taskFlows";
test("four distinct V3 task flows retain eight exact domain stages",()=>{
  expect(taskTypes.map(t=>t.id)).toEqual(["assessment","simulation","planning","comparison"]);
  for(const stages of Object.values(taskFlows)) {
    expect(stages).toHaveLength(8);
    expect(new Set(stages.map(x=>x.id)).size).toBe(8);
  }
  expect(taskFlows.assessment.map(x=>x.title)).toEqual(["数据","准备与对齐","指标","权重与评价","综合计算","分级","时空分析","成果"]);
  expect(taskFlows.planning[2]?.title).toBe("现状诊断");
  expect(taskFlows.simulation[2]?.id).not.toBe(taskFlows.assessment[2]?.id);
  expect(taskFlows.comparison[0]?.title).toBe("选择方案");
});
