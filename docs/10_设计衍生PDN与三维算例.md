# StackEM 设计衍生 PDN 与三维算例

## 结论与使用范围

建议将论文算例分成“受控方法验证”和“公开设计衍生应用验证”两组。保留 base3、dense3、quad4 做消融与参数扫描；主应用实验增加本目录提供的五个算例。新路线保留 OpenROAD 提取的多层电阻、过孔、引脚连接及逐负载电流，再显式构建三维供电连接，因此比在规则方格上分配块功耗更有可追溯依据。

这里的“设计衍生”是指公开二维已放置/布线设计及工具提取结果。五个三维组装均为研究构造，没有流片测量、完整三维信号布线或三维 DRC 认证。不能承诺审稿人不会质疑；可复现的来源链、守恒验证、缺失项和适用范围，比把模型称为“真实芯片”更能支撑论文。

## 现有代码的具体问题

审查基于 StackEM_clean 提交 `90d8dbb1598bcffd6b652dd1582d682f08980864`。没有改写原来的参考结果或发布权重。

| 位置 | 已核查做法 | 新应用实验的处理 |
|---|---|---|
| stackem/power_grid.py 的 DieGrid | 正方形规则格；水平和垂直边共用节点；按块向节点均匀分电流 | 输入完整提取网络，保存各层、过孔、引脚接触电阻和非均匀负载 |
| configs/base3.json 和 config.py 默认值 | 4 mm 方形 die；功耗与热点人为配置；current_fraction 为 0.4；R_feed 为 0 | 新算例使用原始提取电流，不乘 current_fraction；有限封装与层间电阻 |
| assembler.py | 各 die 电气求解独立，热场再耦合 | 多 die 合成一个电气图后求解，底层供电须承担上层电流 |
| experiments/e8_ev6.py | HotSpot 真实来源的模块 floorplan 加自行生成的规则 PDN；约 12.4 × 12.76 mm 的平面被方形网格处理 | floorplan 来源与 PDN 来源分别说明；新路径保留 DEF 的长宽，不裁为正方形 |
| ibmpg.py 的 extract_rails 与 _merge_short | 部分物理截面由 R、L、rho 推定；短段合并保留邻段电流；温度使用投影 | 不将电阻反推截面当作工艺事实；不合并电流不同的段；保留全部电气边 |
| signoff.py 和原先 standalone sizing | 在单 die 签核目标下先调整线宽，再评估堆叠 | 设计原样结果作为主基准；优化后结果另列，防止“先调整再证明失效”的选择偏差 |

上述简化并不使原来的数值方法验证失效，但不能直接证明真实工艺的全芯片寿命。

## 文献做法如何转化为实验

| 来源 | 对 StackEM 有用的做法 | 本次采用或保留的边界 |
|---|---|---|
| PISR，TCAD 2023，Table II 和 Fig.12，PDF p.9 | 从 OpenROAD 的 aes、gcd、ibex 设计出发，由 PDNSim 提取电流；表中有五个设计与工艺组合 | 优先采用这条来源链。本次实际运行 Nangate45 的 GCD、AES；不冒称已运行 ibex、SKY130 |
| BeGAN，ICCAD 2021；公开仓库 README | 分开发布 real-circuit-benchmarks 与 GAN 生成数据；真实设计电流图搭配规则或 OpeNPDN 非规则网络 | 适合扩大电路多样性；推荐真实设计分支，不能将 GAN 图当实测。尚未把其缺失的几何、单位和工艺映射作为本次 EM 输入 |
| GridNet，ICCAD 2020；实验章节 | 在固定网络上改变负载，学习 EM 引起的 IR 变化 | 可借鉴同一拓扑的工况扫描；只能证明该网络的负载泛化，不能代替跨设计验证 |
| GEMIR，DAC 2026；实验章节 | 合成数据训练与实际设计测试/微调分开 | 应按设计家族、拓扑拆分数据，相关变体不能同时进入训练集和测试集 |
| HierPINN-EM，ICCAD 2022；实验章节 | 随机线段、直线与树，用 COMSOL 验证应力 | 保留为求解器精度验证；不能用随机互连证明 PDN 应用真实性 |
| ChipletEM，DAC 2025；实验章节 | 耦合封装、热与应力；局部验证与系统模型分层组织 | 堆叠构造和材料假设需独立公开；不能将论文局部实验参考推及全部系统级预测 |

PISR 的对应性最直接。OpenROAD pdngen 可以按层、线宽、间距、宏单元区域生成供电金属；PDNSim 可以检查连通性、输出静态电流和 SPICE。其 `-enable_em` 报告用于电流检查，不等于执行 StackEM 的应力演化或寿命求解。

## 本次交付的五个算例

| 算例名 | 物理尺寸与组装 | 主要用途 |
|---|---|---|
| gcd_2die_aligned | 两个 100.13 × 100.80 μm GCD，原始 PDN 对齐 | 小规模、容易复核的端到端案例 |
| gcd_pdngen_2die | 同一 GCD 放置设计；先移除 PDN，再用 OpenROAD 官方 Nangate45 策略重新生成，随后双层组装 | 证明能从设计规则策略生成新 PDN，而非只能读取现成 SPICE |
| aes_2die_rotated | 两个 620.15 × 620.60 μm AES，上层平面旋转 180° | 检查坐标变换及非重合馈电点的再分布布线电阻 |
| aes_3die_aligned | 三个 AES，保持原始几何和负载 | 验证层数变化与底层供电负担 |
| aes_gcd_aes_3die | AES–居中 GCD–AES；GCD 不缩放 | 异构尺寸、有限层间连接；热模型额外假定中层存在 AES 尺寸的无源硅载体 |

180° 仅指平面旋转，不代表已验证 face-to-face 翻面。层间垂直路径使用集总电阻，涵盖可能的 TSV/背面接入/键合连接，尚未分别抽取。原始二维供电端口被作为组装接入点，并非已经完成真实 bump/TSV 的几何布局。

组装参数均为显式研究假设：每馈电端封装电阻 0.05 Ω；层间路径 0.1 Ω；再分布金属片电阻 0.02 Ω/□、宽 5 μm。上层端口连接到最近的下层端口；不重合端口按曼哈顿长度计入 RDL 电阻，没有零电阻横向跳接。另运行层间电阻 0.01、0.1、1 Ω 扫描。这些参数不能写成某一商业工艺的实测值。

负载来自固定版本 OpenROAD 对 Liberty、SDC 和默认活动率的功耗估计，属于静态恒电流工况；没有 VCD/SAIF 驱动，也不是硬件工作负载测量。保留原始电流，不为了制造失效而调高功耗。

## 已实现的验证与输出

`stackem/design_pdn.py` 实现严格 SPICE 导入、完整电气求解、DEF 线宽匹配、三维组装和守恒功率映射。未知元件、浮置分量、冲突电源和无法支持的浮置电压源均明确报错。求解采用源电压偏移，降低小压降与小接触电阻造成的相消误差。

输入清单记录来源提交、工具版本和 SHA256。OpenROAD 工具实际版本为 `26Q2-1164-g08f67ee5ec`，输入测试设计版本为 `6932b6296c65aebaadae64850f5a23265758ead0`。保存了执行脚本与日志；二者版本不同这一事实已固定在清单中，没有假定结果跨版本完全相同。

电气核查包括全部报告线段电流的匹配、全部实例端电压匹配、自由节点 KCL、源功率与负载功率及 I²R 损耗平衡。每个算例还输出节点、电阻、负载数量、边类型、最差压降和层间电阻扫描结果。具体数值以 `reference_results/design_pdn/summary.json` 为准。

热输入使用 16 × 16 功率格，保存矩形物理尺寸与 y 轴方向。每个负载按求解后的 V×I 落入所在格，保留总功率；非封装电阻的 I²R 损耗在端点处各沉积一半。HotSpot 使用 32 × 32 网格执行三维稳态计算。硅厚 50 μm、键合层厚 5 μm、等效导热系数 40 W/(m·K)、环境温度 318.15 K 等沿用旧研究场景，尚无封装校准。异构案例的载体假设和有限网格平均应单列敏感性实验。

`stackem/design_em.py` 接入原有 TreeFDM。保留同层连通分支的应力连续性；不因电流变化截断互连。若一个扩散域含无法定位宽度的边或未解析的斜向连接，该域整体拒绝，不截掉问题段后制造零通量端点。过孔和接触连接暂按扩散阻挡处理，需材料证据支持；RDL、键合与 TSV 没有纳入 EM 寿命签核。

DEF 可证实平面宽度，但不能提供本任务所需的全部厚度和界面扩散参数。演示采用统一 0.20 μm 厚度并标为假设，EM 驱动力使用提取的电场 E=I·R/L；不能把为旧长线场景选定的 rho 强加到所有层。温度沿线段端点线性插值，未叠加未经校准的局部 fin 自热峰。时间点为 10⁴、10⁶、10⁸ s。该结果验证了新数据接口可运行，并不构成完整工艺寿命认证。

最终保存结果运行了全部 821 个合格扩散域，不是默认的五域快速检查。已提取的 M4/M7 全局供电金属边全部进入应力求解；重新生成的 GCD 提取网络只包含 M1/M4 的同层电阻边，因此该例不宣称有 M7 电阻边。大量 M1 局部域仍被排除，AES 算例全部同层边的 EM 覆盖率仅约 7.2%，必须与全局金属覆盖率同时报告。扩散模型参数尚未校准，且未在本批新几何上完成空间网格收敛，现有应力数值应作为可运行基线，不直接作为论文最终精度结论。

## 复现与接入现有工程

在仓库根目录执行，依赖 Python、NumPy、SciPy；电气入口不需要重新安装 OpenROAD。

```bash
python -m unittest stackem.tests.test_core stackem.tests.test_design_pdn -v
python tools/run_design_pdn.py --out results/design_pdn
```

完整热与应力路径在 Linux/WSL 下使用已编译 HotSpot：

```bash
python tools/run_design_pdn.py --out results/design_pdn --hotspot /path/to/HotSpot --em-domains 0
```

`--em-domains 0` 表示运行全部几何合格的扩散域，仍不包含被拒绝的域。默认值 5 仅用于快速连通性检查，不能作为全芯片统计。已有电气结果可单独继续热分析：

```bash
python tools/run_design_thermal.py --out results/design_pdn --hotspot /path/to/HotSpot --em-domains 0
```

复现 OpenROAD 提取及重新生成 PDN：

```bash
python tools/prepare_openroad_designs.py --out work/openroad_reproduction
cd work/openroad_reproduction
openroad -exit export_gcd.tcl
openroad -exit export_aes.tcl
openroad -exit regenerate_gcd.tcl
```

下载脚本按 SHA256 校验 LEF/Liberty。外部工艺库按其自身许可使用；包内不捆绑 OpenROAD 二进制或另行下载的库文件。新增输入的引用与许可见 `examples/design_pdn/inputs/manifest.json` 和 `OPENROAD_LICENSE`。

## 论文主实验应如何组织

1. **来源与基线**：主表列原样二维设计、三维组装假设、节点/电阻/负载数量、原始功率、线宽来源和缺失几何比例。先展示未优化设计，再展示修复后的版本。
2. **电气验证**：单层与 OpenROAD 逐段匹配；三维可再与独立 SPICE 求解器交叉检查，包含供电与地返回网络。不要把原来每层独立理想供电称为同一个边界条件下的三维金标准。
3. **真实活动率**：下一批输入用公开 RTL 的 VCD/SAIF，保存时钟、活动窗口及实例功耗映射；分别报告默认活动率和矢量驱动结果。扫描倍率只能列为压力测试。
4. **热与组装敏感性**：扫描键合热阻、硅厚度、层顺序、馈电位置和层间电阻；做 16/32/64 网格收敛及更细热源分箱。缺少校准时只讨论趋势和敏感性。
5. **EM 精度与覆盖率**：列出总扩散域、合格域、拒绝域、参与寿命统计的边数；在短段、长段、分叉和最危险域上做 FDM 网格收敛及 COMSOL 对照。补齐缺失几何前，不报告全芯片通过率。
6. **机器学习泛化**：已有 SKN 权重可能不覆盖新设计里的短段长度、温度、层级材料及分叉。先统计无量纲输入是否越界，再决定再训练；不要直接把旧权重速度比迁移到新 PDN。
7. **拓扑独立性**：同一 AES 的旋转、负载倍率、层数变体不算新的独立设计样本。论文应用组还应增加 ibex、SweRV 或含宏单元的设计，以及第二工艺；五个组装案例不能宣称有五个独立逻辑设计。

更强的最终证据是：使用开放三维物理设计流程完成分区、放置、信号与 PDN 布线及键合端口映射，保存两面 DEF/LEF 和组装文件，再提取互连。TaiWei-Pin-3D 可作为候选，但包含工具与环境依赖，本次未执行。当前 OpenROAD 主分支已提供部分三维分析和测试；文档仍注明连接后的三维网络不能直接由 `write_pg_spice` 完整导出，因此本次明确采用“二维分别提取、显式电气组装”的方案，不能假称调用了官方完整三维导出。

## 可用于论文的方法表述

我们从公开 OpenROAD 测试设计中获取 GCD 和 AES 的已放置布线数据，使用固定版本 PDNSim 提取包含金属、过孔和单元负载的静态供电网络，并在独立稀疏节点求解器中复核电压与电流。在保持各 die 原始平面几何和负载的基础上，构造具有有限封装、层间及再分布电阻的多层组装；组装参数与材料参数作为公开研究假设。功率映射保持负载功率及网络损耗守恒，三维稳态温度由 HotSpot 计算。仅对几何可核实且满足指定扩散边界假设的金属域执行应力求解，其覆盖率与排除原因单独报告。这些案例用于评估公开设计衍生的三维场景，不作为实测硅片的绝对寿命预测。

## 可追溯资料

- StackEM 审查版本：https://github.com/www0209/StackEM_clean/tree/90d8dbb1598bcffd6b652dd1582d682f08980864
- OpenROAD PDN 生成：https://openroad.readthedocs.io/en/latest/main/src/pdn/README.html
- OpenROAD PDNSim 与三维限制：https://openroad.readthedocs.io/en/latest/main/src/psm/README.html
- OpenROAD 设计文件：https://github.com/The-OpenROAD-Project/OpenROAD/tree/6932b6296c65aebaadae64850f5a23265758ead0/src/psm/test
- PISR，TCAD 2023，DOI 10.1109/TCAD.2023.3269393：https://sheldonucr.github.io/published_papers/tcad23_linear_time_electromigration.pdf
- BeGAN，ICCAD 2021，DOI 10.1109/ICCAD51958.2021.9643566：https://www.ece.umn.edu/users/sachin/conf/iccad21kkvacmz.pdf
- BeGAN 公开数据：https://github.com/UMN-EDA/BeGAN-benchmarks/tree/f7ce3d1d832c9833bb911ae8b460bd68b31651bd
- HierPINN-EM：DOI 10.1145/3508352.3549371；ChipletEM：DOI 10.1109/DAC63849.2025.11132600；GEMIR：DOI 10.1145/3770743.3803897；GridNet：DOI 10.1145/3400302.3415714。正文实验核查详见前一份 16 篇文献报告。
- TaiWei-Pin-3D：https://github.com/CODA-Team/TaiWei-Pin-3D
