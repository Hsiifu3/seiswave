"""
地震动文件读写模块

支持格式：
- PEER NGA AT2（新旧两种头部格式）
- 纯文本 txt（单列/双列）
- CSV

参考实现：
- EQSignal C++ readnga() / readtxt()
- MATLAB SelectWave_0802g.m 文件读取部分
"""

import os
import re
import glob
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EQRecord:
    """地震动记录数据容器"""
    acc: np.ndarray                    # 加速度时程
    dt: float                          # 时间步长 (s)
    name: str = ""                     # 记录名称
    filepath: str = ""                 # 文件路径
    metadata: dict = field(default_factory=dict)  # 元数据（事件名、台站等）
    npts: int = 0                      # 数据点数

    def __post_init__(self):
        self.npts = len(self.acc)


class FileIO:
    """地震动文件读写"""

    # ──────────────────────────── 读取 ────────────────────────────

    @staticmethod
    def read_at2(filepath: str) -> EQRecord:
        """读取 PEER NGA AT2 格式文件

        支持两种头部格式：
        - 旧格式：第4行 "NPTS= xxxx, DT= x.xxxx SEC"
        - 新格式：第4行 "xxxx    x.xxxx" 或含 "=" 分隔

        Parameters
        ----------
        filepath : str
            AT2 文件路径

        Returns
        -------
        EQRecord
            包含加速度数据、dt 和元数据的记录对象

        Raises
        ------
        FileNotFoundError
            文件不存在
        ValueError
            无法解析文件格式
        """
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"文件不存在: {filepath}")

        with open(filepath, 'r', errors='replace') as f:
            lines = f.readlines()

        if len(lines) < 5:
            raise ValueError(f"AT2 文件行数不足: {filepath}")

        # 解析元数据（前3行）
        metadata = {
            'header1': lines[0].strip(),
            'header2': lines[1].strip(),
            'header3': lines[2].strip(),
        }

        # 解析第4行：NPTS 和 DT
        header4 = lines[3].strip()
        dt = None
        npts = None

        # 尝试格式1: "NPTS= 4096, DT= 0.0050 SEC"
        match = re.search(r'NPTS\s*=?\s*(\d+)', header4, re.IGNORECASE)
        if match:
            npts = int(match.group(1))

        match_dt = re.search(r'DT\s*=?\s*([0-9.eE+-]+)', header4, re.IGNORECASE)
        if match_dt:
            dt = float(match_dt.group(1))

        # 尝试格式2: 纯数字 "4096    0.0050"
        if dt is None:
            parts = header4.split()
            if len(parts) >= 2:
                try:
                    npts = int(parts[0])
                    dt = float(parts[1])
                except ValueError:
                    pass

        # 尝试格式3: 用 "=" 分隔的其他变体
        if dt is None:
            parts = header4.replace('=', ' ').replace(',', ' ').split()
            nums = []
            for p in parts:
                try:
                    nums.append(float(p))
                except ValueError:
                    continue
            if len(nums) >= 2:
                npts = int(nums[0])
                dt = nums[1]

        if dt is None:
            raise ValueError(
                f"无法从第4行解析 dt: '{header4}'\n文件: {filepath}"
            )

        # 读取加速度数据（第5行开始）
        acc_data = []
        for line in lines[4:]:
            for val in line.split():
                try:
                    acc_data.append(float(val))
                except ValueError:
                    continue

        acc = np.array(acc_data, dtype=np.float64)

        # 如果解析到 npts，验证一致性
        if npts is not None and len(acc) != npts:
            # 有些文件末尾有多余数据，截断到 npts
            if len(acc) > npts:
                acc = acc[:npts]
            # 数据不足时不截断，保留实际长度

        name = os.path.splitext(os.path.basename(filepath))[0]

        return EQRecord(
            acc=acc, dt=dt, name=name,
            filepath=filepath, metadata=metadata
        )

    @staticmethod
    def read_txt(filepath: str, dt: float = None,
                 skip_rows: int = 0, single_col: bool = True) -> EQRecord:
        """读取纯文本格式地震动文件

        Parameters
        ----------
        filepath : str
            文件路径
        dt : float, optional
            时间步长。双列格式时可从数据推断
        skip_rows : int
            跳过的头部行数
        single_col : bool
            True=单列（仅加速度），False=双列（时间+加速度）

        Returns
        -------
        EQRecord
        """
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"文件不存在: {filepath}")

        data = np.loadtxt(filepath, skiprows=skip_rows)

        if data.ndim == 1:
            # 单列数据
            acc = data
            if dt is None:
                raise ValueError("单列格式必须指定 dt")
        elif data.ndim == 2:
            if data.shape[1] == 1:
                acc = data[:, 0]
                if dt is None:
                    raise ValueError("单列格式必须指定 dt")
            elif data.shape[1] >= 2:
                if single_col:
                    # 多列但用户指定单列模式，取第一列
                    acc = data[:, 0]
                    if dt is None:
                        raise ValueError("单列格式必须指定 dt")
                else:
                    # 双列：第一列时间，第二列加速度
                    time = data[:, 0]
                    acc = data[:, 1]
                    if dt is None:
                        dt = np.mean(np.diff(time))
            else:
                raise ValueError(f"无法解析文件格式: {filepath}")
        else:
            raise ValueError(f"数据维度异常: {data.ndim}")

        name = os.path.splitext(os.path.basename(filepath))[0]

        return EQRecord(acc=acc, dt=dt, name=name, filepath=filepath)

    @staticmethod
    def batch_load(directory: str, pattern: str = "*.AT2",
                   recursive: bool = False) -> list[EQRecord]:
        """批量加载目录下的地震动文件

        Parameters
        ----------
        directory : str
            目录路径
        pattern : str
            文件匹配模式，默认 "*.AT2"
        recursive : bool
            是否递归搜索子目录

        Returns
        -------
        list[EQRecord]
            成功加载的记录列表（跳过解析失败的文件）
        """
        if not os.path.isdir(directory):
            raise FileNotFoundError(f"目录不存在: {directory}")

        if recursive:
            search = os.path.join(directory, '**', pattern)
            files = glob.glob(search, recursive=True)
        else:
            search = os.path.join(directory, pattern)
            files = glob.glob(search)

        # 不区分大小写匹配
        if not files:
            pat_lower = pattern.lower()
            all_files = []
            if recursive:
                for root, dirs, fnames in os.walk(directory):
                    for fn in fnames:
                        if fn.lower().endswith(pat_lower.replace('*', '')):
                            all_files.append(os.path.join(root, fn))
            else:
                for fn in os.listdir(directory):
                    if fn.lower().endswith(pat_lower.replace('*', '')):
                        all_files.append(os.path.join(directory, fn))
            files = all_files

        files.sort()
        records = []
        errors = []

        for fp in files:
            try:
                ext = os.path.splitext(fp)[1].lower()
                if ext in ('.at2',):
                    rec = FileIO.read_at2(fp)
                elif ext in ('.txt', '.dat'):
                    # txt 文件尝试自动检测格式
                    rec = FileIO._auto_read_txt(fp)
                else:
                    continue
                records.append(rec)
            except Exception as e:
                errors.append((fp, str(e)))

        if errors:
            import warnings
            for fp, err in errors:
                warnings.warn(f"跳过文件 {os.path.basename(fp)}: {err}")

        return records

    @staticmethod
    def _auto_read_txt(filepath: str) -> EQRecord:
        """自动检测 txt 文件格式并读取

        尝试顺序：
        1. 双列（时间+加速度）
        2. 单列（需要从文件名或默认值推断 dt）
        """
        try:
            data = np.loadtxt(filepath, comments='#')
        except Exception:
            # 尝试跳过头部行
            with open(filepath, 'r') as f:
                lines = f.readlines()
            skip = 0
            for i, line in enumerate(lines):
                try:
                    float(line.split()[0])
                    skip = i
                    break
                except (ValueError, IndexError):
                    continue
            data = np.loadtxt(filepath, skiprows=skip)

        if data.ndim == 2 and data.shape[1] >= 2:
            time = data[:, 0]
            acc = data[:, 1]
            dt = np.mean(np.diff(time))
        elif data.ndim == 1 or (data.ndim == 2 and data.shape[1] == 1):
            acc = data.flatten()
            dt = 0.02  # 默认 dt
        else:
            raise ValueError(f"无法自动解析: {filepath}")

        name = os.path.splitext(os.path.basename(filepath))[0]
        return EQRecord(acc=acc, dt=dt, name=name, filepath=filepath)

    # ──────────────────────────── 写入 ────────────────────────────

    @staticmethod
    def write_at2(filepath: str, acc: np.ndarray, dt: float,
                  metadata: dict = None) -> None:
        """写入 PEER NGA AT2 格式

        Parameters
        ----------
        filepath : str
            输出文件路径
        acc : np.ndarray
            加速度时程
        dt : float
            时间步长
        metadata : dict, optional
            元数据（header1, header2, header3）
        """
        meta = metadata or {}
        npts = len(acc)

        with open(filepath, 'w') as f:
            f.write(meta.get('header1', 'PEER NGA STRONG MOTION DATABASE RECORD') + '\n')
            f.write(meta.get('header2', f'EQSignalPy Generated, dt={dt:.4f}s') + '\n')
            f.write(meta.get('header3', 'ACCELERATION (G)') + '\n')
            f.write(f'NPTS= {npts:>8d}, DT= {dt:>10.6f} SEC\n')

            # 每行5个数据
            for i in range(0, npts, 5):
                chunk = acc[i:i+5]
                line = ''.join(f'{v:>15.7E}' for v in chunk)
                f.write(line + '\n')

    @staticmethod
    def write_txt(filepath: str, acc: np.ndarray, dt: float,
                  two_col: bool = False) -> None:
        """写入纯文本格式

        Parameters
        ----------
        filepath : str
            输出文件路径
        acc : np.ndarray
            加速度时程
        dt : float
            时间步长
        two_col : bool
            True=双列（时间+加速度），False=单列
        """
        if two_col:
            time = np.arange(len(acc)) * dt
            data = np.column_stack([time, acc])
            np.savetxt(filepath, data, fmt='%15.7E', delimiter='  ',
                       header=f'Time(s)  Acceleration\ndt={dt}  npts={len(acc)}',
                       comments='# ')
        else:
            np.savetxt(filepath, acc, fmt='%15.7E',
                       header=f'dt={dt}  npts={len(acc)}',
                       comments='# ')

    @staticmethod
    def write_csv(filepath: str, **columns) -> None:
        """写入 CSV 格式

        Parameters
        ----------
        filepath : str
            输出文件路径
        **columns
            列名=数据数组，如 period=periods, sa=sa_values
        """
        import csv

        names = list(columns.keys())
        arrays = [np.asarray(v) for v in columns.values()]
        n = max(len(a) for a in arrays)

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(names)
            for i in range(n):
                row = []
                for a in arrays:
                    if i < len(a):
                        row.append(f'{a[i]:.7E}')
                    else:
                        row.append('')
                writer.writerow(row)
