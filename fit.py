import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import minimize
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

# ===================== CONFIG =====================
OUTPUT_DIR = "etas_fit_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# WINDOW MAPPING (T1 / T2 / T3)
WINDOW_MAP = {
    "2h-6h": "T1",
    "6h-22h": "T2",
    "24h-72h": "T3"
}


# ===================== READ CSV =====================
def read_catalog(csv_path):
    df = pd.read_csv(csv_path, encoding='utf-8')
    required_cols = ["发震时间", "震级"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"CSV need columns: {required_cols}")

    df["time"] = pd.to_datetime(df["发震时间"])
    df["m"] = df["震级"].astype(float)
    df = df.sort_values("time").reset_index(drop=True)

    mainshock_idx = df[df["m"] >= 6.0].index[0]
    mainshock = df.iloc[mainshock_idx]
    main_time = mainshock["time"]
    main_mag = mainshock["m"]

    print(f"Mainshock found: {main_time} | Mag {main_mag} Mw")
    return df, main_time, main_mag


# ===================== SELECT TIME WINDOW =====================
def select_time_window(df, main_time, window_type):
    t0 = main_time

    if window_type == "2h-6h":
        t_start = t0 + timedelta(hours=2)
        t_end = t0 + timedelta(hours=6)
    elif window_type == "6h-22h":
        t_start = t0 + timedelta(hours=6)
        t_end = t0 + timedelta(hours=22)
    elif window_type == "24h-72h":
        t_start = t0 + timedelta(hours=24)
        t_end = t0 + timedelta(hours=72)
    else:
        raise ValueError("Use: 2h-6h / 6h-22h / 24h-72h")

    mask = (df["time"] >= t_start) & (df["time"] <= t_end)
    df_win = df[mask].copy()

    df_win["t_days"] = (df_win["time"] - t0).dt.total_seconds() / 86400
    times = df_win["t_days"].values
    mags = df_win["m"].values

    window_code = WINDOW_MAP[window_type]
    print(f"Window {window_type} → {window_code} : {len(df_win)} events")
    return times, mags, window_code


# ===================== ETAS LOG-LIKELIHOOD =====================
def etas_neg_ll(params, times, mags, m0):
    mu, K, alpha, c, p = params
    if any(x <= 0 for x in params):
        return 1e12
    n = len(times)
    if n < 3:
        return 1e12
    T = times[-1]

    sum_log = 0.0
    sum_int = 0.0

    for i in range(n):
        ti = times[i]
        lam = mu
        for j in range(i):
            tj = times[j]
            mj = mags[j]
            dt = ti - tj
            gam = K * np.exp(alpha * (mj - m0))
            lam += gam / ((c + dt) ** p)
        if lam <= 0:
            return 1e12
        sum_log += np.log(lam)

        tj = times[i]
        mj = mags[i]
        term = ((c + (T - tj)) ** (1 - p) - c ** (1 - p)) / (1 - p)
        sum_int += K * np.exp(alpha * (mj - m0)) * term

    ll = sum_log - (mu * T + sum_int)
    return -ll


# ===================== FIT ETAS =====================
def fit_etas(times, mags, m0):
    init = [0.05, 0.8, 1.2, 0.005, 1.1]
    bounds = [(1e-5, 5), (1e-3, 50), (0.1, 4), (1e-5, 1), (1.01, 3.5)]

    res = minimize(etas_neg_ll, init, args=(times, mags, m0),
                   method="L-BFGS-B", bounds=bounds)

    mu, K, alpha, c, p = res.x
    aic = 2 * res.fun + 10

    return {
        "mu": round(float(mu), 6),
        "K": round(float(K), 6),
        "alpha": round(float(alpha), 6),
        "c": round(float(c), 6),
        "p": round(float(p), 6),
        "neg_ll": round(float(res.fun), 4),
        "AIC": round(float(aic), 4),
        "success": res.success
    }


# ===================== SAVE JSON =====================
def save_json(params, window_code, base_name):
    fn = f"{base_name}_ETAS_{window_code}.json"
    fp = os.path.join(OUTPUT_DIR, fn)
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(params, f, indent=4)
    print(f"Saved JSON: {fp}")


# ===================== PLOT (ENGLISH ONLY) =====================
def plot_fit(times, params, window_code, base_name):
    mu, K, alpha, c, p = [params[k] for k in ["mu", "K", "alpha", "c", "p"]]
    t_plot = np.linspace(times.min(), times.max(), 200)
    lam = np.full_like(t_plot, mu)

    for i, t in enumerate(t_plot):
        for tj in times[times < t]:
            dt = t - tj
            lam[i] += K * np.exp(alpha * 0) / ((c + dt) ** p)

    plt.figure(figsize=(10, 4))
    plt.scatter(times, np.ones_like(times), c='red', s=15, alpha=0.7, label="Observed events")
    plt.plot(t_plot, lam, 'b-', lw=2, label="ETAS rate")
    plt.title(f"ETAS Model Fit | {window_code}")
    plt.xlabel("Time after mainshock (days)")
    plt.ylabel("Seismicity rate λ(t)")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()

    img_path = os.path.join(OUTPUT_DIR, f"{base_name}_ETAS_{window_code}.png")
    plt.savefig(img_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved plot: {img_path}")


# ===================== MAIN =====================
def run_etas_fit(csv_file, window_type):
    base_name = os.path.splitext(os.path.basename(csv_file))[0]
    df, main_t, main_m = read_catalog(csv_file)
    times, mags, window_code = select_time_window(df, main_t, window_type)
    if len(times) < 3:
        print("Not enough data for fitting")
        return
    params = fit_etas(times, mags, main_m)
    save_json(params, window_code, base_name)
    plot_fit(times, params, window_code, base_name)

    print("\n" + "=" * 50)
    print(f"ETAS 5 PARAMETERS | {window_code}")
    for k, v in params.items():
        print(f"{k:12} : {v}")
    print("=" * 50)


# ===================== RUN =====================
if __name__ == "__main__":
    CSV_FILE = "7d_earthquake/Japan_2011_俯冲带_纬度38.32N_经度142.37E_USGS.csv"  # YOUR CSV FILE NAME
    WINDOW = "24h-72h"  # T1=2h-6h / T2=6h-22h / T3=24h-72h
    run_etas_fit(CSV_FILE, WINDOW)