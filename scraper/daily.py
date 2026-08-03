"""
daily.py - 每日抓取入口（手动或定时调用）
串联：抓取 → 合并 → 推送
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PY = Path(r"C:/Users/12485/.workbuddy/binaries/python/envs/data_analysis/Scripts/python.exe")

def run(cmd, label):
    print(f"\n========== {label} ==========")
    print(f"$ {' '.join(str(c) for c in cmd)}")
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        print(f"❌ {label} 失败 ({r.returncode})")
        sys.exit(r.returncode)
    print(f"✅ {label} 完成")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--types", default="1,2,3,4,5")
    ap.add_argument("--max-pages", type=int, default=0)
    ap.add_argument("--page-size", type=int, default=50)
    ap.add_argument("--no-push", action="store_true", help="不推送到 GitHub")
    args = ap.parse_args()

    # 1. 抓取
    run([str(PY), "scraper/playwright_scrape.py",
         "--types", args.types,
         "--output", "api/qual-today.json",
         "--max-pages", str(args.max_pages),
         "--page-size", str(args.page_size)],
        "Playwright 抓取")

    # 2. 合并
    run([str(PY), "scraper/merge.py"], "合并增量")

    # 3. 推送
    if not args.no_push:
        run([str(PY), "scraper/push.py",
             "--dir", "api",
             "--prefix", "api",
             "--message", f"chore: daily qualification scrape {__import__('time').strftime('%Y-%m-%d %H:%M')}"],
            "推送到 GitHub")

if __name__ == "__main__":
    main()
