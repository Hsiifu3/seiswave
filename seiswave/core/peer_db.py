"""
PEER NGA 数据库管理模块

扫描 AT2 文件、解析元数据、建立索引、延迟加载波形、反应谱缓存。
"""

import os
import re
import json
import warnings
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable


@dataclass
class PeerRecord:
    """PEER NGA 单条记录"""
    rsn: int = 0
    event: str = ""
    station: str = ""
    date: str = ""
    component: str = ""
    direction: str = "H"        # 'H' 水平 / 'V' 竖向
    filepath: str = ""
    dt: float = 0.0
    npts: int = 0
    pga: float = 0.0
    duration: float = 0.0       # 总持时 (s)
    eff_duration: float = 0.0   # 有效持时 5%-95% Arias (s)
    acc: Optional[np.ndarray] = field(default=None, repr=False)
    sa: Optional[np.ndarray] = field(default=None, repr=False)

    def to_dict(self):
        """序列化为 JSON 兼容字典（不含波形和谱）"""
        return {k: v for k, v in asdict(self).items()
                if k not in ('acc', 'sa')}


class PeerDatabase:
    """PEER NGA 数据库"""

    # 竖向分量关键词
    _VERTICAL_KEYS = {'UP', 'DWN', 'DOWN', 'VERT', 'V', '-UP'}

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), '..', '..',
                                     'data', 'peer_nga')
        self.data_dir = os.path.abspath(data_dir)
        self._cache_dir = os.path.join(self.data_dir, '_cache')
        self.records: list[PeerRecord] = []
        self._spectra_periods: Optional[np.ndarray] = None

    def build_index(self, progress_cb: Callable = None) -> int:
        """扫描 AT2 文件，解析头部元数据，建立索引

        Returns
        -------
        int : 成功解析的记录数
        """
        at2_files = sorted([f for f in os.listdir(self.data_dir)
                            if f.upper().endswith('.AT2')])
        self.records = []
        total = len(at2_files)

        for idx, fname in enumerate(at2_files):
            fpath = os.path.join(self.data_dir, fname)
            try:
                rec = self._parse_at2_header(fpath, fname)
                self.records.append(rec)
            except Exception as e:
                warnings.warn(f"跳过 {fname}: {e}")

            if progress_cb and idx % 50 == 0:
                progress_cb(idx, total)

        if progress_cb:
            progress_cb(total, total)

        return len(self.records)

    def _parse_at2_header(self, fpath: str, fname: str) -> PeerRecord:
        """解析单个 AT2 文件头部"""
        rec = PeerRecord(filepath=fpath)

        # 从文件名解析 RSN
        m = re.match(r'RSN(\d+)_', fname)
        if m:
            rec.rsn = int(m.group(1))

        # 从文件名提取分量标识（最后一个下划线后的部分）
        parts = fname.rsplit('.', 1)[0].split('_')
        if len(parts) >= 3:
            rec.component = parts[-1]
        elif len(parts) == 2:
            rec.component = parts[1]

        # 判断方向：分量标识含 UP/DWN/DOWN/VERT → 竖向
        comp_upper = rec.component.upper() if rec.component else ""
        is_vertical = False
        for vk in ('UP', 'DWN', 'DOWN', 'VERT'):
            if comp_upper.endswith(vk) or comp_upper == vk:
                is_vertical = True
                break
            if f'-{vk}' in comp_upper:
                is_vertical = True
                break
        rec.direction = 'V' if is_vertical else 'H'

        # 读取头部（只读前 5 行 + 少量数据行来算 PGA）
        with open(fpath, 'r', errors='replace') as f:
            lines = []
            for i, line in enumerate(f):
                lines.append(line)
                if i >= 3:
                    break

        if len(lines) < 4:
            raise ValueError("文件行数不足")

        # 第 2 行：事件名, 日期, 台站, 分量
        header2 = lines[1].strip()
        h2_parts = [p.strip() for p in header2.split(',')]
        if len(h2_parts) >= 3:
            rec.event = h2_parts[0]
            rec.date = h2_parts[1].strip()
            rec.station = h2_parts[2].strip()
        elif len(h2_parts) == 2:
            rec.event = h2_parts[0]
            rec.station = h2_parts[1].strip()
        else:
            rec.event = header2

        # 第 4 行：NPTS, DT
        header4 = lines[3].strip()
        m_npts = re.search(r'NPTS\s*=?\s*(\d+)', header4, re.IGNORECASE)
        m_dt = re.search(r'DT\s*=?\s*([0-9.eE+-]+)', header4, re.IGNORECASE)
        if m_npts:
            rec.npts = int(m_npts.group(1))
        if m_dt:
            rec.dt = float(m_dt.group(1))

        if rec.dt <= 0:
            # 尝试纯数字格式
            nums = re.findall(r'[0-9.eE+-]+', header4)
            if len(nums) >= 2:
                rec.npts = int(float(nums[0]))
                rec.dt = float(nums[1])

        if rec.dt <= 0:
            raise ValueError(f"无法解析 dt: {header4}")

        rec.duration = rec.npts * rec.dt

        # 快速读取全部数据计算 PGA 和有效持时
        self._load_acc_and_stats(rec)

        return rec

    def _load_acc_and_stats(self, rec: PeerRecord):
        """加载波形并计算 PGA 和有效持时"""
        with open(rec.filepath, 'r', errors='replace') as f:
            lines = f.readlines()

        acc_data = []
        for line in lines[4:]:
            for val in line.split():
                try:
                    acc_data.append(float(val))
                except ValueError:
                    continue

        acc = np.array(acc_data, dtype=np.float64)
        if rec.npts > 0 and len(acc) > rec.npts:
            acc = acc[:rec.npts]

        rec.npts = len(acc)
        rec.pga = float(np.max(np.abs(acc))) if len(acc) > 0 else 0.0
        rec.duration = rec.npts * rec.dt

        # 有效持时（5%-95% Arias intensity）
        rec.eff_duration = self._arias_duration(acc, rec.dt)

        # 不保留波形（延迟加载）
        rec.acc = None

    @staticmethod
    def _arias_duration(acc: np.ndarray, dt: float) -> float:
        """计算 5%-95% Arias 强度有效持时"""
        if len(acc) < 2:
            return 0.0
        ia = np.cumsum(acc ** 2) * dt * np.pi / (2.0 * 9.81)
        ia_total = ia[-1]
        if ia_total <= 0:
            return 0.0
        ia_norm = ia / ia_total
        i5 = np.searchsorted(ia_norm, 0.05)
        i95 = np.searchsorted(ia_norm, 0.95)
        return (i95 - i5) * dt

    def get_horizontal(self) -> list[PeerRecord]:
        """返回所有水平分量记录"""
        return [r for r in self.records if r.direction == 'H']

    def get_vertical(self) -> list[PeerRecord]:
        """返回所有竖向分量记录"""
        return [r for r in self.records if r.direction == 'V']

    def load_waveform(self, record: PeerRecord) -> np.ndarray:
        """延迟加载单条波形"""
        if record.acc is not None:
            return record.acc

        from .io import FileIO
        eq = FileIO.read_at2(record.filepath)
        record.acc = eq.acc
        return record.acc

    def filter(self, rsn: int = None, event: str = None,
               station: str = None, pga_range: tuple = None,
               duration_range: tuple = None,
               direction: str = None) -> list[PeerRecord]:
        """按条件过滤记录"""
        result = self.records
        if rsn is not None:
            result = [r for r in result if r.rsn == rsn]
        if event is not None:
            event_lower = event.lower()
            result = [r for r in result if event_lower in r.event.lower()]
        if station is not None:
            station_lower = station.lower()
            result = [r for r in result if station_lower in r.station.lower()]
        if pga_range is not None:
            lo, hi = pga_range
            result = [r for r in result if lo <= r.pga <= hi]
        if duration_range is not None:
            lo, hi = duration_range
            result = [r for r in result if lo <= r.eff_duration <= hi]
        if direction is not None:
            result = [r for r in result if r.direction == direction]
        return result

    # ── 索引持久化 ──

    def save_index(self):
        """保存索引到 JSON"""
        os.makedirs(self._cache_dir, exist_ok=True)
        path = os.path.join(self._cache_dir, 'index.json')
        data = [r.to_dict() for r in self.records]
        with open(path, 'w') as f:
            json.dump(data, f, indent=1, ensure_ascii=False)

    def load_index(self) -> bool:
        """从 JSON 加载索引

        Returns
        -------
        bool : 是否成功加载
        """
        path = os.path.join(self._cache_dir, 'index.json')
        if not os.path.isfile(path):
            return False
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            self.records = []
            for d in data:
                rec = PeerRecord(**{k: v for k, v in d.items()
                                    if k in PeerRecord.__dataclass_fields__})
                self.records.append(rec)
            return True
        except Exception:
            return False

    # ── 反应谱缓存 ──

    def precompute_spectra(self, periods: np.ndarray = None,
                           zeta: float = 0.05,
                           progress_cb: Callable = None) -> None:
        """批量预计算所有记录的反应谱

        Parameters
        ----------
        periods : 周期数组，默认 0.04-6.0s 200 点
        zeta : 阻尼比
        progress_cb : fn(current, total)
        """
        from .spectrum import Spectra
        from .fortran_bridge import HAS_FORTRAN, spectrum_mixed

        if periods is None:
            periods = Spectra.default_periods(0.04, 6.0, 200)
        self._spectra_periods = periods

        total = len(self.records)
        for idx, rec in enumerate(self.records):
            acc = self.load_waveform(rec)

            if HAS_FORTRAN:
                spa, _ = spectrum_mixed(acc, rec.dt, zeta, periods)
                rec.sa = np.abs(spa)
            else:
                sp = Spectra.compute(acc, rec.dt, periods, zeta, method='mixed')
                rec.sa = sp.sa

            # 释放波形内存
            rec.acc = None

            if progress_cb and idx % 20 == 0:
                progress_cb(idx, total)

        if progress_cb:
            progress_cb(total, total)

        self._save_spectra_cache(periods, zeta)

    def _save_spectra_cache(self, periods: np.ndarray, zeta: float):
        """保存反应谱缓存"""
        os.makedirs(self._cache_dir, exist_ok=True)
        zeta_str = f"{int(zeta * 1000):03d}"
        path = os.path.join(self._cache_dir, f'spectra_z{zeta_str}.npz')

        rsns = np.array([r.rsn for r in self.records])
        sa_matrix = np.array([r.sa if r.sa is not None
                              else np.zeros(len(periods))
                              for r in self.records])

        np.savez_compressed(path, periods=periods, rsn=rsns, sa=sa_matrix)

    def load_spectra_cache(self, zeta: float = 0.05) -> bool:
        """加载反应谱缓存

        Returns
        -------
        bool : 是否成功加载
        """
        zeta_str = f"{int(zeta * 1000):03d}"
        path = os.path.join(self._cache_dir, f'spectra_z{zeta_str}.npz')
        if not os.path.isfile(path):
            return False

        try:
            data = np.load(path)
            periods = data['periods']
            rsns = data['rsn']
            sa_matrix = data['sa']
            self._spectra_periods = periods

            # 按 RSN 匹配
            rsn_to_sa = dict(zip(rsns, sa_matrix))
            matched = 0
            for rec in self.records:
                if rec.rsn in rsn_to_sa:
                    rec.sa = rsn_to_sa[rec.rsn]
                    matched += 1

            # 同一 RSN 多个分量：按文件名匹配
            if matched < len(self.records):
                # 按顺序分配（缓存和索引顺序一致）
                for i, rec in enumerate(self.records):
                    if rec.sa is None and i < len(sa_matrix):
                        rec.sa = sa_matrix[i]

            return True
        except Exception:
            return False

    @property
    def spectra_periods(self) -> Optional[np.ndarray]:
        return self._spectra_periods

    def __len__(self):
        return len(self.records)

    def __repr__(self):
        n_h = sum(1 for r in self.records if r.direction == 'H')
        n_v = sum(1 for r in self.records if r.direction == 'V')
        return f"PeerDatabase({len(self.records)} records, {n_h}H + {n_v}V)"
