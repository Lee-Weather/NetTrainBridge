"""
Isaac 诊断 CSV 改进评估脚本
=================================
针对 `isaac_diag_*.csv`（Isaac 仿真导出的逐 step 诊断日志）评估某一轮训练相对上一轮
是否"改进"。区别于 walk-diagnostics（对称性/响应/周期），本脚本聚焦：

  0. 数据覆盖度 —— 这份 CSV 到底能验证什么、不能验证什么（避免凭空下结论）
  1. 稳定性 —— 分窗 roll/pitch 抖动 + 摔倒判定
  2. 航向漂移 —— 直行指令(cmd_angular_z=0)下 yaw 是否跑偏
  3. 关节高频抖动 —— FFT 主频 / >5Hz 能量占比 / 速度过零次数 / d_action 抖动（踝关节重点）
  4. 限位 bang-bang —— pos_des(_lpf/_raw) 顶硬限位的时间占比（抖动常见根因）
  5. 左右对称性 —— action 活动幅度 L/R 比（沿用旧症状追踪）
  6. 力矩量级 —— 各关节 effort RMS / max
  7. 速度跟踪 —— base_lin_vel_x vs cmd_linear_x（新增）
  8. 落地冲击 —— 接触力峰值与阈值判定（新增）

用法:
    python eval_isaac_diag.py <csv_path>
    python eval_isaac_diag.py <csv_path> --win 1.0 --hf 5.0

注意:
- 新版CSV已包含 base_lin_vel_* 和 contact_force_* 字段，可验证速度跟踪和落地冲击
- 旧版本可能缺失这些字段，脚本会显式报告缺失项
- `imu_accel_*` / `tau_des_*` 可能整列 NaN
"""
import sys
import argparse
import numpy as np
import pandas as pd

# X1 12DOF 腿部关节顺序（与 CSV action_/pos_ 前缀一致）
LEG_JOINTS = [
    "left_hip_pitch_joint", "left_hip_roll_joint", "left_hip_yaw_joint",
    "left_knee_pitch_joint", "left_ankle_pitch_joint", "left_ankle_roll_joint",
    "right_hip_pitch_joint", "right_hip_roll_joint", "right_hip_yaw_joint",
    "right_knee_pitch_joint", "right_ankle_pitch_joint", "right_ankle_roll_joint",
]
ANKLE_JOINTS = ["left_ankle_pitch_joint", "left_ankle_roll_joint",
                "right_ankle_pitch_joint", "right_ankle_roll_joint"]
SYM_BASES = ["hip_pitch", "hip_roll", "hip_yaw", "knee_pitch", "ankle_pitch", "ankle_roll"]

# 推理软限位/URDF 硬限位下限（用于 bang-bang 判定，按需修改）
# 来自 exp_1.md 实验 1_3：ankle_pitch [-0.41, 0.35]
HARD_LIMITS = {
    "left_ankle_pitch_joint": (-0.41, 0.35),
    "right_ankle_pitch_joint": (-0.41, 0.35),
    "left_ankle_roll_joint": (-0.64, 0.64),
    "right_ankle_roll_joint": (-0.64, 0.64),
}


def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def detect_dt(t_ns):
    dt = np.diff(t_ns) / 1e9
    return float(np.median(dt)) if len(dt) else 0.01


def report_coverage(df):
    """报告哪些信号可用、哪些缺失 —— 决定哪些目标可被验证。"""
    section("0. 数据覆盖度（能验证什么 / 不能验证什么）")
    all_nan = [c for c in df.columns if df[c].isna().all()]
    print(f"总列数 {len(df.columns)}，全 NaN 列 {len(all_nan)} 个")

    has = {
        "base 姿态(euler)": all(c in df for c in ["base_euler_x", "base_euler_y", "base_euler_z"]),
        "base 角速度": all(c in df for c in ["base_ang_vel_x", "base_ang_vel_y", "base_ang_vel_z"]),
        "关节 pos/vel/effort/action": f"pos_{LEG_JOINTS[0]}" in df,
        "命令(cmd_*)": "cmd_linear_x" in df,
        "base 线速度(速度跟踪)": all(c in df for c in ["base_lin_vel_x", "base_lin_vel_y", "base_lin_vel_z"]),
        "接触力(落地冲击)": all(c in df for c in ["left_foot_contact_force_z", "right_foot_contact_force_z"]) 
                            or all(c in df for c in ["left_foot_contact_force_mag", "right_foot_contact_force_mag"]),
    }
    # 缺失/无效的关键评估信号
    contact_dead = ("left_contact" in df and df["left_contact"].abs().sum() == 0
                    and "right_contact" in df and df["right_contact"].abs().sum() == 0)
    missing = {
        "contact 标志全为0": contact_dead,
        "imu_accel 全 NaN": all(f"imu_accel_{a}" in all_nan for a in "xyz") if any(f"imu_accel_{a}" in df for a in "xyz") else False,
        "tau_des_* 全 NaN": any(c.startswith("tau_des_") for c in all_nan),
    }
    print("\n[可用信号]")
    for k, v in has.items():
        print(f"  {'OK ' if v else 'NO '} {k}")
    print("\n[缺失/无效 —— 对应目标无法验证]")
    for k, v in missing.items():
        if v:
            print(f"  !! {k}")
    
    # 总结
    can_verify = []
    cannot_verify = []
    if has["base 姿态(euler)"]:
        can_verify.append("稳定性")
    if has["关节 pos/vel/effort/action"]:
        can_verify.append("关节高频抖动")
        can_verify.append("限位bang-bang")
        can_verify.append("左右对称性")
        can_verify.append("关节力矩")
    if has["base 姿态(euler)"] and has["命令(cmd_*)"]:
        can_verify.append("航向漂移")
    if has["base 线速度(速度跟踪)"] and has["命令(cmd_*)"]:
        can_verify.append("速度跟踪")
    else:
        cannot_verify.append("速度跟踪")
    if has["接触力(落地冲击)"]:
        can_verify.append("落地冲击")
    else:
        cannot_verify.append("落地冲击")
    
    print(f"\n>> 结论：可验证【{' / '.join(can_verify)}】")
    if cannot_verify:
        print(f"   无法验证【{' / '.join(cannot_verify)}】（需新版CSV或真机/MuJoCo日志）")
    else:
        print(f"   所有目标均可验证（新版CSV数据完整）")


def report_command(df):
    section("命令(cmd)")
    for c in ["cmd_linear_x", "cmd_linear_y", "cmd_angular_z"]:
        if c in df:
            v = df[c].values
            print(f"  {c:16s} min {v.min():+.3f}  max {v.max():+.3f}  mean {v.mean():+.3f}")


def report_stability(df, win_s, dt):
    section("1. 稳定性（分窗 roll/pitch 抖动 + 摔倒判定）")
    n = len(df)
    w = max(1, int(round(win_s / dt)))
    ex, ey, ez = (df["base_euler_x"].values, df["base_euler_y"].values, df["base_euler_z"].values)
    ax = df["base_ang_vel_x"].values; ay = df["base_ang_vel_y"].values; az = df["base_ang_vel_z"].values
    print(f"  窗口 {win_s:.1f}s ({w} steps)")
    print(f"  {'win':>5} {'std|roll|':>10} {'std|pitch|':>11} {'yaw_mean':>9} {'angvel_rms':>11}")
    for i in range(0, n, w):
        s = slice(i, min(i + w, n))
        av = np.sqrt(ax[s] ** 2 + ay[s] ** 2 + az[s] ** 2)
        print(f"  {i*dt:5.1f} {ex[s].std():10.4f} {ey[s].std():11.4f} {ez[s].mean():+9.4f} {av.mean():11.3f}")
    max_roll, max_pitch = np.abs(ex).max(), np.abs(ey).max()
    fell = max_roll > 0.6 or max_pitch > 0.6  # ~34deg 经验摔倒阈
    print(f"\n  max|roll| = {max_roll:.3f} rad ({np.degrees(max_roll):.1f} deg)"
          f"   max|pitch| = {max_pitch:.3f} rad ({np.degrees(max_pitch):.1f} deg)")
    print(f"  摔倒判定: {'❌ 疑似摔倒/大幅失衡' if fell else '✅ 全程未摔，姿态受控'}")


def report_drift(df, dt):
    section("2. 航向漂移（直行指令下 yaw 偏移）")
    ez = df["base_euler_z"].values
    ang_cmd = df["cmd_angular_z"].abs().mean() if "cmd_angular_z" in df else None
    drift = ez[-1] - ez[0]
    print(f"  cmd_angular_z 均值 = {ang_cmd}")
    print(f"  yaw: 起 {ez[0]:+.3f} → 止 {ez[-1]:+.3f}  漂移 {drift:+.3f} rad ({np.degrees(drift):+.1f} deg)")
    if ang_cmd is not None and ang_cmd < 1e-3:
        verdict = "✅ 基本直行" if abs(drift) < 0.15 else ("⚠️ 有可察漂移" if abs(drift) < 0.4 else "❌ 明显跑偏")
        print(f"  判定（应直行）: {verdict}")


def report_jitter(df, dt, hf_hz):
    section(f"3. 关节高频抖动（FFT 主频 / >{hf_hz:.0f}Hz 能量占比 / 速度过零 / d_action）")
    print(f"  {'joint':24s} {'主频Hz':>7} {'HF占比':>7} {'vel_rms':>8} {'vel_zc':>7} {'std_dact':>9}")
    rows = []
    for j in LEG_JOINTS:
        if f"vel_{j}" not in df:
            continue
        vel = df[f"vel_{j}"].values
        act = df[f"action_{j}"].values
        x = vel - vel.mean()
        freqs = np.fft.rfftfreq(len(x), dt)
        amp = np.abs(np.fft.rfft(x))
        dom = freqs[1:][np.argmax(amp[1:])] if len(amp) > 1 else 0.0
        hf = amp[1:][freqs[1:] > hf_hz].sum()
        tot = amp[1:].sum()
        hf_frac = hf / tot if tot > 0 else 0.0
        zc = int(np.sum(np.abs(np.diff(np.sign(vel))) > 0))
        std_dact = float(np.diff(act).std())
        rows.append((j, dom, hf_frac, np.sqrt(np.mean(vel ** 2)), zc, std_dact))
        flag = "  <== 踝" if j in ANKLE_JOINTS else ""
        print(f"  {j:24s} {dom:7.1f} {hf_frac:7.2f} {np.sqrt(np.mean(vel**2)):8.3f} {zc:7d} {std_dact:9.4f}{flag}")
    # 踝关节聚合判定
    ank = [r for r in rows if r[0] in ANKLE_JOINTS]
    if ank:
        mean_hf = np.mean([r[2] for r in ank])
        mean_zc = np.mean([r[4] for r in ank])
        print(f"\n  踝关节均值: HF占比={mean_hf:.2f}  vel过零={mean_zc:.0f}")
        verdict = ("❌ 踝关节高频抖动严重" if mean_hf > 0.7 else
                   "⚠️ 踝关节存在抖动" if mean_hf > 0.5 else "✅ 踝关节抖动较低")
        print(f"  判定: {verdict}（HF占比越高、过零越多 = 抖动越重）")


def report_bangbang(df):
    section("4. 限位 bang-bang（pos_des 顶硬限位时间占比 —— 抖动常见根因）")
    print(f"  {'joint':24s} {'下限':>7} {'des_min':>9} {'des_max':>9} {'撞下限%':>8} {'撞上限%':>8}")
    for j, (lo, hi) in HARD_LIMITS.items():
        col = None
        for cand in (f"pos_des_lpf_{j}", f"pos_des_raw_{j}"):
            if cand in df:
                col = cand
                break
        if col is None:
            continue
        des = df[col].values
        f_lo = np.mean(des <= lo + 0.01)
        f_hi = np.mean(des >= hi - 0.01)
        print(f"  {j:24s} {lo:7.2f} {des.min():9.3f} {des.max():9.3f} {100*f_lo:8.1f} {100*f_hi:8.1f}")
    print("\n  >> 某关节 des 长时间(>30%)顶在限位 = 策略在限位边界 bang-bang，"
          "\n     是踝关节高频抖动的典型根因；单纯加阻尼难治本。")


def report_symmetry(df):
    section("5. 左右对称性（action 活动幅度 L/R 比）")
    print(f"  {'joint':12s} {'L_range':>9} {'R_range':>9} {'L/R':>7}  评估")
    for base in SYM_BASES:
        lc, rc = f"action_left_{base}_joint", f"action_right_{base}_joint"
        if lc not in df or rc not in df:
            continue
        l, r = df[lc].values, df[rc].values
        lr, rr = l.max() - l.min(), r.max() - r.min()
        ratio = lr / rr if rr > 1e-6 else np.inf
        ev = "✅" if 0.85 <= ratio <= 1.18 else ("⚠️" if 0.7 <= ratio <= 1.4 else "❌")
        print(f"  {base:12s} {lr:9.3f} {rr:9.3f} {ratio:7.3f}  {ev}")


def report_effort(df):
    section("6. 关节力矩量级（effort RMS / max）")
    print(f"  {'joint':24s} {'rms':>9} {'max|tau|':>10}")
    for j in LEG_JOINTS:
        if f"effort_{j}" not in df:
            continue
        e = df[f"effort_{j}"].values
        print(f"  {j:24s} {np.sqrt(np.mean(e**2)):9.3f} {np.abs(e).max():10.3f}")


def report_velocity_tracking(df):
    """第7节：速度跟踪分析"""
    section("7. 速度跟踪（base_lin_vel_x vs cmd_linear_x）")
    
    # 检查数据可用性
    has_vel = all(c in df for c in ["base_lin_vel_x", "base_lin_vel_y", "base_lin_vel_z"])
    has_cmd = "cmd_linear_x" in df
    
    if not has_vel:
        print("  !! 缺失 base_lin_vel_x/y/z 列 → 无法验证速度跟踪")
        print("  >> 需新版CSV或真机/MuJoCo日志")
        return
    
    vx, vy, vz = (df["base_lin_vel_x"].values, 
                  df["base_lin_vel_y"].values, 
                  df["base_lin_vel_z"].values)
    
    # 命令速度
    if has_cmd:
        cmd_vx = df["cmd_linear_x"].mean()
        cmd_vy = df["cmd_linear_y"].mean()
        print(f"  命令速度: cmd_linear_x = {cmd_vx:.3f} m/s, cmd_linear_y = {cmd_vy:.3f} m/s")
    else:
        cmd_vx = None
        print("  命令速度: 缺失 cmd_linear_x 列")
    
    # 实际速度统计
    print(f"\n  {'分量':16s} {'均值':>9} {'RMS':>9} {'max':>9} {'min':>9}")
    print(f"  {'base_lin_vel_x':16s} {vx.mean():9.3f} {np.sqrt(np.mean(vx**2)):9.3f} {vx.max():9.3f} {vx.min():9.3f}")
    print(f"  {'base_lin_vel_y':16s} {vy.mean():9.3f} {np.sqrt(np.mean(vy**2)):9.3f} {vy.max():9.3f} {vy.min():9.3f}")
    print(f"  {'base_lin_vel_z':16s} {vz.mean():9.3f} {np.sqrt(np.mean(vz**2)):9.3f} {vz.max():9.3f} {vz.min():9.3f}")
    
    # 速度跟踪判定
    if cmd_vx is not None and abs(cmd_vx) > 0.1:
        tracking_ratio = vx.mean() / abs(cmd_vx) if cmd_vx != 0 else 0
        print(f"\n  速度跟踪比: {vx.mean():.3f} / {abs(cmd_vx):.3f} = {tracking_ratio:.2%}")
        
        if tracking_ratio >= 0.9:
            verdict = "✅ 速度跟踪良好（≥90%）"
        elif tracking_ratio >= 0.75:
            verdict = "⚠️ 速度跟踪中等（75%~90%）"
        else:
            verdict = "❌ 速度跟踪不足（<75%）"
        print(f"  判定: {verdict}")
        
        # 稳定性检查
        vel_rms_total = np.sqrt(np.mean(vx**2 + vy**2 + vz**2))
        vel_std = np.std(vx)
        print(f"  速度波动: 总RMS={vel_rms_total:.3f} m/s, X方向std={vel_std:.3f} m/s")
        if vel_std > 0.2:
            print("  ⚠️ 速度波动较大，控制可能不稳定")


def report_contact_force(df):
    """第8节：落地冲击分析"""
    section("8. 落地冲击（contact_force 峰值与阈值判定）")
    
    # 检查数据可用性
    has_force = all(c in df for c in 
                    ["left_foot_contact_force_z", "right_foot_contact_force_z"])
    has_mag = all(c in df for c in 
                  ["left_foot_contact_force_mag", "right_foot_contact_force_mag"])
    
    if not has_force and not has_mag:
        print("  !! 缺失 contact_force 列 → 无法验证落地冲击")
        print("  >> 需新版CSV或真机/MuJoCo日志")
        return
    
    # 接触标志检查
    if "left_contact" in df and "right_contact" in df:
        lc = df["left_contact"].values
        rc = df["right_contact"].values
        print(f"  接触标志: left_contact 非零帧 {100*np.mean(lc!=0):.1f}%, "
              f"right_contact 非零帧 {100*np.mean(rc!=0):.1f}%")
    
    # 接触力统计（优先使用 mag，若无则用 z）
    if has_mag:
        lf = df["left_foot_contact_force_mag"].values
        rf = df["right_foot_contact_force_mag"].values
        force_type = "mag"
    else:
        lf = df["left_foot_contact_force_z"].values
        rf = df["right_foot_contact_force_z"].values
        force_type = "z"
    
    print(f"\n  接触力分量: {force_type}")
    print(f"  {'脚':10s} {'均值':>9} {'RMS':>9} {'峰值':>9} {'接触帧数':>10}")
    
    # 左脚
    lf_contact_frames = lf > 10  # >10N视为接触
    lf_contact = lf[lf_contact_frames]
    if len(lf_contact) > 0:
        print(f"  {'左脚':10s} {lf_contact.mean():9.1f} {np.sqrt(np.mean(lf_contact**2)):9.1f} "
              f"{lf.max():9.1f} {len(lf_contact):10d}")
    else:
        print(f"  {'左脚':10s} {'无接触':>9} {'无接触':>9} {'无接触':>9} {0:10d}")
    
    # 右脚
    rf_contact_frames = rf > 10
    rf_contact = rf[rf_contact_frames]
    if len(rf_contact) > 0:
        print(f"  {'右脚':10s} {rf_contact.mean():9.1f} {np.sqrt(np.mean(rf_contact**2)):9.1f} "
              f"{rf.max():9.1f} {len(rf_contact):10d}")
    else:
        print(f"  {'右脚':10s} {'无接触':>9} {'无接触':>9} {'无接触':>9} {0:10d}")
    
    # 峰值判定
    lf_peak = lf.max()
    rf_peak = rf.max()
    
    print(f"\n  峰值判定阈值:")
    print(f"    <150N  = ✅ 软着陆")
    print(f"    150~300N = ⚠️ 中等冲击")
    print(f"    >300N  = ❌ 硬着陆")
    
    # 左脚判定
    if lf_peak > 300:
        lf_verdict = "❌ 硬着陆"
    elif lf_peak > 150:
        lf_verdict = "⚠️ 中等冲击"
    else:
        lf_verdict = "✅ 软着陆"
    
    # 右脚判定
    if rf_peak > 300:
        rf_verdict = "❌ 硬着陆"
    elif rf_peak > 150:
        rf_verdict = "⚠️ 中等冲击"
    else:
        rf_verdict = "✅ 软着陆"
    
    print(f"\n  判定:")
    print(f"    左脚峰值 {lf_peak:.1f}N → {lf_verdict}")
    print(f"    右脚峰值 {rf_peak:.1f}N → {rf_verdict}")
    
    # 左右对称性
    if lf_peak > 0 and rf_peak > 0:
        ratio = lf_peak / rf_peak if rf_peak > 10 else np.inf
        print(f"\n  左右峰值比: {lf_peak:.1f} / {rf_peak:.1f} = {ratio:.2f}")
        if 0.85 <= ratio <= 1.18:
            print(f"    ✅ 左右对称性良好")
        elif 0.7 <= ratio <= 1.4:
            print(f"    ⚠️ 左右轻微不对称")
        else:
            print(f"    ❌ 左右严重不对称")
    
    # 交替着地模式检查
    if "left_contact" in df and "right_contact" in df:
        lc = df["left_contact"].values
        rc = df["right_contact"].values
        
        # 统计交替次数
        transitions = 0
        for i in range(1, len(lc)):
            if (lc[i-1] > 0 and lc[i] == 0 and rc[i] > 0) or \
               (rc[i-1] > 0 and rc[i] == 0 and lc[i] > 0):
                transitions += 1
        
        # 双支撑相占比
        double_support = np.sum((lc > 0) & (rc > 0))
        single_support = np.sum((lc > 0) | (rc > 0))
        double_ratio = double_support / single_support if single_support > 0 else 0
        
        print(f"\n  交替着地模式:")
        print(f"    左→右交替次数: {transitions}")
        print(f"    双支撑相占比: {100*double_ratio:.1f}%")
        
        if transitions > 5:
            print(f"    ✅ 有明显的左右交替着地")
        elif transitions > 0:
            print(f"    ⚠️ 交替次数较少")
        else:
            print(f"    ❌ 无交替着地（可能单脚承重或摔倒）")
    
    # 接触力惩罚项（如有）
    if "feet_contact_force_penalty" in df:
        penalty = df["feet_contact_force_penalty"].values
        print(f"\n  接触力惩罚项:")
        print(f"    均值: {penalty.mean():.3f}, 峰值: {penalty.max():.3f}")
        print(f"    >> 惩罚值越大，策略受惩罚越强，应趋近于0")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--win", type=float, default=1.0, help="稳定性分窗秒数")
    ap.add_argument("--hf", type=float, default=5.0, help="高频能量阈值 Hz")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    dt = detect_dt(df["timestamp_ns"].values) if "timestamp_ns" in df else 0.01

    section("数据概览")
    print(f"  文件: {args.csv}")
    print(f"  行数 {len(df)}  列数 {len(df.columns)}  dt≈{dt*1000:.1f}ms  "
          f"时长≈{len(df)*dt:.2f}s  采样≈{1/dt:.0f}Hz")

    report_coverage(df)
    report_command(df)
    report_stability(df, args.win, dt)
    report_drift(df, dt)
    report_jitter(df, dt, args.hf)
    report_bangbang(df)
    report_symmetry(df)
    report_effort(df)
    report_velocity_tracking(df)
    report_contact_force(df)

    section("评估完成")
    print("  把以上各节判定与上一轮对照，按 SKILL.md 的报告模板汇总改进结论。")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("Usage: python eval_isaac_diag.py <csv_path> [--win 1.0] [--hf 5.0]")
        sys.exit(0)
    main()
