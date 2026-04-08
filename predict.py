import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ===================== 自动路径（永远不会错） =====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # 脚本所在目录
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "etas_prediction")
os.makedirs(OUTPUT_DIR, exist_ok=True)

WINDOW_CONFIG = {
    "T1": {"fit": (2, 6), "pred": (6, 24)},
    "T2": {"fit": (6, 22), "pred": (24, 72)},
    "T3": {"fit": (24, 72), "pred": (72, 168)}
}

# ===================== 读取 CSV（只看拟合窗口，绝不越界） =====================
def load_catalog_fit_only(csv_file, window_code):
    df = pd.read_csv(csv_file, encoding='utf-8')
    df["time"] = pd.to_datetime(df["发震时间"])
    df["m"] = df["震级"].astype(float)
    df = df.sort_values("time").reset_index(drop=True)

    main_idx = df[df["m"] >= 6.0].index[0]
    main_time = df.iloc[main_idx]["time"]
    main_mag = df.iloc[main_idx]["m"]

    h_fit_start, h_fit_end = WINDOW_CONFIG[window_code]["fit"]
    t_start = main_time + timedelta(hours=h_fit_start)
    t_end = main_time + timedelta(hours=h_fit_end)

    mask = (df["time"] >= t_start) & (df["time"] <= t_end)
    df_fit = df[mask].copy()

    df_fit["t_days"] = (df_fit["time"] - main_time).dt.total_seconds() / 86400
    obs_times = df_fit["t_days"].values
    obs_mags = df_fit["m"].values

    return obs_times, obs_mags, main_mag

# ===================== 加载 ETAS 参数 =====================
def load_params(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# ===================== ETAS 速率 =====================
def etas_lambda(t, past_times, past_mags, mu, K, alpha, c, p, m0):
    lam = mu
    for tj, mj in zip(past_times, past_mags):
        dt = t - tj
        if dt <= 0:
            continue
        gam = K * np.exp(alpha * (mj - m0))
        lam += gam / ((c + dt) ** p)
    return max(lam, 1e-6)

# ===================== 概率预测 0~1 =====================
def predict(csv_base, params, window_code, obs_times, obs_mags, m0):
    h_start, h_end = WINDOW_CONFIG[window_code]["pred"]
    t_start = h_start / 24.0
    t_end = h_end / 24.0
    step_h = 0.5
    t_steps = np.arange(t_start, t_end + 1e-6, step_h / 24.0)

    mu = params["mu"]
    K = params["K"]
    alpha = params["alpha"]
    c = params["c"]
    p = params["p"]
    dt_step = step_h / 24.0

    rates = []
    probs = []
    for t in t_steps:
        lam = etas_lambda(t, obs_times, obs_mags, mu, K, alpha, c, p, m0)
        rates.append(lam)
        prob = 1.0 - np.exp(-lam * dt_step)
        probs.append(np.clip(prob, 0.0, 1.0))

    df_out = pd.DataFrame({
        "time_days": t_steps,
        "lambda_rate": rates,
        "probability_0_1": probs
    })

    csv_out = os.path.join(OUTPUT_DIR, f"{csv_base}_PRED_{window_code}.csv")
    df_out.to_csv(csv_out, index=False)
    print(f"✅ Saved probability log: {csv_out}")
    return t_steps, probs

# ===================== 绘图（纯英文） =====================
def plot_prob(t_steps, probs, window_code, csv_base):
    plt.figure(figsize=(10, 4))
    plt.plot(t_steps, probs, 'darkred', lw=2.2, label='Earthquake Probability')
    plt.title(f"ETAS Probability Prediction | {window_code}")
    plt.xlabel("Time after mainshock (days)")
    plt.ylabel("Probability (0 ~ 1)")
    plt.ylim(0, 1.02)
    plt.grid(alpha=0.3, linestyle='--')
    plt.legend()
    plt.tight_layout()
    img_path = os.path.join(OUTPUT_DIR, f"{csv_base}_PRED_{window_code}.png")
    plt.savefig(img_path, dpi=180, bbox_inches='tight')
    plt.close()
    print(f"✅ Saved plot: {img_path}")

# ===================== 主程序 =====================
def run_predict(csv_file, json_file, window_code):
    csv_base = os.path.splitext(os.path.basename(csv_file))[0]
    obs_times, obs_mags, m0 = load_catalog_fit_only(csv_file, window_code)
    params = load_params(json_file)
    t_steps, probs = predict(csv_base, params, window_code, obs_times, obs_mags, m0)
    plot_prob(t_steps, probs, window_code, csv_base)

    print("\n" + "=" * 60)
    print(f"✅ PREDICTION {window_code} SUCCESS")
    print(f"✅ Used data only: {WINDOW_CONFIG[window_code]['fit']} h")
    print(f"✅ Max prob: {max(probs):.4f}")
    print("=" * 60)

# ===================== 你只需要确认这 3 个路径正确 =====================
if __name__ == "__main__":
    CSV_FILE = "7d_earthquake/Chile_2010_俯冲带_纬度35.85S_经度72.71W_USGS.csv"
    ETAS_JSON = "etas_fit_results/Chile_2010_俯冲带_纬度35.85S_经度72.71W_USGS_ETAS_T2.json"
    WINDOW_CODE = "T2"

    run_predict(CSV_FILE, ETAS_JSON, WINDOW_CODE)