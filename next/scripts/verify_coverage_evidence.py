"""Independent original-vs-output pixel check; only explicitly provided evidence/config."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import ColorInterp
from rasterio.windows import Window
from sqlalchemy import create_engine, text

parser=argparse.ArgumentParser()
parser.add_argument('--config',type=Path,required=True)
parser.add_argument('--evidence',type=Path,required=True)
parser.add_argument('--source',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if args.output.exists():raise SystemExit('Evidence output must be new')
config=json.loads(args.config.read_text()); proof=json.loads(args.evidence.read_text())
engine=create_engine(config['database_url'])
with engine.connect() as c:
    key=c.execute(text("SELECT output_key FROM jobs WHERE id=:id AND status='succeeded'"),{'id':proof['run_id']}).scalar_one()
engine.dispose()
root=Path(config['storage_root']);result=json.loads((root/key).read_text())
output=root/result['data']['files'][0]['key']
valid_count=total=differences=0
with rasterio.open(args.source) as original, rasterio.open(output) as actual:
    assert (original.crs,original.transform,original.width,original.height)==(actual.crs,actual.transform,actual.width,actual.height)
    assert actual.dtypes==('uint8',) and actual.nodata is None
    for top in range(0,original.height,1024):
        for left in range(0,original.width,1024):
            window=Window(left,top,min(1024,original.width-left),min(1024,original.height-top))
            raw=original.read(1,window=window)
            valid=(original.read_masks(1,window=window)>0)&np.isfinite(raw.astype('float64')*original.scales[0]+original.offsets[0])
            if ColorInterp.alpha in original.colorinterp:
                valid&=original.read(original.colorinterp.index(ColorInterp.alpha)+1,window=window)>0
            observed=actual.read(1,window=window)
            differences+=int(np.count_nonzero(observed!=valid.astype('uint8')))
            valid_count+=int(valid.sum());total+=valid.size
assert differences==0
assert valid_count==proof['descriptor']['statistics']['valid_pixels']
with args.source.open('rb') as stream: source_hash=hashlib.file_digest(stream,'sha256').hexdigest()
with output.open('rb') as stream: output_hash=hashlib.file_digest(stream,'sha256').hexdigest()
assert source_hash==proof['source']['sha256']
assert output_hash==proof['download_sha256']
args.output.write_text(json.dumps({'status':'PASS','run_id':proof['run_id'],'source_sha256':source_hash,'output_sha256':output_hash,'total_pixels':total,'valid_pixels':valid_count,'invalid_pixels':total-valid_count,'pixel_differences':differences,'method':'Independent window reads of original source mask, scale/offset, finite values and alpha; no production operator invoked','scope':'full_grid','business_validated':False},indent=2)+'\n')
print(json.dumps({'status':'PASS','pixels':total,'differences':differences}))
