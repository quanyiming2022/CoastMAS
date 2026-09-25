"""Create a separate audit namespace and engineering inputs; never reset a live system."""
from pathlib import Path
import sys, json, hashlib, subprocess, shutil, datetime, importlib.util, argparse

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'next/src'), str(ROOT/'next/vendor')]
parser=argparse.ArgumentParser();parser.add_argument('--web-root',type=Path,help='Use an independently built frontend directory; otherwise read the local live web_root only');args=parser.parse_args()
NAME = 'v3-audit-20260925'
OUT = ROOT/'.review/evidence/runs'/NAME
OUT.mkdir(parents=True, exist_ok=True)
PRIVATE = ROOT/'next/.state'/NAME
if PRIVATE.exists():
    raise SystemExit('Audit namespace already exists; preserve it and use its existing config.')
spec=importlib.util.spec_from_file_location('bootstrap',ROOT/'next/scripts/bootstrap.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
created=module.initialize(NAME,'audit-admin@example.test',[])
settings_path=Path(created['config'])
config=json.loads(settings_path.read_text())
live={} if args.web_root else json.loads((ROOT/'next/.state/unified-business-20260924/settings.json').read_text())
config['web_root']=str(args.web_root.resolve()) if args.web_root else live['web_root']
if live.get('runtime_catalog'):config['runtime_catalog']=live['runtime_catalog']
fixtures=PRIVATE/'fixtures';fixtures.mkdir()
sources=PRIVATE/'authorized-source';sources.mkdir()
config['local_sources']=[str(sources)]
settings_path.write_text(json.dumps(config,indent=2))
import numpy as np, rasterio, fiona, zipfile
from rasterio.transform import from_origin
def raster(name,bands,descriptions,tags=None):
    data=np.array(bands,dtype='float32')
    with rasterio.open(fixtures/name,'w',driver='GTiff',height=data.shape[1],width=data.shape[2],count=len(data),dtype='float32',crs='EPSG:32649',transform=from_origin(400000,2500000,30,30),nodata=-9999) as dst:
        dst.write(data)
        for i,d in enumerate(descriptions,1):dst.set_band_description(i,d)
        dst.update_tags(**(tags or {}))
    return fixtures/name
raster('red-nir.tif',[[[.2,.1,.3],[.2,-9999,.4]],[[.6,.3,.5],[.4,-9999,.8]]],['red','nir'])
raster('red-only.tif',[[[.2,.1],[.3,.4]]],['red'])
(fixtures/'observations.csv').write_text('id,value\na,2\nb,5\n')
(fixtures/'yearbook.csv').write_text('district,year,population\na,2022,100\nb,2022,200\n')
(fixtures/'bad.csv').write_text('id,value\na,"unterminated\n')
(fixtures/'simple_model.py').write_text('def predict(values):\n    return [value * 2 for value in values]\n')
features=[{'type':'Feature','id':code,'properties':{'unit_id':code,'cost':cost},'geometry':{'type':'Polygon','coordinates':[[[x,22],[x+.001,22],[x+.001,22.001],[x,22.001],[x,22]]]}} for code,x,cost in [('a',113,2),('b',113.001,5)]]
(fixtures/'units.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features}))
shape=fixtures/'shapefile';shape.mkdir()
with fiona.open(shape/'units.shp','w',driver='ESRI Shapefile',crs='EPSG:4326',schema={'geometry':'Polygon','properties':{'unit_id':'str','cost':'int'}}) as dst:
    for f in features:dst.write(f)
with zipfile.ZipFile(fixtures/'units.zip','w') as z:
    for p in shape.iterdir():z.write(p,p.name)
for name in ['red-nir.tif','observations.csv']:shutil.copy2(fixtures/name,sources/name)
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
baseline={'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'before_commit':head,
 'live_url':'http://127.0.0.1:58013','audit_url':'http://127.0.0.1:58125',
 'served_build_directory':Path(config['web_root']).name,
 'served_index_sha256':hashlib.sha256((Path(config['web_root'])/'index.html').read_bytes()).hexdigest(),
 'audit_database_kind':'SQLite; clean isolated namespace','live_database_changed':False,
 'original_business_files_changed':False,'fixture_kind':'engineering_fixture',
 'runtime_catalog_available':bool(config.get('runtime_catalog')),
 'scope_priority':['latest explicit user decisions','post-V3 specialist supplements','CoastMAS V3.0','master spec engineering details','legacy V2/pages/routes'],
 'source_requirement':'Current conversation V3 IA/task definitions and supplied audit request; no unprovided standalone V3 document assumed.'}
(OUT/'baseline.json').write_text(json.dumps(baseline,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'config':str(settings_path),'access_file':str(PRIVATE/'settings-access.json'),'evidence':str(OUT)},ensure_ascii=False))
