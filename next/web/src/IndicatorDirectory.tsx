import {useState} from "react";
import {useQuery} from "@tanstack/react-query";
import {z} from "zod";
import {api} from "./api";
import {ErrorNotice} from "./shared";
const schema=z.object({items:z.array(z.object({indicator_id:z.string(),name:z.string(),category:z.string(),description:z.string(),status:z.string(),message:z.string(),installation_status:z.string()}))});
export function IndicatorDirectory({project,onUse}:{project:string;onUse?:()=>void}) {
  const [search,setSearch]=useState("");
  const query=useQuery({queryKey:["indicator-directory",project],queryFn:()=>api(`/v1/projects/${project}/indicators`,schema)});
  const items=query.data?.items.filter(x=>x.installation_status==="published"&&(x.name+x.category+x.description).toLowerCase().includes(search.toLowerCase()));
  return <section className="domain-directory" aria-label="指标库"><div className="catalog-toolbar"><h2>指标库</h2><input type="search" aria-label="搜索指标库" value={search} onChange={e=>setSearch(e.target.value)}/>{onUse?<button onClick={onUse}>为当前任务选择指标</button>:<span>进入研究任务后可批量添加、计算。</span>}</div><ErrorNotice error={query.error}/>{query.isPending?<p role="status">正在匹配项目资料…</p>:null}
    {items?.length===0?<p>没有符合筛选的可用指标。</p>:null}
    {items?.length?<div className="table-scroll"><table><thead><tr><th>指标</th><th>分类</th><th>说明</th><th>当前项目资料</th></tr></thead><tbody>{items.map(x=><tr key={x.indicator_id}><th>{x.name}</th><td>{x.category}</td><td>{x.description}</td><td>{x.message}</td></tr>)}</tbody></table></div>:null}
  </section>;
}
