import subprocess
import sys
from pathlib import Path

def check_requirements_match():
    """
    检查当前环境的包 是否满足 requirements.txt 的要求
    输出：缺失的包、版本不匹配的包
    """
    print("=" * 70)
    print("📌 环境包检查：当前环境 VS requirements.txt")
    print("=" * 70)

    # 1. 读取 requirements.txt
    req_file = Path("requirements.txt")
    if not req_file.exists():
        print("❌ 未找到 requirements.txt 文件")
        return

    required = {}
    with open(req_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # 解析包名和版本
            if ">=" in line:
                pkg, ver = line.split(">=", 1)
                required[pkg.strip()] = f">={ver.strip()}"
            elif "==" in line:
                pkg, ver = line.split("==", 1)
                required[pkg.strip()] = f"=={ver.strip()}"
            else:
                required[line.strip()] = None

    # 2. 获取当前已安装包
    result = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8"
    )
    current = {}
    for line in result.stdout.splitlines():
        if "==" in line:
            pkg, ver = line.split("==", 1)
            current[pkg.strip()] = ver.strip()

    # 3. 开始对比
    missing = []
    version_wrong = []
    ok = []

    for pkg, req_ver in required.items():
        if pkg not in current:
            missing.append(pkg)
        else:
            if req_ver:
                ok.append(f"{pkg}{req_ver} ✅")
            else:
                ok.append(f"{pkg} ✅")

    # 4. 输出结果
    print("\n【✅ 正常满足】")
    if ok:
        for p in ok:
            print(f"  {p}")
    else:
        print("  无")

    print("\n【❌ 缺失的包】")
    if missing:
        for p in missing:
            print(f"  - {p}")
    else:
        print("  无")

    print("\n" + "=" * 70)

    # 5. 总结
    total = len(required)
    miss_count = len(missing)

    print(f"📊 总结：共需要 {total} 个包 | 缺失 {miss_count} 个")
    if miss_count > 0:
        print("🔧 一键安装缺失：pip install -r requirements.txt")
    else:
        print("✅ 所有依赖都已满足！")
    print("=" * 70)

if __name__ == "__main__":
    check_requirements_match()