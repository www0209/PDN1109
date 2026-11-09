"""Reproduce design-derived 2-D references and explicit 3-D assembly cases.

Run from repository root: python tools/run_design_pdn.py --out results/design_pdn
Optional Linux HotSpot: --hotspot /path/to/HotSpot --em-domains 5
--em-domains 0 solves all eligible diffusion domains (may be slow).
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from dataclasses import asdict
import csv,gzip,json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stackem.design_pdn import read_spice,solve_dc,attach_def_widths,assemble_stack,power_bins
from stackem.hotspot_stack import HotSpotRunner,write_config,write_lcf
from stackem.design_em import solve_metal_domains

ROOT=Path(__file__).resolve().parents[1]

def save_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")

def scalar_results(net,s):
    vdd=max(net.fixed.values())
    return {"nodes_including_ground":len(net.nodes),"edges":len(net.edges),
        "loads":len(net.sinks),"edge_types":dict(Counter(e.kind for e in net.edges)),
        "worst_drop_V":vdd-s["min_voltage_V"],
        **{k:v for k,v in s.items() if isinstance(v,(float,int))}}

def csv_rows(path):
    with gzip.open(path,"rt",newline="") as f:return list(csv.reader(f))[1:]

def compare_openroad(net,s,path):
    def key(n):return (n.layer,round(n.x*1e6,4),round(n.y*1e6,4))
    currents=defaultdict(list)
    voltages=defaultdict(list)
    for i,n in enumerate(net.nodes):
        if n.x is not None: voltages[key(n)].append(s["voltage"][i])
    for e,i in zip(net.edges,s["current"]):
        a,b=net.nodes[e.a],net.nodes[e.b]
        if a.x is None or b.x is None or e.kind=="contact":continue
        currents[tuple(sorted([key(a),key(b)]))].append(abs(i))
    errs=[];ref=[];missing=0
    for row in csv_rows(path.with_name(path.name+"_em.csv.gz")):
        k=tuple(sorted([(row[0],float(row[1]),float(row[2])),(row[3],float(row[4]),float(row[5]))]))
        if k not in currents:missing+=1;continue
        value=float(row[6]); predicted=sum(currents[k])
        errs.append(abs(predicted-abs(value)));ref.append(abs(value))
    verr=[];vmissing=0
    for row in csv_rows(path.with_name(path.name+"_voltage.csv.gz")):
        k=(row[2],float(row[3]),float(row[4]))
        if k not in voltages:vmissing+=1;continue
        verr.append(min(abs(v-float(row[5])) for v in voltages[k]))
    result={"current_matched_rows":len(errs),"current_unmatched_rows":missing,
            "current_max_abs_error_A":max(errs),
            "current_RMSE_over_max_reference":float(np.sqrt(np.mean(np.array(errs)**2))/max(ref)),
            "voltage_matched_rows":len(verr),"voltage_unmatched_rows":vmissing,
            "voltage_max_abs_error_V":max(verr) if verr else None,
            "note":"Independent SciPy DC vs executed OpenROAD 26Q2; SPICE/report values are rounded"}
    if missing or result["current_RMSE_over_max_reference"]>1e-3:
        raise AssertionError(f"OpenROAD current comparison failed: {result}")
    if vmissing or not verr or max(verr)>2e-6:
        raise AssertionError(f"OpenROAD voltage comparison failed: {result}")
    return result

def write_hotspot(case,net,s,out,hotspot):
    """Rectangular thermal frame; for heterogeneous stack unused area is an
    explicitly assumed passive silicon carrier. No square clipping/rescaling.
    """
    bbox=case["thermal_frame_m"]; x0,y0,x1,y1=bbox
    nx=ny=16; thermal=case["thermal"];ambient=thermal["ambient_K"]
    grids=[];layers=[];names=[];powers=[]
    for k in range(len(case["dies"])):
        die=f"D{k}";grid=power_bins(net,s["voltage"],die=die,bbox_m=bbox,nx=nx,ny=ny)
        # Deposit on-die resistive loss at endpoint bins. Package loss is external.
        for e,i in zip(net.edges,s["current"]):
            if e.kind=="package":continue
            for node in (net.nodes[e.a],net.nodes[e.b]):
                if node.die==die and node.x is not None:
                    ix=min(nx-1,max(0,int((node.x-x0)/(x1-x0)*nx)))
                    iy=min(ny-1,max(0,int((node.y-y0)/(y1-y0)*ny)))
                    grid[iy,ix]+=.5*i*i*e.resistance
        grids.append(grid); lines=[]
        for iy in range(ny):
            for ix in range(nx):
                name=f"D{k}_{ix}_{iy}";names.append(name);powers.append(grid[iy,ix])
                lines.append(f"{name}\t{(x1-x0)/nx:.12g}\t{(y1-y0)/ny:.12g}\t{ix*(x1-x0)/nx:.12g}\t{iy*(y1-y0)/ny:.12g}")
        (out/f"D{k}.flp").write_text("\n".join(lines)+"\n")
        np.savetxt(out/f"D{k}_power_W.csv",grid,delimiter=",")
        layers.append(dict(lateral="Y",power="Y",cp=1.75e6,res=.01,thick=thermal["die_thickness_m"],flp=f"D{k}.flp"))
        name="bond" if k<len(case["dies"])-1 else "tim"
        (out/f"{name}.flp").write_text(f"{name}\t{x1-x0:.12g}\t{y1-y0:.12g}\t0\t0\n")
        layers.append(dict(lateral="Y",power="N",cp=1.6e6 if name=="bond" else 4e6,
            res=1/thermal["bond_k_W_mK"] if name=="bond" else .25,
            thick=thermal["bond_thickness_m"] if name=="bond" else 20e-6,flp=f"{name}.flp"))
    (out/"stack.ptrace").write_text("\t".join(names)+"\n"+"\t".join(f"{p:.12g}" for p in powers)+"\n")
    write_lcf(str(out/"stack.lcf"),layers)
    audit={"heat_W":float(sum(powers)),"load_plus_nonpackage_loss_W":float(s["load_power_W"]+
        sum(i*i*e.resistance for e,i in zip(net.edges,s["current"]) if e.kind!="package")),
        "frame_m":bbox,"parameters":thermal,"padding":case["thermal_padding"],
        "power_bins":"16x16 in physical frame; upward-y rows; VI load + endpoint-deposited I²R",
        "coupling":"one-way DC -> thermal; fixed extracted resistance and fixed current loads"}
    if not np.isclose(audit["heat_W"],audit["load_plus_nonpackage_loss_W"],rtol=1e-10):
        raise AssertionError("Thermal deposition does not conserve power")
    if not hotspot:
        audit["status"]="power maps exported; temperature solver not requested"
        save_json(out/"thermal.json",audit);return None
    runner=HotSpotRunner(hotspot)
    write_config(str(out/"stack.config"),runner.template,{"ambient":ambient,"r_convec":.5,
        "s_sink":.03,"t_sink":.0069,"s_spreader":.012,"t_spreader":.001,
        "t_interface":20e-6,"k_interface":4.,"grid_rows":32,"grid_cols":32,"model_type":"grid"})
    ts=runner.run(str(out),"stack.lcf","stack.ptrace","stack.config","stack",rows=32,cols=32)
    from scipy.ndimage import map_coordinates
    temps=np.full(len(net.nodes),ambient)
    for k in range(len(case["dies"])):
        indices=[i for i,n in enumerate(net.nodes) if n.die==f"D{k}" and n.x is not None]
        xx=np.array([net.nodes[i].x for i in indices]);yy=np.array([net.nodes[i].y for i in indices])
        coords=np.array([(1-(yy-y0)/(y1-y0))*32-.5,(xx-x0)/(x1-x0)*32-.5])
        temps[indices]=map_coordinates(ts[2*k],coords,order=1,mode="nearest")
    audit.update(status="HotSpot executed",max_temperature_K=float(temps.max()),
                 die_max_K=[float(ts[2*k].max()) for k in range(len(case["dies"]))])
    save_json(out/"thermal.json",audit)
    np.save(out/"node_temperature_K.npy",temps)
    return temps

def export_network(net,s,out):
    with gzip.open(out/"network.json.gz","wt",encoding="utf-8") as f:
        json.dump(asdict(net),f,ensure_ascii=False)
    np.savez_compressed(out/"dc_solution.npz",voltage_V=s["voltage"],current_A=s["current"])
    with gzip.open(out/"segments.csv.gz","wt",newline="") as f:
        w=csv.writer(f);w.writerow(["name","a","b","type","R_ohm","I_A","L_m","W_m","H_m","geometry_source"])
        for e,i in zip(net.edges,s["current"]):w.writerow([e.name,e.a,e.b,e.kind,e.resistance,i,e.length_m,e.width_m,e.thickness_m,e.geometry_source])

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--config",type=Path,default=ROOT/"examples/design_pdn/cases.json")
    ap.add_argument("--hotspot");ap.add_argument("--em-domains",type=int,default=5)
    ap.add_argument("--case",help="one named 3D case, otherwise all")
    args=ap.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    inputs=ROOT/"examples/design_pdn/inputs";config=json.loads(args.config.read_text(encoding="utf-8"))
    from hashlib import sha256
    manifest=json.loads((inputs/"manifest.json").read_text(encoding="utf-8"))
    for name,record in manifest["files"].items():
        if sha256((inputs/name).read_bytes()).hexdigest()!=record["sha256"]:
            raise ValueError(f"Input checksum mismatch: {name}")
    nets={};summary={"references":{},"cases":{},"source_manifest":manifest}
    for name in sorted(set(d for case in config["cases"] for d in case["dies"])):
        net=read_spice(inputs/f"{name}_export.sp.gz",coordinate_unit_m=5e-10,
            coordinate_evidence=f"Nangate45_data_{name}.def: UNITS DISTANCE MICRONS 2000")
        attach_def_widths(net,inputs/f"Nangate45_data_{name}.def.gz")
        nets[name]=net;s=solve_dc(net)
        summary["references"][name]={**scalar_results(net,s),"geometry":net.provenance,
            "openroad_validation":compare_openroad(net,s,inputs/name)}
        print(name,summary["references"][name]["edges"],"reference checked",flush=True)
    for case in config["cases"]:
        if args.case and args.case!=case["name"]:continue
        target=out/case["name"];target.mkdir(exist_ok=True)
        dies=[nets[d] for d in case["dies"]]
        net,maps=assemble_stack(dies,transforms=case["transforms"],**case["assembly"])
        s=solve_dc(net); export_network(net,s,target)
        stats=scalar_results(net,s);stats["provenance"]=net.provenance
        stats["die_worst_drop_V"]=[max(net.fixed.values())-min(s["voltage"][v] for k,v in m.items() if k!=0) for m in maps]
        # Bond sweep keeps topology, loads, package and RDL fixed.
        sweep=[]
        for resistance in (.01,.1,1.):
            alternate=dict(case["assembly"],bond_resistance_ohm=resistance)
            nn,_=assemble_stack(dies,transforms=case["transforms"],**alternate)
            ss=solve_dc(nn);sweep.append({"bond_R_ohm":resistance,**scalar_results(nn,ss)})
        stats["bond_sweep"]=sweep
        if any(b["worst_drop_V"]<a["worst_drop_V"]-1e-9 for a,b in zip(sweep,sweep[1:])):
            raise AssertionError("Bond resistance sweep unexpectedly improved worst drop")
        temps=write_hotspot(case,net,s,target,args.hotspot)
        if temps is not None:
            evidence="SCENARIO ONLY: uniform 0.20 um thickness; not measured or extracted from LEF/DEF"
            thickness={f"metal{i}":.2e-6 for i in range(1,11)}
            em_result=solve_metal_domains(net,s["current"],temps,thickness_by_layer=thickness,
                thickness_evidence=evidence,times_s=[1e4,1e6,1e8],n_cells=12,
                max_domains=args.em_domains or None)
            save_json(target/"em_teacher.json",em_result)
        save_json(target/"case.json",case);save_json(target/"summary.json",stats)
        summary["cases"][case["name"]]=stats
        print(case["name"],stats["edges"],"edges; drop",stats["worst_drop_V"],flush=True)
    if args.case and not summary["cases"]:raise ValueError("Unknown case name")
    for case in config["cases"]:
        existing=out/case["name"]/"summary.json"
        if existing.exists() and case["name"] not in summary["cases"]:
            summary["cases"][case["name"]]=json.loads(existing.read_text())
    save_json(out/"summary.json",summary)

if __name__=="__main__":main()
