"""Independent delivered-grid and full valid-mask check, bounded memory."""
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import rasterio

root=Path('/Users/quanyiming/Projects/CoastMAS/next')
evidence=json.loads((root/'artifacts/real-full-domain-evidence.json').read_text())
state=Path(evidence['namespace'])
objects=state/'objects'
source_root=Path('/Users/quanyiming/Projects/data_quan/zhusanjiao/土地利用')
records={}
for purpose,run in evidence['runs'].items():
    started=time.time()
    manifest=json.loads((objects/run['result_key']).read_text())
    sources=[rasterio.open(source_root/a['name']) for a in evidence['assets']]
    output_path=objects/run['files'][0]['key']
    with rasterio.open(output_path) as output, rasterio.Env(GDAL_CACHEMAX=64*1024**2):
        assert output.shape==sources[0].shape==(9000,11416)
        assert output.crs==sources[0].crs
        assert output.transform==sources[0].transform
        predictors=sources if purpose=='cluster' else sources[:-1]
        count=0; mismatches=0; classes={}; minimum=None;maximum=None
        for _,window in output.block_windows(1):
            valid=np.ones((int(window.height),int(window.width)),dtype=bool)
            for dataset in predictors:
                values=dataset.read(1,window=window,masked=True)
                valid &= ~np.ma.getmaskarray(values) & np.isfinite(values.data)
            result=output.read(1,window=window,masked=True)
            actual=~np.ma.getmaskarray(result)&np.isfinite(result.data)
            mismatches+=int(np.count_nonzero(actual!=valid))
            count+=int(actual.sum())
            values=result.data[actual]
            if values.size:
                minimum=float(values.min()) if minimum is None else min(minimum,float(values.min()))
                maximum=float(values.max()) if maximum is None else max(maximum,float(values.max()))
                if purpose=='cluster':
                    labels,n=np.unique(values,return_counts=True)
                    for label,total in zip(labels,n):classes[str(int(label))]=classes.get(str(int(label)),0)+int(total)
        assert mismatches==0
        assert count==run['application']['predicted_cells']
        digest=hashlib.sha256(output_path.read_bytes()).hexdigest()
        assert digest==run['files'][0]['sha256']
        records[purpose]={'status':'PASS','valid_cells':count,'mask_mismatch_cells':mismatches,'shape':list(output.shape),'crs':str(output.crs),'output_sha256':digest,'full_domain_min':minimum,'full_domain_max':maximum,'class_counts':classes,'seconds':time.time()-started}
    for dataset in sources:dataset.close()
(root/'artifacts/real-output-integrity.json').write_text(json.dumps({'scope':'independent full delivered raster grid/mask/hash checks, not scientific validation','runs':records},ensure_ascii=False,indent=2))
print(json.dumps(records))
