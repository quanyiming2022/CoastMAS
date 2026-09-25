import {useState} from "react";
import {useQuery} from "@tanstack/react-query";
import {z} from "zod";
import {api} from "./api";
import {ErrorNotice} from "./shared";
import {ManagedCatalog,type CatalogRow} from "./ManagedCatalog";

const releaseSchema=z.object({release:z.object({model_id:z.string(),package:z.string(),version:z.string()}),release_digest:z.string(),approved:z.boolean(),can_approve:z.boolean()});
export function ModelDirectory({project}:{project:string}) {
  const query=useQuery({queryKey:["model-directory",project],queryFn:()=>api(`/projects/${project}/models`,z.array(releaseSchema))});
  const [error,setError]=useState<unknown>(null),[busy,setBusy]=useState(false);
  async function approve(row:z.infer<typeof releaseSchema>) {
    setBusy(true);setError(null);
    try {await api(`/projects/${project}/models/${row.release.model_id}/approve`,z.unknown(),{method:"POST",body:JSON.stringify({release_digest:row.release_digest})});await query.refetch();}catch(e){setError(e);}finally{setBusy(false);}
  }
  return <section className="domain-directory" aria-label="模型目录"><h2>模型目录</h2><ErrorNotice error={query.error??error}/>{query.isPending?<p role="status">正在读取已核验运行包…</p>:null}
    {query.data?.length===0?<p>尚未接入已核验模型包。</p>:null}
    {query.data?.length?<div className="table-scroll"><table><thead><tr><th>模型</th><th>版本</th><th>当前项目执行授权</th><th>操作</th></tr></thead><tbody>{query.data.map(row=><tr key={row.release_digest}><td>{row.release.model_id==="ppci_mcdc"?"投影寻踪聚类":row.release.model_id==="ppr_ols"?"投影寻踪回归":row.release.model_id}<details><summary>运行包详情</summary><p>{row.release.package}</p><code>{row.release_digest}</code></details></td><td>{row.release.version}</td><td>{row.approved?"已批准":"未批准"}</td><td>{row.can_approve&&!row.approved?<button disabled={busy} type="button" onClick={()=>void approve(row)}>批准此固定版本</button>:"—"}</td></tr>)}</tbody></table></div>:null}
  </section>;
}
const checks=z.object({ready:z.boolean(),issues:z.array(z.object({code:z.string(),message:z.string().optional()}).passthrough())}).passthrough();
export function MatchingDirectory({project}:{project:string}) {
  const [task,setTask]=useState<CatalogRow|null>(null),[value,setValue]=useState<z.infer<typeof checks>|null>(null),[error,setError]=useState<unknown>(null),[busy,setBusy]=useState(false);
  async function inspect(row:CatalogRow) {
    setTask(row);setValue(null);setError(null);setBusy(true);
    try {setValue(await api(`/tasks/${row.id}/preflight`,checks));}catch(e){setError(e);}finally{setBusy(false);}
  }
  return <section className="domain-directory" aria-label="数据—模型匹配"><h2>数据—模型匹配</h2><p>选择已有任务核对其固定输入、方法和运行包；检查不会应用方法或启动模型。</p>
    <ManagedCatalog kind="tasks" project={project} extraActions={row=><button className="secondary" disabled={busy} onClick={()=>void inspect(row)}>核对匹配</button>}/>
    {task?<section aria-label="匹配检查"><h3>{task.name}</h3><ErrorNotice error={error}/>{busy?<p role="status">正在核对任务输入…</p>:null}{value?<><p>{value.ready?"当前任务预检通过":"尚有未满足的执行条件"}</p><ul>{value.issues.map((issue,i)=><li key={i}>{issue.message??issue.code}<details><summary>检查依据</summary><code>{issue.code}</code></details></li>)}</ul></>:null}</section>:null}
  </section>;
}
