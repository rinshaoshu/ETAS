import pandas as pd
from datetime import datetime, timedelta
import os

# ====================== 配置 ======================
INPUT_CSV = "15d_earthquake/Japan_2011_俯冲带_纬度38.32N_经度142.37E_USGS.csv"
OUTPUT_FOLDER = "output_results"
# ==================================================

def process_main_and_T1T2T3():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # 读取并按时间排序
    df = pd.read_csv(INPUT_CSV, encoding='utf-8-sig')
    df['发震时间'] = pd.to_datetime(df['发震时间'])
    df = df.sort_values('发震时间').reset_index(drop=True)

    # 找第一个 ≥6.0 为主震
    main_df = df[df['震级'] >= 6.0]
    if main_df.empty:
        print("未找到≥6.0级主震")
        return

    main = main_df.iloc[0]
    t_main = main['发震时间']
    lon_main = main['经度']
    lat_main = main['纬度']
    mag_main = main['震级']
    mag_type_main = main.get('震级类型', 'Mw')

    print("✅ 主震识别完成")
    print(f"   时间：{t_main}")
    print(f"   位置：{lat_main:.2f}, {lon_main:.2f}")
    print(f"   震级：{mag_main:.1f} {mag_type_main}")

    # 时间窗口
    t1_end = t_main + timedelta(hours=24)
    t2_end = t_main + timedelta(hours=72)
    t3_end = t_main + timedelta(hours=168)

    afters = df[df['发震时间'] > t_main]
    t1 = afters[(afters['发震时间'] > t_main) & (afters['发震时间'] <= t1_end)]
    t2 = afters[(afters['发震时间'] > t1_end) & (afters['发震时间'] <= t2_end)]
    t3 = afters[(afters['发震时间'] > t2_end) & (afters['发震时间'] <= t3_end)]

    def get_max_event(win_df):
        if win_df.empty:
            return None
        return win_df.loc[win_df['震级'].idxmax()]

    max1 = get_max_event(t1)
    max2 = get_max_event(t2)
    max3 = get_max_event(t3)

    rows = []

    # ========== 主震行（不再空，填真实信息）==========
    rows.append({
        '主震时间': t_main.strftime('%Y-%m-%d %H:%M:%S'),
        '主震纬度': round(lat_main, 2),
        '主震经度': round(lon_main, 2),
        '主震震级': round(mag_main, 1),
        '震级类型': mag_type_main,
        '窗口类型': '主震',
        '窗口最大震级': round(mag_main, 1),
        '对应发震时间': t_main.strftime('%Y-%m-%d %H:%M:%S')
    })

    # ========== T1 ==========
    if max1 is not None:
        rows.append({
            '主震时间': t_main.strftime('%Y-%m-%d %H:%M:%S'),
            '主震纬度': round(lat_main, 2),
            '主震经度': round(lon_main, 2),
            '主震震级': round(mag_main, 1),
            '震级类型': max1.get('震级类型', 'Mw'),
            '窗口类型': 'T1(0-24h)',
            '窗口最大震级': round(max1['震级'], 1),
            '对应发震时间': max1['发震时间'].strftime('%Y-%m-%d %H:%M:%S')
        })

    # ========== T2 ==========
    if max2 is not None:
        rows.append({
            '主震时间': t_main.strftime('%Y-%m-%d %H:%M:%S'),
            '主震纬度': round(lat_main, 2),
            '主震经度': round(lon_main, 2),
            '主震震级': round(mag_main, 1),
            '震级类型': max2.get('震级类型', 'Mw'),
            '窗口类型': 'T2(24-72h)',
            '窗口最大震级': round(max2['震级'], 1),
            '对应发震时间': max2['发震时间'].strftime('%Y-%m-%d %H:%M:%S')
        })

    # ========== T3 ==========
    if max3 is not None:
        rows.append({
            '主震时间': t_main.strftime('%Y-%m-%d %H:%M:%S'),
            '主震纬度': round(lat_main, 2),
            '主震经度': round(lon_main, 2),
            '主震震级': round(mag_main, 1),
            '震级类型': max3.get('震级类型', 'Mw'),
            '窗口类型': 'T3(72-168h)',
            '窗口最大震级': round(max3['震级'], 1),
            '对应发震时间': max3['发震时间'].strftime('%Y-%m-%d %H:%M:%S')
        })

    # 保存为一个CSV
    out_df = pd.DataFrame(rows)
    filename = f"{t_main.strftime('%Y%m%d%H%M%S')}_主震_T1T2T3.csv"
    out_path = os.path.join(OUTPUT_FOLDER, filename)
    out_df.to_csv(out_path, index=False, encoding='utf-8-sig')

    print(f"\n📁 已输出到文件夹：{OUTPUT_FOLDER}")
    print(f"📄 文件名：{filename}")

if __name__ == '__main__':
    process_main_and_T1T2T3()