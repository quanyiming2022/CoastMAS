import { expect, test } from "vitest";
import {navigation, v3Centers, visibleNavigation, activeNavigation, navigationURL} from "./navigation";
test("V3 centers and ownership cannot be merged or renamed by infrastructure additions",()=>{
  expect(v3Centers.map(x=>x.label)).toEqual(["工作台","项目与研究","数据","指标与方法","模型工程","耦合与工作流","规划与优化","运行","成果","管理"]);
  expect(new Set(navigation.map(x=>x.id)).size).toBe(navigation.length);
  const available=visibleNavigation(true,true,true).filter(x=>x.path);
  expect(new Set(available.map(x=>navigationURL(x,"p"))).size).toBe(available.length);
  expect(navigation.find(x=>x.id==="projects")?.group).toBe("research");
  for(const [id,group] of [["models","modelops"],["matching","coupling"],["planning","planning"],["runs","runs"],["results","results"]])expect(navigation.find(x=>x.id===id)).toMatchObject({group,path:expect.any(String)});
});
test("permission filtering and development-only unavailable states never create dummy links",()=>{
  const ordinary=visibleNavigation(false,false,true);
  expect(ordinary.some(x=>x.id==="projects")).toBe(true);
  expect(ordinary.some(x=>["users","settings","audit"].includes(x.id))).toBe(false);
  expect(visibleNavigation(true,false,true).some(x=>x.id==="users")).toBe(false);
  expect(visibleNavigation(true,true,false).every(x=>x.path)).toBe(true);
  for(const x of navigation.filter(x=>!x.path))expect(()=>navigationURL(x,"p")).toThrow();
});
test("detail routes have a single exact owner",()=>{
  expect(activeNavigation("/tasks/actual","?project=p","assessment")).toBe("workspace");
  expect(activeNavigation("/tasksmith/actual","","assessment")).toBeNull();
  expect(activeNavigation("/projects","","assessment")).toBe("projects");
});
