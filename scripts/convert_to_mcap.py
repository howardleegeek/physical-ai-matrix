#!/usr/bin/env python3
"""
Convert a robot-episode dataset into MCAP files for Physical AI / VLA training.

MCAP (https://mcap.dev) is the de-facto container format for multimodal,
time-aligned robot data. This script writes one .mcap file per episode with
separate, time-stamped channels for each modality so the result can be opened
in Foxglove Studio and streamed by training pipelines (LeRobot, custom loaders,
robotics dataloaders, etc.).

Modalities supported (channels created only when the data exists):
  - RGB cameras        -> /camera/<name>      schema: foxglove.CompressedImage
  - Depth images       -> /depth/<name>       schema: foxglove.CompressedImage (png)
  - Robot state        -> /observation/state  schema: physical_ai.VectorStamped
  - Action             -> /action             schema: physical_ai.VectorStamped
  - Language instruction -> /task/instruction  schema: physical_ai.TaskInstruction

----------------------------------------------------------------------------
Expected on-disk layout (adapt with CLI flags if yours differs)
----------------------------------------------------------------------------
    dataset_root/
      episode_0001/
        meta.json            # {"instruction": "pick up the red cube", "fps": 30}
        cam_high/000000.jpg  # RGB frames, sorted by filename = time order
        cam_high/000001.jpg
        cam_wrist/000000.jpg
        depth/000000.png     # optional 16-bit depth frames
        states.csv           # header: t,joint_0,...,gripper,ee_x,ee_y,ee_z
        actions.csv          # header: t,action_0,...,action_m
      episode_0002/
        ...

Notes
  - The first CSV column is treated as time in SECONDS (relative to episode
    start). If there is no time column, pass --fps and timestamps are
    synthesised. Remaining columns become the vector `values` with `names`
    taken from the header row.
  - Image frame timestamps come from <camera>_times.csv (one float per line) if
    present, otherwise from --fps.
  - Image bytes are embedded as-is (no re-encoding); just point at .jpg/.png.

Quick start
    pip install -r scripts/requirements.txt
    python scripts/convert_to_mcap.py --demo                 # generate + convert a sample
    python scripts/convert_to_mcap.py ./dataset_root ./out   # convert your data
"""

from __future__ import annotations

import argparse
import base64
import csv
import glob
import json
import os
import sys
from datetime import datetime, timezone

try:
    from mcap.writer import Writer
except ImportError:
    sys.exit(
        "Missing dependency 'mcap'. Install with:\n"
        "    pip install -r scripts/requirements.txt\n"
        "    (or: pip install mcap)"
    )

# Fixed epoch base so re-runs are deterministic. Absolute wall-clock time does
# not matter for training; only the relative ordering within an episode does.
EPOCH_BASE_NS = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1e9)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


# --------------------------------------------------------------------------- #
# JSON schemas (kept minimal; channel/schema names match Foxglove well-known   #
# types so Foxglove Studio auto-recognises image panels).                      #
# --------------------------------------------------------------------------- #
COMPRESSED_IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "timestamp": {
            "type": "object",
            "properties": {"sec": {"type": "integer"}, "nsec": {"type": "integer"}},
        },
        "frame_id": {"type": "string"},
        "data": {"type": "string", "contentEncoding": "base64"},
        "format": {"type": "string"},
    },
}

VECTOR_STAMPED_SCHEMA = {
    "type": "object",
    "properties": {
        "timestamp": {
            "type": "object",
            "properties": {"sec": {"type": "integer"}, "nsec": {"type": "integer"}},
        },
        "names": {"type": "array", "items": {"type": "string"}},
        "values": {"type": "array", "items": {"type": "number"}},
    },
}

TASK_INSTRUCTION_SCHEMA = {
    "type": "object",
    "properties": {
        "timestamp": {
            "type": "object",
            "properties": {"sec": {"type": "integer"}, "nsec": {"type": "integer"}},
        },
        "instruction": {"type": "string"},
    },
}


def _stamp(ns: int) -> dict:
    return {"sec": ns // 1_000_000_000, "nsec": ns % 1_000_000_000}


def _ext_format(path: str) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return "jpeg" if ext == "jpg" else ext


# --------------------------------------------------------------------------- #
# Data loading (adapter layer) — edit these if your layout differs.            #
# --------------------------------------------------------------------------- #
def discover_episodes(root: str) -> list[str]:
    """Each immediate subdirectory of `root` is treated as one episode."""
    subdirs = [
        os.path.join(root, d)
        for d in sorted(os.listdir(root))
        if os.path.isdir(os.path.join(root, d))
    ]
    return subdirs


def list_image_dirs(episode_dir: str, depth_dir_name: str) -> tuple[list[str], str | None]:
    """Return (rgb_camera_dirs, depth_dir) auto-detected inside an episode."""
    cams, depth = [], None
    for name in sorted(os.listdir(episode_dir)):
        path = os.path.join(episode_dir, name)
        if not os.path.isdir(path):
            continue
        has_images = any(f.lower().endswith(IMAGE_EXTS) for f in os.listdir(path))
        if not has_images:
            continue
        if name == depth_dir_name:
            depth = path
        else:
            cams.append(path)
    return cams, depth


def sorted_frames(image_dir: str) -> list[str]:
    files = [
        f for f in os.listdir(image_dir) if f.lower().endswith(IMAGE_EXTS)
    ]
    return [os.path.join(image_dir, f) for f in sorted(files)]


def load_times(image_dir: str, n_frames: int, fps: float) -> list[float]:
    """Per-frame timestamps in seconds. Prefer <dir>_times.csv, else use fps."""
    times_path = image_dir.rstrip("/") + "_times.csv"
    if os.path.exists(times_path):
        with open(times_path) as f:
            ts = [float(line.strip()) for line in f if line.strip()]
        if len(ts) == n_frames:
            return ts
    return [i / fps for i in range(n_frames)]


def read_csv_series(csv_path: str, fps: float) -> tuple[list[str], list[tuple[float, list[float]]]]:
    """Return (value_names, [(t_seconds, values), ...]) from a CSV with header."""
    rows: list[tuple[float, list[float]]] = []
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        time_col = header[0].lower() in ("t", "time", "timestamp", "ts")
        names = header[1:] if time_col else header
        for i, raw in enumerate(reader):
            if not raw:
                continue
            if time_col:
                t = float(raw[0])
                vals = [float(x) for x in raw[1:]]
            else:
                t = i / fps
                vals = [float(x) for x in raw]
            rows.append((t, vals))
    return names, rows


# --------------------------------------------------------------------------- #
# MCAP writing                                                                 #
# --------------------------------------------------------------------------- #
class McapEpisodeWriter:
    def __init__(self, out_path: str):
        self._fh = open(out_path, "wb")
        self._w = Writer(self._fh)
        self._w.start()
        self._schema_ids: dict[str, int] = {}
        self._channel_ids: dict[str, int] = {}

    def _schema(self, name: str, schema: dict) -> int:
        if name not in self._schema_ids:
            self._schema_ids[name] = self._w.register_schema(
                name=name, encoding="jsonschema", data=json.dumps(schema).encode()
            )
        return self._schema_ids[name]

    def _channel(self, topic: str, schema_name: str, schema: dict) -> int:
        if topic not in self._channel_ids:
            self._channel_ids[topic] = self._w.register_channel(
                topic=topic,
                message_encoding="json",
                schema_id=self._schema(schema_name, schema),
            )
        return self._channel_ids[topic]

    def write_image(self, topic: str, frame_id: str, ns: int, raw: bytes, fmt: str):
        cid = self._channel(topic, "foxglove.CompressedImage", COMPRESSED_IMAGE_SCHEMA)
        msg = {
            "timestamp": _stamp(ns),
            "frame_id": frame_id,
            "data": base64.b64encode(raw).decode("ascii"),
            "format": fmt,
        }
        self._w.add_message(cid, log_time=ns, data=json.dumps(msg).encode(), publish_time=ns)

    def write_vector(self, topic: str, ns: int, names: list[str], values: list[float]):
        cid = self._channel(topic, "physical_ai.VectorStamped", VECTOR_STAMPED_SCHEMA)
        msg = {"timestamp": _stamp(ns), "names": names, "values": values}
        self._w.add_message(cid, log_time=ns, data=json.dumps(msg).encode(), publish_time=ns)

    def write_instruction(self, topic: str, ns: int, instruction: str):
        cid = self._channel(topic, "physical_ai.TaskInstruction", TASK_INSTRUCTION_SCHEMA)
        msg = {"timestamp": _stamp(ns), "instruction": instruction}
        self._w.add_message(cid, log_time=ns, data=json.dumps(msg).encode(), publish_time=ns)

    def close(self):
        self._w.finish()
        self._fh.close()


def convert_episode(episode_dir: str, out_path: str, args) -> dict:
    fps = args.fps
    meta_path = os.path.join(episode_dir, args.meta)
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
    fps = float(meta.get("fps", fps))
    instruction = meta.get("instruction") or args.instruction

    cam_dirs, depth_dir = list_image_dirs(episode_dir, args.depth_dir)
    writer = McapEpisodeWriter(out_path)
    counts: dict[str, int] = {}

    try:
        # Language instruction (logged once at episode start, t=0).
        if instruction:
            writer.write_instruction("/task/instruction", EPOCH_BASE_NS, instruction)
            counts["/task/instruction"] = 1

        # RGB cameras.
        for cam_dir in cam_dirs:
            name = os.path.basename(cam_dir)
            frames = sorted_frames(cam_dir)
            times = load_times(cam_dir, len(frames), fps)
            topic = f"/camera/{name}"
            for path, t in zip(frames, times):
                with open(path, "rb") as f:
                    raw = f.read()
                ns = EPOCH_BASE_NS + int(t * 1e9)
                writer.write_image(topic, name, ns, raw, _ext_format(path))
            counts[topic] = len(frames)

        # Depth.
        if depth_dir:
            frames = sorted_frames(depth_dir)
            times = load_times(depth_dir, len(frames), fps)
            topic = "/depth/" + os.path.basename(depth_dir)
            for path, t in zip(frames, times):
                with open(path, "rb") as f:
                    raw = f.read()
                ns = EPOCH_BASE_NS + int(t * 1e9)
                writer.write_image(topic, "depth", ns, raw, _ext_format(path))
            counts[topic] = len(frames)

        # Robot state.
        states_path = os.path.join(episode_dir, args.states)
        if os.path.exists(states_path):
            names, rows = read_csv_series(states_path, fps)
            for t, vals in rows:
                writer.write_vector("/observation/state", EPOCH_BASE_NS + int(t * 1e9), names, vals)
            counts["/observation/state"] = len(rows)

        # Action.
        actions_path = os.path.join(episode_dir, args.actions)
        if os.path.exists(actions_path):
            names, rows = read_csv_series(actions_path, fps)
            for t, vals in rows:
                writer.write_vector("/action", EPOCH_BASE_NS + int(t * 1e9), names, vals)
            counts["/action"] = len(rows)
    finally:
        writer.close()

    return counts


def run(args) -> int:
    root = args.dataset_root
    if not os.path.isdir(root):
        sys.exit(f"Dataset root not found: {root}")
    os.makedirs(args.out_dir, exist_ok=True)

    episodes = discover_episodes(root)
    if not episodes:
        sys.exit(f"No episode subdirectories found under {root}")

    total = 0
    for ep in episodes:
        name = os.path.basename(ep.rstrip("/"))
        out_path = os.path.join(args.out_dir, f"{name}.mcap")
        counts = convert_episode(ep, out_path, args)
        n_msgs = sum(counts.values())
        total += n_msgs
        size_kb = os.path.getsize(out_path) / 1024
        summary = ", ".join(f"{k}:{v}" for k, v in counts.items())
        print(f"✓ {name}.mcap  ({size_kb:.0f} KB, {n_msgs} msgs)  [{summary}]")

    print(f"\nDone. {len(episodes)} episode(s), {total} messages -> {args.out_dir}/")
    return 0


# --------------------------------------------------------------------------- #
# Demo: synthesise a tiny dataset and convert it, so the pipeline is runnable  #
# end-to-end without the real Drive data.                                      #
# --------------------------------------------------------------------------- #
def build_demo(root: str) -> None:
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        sys.exit("Demo needs numpy + Pillow:\n    pip install numpy pillow")

    rng = np.random.default_rng(0)
    for ep in range(1, 3):
        ep_dir = os.path.join(root, f"episode_{ep:04d}")
        os.makedirs(os.path.join(ep_dir, "cam_high"), exist_ok=True)
        os.makedirs(os.path.join(ep_dir, "cam_wrist"), exist_ok=True)
        os.makedirs(os.path.join(ep_dir, "depth"), exist_ok=True)
        n = 10
        for i in range(n):
            for cam in ("cam_high", "cam_wrist"):
                arr = (rng.random((64, 64, 3)) * 255).astype("uint8")
                Image.fromarray(arr).save(os.path.join(ep_dir, cam, f"{i:06d}.jpg"))
            depth = (rng.random((64, 64)) * 65535).astype("uint16")
            Image.fromarray(depth, mode="I;16").save(os.path.join(ep_dir, "depth", f"{i:06d}.png"))
        with open(os.path.join(ep_dir, "states.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "joint_0", "joint_1", "gripper", "ee_x", "ee_y", "ee_z"])
            for i in range(n):
                w.writerow([round(i / 10, 3)] + [round(float(x), 4) for x in rng.random(6)])
        with open(os.path.join(ep_dir, "actions.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "dx", "dy", "dz", "dgrip"])
            for i in range(n):
                w.writerow([round(i / 10, 3)] + [round(float(x), 4) for x in rng.random(4)])
        with open(os.path.join(ep_dir, "meta.json"), "w") as f:
            json.dump({"instruction": "pick up the red cube and place it in the bin", "fps": 10}, f)
    print(f"Demo dataset written to {root}/")


def main():
    p = argparse.ArgumentParser(description="Convert a robot-episode dataset to MCAP.")
    p.add_argument("dataset_root", nargs="?", help="Directory containing per-episode subfolders")
    p.add_argument("out_dir", nargs="?", default="mcap_out", help="Output directory (default: mcap_out)")
    p.add_argument("--fps", type=float, default=30.0, help="Fallback FPS when no timestamps present")
    p.add_argument("--meta", default="meta.json", help="Per-episode metadata filename")
    p.add_argument("--states", default="states.csv", help="Robot-state CSV filename")
    p.add_argument("--actions", default="actions.csv", help="Action CSV filename")
    p.add_argument("--depth-dir", default="depth", help="Depth subfolder name")
    p.add_argument("--instruction", default="", help="Default language instruction if no meta.json")
    p.add_argument("--demo", action="store_true", help="Generate a sample dataset and convert it")
    args = p.parse_args()

    if args.demo:
        demo_root = "demo_dataset"
        build_demo(demo_root)
        args.dataset_root = demo_root
        args.out_dir = "demo_mcap_out"

    if not args.dataset_root:
        p.error("dataset_root is required (or pass --demo)")

    return run(args)


if __name__ == "__main__":
    sys.exit(main())
