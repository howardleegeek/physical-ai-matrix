# Physical AI 核心技术体系

## 1. World Model 核心概念

### 什么是 World Model？
World Model 是 AI 系统学习物理世界内部表征的技术，能够：
- 理解物体如何运动和相互作用
- 预测动作的后果
- 在虚拟环境中进行规划和模拟

### JEPA (Joint Embedding Predictive Architecture)
Yann LeCun 提出的一种非生成式架构：
- **核心思想**：预测抽象表征，而非像素
- **优势**：避免生成模型的误差累积
- **发展**：I-JEPA → V-JEPA → V-JEPA 2 → PEVA

## 2. 主要技术分支

### World Model 分支
- **JEPA 系列** (Meta/Yann LeCun)
- **NVIDIA Cosmos** - 世界基础模型平台
- **Google DeepMind Genie** - 交互式 3D

### VLA (Vision-Language-Action)
- **RT-1/RT-2** (Google)
- **π0** (Physical Intelligence)
- **GR00T** (NVIDIA)
- **Green-VLA** (Sber)

### Edge/TTT
- **Spatial-TTT** - 我们的实现
- **VMamba** - 状态空间模型
- **TTT-Linear/Video**

## 3. 主要公司/人物

| 人物/公司 | 公司/项目 | 资金/估值 |
|-----------|-----------|-----------|
| 李飞飞 | World Labs / Marble | $1B |
| Yann LeCun | AMI Labs | $5B |
| Jensen Huang | NVIDIA Cosmos | 平台 |
| - | Tesla Optimus | 内部 |
| - | Figure AI | $854M |
| - | Boston Dynamics | 商用 |

## 4. 我们的技术栈

```
ClawGlasses (传感器)
    ↓
relay (边缘网关)
    ↓
Spatial-TTT (实时处理)
    ↓
VJEPA (世界嵌入)
    ↓
Hermes-Agent (推理/规划)
```

## 5. 关键技术来源

- **MAE** → I-JEPA → V-JEPA
- **Diffusion** → Cosmos → GR00T
- **Transformers** → RT-1 → VLA
- **Mamba** → VMamba → Edge TTT
