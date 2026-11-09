"""Materialize pinned DEF/SDC/scripts and verify external LEF/Liberty inputs.

python tools/prepare_openroad_designs.py --out work/openroad_reproduction
Then, in that directory: openroad -exit export_gcd.tcl (and export_aes.tcl,
regenerate_gcd.tcl). Re-extraction is optional: checked SPICE is shipped.
"""
import argparse,gzip,hashlib,json,shutil,urllib.request,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--cache",type=Path,help="reuse already downloaded LEF/Liberty after hash check")
    ap.add_argument("--direct",action="store_true",help="disable environment HTTP proxy")
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    src=ROOT/"examples/design_pdn/inputs"
    manifest=json.loads((src/"manifest.json").read_text())
    for name,record in manifest["files"].items():
        raw=(src/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=record["sha256"]:raise ValueError(name)
        (args.out/name.removesuffix(".gz")).write_bytes(gzip.decompress(raw) if name.endswith(".gz") else raw)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({})) if args.direct else urllib.request.build_opener()
    for name,record in manifest["external_runtime_inputs"].items():
        cached=args.cache/name if args.cache else None
        if cached and cached.exists():data=cached.read_bytes()
        else:
            for attempt in range(4):
                try:
                    with opener.open(record["url"],timeout=90) as response:data=response.read()
                    break
                except Exception:
                    if attempt==3:raise
                    time.sleep(1+attempt)
        if hashlib.sha256(data).hexdigest()!=record["sha256"]:raise ValueError(f"Unexpected library version: {name}")
        (args.out/name).write_bytes(data)
    print("Prepared pinned OpenROAD inputs in",args.out.resolve())

if __name__=="__main__":main()
