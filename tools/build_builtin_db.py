#!/usr/bin/env python3
"""把 PEER 地震动 zip 预处理成紧凑内置库。

产物（默认写到 seiswave/data/builtin_db/）：
- waveforms.npz   每条加速度的 int16 量化数组（键=记录 id）
- spectra_z0.05.npz   全部记录的反应谱 sa（N×Np float32）+ ids + periods
- index.json      每条元数据：id/event/station/component/dt/npts/pga/duration/eff_duration/scale

策略：仅水平分量、int16 峰值相对量化（反应谱误差 <0.1%）。

用法：
    python tools/build_builtin_db.py ~/Downloads/peer_ground_motion.zip
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seiswave.core.io import FileIO          # noqa: E402
from seiswave.core.signal import EQSignal    # noqa: E402
from seiswave.core.spectrum import Spectra   # noqa: E402

# 竖向分量标记（跳过）
_VERT = re.compile(r"(-?UP|-?UD|-?V|-?Z|VERT)$", re.IGNORECASE)


def _parse_header2(h2: str, rid: str) -> dict:
    """从 PEER AT2 第二行解析 事件/日期/台站/分量(格式不统一,稳健提取)。"""
    parts = [p.strip() for p in h2.split(",")]
    m = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", h2)
    date = m.group(0) if m else ""
    ev = re.match(
        r"^([A-Za-z][A-Za-z0-9\s\-\.&/]*?)(?=\s*\d{1,2}/|\s+\d{4}\b|\s+\d{2}:\d{2}|$)",
        parts[0],
    )
    event = (ev.group(1) if ev else parts[0]).strip()
    event = re.sub(r"\s+EQ\.?$", "", event).strip() or parts[0]
    station = parts[-2].strip() if len(parts) >= 2 else ""
    comp = re.split(r"[(]", parts[-1])[0].strip() if parts else ""
    if not comp and "-" in rid:
        comp = rid.split("-")[-1]
    return {"event": event, "date": date, "station": station, "component": comp}


def _is_horizontal(name: str) -> bool:
    stem = Path(name).stem
    if not name.lower().endswith((".at2",)):
        return False
    # 去掉末尾分量 token 判断
    return _VERT.search(stem) is None


def _record_id(name: str) -> str:
    return Path(name).stem


def main(zip_path: str, out_dir: str | None = None, limit: int = 0) -> None:
    out = Path(out_dir) if out_dir else ROOT / "seiswave" / "data" / "builtin_db"
    out.mkdir(parents=True, exist_ok=True)
    periods = Spectra.default_periods()

    waveforms: dict[str, np.ndarray] = {}
    index: dict[str, dict] = {}
    sa_list: list[np.ndarray] = []
    sa_ids: list[str] = []

    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if _is_horizontal(n)]
        names.sort()
        if limit:
            names = names[:limit]
        total = len(names)
        print(f"水平分量记录: {total} 条")
        kept = skipped = 0
        for i, name in enumerate(names, 1):
            rid = _record_id(name)
            if rid in index:
                continue
            try:
                data = zf.read(name)
                with tempfile.NamedTemporaryFile(suffix=".at2", delete=False) as tf:
                    tf.write(data)
                    tmp = tf.name
                rec = FileIO.read_at2(tmp)
                os.unlink(tmp)
                acc = np.asarray(rec.acc, dtype=np.float64)
                if acc.size < 2 or not np.isfinite(acc).all():
                    skipped += 1
                    continue
                peak = float(np.max(np.abs(acc)))
                if peak <= 0:
                    skipped += 1
                    continue
                scale = peak / 32767.0
                q = np.round(acc / scale).astype(np.int16)

                sig = EQSignal(acc, rec.dt)
                sig.a2vd()
                sp = Spectra.compute(acc, rec.dt, periods, zeta=0.05)

                meta = rec.metadata or {}
                prov = _parse_header2(str(meta.get("header2", "")), rid)
                index[rid] = {
                    "id": rid,
                    "event": prov["event"],
                    "date": prov["date"],
                    "station": prov["station"],
                    "component": prov["component"],
                    "dt": float(rec.dt),
                    "npts": int(acc.size),
                    "pga": peak,
                    "duration": float(acc.size * rec.dt),
                    "eff_duration": float(sig.effective_duration),
                    "scale": scale,
                }
                waveforms[rid] = q
                sa_list.append(np.asarray(sp.sa, dtype=np.float32))
                sa_ids.append(rid)
                kept += 1
            except Exception as exc:
                skipped += 1
                if skipped <= 10:
                    print(f"  跳过 {name}: {exc}")
            if i % 500 == 0:
                print(f"  {i}/{total}  入库 {kept} 跳过 {skipped}")

    print(f"\n保留 {kept} 条,跳过 {skipped} 条。写出...")
    np.savez_compressed(out / "waveforms.npz", **waveforms)
    np.savez_compressed(
        out / "spectra_z0.05.npz",
        sa=np.vstack(sa_list).astype(np.float32),
        ids=np.array(sa_ids),
        periods=periods.astype(np.float64),
    )
    (out / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=0), encoding="utf-8"
    )
    wf_mb = (out / "waveforms.npz").stat().st_size / 1048576
    sp_mb = (out / "spectra_z0.05.npz").stat().st_size / 1048576
    print(f"waveforms.npz {wf_mb:.1f}MB  spectra {sp_mb:.1f}MB  index {len(index)} 条")
    print(f"内置库总计 ≈ {wf_mb + sp_mb:.1f}MB  →  {out}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None,
         int(sys.argv[3]) if len(sys.argv) > 3 else 0)
