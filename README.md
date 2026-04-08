# ETAS 地震数据处理与预测工具集

## 项目介绍

这个项目是我做地震余震预测研究时整理的一套工具，主要用来处理地震数据、拟合ETAS模型参数，然后预测余震发生的概率。整个流程从数据获取到最终预测都涵盖了，希望能帮到有需要的人。

## 作者信息

- 成都理工大学 本科生
- 联系电话：18681308482（有问题直接打电话就行）

## 安装步骤

### 1. 环境要求

- Python 3.9 或更高版本
- 系统：Windows / macOS / Linux 都可以

### 2. 安装依赖

在项目根目录下运行：

```bash
pip install -r requirements.txt
```

### 3. 检查环境

装完之后跑一下检查工具：

```bash
python env_check.py
```

看到"✅ 所有依赖都已满足！"就说明没问题。

## 使用步骤

### 第一步：获取地震数据

用 `etas_claw.py` 从全球地震台网抓数据。

**运行**：

```bash
python etas_claw.py
```

**操作流程**：

1. 选择地震事件：可以直接选预设的（Japan_2011、Chile_2010这些），也可以自己输入经纬度
2. 设置参数：
   - 数据源：USGS、IRIS、GFZ、ISC 四个台网选一个，或者让它自动选
   - 时间范围：开始和结束日期，格式 YYYY-MM-DD
   - 历史数据：要不要爬主震前的数据（1年、3年、5年、10年）
   - 搜索半径：10-500公里
   - Mc震级门槛：一般设4.0或4.5
3. 点"开始爬取"，等它跑完

**输出**：

数据会存到 `7d_earthquake/` 目录，文件名格式是 `{事件名}_{构造类型}_纬度XX.XXN_经度XX.XXE_{台网}.csv`。

CSV 里有这些列：发震时间、纬度、经度、震级、震级类型、深度(km)、位置、台网来源。

### 第二步：拟合 ETAS 参数

用 `fit.py` 拟合模型的5个参数。

**准备**：

打开 `fit.py`，改这两行：

```python
CSV_FILE = "7d_earthquake/你的数据文件.csv"  # 上一步生成的文件
WINDOW = "6h-22h"  # 时间窗口：T1=2h-6h / T2=6h-22h / T3=24h-72h
```

**运行**：

```bash
python fit.py
```

**输出**：

- JSON 文件：`etas_fit_results/{文件名}_ETAS_{窗口}.json`，里面有拟合出来的参数
- PNG 图片：`etas_fit_results/{文件名}_ETAS_{窗口}.png`，拟合效果图

**时间窗口**：

- T1（2h-6h）：主震后2-6小时，用来预测6-24小时
- T2（6h-22h）：主震后6-22小时，用来预测24-72小时
- T3（24h-72h）：主震后24-72小时，用来预测72-168小时

### 第三步：预测余震概率

用 `predict.py` 算概率。

**准备**：

打开 `predict.py`，改这几行：

```python
CSV_FILE = "7d_earthquake/你的数据文件.csv"
ETAS_JSON = "etas_fit_results/{文件名}_ETAS_T2.json"  # 上一步的JSON
WINDOW_CODE = "T2"  # 跟JSON里的窗口要一致
```

**运行**：

```bash
python predict.py
```

**输出**：

- CSV：`etas_prediction/{文件名}_PRED_{窗口}.csv`，有时间、发生率、概率值
- PNG：`etas_prediction/{文件名}_PRED_{窗口}.png`，概率曲线图

## 数据统一化处理

从不同台网爬下来的数据格式不太一样，我做了统一处理：

### 1. 震级统一转换为 Mw

不同台网报的震级类型不一样，有 Mb、ML、Ms、Mw 各种，我在爬取的时候都转成了 Mw。转换公式用的经验关系：

- **Mb → Mw**：
  - Mb < 6.1：Mw = 0.63 × Mb + 2.76
  - 6.1 ≤ Mb ≤ 8.0：Mw = 1.02 × Mb - 0.12

- **ML → Mw**：Mw = 0.68 × ML + 1.07

- **Ms → Mw**：Mw = 0.67 × Ms + 2.07

这些公式是参考了一些文献的经验关系，具体见参考文献部分。

### 2. 时间格式统一

所有时间都转成了 `YYYY-MM-DD HH:MM:SS` 格式，方便后续处理。

### 3. 坐标精度

经纬度保留4位小数，深度保留整数（单位统一为公里）。

### 4. 缺失值处理

有些台网的数据可能缺深度或位置信息，这种情况就留空，不影响后续分析。

## 工具说明

### etas_claw.py - 数据爬取

从 USGS、IRIS、GFZ、ISC 四个台网抓数据，能自动选最近的台网，也支持爬历史数据。震级转换是自动的，不用管。

### fit.py - 参数拟合

拟合 ETAS 模型的5个参数：mu（背景地震率）、K（余震生产力）、alpha（震级影响）、c（时间常数）、p（衰减指数）。

用的是最大似然估计，优化算法是 L-BFGS-B。

### predict.py - 概率预测

基于拟合出来的参数，算预测窗口内发生地震的概率。公式是 P = 1 - exp(-λ·Δt)，λ 是地震发生率。

### env_check.py - 环境检查

检查依赖包有没有装全，缺什么会告诉你。

### earthquake_events.csv - 预设事件

存了14个历史大地震的信息，包括构造类型、位置、震级、时间这些。

## 输出文件

### 地震数据（CSV）

位置：`7d_earthquake/`

```
发震时间,纬度,经度,震级,震级类型,深度(km),位置,台网来源
2010-02-27 06:34:14,-35.85,-72.71,8.8,Mw,35,Chile,USGS
```

### ETAS 参数（JSON）

位置：`etas_fit_results/`

```json
{
    "mu": 0.05,
    "K": 0.8,
    "alpha": 1.2,
    "c": 0.005,
    "p": 1.1,
    "neg_ll": 123.45,
    "AIC": 256.9,
    "success": true
}
```

### 预测结果（CSV）

位置：`etas_prediction/`

```
time_days,lambda_rate,probability_0_1
0.25,0.15,0.07
0.27,0.14,0.07
```

## 完整流程示例

以 2010 年智利地震为例：

**第一步：抓数据**

```bash
python etas_claw.py
```

选 Chile_2010，时间 2010-02-27 到 2010-03-14，半径 300km，Mc 设 4.5，点开始。

**第二步：拟合 T2**

改 `fit.py`：

```python
CSV_FILE = "7d_earthquake/Chile_2010_俯冲带_纬度35.85S_经度72.71W_USGS.csv"
WINDOW = "6h-22h"
```

跑：

```bash
python fit.py
```

**第三步：预测 T2**

改 `predict.py`：

```python
CSV_FILE = "7d_earthquake/Chile_2010_俯冲带_纬度35.85S_经度72.71W_USGS.csv"
ETAS_JSON = "etas_fit_results/Chile_2010_俯冲带_纬度35.85S_经度72.71W_USGS_ETAS_T2.json"
WINDOW_CODE = "T2"
```

跑：

```bash
python predict.py
```

结果在 `etas_fit_results/` 和 `etas_prediction/` 里。

## 注意事项

1. **网络**：国内访问 USGS 可能要代理，改 `etas_claw.py` 里的 `USE_PROXY = True`

2. **数据量**：拟合窗口里至少要有3个地震事件，不然会报错。事件太少就降低 Mc 或增大搜索半径

3. **窗口对应**：T1 拟合对应 T1 预测，T2 对应 T2，T3 对应 T3，别搞混了

4. **文件路径**：改代码里的路径时注意别写错，最好用绝对路径

## 参考文献

1. Ogata, Y. (1988). Statistical models for earthquake occurrences and residual analysis for point processes. *Journal of the American Statistical Association*, 83(401), 9-27.

2. Ogata, Y. (1999). Seismicity analysis through point-process modeling: A review. *Pure and Applied Geophysics*, 155(2-4), 471-507.

3. Utsu, T. (1961). A statistical study on the occurrence of aftershocks. *Geophysical Magazine*, 30, 521-605.

4. Utsu, T., Ogata, Y., & Matsu'ura, R. S. (1995). The centenary of the Omori formula for a decay law of aftershock activity. *Journal of Physics of the Earth*, 43(1), 1-33.

5. Helmstetter, A., & Sornette, D. (2002). Subcritical and supercritical regimes in epidemic models of earthquake aftershocks. *Journal of Geophysical Research: Solid Earth*, 107(B10), ESE 10-1-ESE 10-21.

6. 震级转换关系参考：
   - Scordilis, E. M. (2006). Empirical global relations converting Ms and mb to moment magnitude. *Journal of Seismology*, 10(2), 225-236.
   - Lolli, B., & Gasperini, P. (2012). A comparison among general orthogonal regression methods for seismic magnitude conversions. *Geophysical Journal International*, 190(2), 1135-1151.

7. ETAS 模型综述：
   - Zhuang, J., Ogata, Y., & Vere-Jones, D. (2002). Stochastic declustering of space-time earthquake occurrences. *Journal of the American Statistical Association*, 97(458), 369-380.

## 许可证

学术研究和教学用，别拿去商用就行。

## 联系方式

有问题打电话：18681308482
