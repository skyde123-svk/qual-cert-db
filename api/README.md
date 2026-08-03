# 资质证书查询 API · 接口说明（静态 JSON，免鉴权）

> 数据来源：欧菲斯 SCS 平台资质池 · 每日 17:00 自动更新  
> 适用：Dify / Coze / 任意 HTTP 客户端，按品牌查询资质证书，只返回命中数据（KB 级），无需下载整页

## 接口域名

**首选：阿里云 OSS（国内服务器/Dify 直连，最快最稳）**

```
https://<YOUR-BUCKET>.oss-cn-hangzhou.aliyuncs.com/qual-cert-db/api/
```

**备用：GitHub Pages（免配置 OSS）**
- `https://<YOUR-USERNAME>.github.io/qual-cert-db/api/`

浏览器访问查询页面：`https://<YOUR-USERNAME>.github.io/qual-cert-db/`

## 接口清单（全部 GET，返回 JSON）

| 接口 | 说明 | 大小 |
|---|---|---|
| `api/index.json` | 品牌索引：品牌名 → 分片号 | ~1 KB |
| `api/shard/{分片号}.json` | 品牌数据分片（含资质证书明细） | 每片 ≤300 KB |

### index.json 结构
```json
{
  "today": "2026-07-30",
  "generated": "2026-07-30 17:04:12",
  "shardCount": 1,
  "brandCount": 15,
  "recordCount": 70,
  "brands": { "惠普/HP": 0, "美的/Midea": 0, "伊利": 0 }
}
```

### shard/N.json 结构
```json
{
  "惠普/HP": {
    "certs": [
      {
        "code": "CERT-2026000001",
        "name": "惠普CCC认证证书",
        "type": "强制认证证书",
        "typeKey": "ccc",
        "brand": "惠普/HP",
        "subject": "惠普贸易(上海)有限公司",
        "model": "HP-LJ-1020",
        "issuer": "中国质量认证中心",
        "enable": "2025-01-15",
        "disable": "2028-01-14",
        "months": 18.5,
        "flag": "valid",
        "flagText": "有效",
        "status": "有效",
        "files": ["https://msapi.officemate.cn/aliyun-oss-ofs-scs/prod/..."],
        "category": "办公设备",
        "project": "中国海油",
        "region": "全国"
      }
    ]
  }
}
```

## 字段字典

### cert（资质证书）
| 字段 | 说明 | 示例 |
|---|---|---|
| `code` | 证书编号 | CERT-2026000001 |
| `name` | 证书名称 | 惠普CCC认证证书 |
| `type` | 资质类型（中文） | 强制认证证书 |
| `typeKey` | 资质类型键 | ccc / coc / test_report / prod_cert / food_lic |
| `brand` | 品牌 | 惠普/HP |
| `subject` | 持证主体/企业 | 惠普贸易(上海)有限公司 |
| `model` | 型号/规格 | HP-LJ-1020 |
| `issuer` | 签发机构 | 中国质量认证中心 |
| `enable` | 生效日期 | 2025-01-15 |
| `disable` | 失效日期 | 2028-01-14 |
| `months` | 剩余有效期（月，负数=已过期） | 18.5 |
| `flag` | 状态标识 | valid / expiring / expired |
| `flagText` | 状态文本 | 有效 / 临期 / 已失效 |
| `files` | 附件链接数组（图片或PDF） | ["https://..."] |
| `category` | 品类 | 办公设备 |
| `project` | 关联项目 | 中国海油 |

### 资质类型枚举（typeKey）
| typeKey | 中文名称 |
|---|---|
| `test_report` | 检测报告 |
| `coc` | 合格证 |
| `ccc` | 强制认证证书 |
| `prod_cert` | 产品认证证书 |
| `food_lic` | 食品生产许可证 |

## Dify 工作流示例

### 节点1 · HTTP 请求（GET 索引）
- 方法：GET
- URL：`https://<BUCKET>.oss-cn-hangzhou.aliyuncs.com/qual-cert-db/api/index.json`

### 节点2 · 代码执行（品牌匹配 + 类型筛选）
```python
def main(index: dict, keyword: str, cert_type: str = "") -> dict:
    brands = index.get("brands", {})
    hits = [{"brand": b, "shard": s} for b, s in brands.items() if keyword in b]
    shards = sorted({h["shard"] for h in hits})
    return {"hits": hits, "shards": shards, "found": len(hits) > 0, "cert_type": cert_type}
```

### 节点3 · HTTP 请求（GET 分片）+ 提取
```python
def main(shard: dict, hits: list, cert_type: str = "") -> dict:
    certs = []
    for h in hits:
        g = shard.get(h["brand"])
        if g and g.get("certs"):
            items = g["certs"]
            if cert_type:
                items = [c for c in items if c.get("typeKey") == cert_type]
            certs += items
    return {"certs": certs, "count": len(certs)}
```

## 直接调用示例（curl）

```bash
# 查品牌索引
curl -s https://<BUCKET>.oss-cn-hangzhou.aliyuncs.com/qual-cert-db/api/index.json

# 查"惠普"的资质证书（假设在分片 0）
curl -s https://<BUCKET>.oss-cn-hangzhou.aliyuncs.com/qual-cert-db/api/shard/0.json | python3 -c "
import sys,json
d=json.load(sys.stdin)
for brand, group in d.items():
    if '惠普' in brand:
        for c in group.get('certs',[]):
            print(f\"{c['type']} | {c['name']} | {c['disable']} | {c['flagText']}\")
"
```

## 备注

- 同名品牌可能存在多个键（如 惠普 / 惠普/HP），建议按"包含关键词"模糊匹配后合并结果。
- 附件链接为欧菲斯 OSS 公网地址，可直接打开预览。
- 数据每日 17:00 自动更新并同步到阿里云 OSS（需配置 GitHub Secrets: `SCS_COOKIE` 和 `SCS_API_URL`）。
- index.json 中 `today` 字段可校验数据日期。
