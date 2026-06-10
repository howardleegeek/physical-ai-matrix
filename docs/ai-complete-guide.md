# AI 技术体系完全指南

## 一、AI 发展时间线

### 2017-2020: 深度学习时代
- **2017**: Transformer 论文发布
- **2018**: BERT, GPT-1
- **2019**: GPT-2, BERT广泛应用
- **2020**: GPT-3, CLIP, DALL-E

### 2021-2022: 大模型爆发
- **2021**: GPT-3, Codex, GitHub Copilot
- **2022**: ChatGPT, Stable Diffusion, LLaMA

### 2023-2024: 多模态时代
- **2023**: GPT-4, LLaVA, Claude
- **2024**: GPT-4o, Claude 3, Gemini

### 2025-2026: Physical AI 时代
- **2025**: World Models 爆发, VLA, TTT
- **2026**: JEPA 2, Physical AI 商业化

---

## 二、核心技术分类

### 1. 语言模型 (LLM)
| 模型 | 机构 | 特点 |
|-----|------|------|
| GPT-4 | OpenAI | 多模态 |
| Claude | Anthropic | 安全对齐 |
| Gemini | Google | 原生多模态 |
| LLaMA | Meta | 开源 |
| Qwen | 阿里 | 中文 |

### 2. 视觉模型 (Vision)
| 模型 | 用途 |
|-----|------|
| CLIP | 图像-文本对齐 |
| DALL-E | 图像生成 |
| Stable Diffusion | 开源图像生成 |
| SAM | 图像分割 |
| Grounding DINO | 目标检测 |

### 3. 语音模型 (Audio)
| 模型 | 用途 |
|-----|------|
| Whisper | 语音识别 |
| ElevenLabs | 语音合成 |
| GPT-4o | 实时语音 |

### 4. 世界模型 (World Model) - 重点!
| 模型 | 机构 | 核心 |
|-----|------|-----|
| JEPA | Meta/LeCun | 表征预测 |
| V-JEPA | Meta | 视频理解 |
| Cosmos | NVIDIA | 物理世界 |
| Genie | Google | 交互式3D |
| Marble | World Labs | 空间智能 |

### 5. 机器人/动作 (Robotics)
| 模型 | 机构 | 类型 |
|-----|------|-----|
| RT-2 | Google | VLA |
| π0 | Physical Int | 扩散策略 |
| GR00T | NVIDIA | 机器人基础 |
| Figure | Figure AI | 人形机器人 |
| Optimus | Tesla | 人形机器人 |

### 6. 边缘/高效模型 (Edge AI)
| 技术 | 用途 |
|-----|-----|
| TTT | 测试时训练 |
| VMamba | 状态空间模型 |
| LoRA | 参数高效微调 |
| Quantization | 模型压缩 |

---

## 三、Physical AI 技术树

```
                    LLM (语言)
                       │
         ┌─────────────┼─────────────┐
         │             │             │
      Vision       Audio        Action
         │             │             │
         └─────────────┼─────────────┘
                       │
                    World Model
                       │
         ┌─────────────┼─────────────┐
         │             │             │
      JEPA         Cosmos        VLA
    (LeCun)       (NVIDIA)     (Google)
         │             │             │
      V-JEPA      GR00T         RT-2
         │             │             │
       PEVA        机器人         π0
                       │
                    Physical AI
                       │
         ┌─────────────┼─────────────┐
         │             │             │
   ClawGlasses    VJEPA       Hermes
   (传感器)       (我们)       (Agent)
```

---

## 四、关键技术详解

### 1. JEPA (Joint Embedding Predictive Architecture)
**核心思想**：不生成像素，而是预测抽象表征

**为什么重要**：
- 解决 LLM 无法理解物理世界的问题
- 误差可控，不累积
- 自监督学习，不需要标注

**发展**：
- I-JEPA (图像) → V-JEPA (视频) → V-JEPA 2 (物理) → PEVA (16秒预测)

### 2. VLA (Vision-Language-Action)
**核心思想**：端到端从视觉理解到动作执行

**应用**：
- 机器人控制
- 自动驾驶
- 智能制造

**代表工作**：
- RT-1/2 (Google)
- π0 (Physical Intelligence)
- GR00T (NVIDIA)

### 3. TTT (Test-Time Training)
**核心思想**：在推理时动态训练模型

**优势**：
- 适应新环境
- 边缘设备友好
- 实时学习

**应用**：
- Spatial-TTT (我们的实现)
- TTT-Linear
- TTT-Video

### 4. World Model
**核心思想**：建立物理世界的内部表征

**用途**：
- 规划和模拟
- 机器人预测
- 自动驾驶

---

## 五、数据需求

| 技术路线 | 数据类型 | 规模 |
|---------|----------|------|
| LLM | 文本 | Trillions tokens |
| 多模态 | 图像+视频 | Billions |
| VLA | 图像+动作 | 100K+ episodes |
| World Model | 视频 | Millions |
| Edge TTT | 实时视频流 | Real-time |

---

## 六、关键人物

| 人物 | 贡献 | 当前焦点 |
|-----|------|---------|
| Yann LeCun | 卷积网络, JEPA | World Models |
| Geoffrey Hinton | 反向传播, BERT | AI安全 |
| Ilya Sutskever | Transformer, GPT | Superalignment |
| Fei-Fei Li | ImageNet, Spatial AI | World Labs |
| Jensen Huang | NVIDIA AI | Physical AI平台 |
| Andrej Karpathy | Tesla AI, OpenAI | 教育 |
| Demis Hassabis | AlphaGo, Gemini | AGI |

---

## 七、我们的技术栈

```
🦪 Oysterworld Physical AI

硬件层: ClawGlasses → ClawPhones → IP Cameras
   ↓
边缘层: relay (H3 空间索引, 1FPS JPEG)
   ↓
处理层: Spatial-TTT (Test-Time Training)
   ↓
世界模型: VJEPA (128-dim 表征)
   ↓
推理层: Hermes-Agent
   ↓
存储层: pgvector + SpaceTimeDB + H3
```

---

## 八、学习路径

### 入门 (1-2周)
1. 了解 Transformer 基础
2. 学习 CLIP, Grounding DINO
3. 运行 Stable Diffusion

### 进阶 (1个月)
1. 部署本地 LLM (LLaMA, Qwen)
2. 学习 VLA 原理
3. 了解 World Model 概念

### 专家 (3个月+)
1. 实现 JEPA 架构
2. 部署 TTT 系统
3. 构建 Physical AI 应用
