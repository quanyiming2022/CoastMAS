"""Source/API reachability index for independent review; no implementation changes."""
from pathlib import Path
import ast,json,re,hashlib,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[2];O=R/'.review/evidence/runs/v3-audit-20260925';api=json.loads((O/'api.json').read_text());routes=[]
for f in (R/'next/src/coastmas_next').glob('*.py'):
 tree=ast.parse(f.read_text())
 for node in ast.walk(tree):
  if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
   for d in node.decorator_list:
    if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr in {'get','post','put','patch','delete'} and d.args and isinstance(d.args[0],ast.Constant):
     path=d.args[0].value;routes.append({'path':path,'method':d.func.attr.upper(),'source':str(f.relative_to(R)), 'line':node.lineno,'function':node.name,'in_current_openapi':path in api['capability_probe']['actual_paths']})
nav=[]
s=(R/'next/web/src/navigation.ts').read_text()
for line in s.splitlines():
 m=re.search(r'\.\.\.items\("([^"]+)"',line)
 if m:
  for id,label,path in re.findall(r'\["([^"]+)","([^"]+)"(?:,"([^"]+)")?\]',line):nav.append({'id':id,'center':m[1],'label':label,'path':path or None,'permission':'systemOnly' if '"systemOnly"' in line else 'manage' if '"manage"' in line else 'project','actual_link':any(n.get('href','') and n['href'].split('?')[0]==path for n in json.loads((O/'browser.json').read_text())['navigation'])})
tests=ET.parse(O/'backend-junit.xml');testcases=[{'name':x.attrib.get('name'),'class':x.attrib.get('classname'),'status':'FAIL' if x.find('failure') is not None or x.find('error') is not None else 'NOT_RUN' if x.find('skipped') is not None else 'PASS'} for x in tests.iter('testcase')]
value={'before_commit':'8d8ae10e8a53c3aa63501c0244b7e37739609c13','source_scope':'active next/src and next/web; vendored and legacy kernels are separately identified, not assumed reachable','navigation':nav,'counts':{'navigation_entries':len(nav),'actual_links':sum(x['actual_link'] for x in nav),'openapi_paths':len(api['capability_probe']['actual_paths']),'db_tables':len(api['capability_probe']['actual_tables']),'source_decorated_routes':len(routes),'backend_tests':len(testcases)},'routes':routes,'tables':api['capability_probe']['actual_tables'],'backend_tests':testcases,'note':'routes.json initial direct FastAPI introspection saw lazy include wrappers only; use this decorator + actual OpenAPI intersection index instead.'}
(O/'source-index.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');print(value['counts'])
