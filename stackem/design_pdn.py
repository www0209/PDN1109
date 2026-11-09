"""Lossless DC import and explicit 3-D assembly of design-derived PDNs.

This module does NOT infer silicon geometry from a resistor. Coordinates require
an explicit scale. Metal/via/contact edges are retained individually. Only
linear R/I networks and ground-referenced DC voltage sources are accepted.
"""
from __future__ import annotations

import gzip
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import spsolve


@dataclass
class Node:
    name: str
    x: float | None = None
    y: float | None = None
    layer: str = "unknown"
    die: str = "D0"


@dataclass
class Edge:
    name: str
    a: int
    b: int
    resistance: float
    kind: str = "unclassified"
    length_m: float | None = None
    width_m: float | None = None
    thickness_m: float | None = None
    geometry_source: str = "not provided"


@dataclass
class Network:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    # Positive sink is current removed from this node.
    sinks: list[tuple[int, int, float, str]] = field(default_factory=list)
    fixed: dict[int, float] = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)


def spice_number(token):
    token = token.split("=", 1)[-1]
    m = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(meg|[tgkmunpf])?", token, re.I)
    if not m:
        raise ValueError(f"Unsupported SPICE number: {token}")
    scale = {None: 1., "t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3,
             "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}
    return float(m[1]) * scale[m[2].lower() if m[2] else None]


def node_coordinates(name, unit_m):
    # PDNSim current export; BeGAN actual and documented legacy conventions.
    for pattern in (r"(?:ITermNode|BPinNode|Node)_(metal\d+)_(-?\d+)_(-?\d+)",
                    r"n\d+_(m\d+)_(-?\d+)_(-?\d+)"):
        m = re.fullmatch(pattern, name)
        if m:
            return float(m[2])*unit_m, float(m[3])*unit_m, m[1]
    m = re.fullmatch(r"n\d+_(-?\d+)_(-?\d+)_(\d+)", name)
    if m:
        return float(m[1])*unit_m, float(m[2])*unit_m, "m"+m[3]
    return None, None, "unknown"


def read_spice(path, *, coordinate_unit_m, coordinate_evidence, die="D0"):
    if not np.isfinite(coordinate_unit_m) or coordinate_unit_m <= 0 or not coordinate_evidence:
        raise ValueError("An explicit coordinate scale and its evidence are required")
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig") as f:
        lines = f.readlines()
    net = Network(provenance={"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                             "coordinate_unit_m": coordinate_unit_m,
                             "coordinate_evidence": coordinate_evidence})
    names = {}
    def node(s):
        if s.lower() in ("0", "gnd"):
            s = "0"
        if s not in names:
            x, y, layer = node_coordinates(s, coordinate_unit_m)
            names[s] = len(net.nodes)
            net.nodes.append(Node(s, x, y, layer, die))
        return names[s]
    ground = node("0")
    net.fixed[ground] = 0.0
    seen = set()
    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        if line.startswith("."):
            if line.split()[0].upper() not in (".OP", ".END", ".OPTION", ".OPTIONS", ".SAVE", ".PRINT"):
                raise ValueError(f"{path.name}:{lineno}: unsupported directive {line}")
            continue
        t = line.split()
        if t[0][0].upper() not in "RIV" or len(t) not in (4, 5):
            raise ValueError(f"{path.name}:{lineno}: unsupported element {line}")
        if t[0].lower() in seen:
            raise ValueError(f"duplicate element {t[0]}")
        seen.add(t[0].lower())
        if len(t) == 5 and t[3].upper() != "DC":
            raise ValueError(f"only DC is supported: {line}")
        a, b, val = node(t[1]), node(t[2]), spice_number(t[-1])
        if not np.isfinite(val):
            raise ValueError("nonfinite value")
        if t[0][0].upper() == "R":
            if val <= 0 or a == b:
                raise ValueError(f"nonpositive/self resistor {line}")
            na, nb = net.nodes[a], net.nodes[b]
            kind, length = "unclassified", None
            if na.x is not None and nb.x is not None:
                length = abs(na.x-nb.x)+abs(na.y-nb.y)
                kind = "contact" if length == 0 and na.layer == nb.layer else (
                    "via" if na.layer != nb.layer else "metal")
                if kind == "metal" and abs(na.x-nb.x)>1e-15 and abs(na.y-nb.y)>1e-15:
                    kind = "diagonal_unresolved"
                if "ITermNode" in na.name or "ITermNode" in nb.name:
                    kind = "contact"  # PDNSim's pin-attachment edge, not a routed metal segment.
            net.edges.append(Edge(t[0], a, b, val, kind, length))
        elif t[0][0].upper() == "I":
            net.sinks.append((a, b, val, t[0]))
        else:
            if b != ground:
                raise ValueError("Floating voltage source requires MNA; not silently approximated")
            if a in net.fixed and not np.isclose(net.fixed[a], val, rtol=0, atol=1e-14):
                raise ValueError("conflicting voltage sources")
            net.fixed[a] = val
    if not net.edges:
        raise ValueError("empty resistor network")
    return net


def solve_dc(net):
    n = len(net.nodes)
    a = np.array([e.a for e in net.edges]); b = np.array([e.b for e in net.edges])
    r = np.array([e.resistance for e in net.edges])
    if not np.all(np.isfinite(r) & (r > 0)):
        raise ValueError("All resistance values must be positive and finite")
    g = 1/r
    mat = coo_matrix((np.r_[g,g,-g,-g], (np.r_[a,b,a,b],np.r_[a,b,b,a])),shape=(n,n)).tocsr()
    _, labels = connected_components(mat, directed=False)
    supplied = set(labels[list(net.fixed)])
    if any(label not in supplied for label in labels):
        raise ValueError("Floating resistor component: no voltage source")
    demand = np.zeros(n)
    for u,v,i,_ in net.sinks:
        demand[u] += i; demand[v] -= i
    fixed = np.array(sorted(net.fixed), dtype=int)
    free = np.setdiff1d(np.arange(n),fixed)
    # Solve relative to a source in each component: avoid subtracting 1.1 V
    # across milliohm contacts when the relevant drop is only microvolts.
    origins={int(labels[k]):net.fixed[k] for k in fixed}
    offset=np.array([origins[int(label)] for label in labels])
    delta=np.zeros(n)
    delta[fixed]=[net.fixed[k]-offset[k] for k in fixed]
    delta[free] = spsolve(mat[free][:,free], -demand[free]-mat[free][:,fixed]@delta[fixed])
    voltage=offset+delta
    if not np.all(np.isfinite(voltage)):
        raise ValueError("Nonfinite DC solution")
    current = (delta[a]-delta[b])/r
    residual = mat@delta+demand
    # Source power balances voltage-dependent load power plus every I²R loss.
    load_power = sum((voltage[u]-voltage[v])*i for u,v,i,_ in net.sinks)
    source_power = float(voltage[fixed]@residual[fixed])
    loss = float(np.sum(current**2*r))
    scale_i = max(sum(abs(i) for _,_,i,_ in net.sinks), 1e-15)
    maxres = float(np.max(np.abs(residual[free]))) if len(free) else 0.0
    balance = abs(source_power-load_power-loss)/max(abs(source_power),1e-15)
    if maxres > 1e-7*scale_i or balance > 1e-6:
        raise ArithmeticError(f"DC conservation failed: KCL={maxres}, power={balance}")
    active = [i for i,node in enumerate(net.nodes) if node.name != "0"]
    return {"voltage":voltage, "current":current, "source_current":residual[fixed],
            "fixed_nodes":fixed, "min_voltage_V":float(np.min(voltage[active])),
            "kcl_max_A":maxres,"kcl_relative":maxres/scale_i,
            "load_power_W":float(load_power),"resistive_loss_W":loss,
            "source_power_W":source_power,"power_balance_relative":float(balance)}


def attach_def_widths(net, def_path):
    """Match each metal edge to a covering VDD SPECIALNET stripe, never via R."""
    with (gzip.open(def_path,"rt") if str(def_path).endswith(".gz") else open(def_path,encoding="utf-8")) as f:
        text=f.read()
    units = float(re.search(r"UNITS DISTANCE MICRONS (\d+)",text)[1])
    scale = 1e-6/units
    if not np.isclose(scale,net.provenance["coordinate_unit_m"], rtol=1e-12,atol=0):
        raise ValueError("DEF/SPICE coordinate scale mismatch")
    special = text.split("SPECIALNETS",1)[1].split("END SPECIALNETS",1)[0]
    match = re.search(r"(?:^|\n)\s*- VDD\b(.*?)(?:;)",special,re.S)
    if not match:
        raise ValueError("No VDD SPECIALNET")
    stripes=[]
    pattern=r"(?:ROUTED|NEW)\s+(\w+)\s+(\d+)\s+\+ SHAPE \w+\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*\(\s*([*\d-]+)\s+([*\d-]+)\s*\)"
    for m in re.finditer(pattern,match[1]):
        layer,w,x,y,xx,yy=m.groups(); x,y=int(x),int(y)
        xx=x if xx=="*" else int(xx); yy=y if yy=="*" else int(yy)
        if int(w)>0: stripes.append((layer,int(w)*scale,x*scale,y*scale,xx*scale,yy*scale))
    lookup=defaultdict(list)
    for stripe in stripes:
        layer,w,x,y,xx,yy=stripe
        axis="H" if y==yy else "V"
        lookup[(layer,axis,round(y if axis=="H" else x,14))].append(stripe)
    for edge in net.edges:
        if edge.kind != "metal": continue
        a,b=net.nodes[edge.a],net.nodes[edge.b]
        widths=set()
        axis="H" if abs(a.y-b.y)<1e-15 else "V"
        candidates=lookup[(a.layer,axis,round(a.y if axis=="H" else a.x,14))]
        for layer,w,x,y,xx,yy in candidates:
            if all(min(x,xx)-1e-14<=p.x<=max(x,xx)+1e-14 and min(y,yy)-1e-14<=p.y<=max(y,yy)+1e-14 for p in (a,b)):
                widths.add(round(w,15))
        if len(widths)==1:
            edge.width_m=widths.pop(); edge.geometry_source=f"{Path(def_path).name}:VDD SPECIALNETS"
    diearea=re.search(r"DIEAREA\s*\(\s*(\d+)\s+(\d+)\s*\)\s*\(\s*(\d+)\s+(\d+)\s*\)",text)
    net.provenance["die_bbox_m"]=[int(x)*scale for x in diearea.groups()]
    net.provenance["width_coverage"]={"matched":sum(e.width_m is not None for e in net.edges),
        "metal_edges":sum(e.kind=="metal" for e in net.edges), "thickness":"not in DEF; requires independent evidence"}
    return net


def assemble_stack(dies, *, bond_resistance_ohm, package_resistance_ohm,
                   rdl_sheet_ohm, rdl_width_m, transforms=None):
    """Replace per-die ideal feeds by ONE package supply and finite links.

    dies have a common nominal voltage. Each upper original feed connects to
    the nearest lower original feed through a Manhattan RDL + vertical bond.
    This is an explicit assembly hypothesis, NOT a 3-D place-and-route result.
    No width, current or die dimensions are scaled. Return node maps as well.
    """
    if min(bond_resistance_ohm, package_resistance_ohm,rdl_sheet_ohm,rdl_width_m)<=0:
        raise ValueError("Strictly positive assembly parameters required")
    out=Network(nodes=[Node("0"),Node("package_VDD")],fixed={0:0.0})
    maps=[]; ports=[]; assumptions=[]; nominal=None
    transforms=transforms or [{} for _ in dies]
    if len(transforms)!=len(dies): raise ValueError("one transform per die required")
    for k,(net,tf) in enumerate(zip(dies,transforms)):
        vals={v for i,v in net.fixed.items() if net.nodes[i].name!="0"}
        if len(vals)!=1: raise ValueError("One VDD domain per die required")
        v=vals.pop()
        if nominal is None: nominal=v
        if abs(v-nominal)>1e-12: raise ValueError("Different VDD domains cannot be shorted")
        extent=net.provenance.get("die_bbox_m")
        if extent is None: raise ValueError("Physical die extent required for assembly")
        x0,y0,x1,y1=extent; rotation=tf.get("rotation_deg",0)
        if rotation not in (0,180): raise ValueError("Only 0/180 degree in-plane rotation supported")
        dx,dy=tf.get("offset_m",[0,0]); mapping={}
        for i,node in enumerate(net.nodes):
            if node.name=="0": mapping[i]=0; continue
            x,y=node.x,node.y
            if x is not None:
                if rotation==180: x,y=x0+x1-x,y0+y1-y
                x,y=x+dx,y+dy
            mapping[i]=len(out.nodes)
            out.nodes.append(Node(f"D{k}/{node.name}",x,y,node.layer,f"D{k}"))
        for e in net.edges:
            out.edges.append(Edge(f"D{k}/{e.name}",mapping[e.a],mapping[e.b],e.resistance,
                                  e.kind,e.length_m,e.width_m,e.thickness_m,e.geometry_source))
        out.sinks.extend((mapping[a],mapping[b],i,f"D{k}/{name}") for a,b,i,name in net.sinks)
        ports.append([mapping[i] for i in net.fixed if net.nodes[i].name!="0"])
        if any(out.nodes[i].x is None for i in ports[-1]): raise ValueError("Unlocated feed")
        maps.append(mapping)
    out.fixed[1]=nominal
    for j,p in enumerate(ports[0]):
        out.edges.append(Edge(f"package_{j}",1,p,package_resistance_ohm,"package"))
    for k in range(1,len(dies)):
        for j,p in enumerate(ports[k]):
            up=out.nodes[p]
            distances=[abs(up.x-out.nodes[q].x)+abs(up.y-out.nodes[q].y) for q in ports[k-1]]
            index=int(np.argmin(distances)); q=ports[k-1][index]; length=distances[index]
            land=len(out.nodes)
            out.nodes.append(Node(f"D{k}/landing{j}",up.x,up.y,"interface",f"D{k}"))
            rdl_r=rdl_sheet_ohm*length/rdl_width_m
            # At coincident sites no lateral edge or artificial epsilon resistor.
            if length>1e-15:
                out.edges.append(Edge(f"rdl_{k}_{j}",q,land,rdl_r,"rdl",length,rdl_width_m,
                                      geometry_source="assembly assumption; Manhattan length"))
                lower=land
            else:
                out.nodes.pop(); lower=q
            out.edges.append(Edge(f"bond_{k}_{j}",lower,p,bond_resistance_ohm,"bond",
                                  geometry_source="assembly assumption; lumped vertical path"))
            assumptions.append({"upper":up.name,"lower":out.nodes[q].name,"rdl_length_m":length,
                                "rdl_R_ohm":rdl_r,"bond_R_ohm":bond_resistance_ohm})
    out.provenance={"class":"design-derived hypothetical 3D assembly", "dies":[n.provenance for n in dies],
                    "transforms":transforms,"links":assumptions,
                    "package_R_per_port_ohm":package_resistance_ohm,
                    "return_network":"ideal common VSS; VDD-only analysis",
                    "bond_scope":"lumped interdie vertical path; TSV+bond not separately extracted"}
    return out,maps


def power_bins(net, voltage, *, die, bbox_m, nx=16, ny=16):
    """Conserve actual DC load power; no current_fraction or uniform block load."""
    x0,y0,x1,y1=bbox_m
    if x1<=x0 or y1<=y0: raise ValueError("invalid rectangular bbox")
    grid=np.zeros((ny,nx)); total=0.
    for a,b,i,_ in net.sinks:
        node=net.nodes[a]
        if node.die!=die: continue
        if net.nodes[b].name!="0" or node.x is None or i<0:
            raise ValueError("Thermal map requires located, nonnegative ground-referenced loads")
        if not (x0-1e-14<=node.x<=x1+1e-14 and y0-1e-14<=node.y<=y1+1e-14):
            raise ValueError("Load falls outside physical die; cropping is forbidden")
        ix=min(nx-1,max(0,int((node.x-x0)/(x1-x0)*nx)))
        iy=min(ny-1,max(0,int((node.y-y0)/(y1-y0)*ny)))
        p=(voltage[a]-voltage[b])*i
        if p<0: raise ValueError("Negative load power: DC operating point invalid")
        grid[iy,ix]+=p; total+=p
    if not np.isclose(grid.sum(),total,rtol=1e-12,atol=1e-15): raise ArithmeticError("power loss in binning")
    return grid
