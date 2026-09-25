import { useId, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronDown, ChevronRight } from "lucide-react";
import { activeNavigation, navigationURL, v3Centers, visibleNavigation, type NavigationItem } from "./navigation";

export function V3Navigation({project,canManage,systemAdmin,taskPurpose}: {project:string;canManage:boolean;systemAdmin:boolean;taskPurpose:string|null}) {
  const location=useLocation(), prefix=useId();
  const items=visibleNavigation(canManage,systemAdmin);
  const active=activeNavigation(location.pathname,location.search,taskPurpose);
  const group=items.find(item=>item.id===active)?.group;
  const [groups,setGroups]=useState<{path:string;open:string[]}>(()=>{
    try { const saved:unknown=JSON.parse(localStorage.getItem("coastmas.v3.navigation.groups")??"null");
      if(Array.isArray(saved)&&saved.every(x=>typeof x==="string"))return {path:location.pathname,open:[...new Set([...saved,...(group?[group]:[])])]};
    }catch { /* UI preferences cannot prevent navigation. */ }
    return {path:location.pathname,open:group?[group]:["research","data"]};
  });
  if(groups.path!==location.pathname) setGroups({path:location.pathname,open:group&&!groups.open.includes(group)?[...groups.open,group]:groups.open});
  const open=groups.open;
  function toggle(id:string) {
    setGroups(previous=>{const next=previous.open.includes(id)?previous.open.filter(x=>x!==id):[...previous.open,id];
      try {localStorage.setItem("coastmas.v3.navigation.groups",JSON.stringify(next));}catch {/* optional */}
      return {...previous,open:next};
    });
  }
  function entry(item:NavigationItem) {
    const Icon=item.icon;
    return <li key={item.id}>{item.path ? <Link to={navigationURL(item,project)} title={item.label} aria-label={item.label} aria-current={active===item.id?"page":undefined} className={active===item.id?"active":""}>
      <Icon size={16} aria-hidden="true"/><span className="nav-short" aria-hidden="true">{item.short}</span><span className="nav-full">{item.label}</span>
    </Link>:<button type="button" disabled className="nav-unavailable" title={`${item.label}：开发中，尚未接通可用页面`}><Icon size={16} aria-hidden="true"/><span>{item.label}</span><small>开发中</small></button>}</li>;
  }
  return <nav aria-label="主要功能">{v3Centers.map(center=>{
    const children=items.filter(item=>item.group===center.id);
    if(!children.length)return null;
    if(center.id==="workspace")return <ul className="nav-workspace" key={center.id}>{children.map(entry)}</ul>;
    const expanded=open.includes(center.id),id=`${prefix}-${center.id}`;
    return <div role="group" className="business-nav-group" key={center.id} aria-label={center.label}>
      <button type="button" className="nav-group-toggle" aria-expanded={expanded} aria-controls={id} onClick={()=>toggle(center.id)}><span>{center.label}</span>{expanded?<ChevronDown size={14}/>:<ChevronRight size={14}/>}</button>
      <ul id={id} hidden={!expanded}>{children.map(entry)}</ul>
    </div>;
  })}</nav>;
}
