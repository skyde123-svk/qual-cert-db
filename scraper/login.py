"""
login.py - 首次登录辅助：打开需要登录的SCS持久化浏览器
用法：
  python login.py                          # 第一次：手动登录
  python login.py --check                  # 检查登录状态是否还在
"""
import argparse
import asyncio
import sys
from pathlib import Path

SCA_DIR = Path(__file__).parent / ".scs_session"
QUAL_URL = "https://scs.officemate.cn/scspro/#/product/management"

def _get_chrome():
    """优先使用系统已装的 Chrome/Edge，避免下载 chromium"""
    candidates = [
        r"C:/Program Files/Google/Chrome/Application/chrome.exe",
        r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        r"C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None  # 让 Playwright 用自带 chromium

async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true", help="只检查登录状态")
    p.add_argument("--url", default=QUAL_URL, help="登录后跳转的URL")
    args = p.parse_args()

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("缺少 playwright。请在 data_analysis venv 安装：")
        print("  C:/Users/12485/.workbuddy/binaries/python/envs/data_analysis/Scripts/python.exe -m pip install playwright")
        sys.exit(1)

    SCA_DIR.mkdir(parents=True, exist_ok=True)
    chrome = _get_chrome()
    print(f"浏览器: {chrome or '内置 chromium'}")
    print(f"会话目录: {SCA_DIR}")

    async with async_playwright() as pw:
        if chrome:
            browser = await pw.chromium.launch(
                headless=False,
                executable_path=chrome,
                args=["--disable-blink-features=AutomationControlled"],
            )
        else:
            browser = await pw.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )

        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="zh-CN",
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")

        page = await context.new_page()
        await page.goto("https://scs.officemate.cn/scspro/", wait_until="domcontentloaded", timeout=60000)
        print(f"打开: {page.url}")

        if args.check:
            await asyncio.sleep(2)
            print(f"当前 URL: {page.url}")
            print(f"标题: {await page.title()}")
            print("如果已登录到 SCS 主页面 → 登录状态有效")
            print("如果跳转回登录页 → 需要重新登录")
            await asyncio.sleep(2)
        else:
            print("\n请在打开的浏览器中完成以下操作：")
            print("  1) 登录（账号 + 密码 + 短信验证码）")
            print("  2) 进入 '我的商品 → 商品列表 → 商品库 → 资质列表'")
            print("  3) 看到表格数据后，回到这里按回车")
            print("  4) 关闭浏览器窗口结束")
            await (await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline))
            await context.storage_state(path=str(SCA_DIR / "state.json"))
            print(f"已保存登录状态到: {SCA_DIR / 'state.json'}")

        # 保留会话：将 context 写到磁盘
        await context.storage_state(path=str(SCA_DIR / "state.json"))
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
