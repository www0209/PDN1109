# PDN1109

基于 StackEM 的公开设计衍生三维供电网络实验。保留 OpenROAD 提取的金属、过孔、接触电阻和非均匀负载，在有限封装、层间及再分布电阻下联合求解多 die 供电网络，并连接 HotSpot 三维热分析和 StackEM 应力求解。

本仓库包含完整代码、输入数据、五个算例、验证结果与中文方案。基于 [StackEM_clean](https://github.com/www0209/StackEM_clean) 提交 `90d8dbb1598bcffd6b652dd1582d682f08980864`；原项目代码、权重及参考结果保留。

**真实性边界：** 二维设计与网络提取来源可追溯；三维组装、部分材料和封装参数属于明确的研究假设。这里不是已流片三维芯片的实测数据，也不构成全芯片寿命签核。

## 先读这些文件

- [中文方案与现有案例审查](docs/10_设计衍生PDN与三维算例.md)
- [中文 Word 报告](docs/StackEM_PDN真实性改进与五个三维算例.docx)
- [运行入口与文件说明](START_HERE_DESIGN_PDN.md)
- [实际运行结果表](reference_results/design_pdn/RESULTS.md)
- [原版 StackEM 说明](README_STACKEM.md)

## 五个新算例

| 算例 | 组装方式 | 电阻数 | 最差压降 mV |
|---|---|---:|---:|
| `gcd_2die_aligned` | 原始 GCD 双层对齐 | 7,752 | 0.516523 |
| `gcd_pdngen_2die` | OpenROAD pdngen 重新生成 GCD PDN 后双层组装 | 7,466 | 0.614091 |
| `aes_2die_rotated` | AES 双层，上层平面旋转 180° | 323,943 | 43.506549 |
| `aes_3die_aligned` | AES 三层对齐 | 485,904 | 43.672168 |
| `aes_gcd_aes_3die` | AES–居中 GCD–AES 异构组装 | 327,821 | 54.049266 |

电流保留 OpenROAD 默认活动率下的提取值，不使用原规则网格的 `current_fraction`。VSS 暂作理想共地；垂直路径为集总模型。各例的尺寸、参数与假设见 [cases.json](examples/design_pdn/cases.json)。

## 已完成验证

- 三个单层网络与实际运行的 OpenROAD 逐项核对，全部报告电流匹配；最大电压差小于 1 μV。
- 五个堆叠案例检查 KCL、源功率平衡、功率分箱守恒及层间电阻扫描。
- 五个 HotSpot 三维稳态热场和全部 **821 个几何合格扩散域**的应力求解。
- **34 项测试通过**，见 [测试日志](reference_results/design_pdn/tests.log)。

提取出的全局 M4/M7 金属边均完成应力计算；重新生成的 GCD 网络只有 M1/M4 同层电阻边。部分 M1 局部扩散域因几何信息不足而整体排除。每例的 `em_teacher.json` 同时保存分层覆盖率和排除记录；不能把全局金属结果描述为全芯片签核。新几何的网格收敛、材料校准及 SKN 越界检查仍需完成。

## 快速运行

电气分析及测试需要 Python、NumPy、SciPy。三维热场与完整应力流程已在 Linux/WSL、NumPy 1.26.4、SciPy 1.11.4 下运行。

```bash
python -m pip install -r requirements-design-pdn.txt
python -m unittest stackem.tests.test_core stackem.tests.test_design_pdn -v
python tools/run_design_pdn.py --out results/design_pdn
```

热分析需要已编译的 HotSpot，可使用仓库自带 `third_party/HotSpot-master.zip` 的源码。在 Linux/WSL 下运行：

```bash
python tools/run_design_thermal.py --out results/design_pdn --hotspot /path/to/HotSpot --em-domains 0
```

`--em-domains 0` 表示全部几何合格域；默认值 5 仅用于快速检查。运行结果写入 `results/`，不会覆盖仓库提供的参考结果。

## 重新提取与生成 OpenROAD PDN

固定输入的 SPICE 已随仓库提供，日常运行无需 OpenROAD。需要重做工具提取时：

```bash
python tools/prepare_openroad_designs.py --out work/openroad_reproduction
cd work/openroad_reproduction
openroad -exit export_gcd.tcl
openroad -exit export_aes.tcl
openroad -exit regenerate_gcd.tcl
```

准备脚本下载并校验固定版本的 LEF/Liberty。执行版本为 OpenROAD `26Q2-1164-g08f67ee5ec`；设计文件版本、下载地址和 SHA256 见 [输入清单](examples/design_pdn/inputs/manifest.json)。外部库文件和 OpenROAD 二进制没有随仓库打包。

## 目录

| 目录或文件 | 内容 |
|---|---|
| `stackem/design_pdn.py` | 完整网络导入、DC 求解、DEF 宽度匹配和显式堆叠 |
| `stackem/design_em.py` | 按完整扩散域检查几何并接入 TreeFDM |
| `tools/run_design_pdn.py` | 电气验证、堆叠与参数扫描入口 |
| `tools/run_design_thermal.py` | 已保存网络的热分析和应力求解 |
| `examples/design_pdn/` | 五个案例配置、提取输入、执行脚本与来源清单 |
| `reference_results/design_pdn/` | 完整电气图、电压电流、热输入输出、应力与覆盖率 |
| `docs/` | 新方案、Word 报告和原版操作说明 |
| `PACKAGE_MANIFEST.json` | 发布文件的 SHA256 清单，不包含自身及 Git 内部文件 |

## 来源与许可

StackEM 代码沿用 [MIT License](LICENSE)。OpenROAD 来源数据的许可见 [OPENROAD_LICENSE](examples/design_pdn/OPENROAD_LICENSE)。其他第三方材料保留原始许可及出处。

文献依据包括 PISR、BeGAN、HierPINN-EM、ChipletEM、GEMIR、GridNet；具体采纳的做法、未完成的验证和可用于论文的方法表述见 [中文方案](docs/10_设计衍生PDN与三维算例.md)。
