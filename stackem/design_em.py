"""Auditable bridge from extracted PDNs to StackEM's existing FV teacher.

The default boundary assumption is diffusion blocking at vias/contacts. All
connected same-layer metal edges stay in one domain, including branches. A
domain containing unresolved widths is rejected as a whole, never truncated.
Material/thickness and temperature are explicit scenario inputs, not PDK signoff.
"""
from collections import defaultdict,Counter
import numpy as np
from .constants import EMParams
from .korhonen_fdm import TreeFDM
from .thermal_profile import SegmentProfile


def metal_domains(net):
    adjacency=defaultdict(list)
    for i,e in enumerate(net.edges):
        if e.kind in ("metal","diagonal_unresolved"):
            adjacency[e.a].append(i); adjacency[e.b].append(i)
    visited=set(); groups=[]
    for start in adjacency:
        if start in visited: continue
        todo=[start]; nodes=set(); edges=set()
        while todo:
            v=todo.pop()
            if v in visited: continue
            visited.add(v);nodes.add(v)
            for ei in adjacency[v]:
                edges.add(ei);e=net.edges[ei]
                todo.append(e.b if e.a==v else e.a)
        groups.append((sorted(nodes),sorted(edges)))
    return groups


def solve_metal_domains(net, current, node_temperature, *, thickness_by_layer,
                        thickness_evidence, times_s, n_cells=12,
                        max_domains=None, em=None):
    if not thickness_evidence: raise ValueError("Thickness provenance or assumption required")
    temp=np.asarray(node_temperature,dtype=float)
    if len(temp)!=len(net.nodes) or np.any(~np.isfinite(temp)) or np.min(temp)<=0:
        raise ValueError("Positive finite temperature required for every node")
    em=em or EMParams()
    domains=metal_domains(net); accepted=[]; rejected=[]
    for ns,es in domains:
        missing=[net.edges[i].name for i in es if net.edges[i].kind!="metal" or net.edges[i].width_m is None or
                 net.nodes[net.edges[i].a].layer not in thickness_by_layer]
        if missing:
            rejected.append({"edge_count":len(es),"unresolved_edges":missing});continue
        # Selection for optional smoke runs is deterministic and disclosed.
        score=max(abs(current[i])*net.edges[i].resistance for i in es)
        accepted.append((score,ns,es))
    accepted.sort(key=lambda row:row[0],reverse=True)
    selected=accepted if max_domains is None else accepted[:max_domains]
    results=[]
    for _,ns,es in selected:
        tr=TreeFDM(em,n_cells=n_cells); mapping={n:tr.add_node() for n in ns}
        for i in es:
            e=net.edges[i]; layer=net.nodes[e.a].layer
            h=thickness_by_layer[layer]
            if h<=0: raise ValueError("positive thickness required")
            area=e.width_m*h
            # EM force uses the actual extracted field E=I*R/L. Encoding that
            # field through G_of_j avoids imposing one bulk rho on every layer.
            equivalent_j=current[i]*e.resistance/(e.length_m*em.rho)
            prof=SegmentProfile(e.length_m,temp[e.a],temp[e.b],T_m=0.)
            tr.add_segment(mapping[e.a],mapping[e.b],e.length_m,area,equivalent_j,prof,
                           sigma_T=float(em.sigma_T(prof.T_bar)))
        sol=tr.solve(times_s)
        results.append({"die":net.nodes[ns[0]].die,"layer":net.nodes[ns[0]].layer,
                        "edges":[net.edges[i].name for i in es],"edge_count":len(es),
                        "max_stress_Pa":sol.max_stress_history().tolist(),
                        "max_abs_j_A_m2":float(max(abs(current[i])/(net.edges[i].width_m*
                          thickness_by_layer[net.nodes[net.edges[i].a].layer]) for i in es))})
    total_by_layer=Counter(net.nodes[net.edges[i].a].layer for _,es in domains for i in es)
    solved_by_layer=Counter(net.nodes[net.edges[i].a].layer for _,_,es in selected for i in es)
    return {"results":results,"times_s":list(times_s),"n_cells_per_edge":n_cells,
            "layer_coverage":{layer:{"total_edges":count,"solved_edges":solved_by_layer[layer]}
                              for layer,count in sorted(total_by_layer.items())},
            "total_domains":len(domains),"accepted_domains":len(accepted),
            "solved_domains":len(selected),"rejected_domains":rejected,
            "total_metal_edges":sum(len(es) for _,es in domains),
            "solved_edges":sum(len(es) for _,_,es in selected),
            "thickness_evidence":thickness_evidence,
            "boundary_assumption":"same-layer continuity; vias/contacts/RDL/bonds diffusion blocking",
            "thermal_scope":"endpoint-linear temperature; no uncalibrated fin bump",
            "scope":"FV teacher integration; NOT full-chip qualified lifetime or SKN accuracy"}
