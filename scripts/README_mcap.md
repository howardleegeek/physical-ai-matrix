# 把数据集转成 MCAP（用于 Physical AI / VLA 训练）

`convert_to_mcap.py` 把「按 episode 组织的机器人数据」转成 **MCAP** 文件——
每个 episode 一个 `.mcap`，里面按时间戳对齐多路 channel，可直接用
[Foxglove Studio](https://foxglove.dev) 打开，也能被训练 pipeline 流式读取。

> ⚠️ **为什么不能在云端 Claude 会话里跑：** 云端容器是隔离沙箱，网络策略
> 封禁了 Google 全域（`google.com` 本身就 403），也无法 ssh 到内网的
> `minipc1`。所以**下载 Drive 数据 + 转换都要在 minipc1（或任意能访问 Drive
> 的机器）上跑**。下面就是 minipc1 上的完整步骤。

---

## 1. 在 minipc1 上拉代码 + 装依赖

```bash
git clone <repo>            # 或在已有 clone 里：git pull
cd physical-ai-matrix
git checkout claude/mcap-format-conversion-ovmo0n
pip install -r scripts/requirements.txt
```

## 2. 从公开 Google Drive 文件夹下载数据

```bash
pip install gdown
gdown --folder "https://drive.google.com/drive/folders/1dwuNEKJPM20mxCw6aoMvAyveFug2lAfU" -O ./dataset_root
```

- 文件夹必须设为「知道链接的任何人可查看」，`gdown` 才能免登录下载。
- 文件多 / 体积大时 `gdown` 可能限速，可分批或改用 `rclone`（配 Drive remote）。

## 3. 先跑 demo 确认环境 OK（可选，强烈建议）

```bash
python scripts/convert_to_mcap.py --demo
# -> demo_mcap_out/episode_0001.mcap 等，可拖进 Foxglove Studio 看效果
```

## 4. 转换你的数据

```bash
python scripts/convert_to_mcap.py ./dataset_root ./mcap_out
```

输出示例：
```
✓ episode_0001.mcap  (135 KB, 51 msgs)  [/camera/cam_high:10, /observation/state:10, ...]
```

---

## 期望的目录结构

脚本把 `dataset_root` 下**每个一级子目录当作一个 episode**：

```
dataset_root/
  episode_0001/
    meta.json            # {"instruction": "pick up the red cube", "fps": 30}
    cam_high/000000.jpg  # RGB 帧，按文件名排序 = 时间顺序
    cam_wrist/000000.jpg
    depth/000000.png     # 可选：16-bit 深度帧
    states.csv           # 表头: t,joint_0,...,gripper,ee_x,ee_y,ee_z
    actions.csv          # 表头: t,action_0,...
```

生成的 channel（**有数据才建**）：

| Channel | 模态 | Schema |
|---|---|---|
| `/camera/<name>`     | RGB 相机（每个相机一路） | `foxglove.CompressedImage` |
| `/depth/<name>`      | 深度图（png）            | `foxglove.CompressedImage` |
| `/observation/state` | 机器人本体状态            | `physical_ai.VectorStamped` |
| `/action`            | 动作                     | `physical_ai.VectorStamped` |
| `/task/instruction`  | 语言指令                 | `physical_ai.TaskInstruction` |

### 时间戳规则
- CSV 第一列若叫 `t/time/timestamp/ts`，按**秒**解析；否则用 `--fps` 合成。
- 图像优先读同名 `<dir>_times.csv`（每行一个秒数），否则用 `--fps`。

### 常用参数（适配你自己的布局）
```bash
python scripts/convert_to_mcap.py ./dataset_root ./mcap_out \
  --fps 30 \
  --depth-dir depth \
  --states states.csv \
  --actions actions.csv \
  --meta meta.json
```

---

## 如果你的源数据是别的格式

| 你的数据 | 怎么办 |
|---|---|
| **ROS1/ROS2 bag**（`.bag` / `.db3`） | 不用这个脚本，直接 `mcap convert in.bag out.mcap`（装 [mcap CLI](https://github.com/foxglove/mcap)） |
| **HDF5 / LeRobot / RLDS** | 改 `convert_to_mcap.py` 里的 *adapter layer*（`discover_episodes` / `read_csv_series` / `list_image_dirs`），其余 MCAP 写入逻辑可复用 |
| **布局和上面差很多** | 把你真实的目录树发我，我按你的结构改适配层 |

> 把数据的真实目录结构（`tree -L 3 dataset_root` 的输出）发我，我可以把适配层
> 改成跟你的数据完全对上，免去手动调参数。
