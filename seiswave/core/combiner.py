"""
组合输出引擎

将天然波选取结果 + 人工波生成结果组合为最终输出包。
支持 7 组三向输入（5 天然 + 2 人工）。
"""

import os
import io
import json
import base64
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

from .peer_db import PeerDatabase, PeerRecord
from .selector import SelectionResult, SelectionConfig
from .code_spec import CodeSpectrum
from .signal import EQSignal
from .spectrum import Spectra
from .io import FileIO


@dataclass
class ValidationResult:
    """规范校验结果"""
    passed: bool
    n_groups: int
    n_required: int
    individual_checks: list  # [(group_name, ratio, passed), ...]
    mean_check: bool
    mean_ratios: Optional[np.ndarray] = field(default=None, repr=False)
    envelope_check: bool = True
    messages: list = field(default_factory=list)


@dataclass
class WaveGroup:
    """一组三向地震动"""
    name: str
    source: str                          # 'natural' / 'artificial'
    rsn: int = 0
    event: str = ""
    station: str = ""
    scale_factor: float = 1.0
    match_error: float = 0.0
    h1: Optional[EQSignal] = field(default=None, repr=False)
    h2: Optional[EQSignal] = field(default=None, repr=False)
    v: Optional[EQSignal] = field(default=None, repr=False)


class Combiner:
    """组合输出引擎"""

    def __init__(self, output_dir: str = None):
        if output_dir is None:
            output_dir = os.path.join(os.getcwd(), 'output')
        self.output_dir = os.path.abspath(output_dir)
        self.groups: list[WaveGroup] = []

    def add_natural(self, result: SelectionResult,
                    database: PeerDatabase) -> WaveGroup:
        """从选波结果添加天然波组

        自动查找同 RSN 的三个分量（H1, H2, V）。
        """
        rec = result.record
        rsn = rec.rsn

        # 查找同 RSN 的所有分量
        all_comps = database.filter(rsn=rsn)
        h_comps = [r for r in all_comps if r.direction == 'H']
        v_comps = [r for r in all_comps if r.direction == 'V']

        group = WaveGroup(
            name=f"RSN{rsn}_{rec.event.replace(' ', '_')}",
            source='natural',
            rsn=rsn,
            event=rec.event,
            station=rec.station,
            scale_factor=result.scale_factor,
            match_error=result.match_error,
        )

        # 加载波形并缩放
        sf = result.scale_factor

        if len(h_comps) >= 1:
            acc = database.load_waveform(h_comps[0])
            sig = EQSignal(acc * sf, h_comps[0].dt,
                           name=f"{group.name}_H1")
            sig.a2vd()
            group.h1 = sig

        if len(h_comps) >= 2:
            acc = database.load_waveform(h_comps[1])
            sig = EQSignal(acc * sf, h_comps[1].dt,
                           name=f"{group.name}_H2")
            sig.a2vd()
            group.h2 = sig

        if len(v_comps) >= 1:
            acc = database.load_waveform(v_comps[0])
            # 竖向缩放系数 = 水平 × 0.65（规范要求）
            sig = EQSignal(acc * sf * 0.65, v_comps[0].dt,
                           name=f"{group.name}_V")
            sig.a2vd()
            group.v = sig

        self.groups.append(group)
        return group

    def add_artificial(self, h1: EQSignal, h2: EQSignal = None,
                       v: EQSignal = None,
                       name: str = "artificial",
                       index: int = 0) -> WaveGroup:
        """添加人工波组"""
        group = WaveGroup(
            name=f"{name}_{index + 1}",
            source='artificial',
            h1=h1,
            h2=h2,
            v=v,
        )
        self.groups.append(group)
        return group

    def export(self, fmt: str = 'at2') -> str:
        """导出所有波组到输出目录

        Parameters
        ----------
        fmt : 'at2' | 'txt' | 'both'

        Returns
        -------
        str : 输出目录路径
        """
        os.makedirs(self.output_dir, exist_ok=True)

        for i, group in enumerate(self.groups):
            group_dir = os.path.join(self.output_dir, f"{i + 1:02d}_{group.name}")
            os.makedirs(group_dir, exist_ok=True)

            for label, sig in [('H1', group.h1), ('H2', group.h2), ('V', group.v)]:
                if sig is None:
                    continue

                base = f"{group.name}_{label}"

                if fmt in ('at2', 'both'):
                    path = os.path.join(group_dir, f"{base}.AT2")
                    self._write_at2(path, sig, group)

                if fmt in ('txt', 'both'):
                    path = os.path.join(group_dir, f"{base}.txt")
                    self._write_txt(path, sig)

        # 写入汇总 JSON
        self._write_summary()

        return self.output_dir

    def _write_at2(self, path: str, sig: EQSignal, group: WaveGroup):
        """写入 PEER AT2 格式"""
        with open(path, 'w') as f:
            f.write(f"PEER NGA - {group.event} - {group.station}\n")
            f.write(f"{group.event}, {group.station}, {sig.name}\n")
            f.write(f"ACCELERATION (g) - SCALE FACTOR: {group.scale_factor:.4f}\n")
            f.write(f"NPTS= {sig.n}, DT= {sig.dt:.6f} SEC\n")

            acc = sig.acc
            for j in range(0, len(acc), 5):
                vals = acc[j:j + 5]
                line = '  '.join(f"{v:13.6E}" for v in vals)
                f.write(line + '\n')

    def _write_txt(self, path: str, sig: EQSignal):
        """写入简单文本格式（时间-加速度两列）"""
        t = np.arange(sig.n) * sig.dt
        data = np.column_stack([t, sig.acc])
        np.savetxt(path, data, fmt='%.6e', header='Time(s)  Acc(g)')

    def _write_summary(self):
        """写入汇总 JSON"""
        summary = {
            'n_groups': len(self.groups),
            'groups': []
        }

        for i, g in enumerate(self.groups):
            info = {
                'index': i + 1,
                'name': g.name,
                'source': g.source,
                'rsn': g.rsn,
                'event': g.event,
                'station': g.station,
                'scale_factor': g.scale_factor,
                'match_error': g.match_error,
                'has_h1': g.h1 is not None,
                'has_h2': g.h2 is not None,
                'has_v': g.v is not None,
            }

            if g.h1 is not None:
                info['h1_pga'] = float(np.max(np.abs(g.h1.acc)))
                info['h1_duration'] = g.h1.n * g.h1.dt
            if g.h2 is not None:
                info['h2_pga'] = float(np.max(np.abs(g.h2.acc)))
            if g.v is not None:
                info['v_pga'] = float(np.max(np.abs(g.v.acc)))

            summary['groups'].append(info)

        path = os.path.join(self.output_dir, 'summary.json')
        with open(path, 'w') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

    def report_text(self) -> str:
        """生成文本报告"""
        lines = [f"选波结果汇总 ({len(self.groups)} 组)"]
        lines.append("=" * 60)

        for i, g in enumerate(self.groups):
            lines.append(f"\n第 {i + 1} 组: {g.name}")
            lines.append(f"  来源: {'天然波' if g.source == 'natural' else '人工波'}")
            if g.rsn:
                lines.append(f"  RSN: {g.rsn}")
                lines.append(f"  事件: {g.event}")
                lines.append(f"  台站: {g.station}")
            lines.append(f"  缩放系数: {g.scale_factor:.3f}")
            lines.append(f"  匹配误差: {g.match_error:.4f}")

            for label, sig in [('H1', g.h1), ('H2', g.h2), ('V', g.v)]:
                if sig is not None:
                    pga = float(np.max(np.abs(sig.acc)))
                    dur = sig.n * sig.dt
                    lines.append(f"  {label}: PGA={pga:.4f}g, 持时={dur:.1f}s")

        return '\n'.join(lines)

    def compute_spectra(self, periods: np.ndarray,
                        zeta: float = 0.05) -> list[np.ndarray]:
        """对所有 groups 的 h1 计算反应谱

        Parameters
        ----------
        periods : np.ndarray
            周期数组
        zeta : float
            阻尼比

        Returns
        -------
        list[np.ndarray]
            每组 h1 的加速度反应谱 Sa
        """
        spectra_list = []
        for g in self.groups:
            if g.h1 is not None:
                sp = Spectra.compute(g.h1.acc, g.h1.dt, periods,
                                     zeta=zeta, method="newmark")
                spectra_list.append(sp.sa)
            else:
                spectra_list.append(np.zeros(len(periods)))
        return spectra_list

    def validate(self, target_pga: float, target_sa: np.ndarray,
                 periods: np.ndarray, mode: str = "mean") -> ValidationResult:
        """规范校验

        Parameters
        ----------
        target_pga : float
            目标 PGA (g)
        target_sa : np.ndarray
            目标反应谱 Sa
        periods : np.ndarray
            周期数组
        mode : str
            "mean" = 平均谱校核, "envelope" = 包络谱校核

        Returns
        -------
        ValidationResult
        """
        messages = []
        n_groups = len(self.groups)
        n_required = 7

        # 组合数量检查
        if n_groups < n_required:
            messages.append(f"组合数量不足: {n_groups}/{n_required}")

        # 计算各组 h1 反应谱
        spectra_list = self.compute_spectra(periods)
        valid_spectra = [s for s, g in zip(spectra_list, self.groups)
                         if g.h1 is not None]

        if len(valid_spectra) == 0:
            return ValidationResult(
                passed=False, n_groups=n_groups, n_required=n_required,
                individual_checks=[], mean_check=False,
                mean_ratios=None, envelope_check=False,
                messages=["无有效波形数据"])

        sa_matrix = np.array(valid_spectra)

        # 平均谱 / 包络谱
        mean_sa = np.mean(sa_matrix, axis=0)
        envelope_sa = np.max(sa_matrix, axis=0)

        # 底部剪力校核：单条 0.65~1.35 倍目标谱
        individual_checks = []
        safe_target = np.where(target_sa > 1e-12, target_sa, 1e-12)
        for i, (sa, g) in enumerate(zip(spectra_list, self.groups)):
            if g.h1 is None:
                continue
            ratios = sa / safe_target
            min_r = float(np.min(ratios))
            max_r = float(np.max(ratios))
            ok = (min_r >= 0.65) and (max_r <= 1.35)
            individual_checks.append((g.name, (min_r, max_r), ok))
            if not ok:
                messages.append(
                    f"{g.name}: 谱比范围 [{min_r:.2f}, {max_r:.2f}] "
                    f"超出 [0.65, 1.35]")

        # 平均谱 ≥ 0.80 × 目标谱
        mean_ratios = mean_sa / safe_target
        mean_check = bool(np.all(mean_ratios >= 0.80))
        if not mean_check:
            min_mean = float(np.min(mean_ratios))
            messages.append(
                f"平均谱最小比值 {min_mean:.3f} < 0.80")

        # 包络谱检查
        env_ratios = envelope_sa / safe_target
        envelope_check = bool(np.all(env_ratios >= 1.0))

        all_individual_ok = all(c[2] for c in individual_checks)
        passed = (n_groups >= n_required and mean_check
                  and all_individual_ok)

        return ValidationResult(
            passed=passed,
            n_groups=n_groups,
            n_required=n_required,
            individual_checks=individual_checks,
            mean_check=mean_check,
            mean_ratios=mean_ratios,
            envelope_check=envelope_check,
            messages=messages,
        )

    def generate_html_report(self, target_sa: np.ndarray,
                             periods: np.ndarray,
                             output_path: str = None) -> str:
        """生成独立 HTML 报告

        Parameters
        ----------
        target_sa : np.ndarray
            目标反应谱 Sa
        periods : np.ndarray
            周期数组
        output_path : str, optional
            输出路径，默认 output_dir/report.html

        Returns
        -------
        str
            HTML 文件路径
        """
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        # 配置字体：中文宋体(Songti SC) + 英文 Times New Roman
        plt.rcParams['font.family'] = ['Times New Roman', 'Songti SC']
        plt.rcParams['axes.unicode_minus'] = False

        if output_path is None:
            os.makedirs(self.output_dir, exist_ok=True)
            output_path = os.path.join(self.output_dir, 'report.html')

        # 计算反应谱
        spectra_list = self.compute_spectra(periods)
        valid_spectra = [s for s, g in zip(spectra_list, self.groups)
                         if g.h1 is not None]

        # 生成反应谱对比图
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(periods, target_sa, 'k-', linewidth=2, label='目标谱')

        for sa, g in zip(spectra_list, self.groups):
            if g.h1 is not None:
                ax.plot(periods, sa, alpha=0.6, label=g.name)

        if len(valid_spectra) > 0:
            mean_sa = np.mean(valid_spectra, axis=0)
            ax.plot(periods, mean_sa, 'r--', linewidth=2, label='平均谱')
            ax.plot(periods, target_sa * 0.80, 'k:',
                    linewidth=1, label='0.80×目标谱')

        ax.set_xlabel('周期 T (s)')
        ax.set_ylabel('加速度反应谱 Sa (g)')
        ax.set_title('反应谱对比')
        ax.legend(fontsize=8)
        ax.set_xlim(periods[0], periods[-1])
        ax.grid(True, alpha=0.3)

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode('ascii')

        # 构建 HTML
        html = self._build_html(img_b64, spectra_list, target_sa, periods)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return output_path

    def _build_html(self, img_b64: str, spectra_list: list,
                    target_sa: np.ndarray, periods: np.ndarray) -> str:
        """构建 HTML 报告内容"""
        rows_html = []
        for i, g in enumerate(self.groups):
            pga_h1 = f"{g.h1.pga:.4f}" if g.h1 else "-"
            dur_h1 = f"{g.h1.duration:.1f}" if g.h1 else "-"
            pga_h2 = f"{g.h2.pga:.4f}" if g.h2 else "-"
            pga_v = f"{g.v.pga:.4f}" if g.v else "-"
            rows_html.append(
                f"<tr><td>{i+1}</td><td>{g.name}</td>"
                f"<td>{'天然波' if g.source=='natural' else '人工波'}</td>"
                f"<td>{g.scale_factor:.3f}</td>"
                f"<td>{pga_h1}</td><td>{pga_h2}</td><td>{pga_v}</td>"
                f"<td>{dur_h1}</td></tr>")
        table_rows = "\n".join(rows_html)

        # 校验结果
        safe_target = np.where(target_sa > 1e-12, target_sa, 1e-12)
        valid_spectra = [s for s, g in zip(spectra_list, self.groups)
                         if g.h1 is not None]
        check_html = ""
        if valid_spectra:
            mean_sa = np.mean(valid_spectra, axis=0)
            mean_ratios = mean_sa / safe_target
            min_ratio = float(np.min(mean_ratios))
            status = "通过" if min_ratio >= 0.80 else "不通过"
            color = "#4CAF50" if min_ratio >= 0.80 else "#f44336"
            check_html = (
                f'<p>平均谱最小比值: <span style="color:{color}">'
                f'{min_ratio:.3f}</span> ({status})</p>')

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>地震波组合报告</title>
<style>
body {{ font-family: "Microsoft YaHei", sans-serif; margin: 40px; background: #f5f5f5; }}
.container {{ max-width: 1000px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
h1 {{ color: #333; border-bottom: 2px solid #2196F3; padding-bottom: 10px; }}
h2 {{ color: #555; margin-top: 30px; }}
table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: center; }}
th {{ background: #2196F3; color: white; }}
tr:nth-child(even) {{ background: #f9f9f9; }}
img {{ max-width: 100%; height: auto; margin: 15px 0; }}
.info {{ color: #666; font-size: 14px; }}
</style>
</head>
<body>
<div class="container">
<h1>地震波组合报告</h1>
<p class="info">共 {len(self.groups)} 组地震波</p>

<h2>反应谱对比</h2>
<img src="data:image/png;base64,{img_b64}" alt="反应谱对比图">

<h2>波形信息</h2>
<table>
<tr><th>序号</th><th>名称</th><th>来源</th><th>缩放系数</th><th>H1 PGA(g)</th><th>H2 PGA(g)</th><th>V PGA(g)</th><th>H1 持时(s)</th></tr>
{table_rows}
</table>

<h2>校验结果</h2>
{check_html}
</div>
</body>
</html>"""
