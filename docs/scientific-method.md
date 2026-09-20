# 科学方法与实现边界

当前文档对应正在开发的核心函数，未表示完整系统已验收。

## 评价
`domain/assessment.py` 接受显式参考上下界与指标方向；超出参考范围、缺失/非有限值、零宽参考拒绝执行，不静默剪裁。常数样本列可在外部非退化参考下计算。权重要求非负且总和为正并归一化。熵权处理 0 log 0 为 0，常数列信息权重为 0，所有列无信息则拒绝生成权重。TOPSIS 使用向量归一化与加权理想点欧氏距离；理想点退化时报错，不生成伪排名。多期使用相同参考和权重，输出竞争排名、末期减初期变化、按实际时间坐标的最小二乘斜率。

## 淹没筛查
`domain/screening.py` 仅是地形连通性筛查，不是二维/三维水动力模型。输入单位为米；绝对水位为显式 baseline + increment；垂向基准缺失或不同阻断。显式海侧种子、4/8 邻接、屏障与 NoData 决定连通域；高度等于水位计为潜在淹没。NaN 为 NoData，输出 -1，绝不当作低风险。面积使用调用方明确提供的平方米像元面积，不能把经纬度平方当平方米。

## 适配
Pint 用于同维单位及偏移温度转换。PyProj 强制 x/y 顺序，禁用 ballpark 并要求可用最佳转换；垂向变换不能从水平 CRS 可转换推断。总量分配矩阵按源面积份额定义，源覆盖列和必须为 1（绝对容差 1e-10），输出总量容差相对/绝对 1e-10。未获批准语义映射不自动接受。时间插值不外推，积累量只能在显式总和操作中聚合，非等间隔观测不作默认算术平均。

## 证据及责任
科学模型、工程 Adapter、LLM 推荐、科学校验和用户审核是独立职责。LLM 不替代专业模型机理。模型选择必须先通过硬约束；运行成功不等同于科学验证或管理审核。手算测试数值容差按具体算法设定，不能用大容差隐藏错误。后续空间覆盖、栅格转换、真实数据验证、模型校准和专业审核仍需完成。

## 实施时核对的依赖文档
- [Pydantic 模型与校验](https://docs.pydantic.dev/latest/concepts/models/)
- [Pint 单位转换](https://pint.readthedocs.io/en/stable/getting/tutorial.html)
- [PyProj 坐标转换](https://pyproj4.github.io/pyproj/stable/api/transformer.html)
- [NumPy 向量范数](https://numpy.org/doc/stable/reference/generated/numpy.linalg.norm.html)
