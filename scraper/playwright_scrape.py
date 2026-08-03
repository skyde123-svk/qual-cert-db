"""
playwright_scrape.py
核心抓取脚本：复用持久化登录态，真实点击翻页，拦截 getPage 响应获取所有资质。

用法：
  python playwright_scrape.py              # 抓取所有资质类型
  python playwright_scrape.py --types 1,2  # 只抓指定类型
  python playwright_scrape.py --output api/qual-today.json
"""
import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote

SCA_DIR = Path(__file__).parent / ".scs_session"
STATE = SCA_DIR / "state.json"

# 资质类型（与页面下拉框对应）
QUAL_TYPES = {
    "1": "检测报告",
    "2": "合格证",
    "3": "强制认证证书",
    "4": "产品认证证书",
    "5": "食品生产许可证",
}

QUAL_URL = "https://scs.officemate.cn/scspro/#/product/management"

def _get_chrome():
    for c in [
        r"C:/Program Files/Google/Chrome/Application/chrome.exe",
        r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        r"C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    ]:
        if Path(c).exists():
            return c
    return None

async def run(qual_types: list[str], output: str, max_pages: int = 0, page_size: int = 50):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("缺少 playwright"); sys.exit(1)

    if not STATE.exists():
        print(f"❌ 未找到登录状态 {STATE}，请先运行：python login.py")
        sys.exit(1)

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        chrome = _get_chrome()
        launch_kwargs = dict(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        if chrome:
            launch_kwargs["executable_path"] = chrome
        browser = await pw.chromium.launch(**launch_kwargs)

        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="zh-CN",
            storage_state=str(STATE),
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")

        page = await context.new_page()

        # 拦截器：保存所有 /api/product/qualification/getPage 响应
        captured: dict[str, list] = {k: [] for k in qual_types}
        seen_signatures: set = set()

        async def on_response(resp):
            try:
                url = resp.url
                m = re.search(r"/api/product/qualification/getPage\b", url)
                if not m:
                    return
                # 判断类型：从请求体或URL参数
                req = resp.request
                body = req.post_data
                qtype = None
                if body:
                    try:
                        bj = json.loads(body)
                        qtype = bj.get("qualType") or bj.get("type") or bj.get("qualificationType")
                    except Exception:
                        # 可能是加密字符串
                        # 尝试从 URL 参数解析
                        from urllib.parse import parse_qs
                        qs = parse_qs(url.split("?", 1)[-1]) if "?" in url else {}
                        qtype = (qs.get("qualType") or qs.get("type") or [None])[0]
                if qtype is None:
                    # 通过响应内容反推：先缓存，全部抓取后按total排序
                    qtype = "_pending"
                if str(qtype) not in list(captured.keys()) + ["_pending"]:
                    captured.setdefault(qtype, [])
                txt = await resp.text()
                # 跳过空响应
                if not txt or len(txt) < 50:
                    return
                try:
                    data = json.loads(txt)
                except Exception:
                    return
                records = (data.get("data") or {}).get("records") or []
                if not records:
                    return
                # 用 first record id + total + current 标记
                sig = (json.dumps({"q": qtype, "t": data.get("data", {}).get("total"), "c": data.get("data", {}).get("current"), "f": records[0].get("id")}, sort_keys=True))
                if sig in seen_signatures:
                    return
                seen_signatures.add(sig)
                if qtype not in captured:
                    captured[qtype] = []
                captured[qtype].append({
                    "page": data.get("data", {}).get("current"),
                    "total": data.get("data", {}).get("total"),
                    "records": records,
                })
            except Exception as e:
                print(f"  [拦截异常] {e}")

        page.on("response", on_response)

        print(f"打开资质页面: {QUAL_URL}")
        await page.goto(QUAL_URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        # 检查登录
        if "login" in page.url.lower() or "passport" in page.url.lower():
            print("❌ 登录状态已失效，请重新运行：python login.py")
            await browser.close()
            sys.exit(2)

        print(f"当前 URL: {page.url}")
        await asyncio.sleep(3)

        # 等表格渲染
        for _ in range(30):
            ok = await page.evaluate("""() => {
                const t = document.querySelector('table');
                if (!t) return false;
                const rows = t.querySelectorAll('tbody tr');
                return rows.length > 0;
            }""")
            if ok:
                break
            await asyncio.sleep(1)
        else:
            print("⚠️ 未检测到表格，可能需要手动选择资质类型")

        # 切换每页条数：尝试 50/页（或 100），加快抓取
        await _set_page_size(page, page_size)

        # 处理每种资质类型
        for qt in qual_types:
            print(f"\n========== 资质类型: {QUAL_TYPES.get(qt, qt)} ({qt}) ==========")
            captured_this_type = []
            # 重置拦截计数
            if qt not in captured:
                captured[qt] = []
            captured_this_type = captured[qt]

            # 切换类型下拉框
            await _select_qual_type(page, qt)

            # 等待新数据
            await asyncio.sleep(3)

            # 读取总页数
            total_pages = await _get_total_pages(page)
            print(f"  总页数: {total_pages}")
            if max_pages:
                total_pages = min(total_pages, max_pages)

            # 强制翻页：逐页点击真实"下一页"按钮
            status = await _paginate(page, total_pages)
            await asyncio.sleep(2)
            print(f"  ✓ 当前类型捕获 {len(captured[qt])} 页")

        await browser.close()

        # 输出结果
        all_records = []
        for qt, pages in captured.items():
            for pg in pages:
                for r in pg["records"]:
                    r["_qualType"] = qt
                    r["_qualTypeName"] = QUAL_TYPES.get(qt, qt)
                    all_records.append(r)

        # 去重（按 id）
        seen = set()
        unique = []
        for r in all_records:
            rid = r.get("id") or r.get("qualId") or (r.get("productId"), r.get("qualType"))
            if rid in seen: continue
            seen.add(rid)
            unique.append(r)

        out = {
            "capturedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "qualTypes": qual_types,
            "pageSize": page_size,
            "total": len(unique),
            "byType": {qt: len([r for r in unique if r.get("_qualType") == qt]) for qt in qual_types},
            "records": unique,
        }
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✅ 共 {len(unique)} 条记录，保存到 {out_path}")
        return out


async def _set_page_size(page, size):
    """尝试把每页条数设为 size 以减少翻页次数"""
    try:
        ok = await page.evaluate("""(size) => {
            const sels = Array.from(document.querySelectorAll('.ant-pagination-options .ant-select-selection-item, .ant-select-selection-item'));
            for (const s of sels) {
                if (s.textContent.trim() === '10' || s.textContent.trim() === '20') {
                    s.click();
                    return true;
                }
            }
            return false;
        }""", size)
        if ok:
            await asyncio.sleep(1)
            # 选择 size
            chosen = await page.evaluate("""(size) => {
                const items = document.querySelectorAll('.ant-select-item-option-content');
                for (const it of items) {
                    if (it.textContent.trim() == String(size)) {
                        it.click();
                        return true;
                    }
                }
                return false;
            }""", size)
            if chosen:
                await asyncio.sleep(2)
                print(f"  每页已设为 {size} 条")
    except Exception as e:
        print(f"  [设置每页条数失败] {e}")


async def _select_qual_type(page, qual_type: str):
    """切换资质类型下拉框"""
    try:
        # 找资质类型 combobox
        opened = await page.evaluate("""(qt) => {
            const cbs = document.querySelectorAll('.ant-select-selector');
            for (const cb of cbs) {
                // 找第一个含"资质"或"全部"的选择器
                const txt = cb.textContent;
                if (txt.includes('资质') || txt.includes('类型') || txt.includes('全部')) {
                    cb.click();
                    return true;
                }
            }
            return false;
        }""", qual_type)
        if not opened:
            print("  ⚠️ 未找到资质类型下拉框使用默认筛选")
            return False
        await asyncio.sleep(1)
        # 选择对应项
        chosen = await page.evaluate("""(qt) => {
            const opts = document.querySelectorAll('.ant-select-item-option');
            for (const o of opts) {
                const t = o.textContent.trim();
                // eslint-disable-next-line no-restricted-globals
                if (t == qt || t.includes(qt) || t === String(qt)) {
                    o.click();
                    return t;
                }
            }
            return null;
        }""", qual_type)
        if chosen:
            print(f"  已选类型: {chosen}")
            await asyncio.sleep(2)
            return True
        # 关闭 dropdown
        await page.keyboard.press("Escape")
        return False
    except Exception as e:
        print(f"  [切换类型异常] {e}")
        return False


async def _get_total_pages(page):
    """从分页器读取总页数"""
    try:
        total = await page.evaluate("""() => {
            // 1. 包含"共 X 条"的元素
            const list = document.querySelectorAll('.pagination-info, .ant-pagination-total-text, .total');
            for (const el of list) {
                const m = (el.textContent || '').match(/(\d+)/);
                if (m) return parseInt(m[1]);
            }
            // 2. 翻页按钮 last-page 的 title
            const items = document.querySelectorAll('.ant-pagination-item');
            if (items.length) return parseInt(items[items.length - 1].textContent) || 1;
            return 1;
        }""")
        return total or 1
    except Exception:
        return 1


async def _paginate(page, total_pages: int):
    """逐页点击'下一页'按钮，捕获每个分页的请求"""
    if total_pages <= 1:
        return "single"
    clicked = 0
    for i in range(1, total_pages):
        # 1. 找下一页按钮
        ok = await page.evaluate("""() => {
            const next = document.querySelector('.ant-pagination-next');
            if (!next || next.classList.contains('ant-pagination-disabled')) return false;
            // 真实点击中心
            const r = next.getBoundingClientRect();
            const ev = new MouseEvent('click', { bubbles: true, cancelable: true, view: window, clientX: r.left + r.width/2, clientY: r.top + r.height/2 });
            next.dispatchEvent(ev);
            return true;
        }""")
        if not ok:
            print(f"    第 {i+1} 页：下一页按钮已禁用，停止")
            break
        await asyncio.sleep(1.2)
        # 2. 真实鼠标点击（触发页面真正交互）
        clicked += 1
        if i % 10 == 0:
            print(f"    已翻到第 {i+1} 页...")
    return f"clicked {clicked}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--types", default="1,2,3,4,5", help="逗号分隔的资质类型")
    ap.add_argument("--output", default="api/qual-today.json", help="输出路径")
    ap.add_argument("--max-pages", type=int, default=0, help="限制最大翻页数（0=全部）")
    ap.add_argument("--page-size", type=int, default=50, help="每页条数")
    args = ap.parse_args()
    asyncio.run(run(args.types.split(","), args.output, args.max_pages, args.page_size))
