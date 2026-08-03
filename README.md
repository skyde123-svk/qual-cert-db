# 欧菲斯 SCS 资质证书数据库

定时抓取欧菲斯 SCS 平台（我的商品 → 商品列表 → 商品库 → 资质列表）上的 5 类资质证书，并发布到 GitHub Pages。

- 检测报告
- 合格证
- 强制认证证书（CCC）
- 产品认证证书
- 食品生产许可证

## 数据来源

- 源平台 `https://scs.officemate.cn/scspro/`
- 资质列表接口 `POST /api/product/qualification/getPage`（AES 加密 + 短信校验登录态，无法直接外部调用）
- 真实点击 UI 翻页 + 拦截 fetch 响应，浏览器上下文解密（Playwright 真实输入事件）

## 抓取架构

```
SCS 前端 (浏览器上下文)
  ↓ 用户截图登录 + 短信验证码
  ↓ Playwright 真实点击翻页
fetch /api/product/qualification/getPage (AES 解密后)
  ↓ response listener 拦截
本地 JSON (api/qual-today.json)
  ↓ merge.py 去重合并
api/qual-history.json + api/shard/N.json + api/index.json
  ↓ push.py
GitHub: suzyzaq/qual-cert-db
  ↓ GitHub Pages 自动部署
https://suzyzaq.github.io/qual-cert-db/
```

## 一次性配置

### 1. 创建 GitHub 仓库 + PAT
1. 登录 GitHub（账号 suzyzaq），新建仓库 `qual-cert-db`（公开）
2. `Settings → Developer settings → Personal access tokens → Tokens (classic)`
3. Generate new token，勾选 `repo` 权限，过期选最长（如 1 年）
4. 复制 token（仅显示一次）

### 2. 创建 .env 文件
```
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
GITHUB_REPO=suzyzaq/qual-cert-db
```

保存到 `scraper/.env`。

### 3. 首次登录（手动一次）
在仓库目录 `cd qual-cert-db`：
```bash
"C:/Users/12485/.workbuddy/binaries/python/envs/data_analysis/Scripts/python.exe" scraper/login.py
```
浏览器打开后：
1. 输入账号 `18341325442`、密码 `Cyyl23456.`
2. 短信验证码（用户手机收到）
3. 进入"我的商品 → 商品列表 → 商品库 → 资质列表"
4. 看到表格数据后回到命令行，按回车
5. 关闭浏览器

登录状态会保存到 `scraper/.scs_session/state.json`。

### 4. 启用 GitHub Pages
1. 仓库 → `Settings → Pages`
2. Source: `Deploy from a branch`
3. Branch: `main` / `(root)`
4. 保存

## 每日自动抓取

推荐用本机定时任务（电脑需开机）：

```bash
# 手动跑一次完整流程
"C:/Users/12485/.workbuddy/binaries/python/envs/data_analysis/Scripts/python.exe" scraper/daily.py
```

`daily.py` 串联：
1. `playwright_scrape.py` —— 抓取 5 类资质
2. `merge.py` —— 增量合并到历史库
3. `push.py` —— 推送 api/ 到 GitHub

GitHub Pages 自动重新部署，约 1-2 分钟后访问 https://suzyzaq.github.io/qual-cert-db/ 看到最新数据。

## 常用命令

```bash
# 只抓取检测报告（快速验证）
python scraper/playwright_scrape.py --types 1 --output api/qual-test.json --max-pages 3

# 抓取所有类型
python scraper/playwright_scrape.py --types 1,2,3,4,5 --output api/qual-today.json

# 合并 + 推送（不抓取）
python scraper/merge.py && python scraper/push.py

# 强制每页 100 条（加快首次全量）
python scraper/playwright_scrape.py --page-size 100
```

## 字段说明

| 字段 | 含义 |
|------|------|
| `code` | 资质编号 |
| `name` | 资质名称 |
| `type` | 资质类型（5 类） |
| `brand` | 品牌 |
| `category` | 产品类目 |
| `status` | 资质状态 |
| `disable` | 有效期至 |
| `company` | 所属公司 |
| `files` | 附件 URL 数组（图片/PDF） |

## 注意事项

- **登录态失效**：SCS 登录会话几天到几周会自动过期；发现抓不到数据时重新跑 `login.py`
- **翻页风险**：当前通过 dispatchEvent 触发的"下一页"在某些 SCS 版本可能失效；如需真实鼠标点击（CDP mouse.click），后续切换到 chrome devtools protocol
- **数据规模**：每类约 100-200 页（每页 50 条），全部抓取约 5-15 分钟
- **GitHub Pages 限制**：单文件 ≤ 100MB，分片后远小于此
