"""Run HotSpot and FV teacher on saved run_design_pdn output without re-solving DC.

Linux: python tools/run_design_thermal.py --out results/design_pdn --hotspot /path/to/HotSpot
"""
import argparse,gzip,json,sys,gc
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stackem.design_pdn import Network,Node,Edge
from stackem.design_em import solve_metal_domains
from run_design_pdn import write_hotspot,save_json

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--hotspot",required=True);ap.add_argument("--em-domains",type=int,default=5)
    ap.add_argument("--case");args=ap.parse_args()
    for p in sorted(args.out.glob("*/case.json")):
        if args.case and p.parent.name!=args.case:continue
        out=p.parent.resolve();case=json.loads(p.read_text())
        with gzip.open(out/"network.json.gz","rt") as f:data=json.load(f)
        net=Network([Node(**n) for n in data["nodes"]],[Edge(**e) for e in data["edges"]],
            data["sinks"],{int(k):v for k,v in data["fixed"].items()},data["provenance"])
        del data;gc.collect()
        summary=json.loads((out/"summary.json").read_text())
        with np.load(out/"dc_solution.npz") as a:
            s={**summary,"voltage":a["voltage_V"],"current":a["current_A"]}
        t=write_hotspot(case,net,s,out,args.hotspot)
        result=solve_metal_domains(net,s["current"],t,thickness_by_layer={f"metal{i}":.2e-6 for i in range(1,11)},
            thickness_evidence="SCENARIO ONLY: uniform 0.20 um; not process-calibrated",times_s=[1e4,1e6,1e8],
            n_cells=12,max_domains=args.em_domains or None)
        save_json(out/"em_teacher.json",result)
        print(out.name,"HotSpot + FV completed",result["solved_domains"],"domains",flush=True)
        del net,s,t,result;gc.collect()

if __name__=="__main__":main()
