import tempfile
import unittest
from pathlib import Path
import numpy as np
from stackem.design_pdn import (read_spice,solve_dc,assemble_stack,power_bins,spice_number)
from stackem.design_em import metal_domains,solve_metal_domains
from stackem.constants import EMParams


class DesignPDNTests(unittest.TestCase):
    def net(self, text):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"a.sp";p.write_text(text)
            n=read_spice(p,coordinate_unit_m=1e-6,coordinate_evidence="unit test, micrometres")
        n.provenance["die_bbox_m"]=[0,0,10e-6,10e-6]
        return n

    def basic(self):
        return self.net("R1 Node_metal1_0_0 Node_metal1_10_0 2\nI1 Node_metal1_10_0 0 1m\nV1 Node_metal1_0_0 0 1")

    def test_analytic_and_balance(self):
        n=self.basic();s=solve_dc(n)
        self.assertAlmostEqual(s["min_voltage_V"],.998)
        self.assertAlmostEqual(s["resistive_loss_W"],2e-6)
        self.assertLess(s["power_balance_relative"],1e-12)

    def test_parallel_resistors_retained(self):
        n=self.net("R1 Node_metal1_0_0 Node_metal1_10_0 2\nR2 Node_metal1_0_0 Node_metal1_10_0 2\nI1 Node_metal1_10_0 0 1m\nV1 Node_metal1_0_0 0 1")
        self.assertEqual(len(n.edges),2)
        self.assertTrue(np.allclose(solve_dc(n)["current"],.0005))

    def test_stack_analytic(self):
        n=self.basic();stack,_=assemble_stack([n,n],bond_resistance_ohm=3,
            package_resistance_ohm=4,rdl_sheet_ohm=.1,rdl_width_m=1e-6)
        s=solve_dc(stack)
        self.assertAlmostEqual(s["min_voltage_V"],1-.002*4-.001*3-.001*2)
        self.assertEqual(len(stack.fixed),2)
        bonds=[i for i,e in enumerate(stack.edges) if e.kind=="bond"]
        self.assertAlmostEqual(abs(s["current"][bonds[0]]),.001)

    def test_disconnected_rejected(self):
        n=self.net("R1 a b 1\nR2 c d 1\nV1 a 0 1")
        with self.assertRaisesRegex(ValueError,"Floating"):solve_dc(n)

    def test_no_silent_dynamic_or_floating_source(self):
        for text in ("R1 a b 1\nC1 b 0 1p", "R1 a b 1\nV1 a b 1", "R1 a b 1\n.include other.sp"):
            with self.assertRaises(ValueError):self.net(text)

    def test_unit_suffix(self):
        self.assertEqual(spice_number("1meg"),1e6)
        self.assertEqual(spice_number("R=2m"),.002)

    def test_power_conservation_and_bounds(self):
        n=self.basic();s=solve_dc(n)
        self.assertAlmostEqual(power_bins(n,s["voltage"],die="D0",bbox_m=[0,0,10e-6,10e-6]).sum(),s["load_power_W"])
        with self.assertRaises(ValueError):power_bins(n,s["voltage"],die="D0",bbox_m=[0,0,1e-6,1e-6])

    def test_rotation_and_finite_rdl(self):
        n=self.basic();stack,maps=assemble_stack([n,n],bond_resistance_ohm=3,
            package_resistance_ohm=4,rdl_sheet_ohm=.1,rdl_width_m=1e-6,
            transforms=[{}, {"rotation_deg":180}])
        self.assertTrue(any(e.kind=="rdl" and e.resistance>0 for e in stack.edges))
        self.assertAlmostEqual(stack.nodes[maps[1][2]].y,10e-6)
        solve_dc(stack)

    def test_branch_not_split_at_current_change(self):
        n=self.net("R1 Node_metal1_0_0 Node_metal1_5_0 1\nR2 Node_metal1_5_0 Node_metal1_10_0 1\nR3 Node_metal1_5_0 Node_metal1_5_5 1\nV1 Node_metal1_0_0 0 1")
        self.assertEqual(len(metal_domains(n)),1)
        self.assertEqual(len(metal_domains(n)[0][1]),3)

    def test_conflicting_source_rejected(self):
        with self.assertRaises(ValueError):self.net("R1 a b 1\nV1 a 0 1\nV2 a 0 2")

    def test_missing_geometry_rejects_whole_domain(self):
        n=self.basic();s=solve_dc(n)
        result=solve_metal_domains(n,s["current"],np.full(len(n.nodes),350.),
            thickness_by_layer={"metal1":.2e-6},thickness_evidence="test assumption",times_s=[1e4])
        self.assertEqual(result["solved_domains"],0)
        self.assertEqual(result["rejected_domains"][0]["edge_count"],1)

    def test_field_driven_em_independent_of_encoding_rho(self):
        n=self.basic();n.edges[0].width_m=1e-6;s=solve_dc(n)
        options=dict(thickness_by_layer={"metal1":.2e-6},thickness_evidence="unit test",
                     times_s=[1e4,1e6],n_cells=12)
        a=solve_metal_domains(n,s["current"],np.full(len(n.nodes),350.),em=EMParams(rho=3e-8),**options)
        b=solve_metal_domains(n,s["current"],np.full(len(n.nodes),350.),em=EMParams(rho=6e-8),**options)
        self.assertTrue(np.allclose(a["results"][0]["max_stress_Pa"],b["results"][0]["max_stress_Pa"],rtol=1e-10))


if __name__=="__main__":unittest.main()
