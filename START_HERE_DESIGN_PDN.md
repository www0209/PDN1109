# 新版 PDN 案例入口

这是基于 StackEM_clean 提交 90d8dbb1598bcffd6b652dd1582d682f08980864 的本地增强版本。
原始参考结果保留；新结果位于 `reference_results/design_pdn/`。

建议先读 `docs/10_设计衍生PDN与三维算例.md` 和
`reference_results/design_pdn/RESULTS.md`。

## 已完成

- OpenROAD 对原 GCD、AES 的网络提取与独立电压、电流核对。
- OpenROAD pdngen 重新生成 GCD 供电网络，检查连接并提取。
- 五个显式有限层间供电的堆叠网络、原始 DC 结果及三档层间电阻扫描。
- 五个 HotSpot 三维稳态热场，功率守恒映射。
- 全部 821 个几何合格扩散域的 StackEM TreeFDM 运行；每例保存分层覆盖率与排除记录。
- 34 项测试通过，日志附在新结果目录。

## 复现

需要 Python、NumPy、SciPy。从本目录运行：

```bash
python -m unittest stackem.tests.test_core stackem.tests.test_design_pdn -v
python tools/run_design_pdn.py --out results/design_pdn
```

在 Linux 或 WSL 下接入已编译的 HotSpot：

```bash
python tools/run_design_thermal.py --out results/design_pdn --hotspot /path/to/HotSpot --em-domains 0
```

`--em-domains 0` 运行全部几何合格域。未提供这个参数时默认仅运行五域快速检查。
可从仓库自带 `third_party/HotSpot-master.zip` 解压并编译 HotSpot。

## 文件说明

- `examples/design_pdn/cases.json`：五个案例的来源、尺寸、变换、组装参数、热假设。
- `examples/design_pdn/inputs/manifest.json`：原始数据与工具版本、来源链接和哈希。
- `tools/prepare_openroad_designs.py`：恢复 OpenROAD 可执行输入，下载并校验 LEF/Liberty。
- `stackem/design_pdn.py`：保留完整网络的导入、求解和组装。
- `stackem/design_em.py`：接入原有 TreeFDM，按完整扩散域检查几何。
- `reference_results/design_pdn/*/network.json.gz`：可审查的完整电气图。
- `dc_solution.npz` 和 `segments.csv.gz`：节点电压与每条边的电流、电阻、几何字段。
- `thermal.json`、`.flp`、`.lcf`、`.ptrace`、`.config`、`.grid.steady`：热输入、参数与结果。
- `em_teacher.json`：应力、每层覆盖率、完整拒绝列表和材料假设。

这些是公开二维设计衍生的三维研究组装，不是已流片芯片。VSS 暂作理想共地；
垂直路径、封装热参数、厚度与扩散边界仍含明确假设。未完成本批新几何的网格收敛、
SKN 越界检查与全芯片寿命签核。详见中文说明，不能仅看最大应力或压降就推断工艺可靠性。
