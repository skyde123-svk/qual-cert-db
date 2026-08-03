"""
merge.py - 增量合并历史数据 + 当日新抓取数据
输出：
  api/index.json          索引
  api/qual-history.json   合并后的历史库
  api/shard/N.json        分片
字段映射：
  qualificationCode → qualCode
  qualificationDisableDate → expireDate
  qualificationName → name
  qualificationTypeName → typeName
  qualificationStatus → status
  productBrand / brandName → brand
  attachment / attachUrl / files → files (array)
"""
import argparse
import json
import re
from pathlib import Path
from collections import defaultdict

# 资质类型映射
TYPE_NORMALIZE = {
    "检测报告": "检测报告",
    "TEST_REPORT": "检测报告",
    "testReport": "检测报告",
    "1": "检测报告",
    "合格证": "合格证",
    "COC": "合格证",
    "coc": "合格证",
    "2": "合格证",
    "强制认证证书": "强制认证证书",
    "CCC": "强制认证证书",
    "ccc": "强制认证证书",
    "3": "强制认证证书",
    "产品认证证书": "产品认证证书",
    "PRODUCT_CERT": "产品认证证书",
    "productCert": "产品认证证书",
    "4": "产品认证证书",
    "食品生产许可证": "食品生产许可证",
    "FOOD_LICENSE": "食品生产许可证",
    "foodLicense": "食品生产许可证",
    "5": "食品生产许可证",
}

def _norm_type(rec):
    for k in ["qualTypeName", "qualType", "typeName", "type", "qualificationType", "certTypeName"]:
        v = rec.get(k)
        if v is None: continue
        s = str(v).strip()
        if s in TYPE_NORMALIZE:
            return TYPE_NORMALIZE[s]
        for key, val in TYPE_NORMALIZE.items():
            if key in s or s in key:
                return val
    return rec.get("_qualTypeName") or "其他"

def _record_id(rec):
    return str(rec.get("qualId") or rec.get("id") or rec.get("qualificationId") or "")

def _brand(rec):
    return (rec.get("brandName") or rec.get("brand") or rec.get("productBrand") or rec.get("brand_name") or "未分类").strip()

def _files(rec):
    """统一 files 字段为数组"""
    f = rec.get("files") or rec.get("attachUrls") or rec.get("attachments") or rec.get("attachment")
    if not f:
        u = rec.get("attachUrl") or rec.get("fileUrl") or rec.get("url")
        f = [u] if u else []
    if isinstance(f, str):
        return [x.strip() for x in f.split(",") if x.strip()]
    if isinstance(f, list):
        return [str(x) for x in f if x]
    return []

def normalize(rec):
    """规范化字段，让前端和参考站 suzyzaq 风格一致"""
    out = {
        "code": rec.get("qualificationCode") or rec.get("code") or rec.get("qualCode") or "",
        "name": rec.get("qualificationName") or rec.get("name") or rec.get("qualName") or "",
        "type": _norm_type(rec),
        "status": rec.get("qualificationStatus") or rec.get("status") or "有效",
        "brand": _brand(rec),
        "category": rec.get("category") or rec.get("categoryName") or "",
        "productName": rec.get("productName") or rec.get("name") or "",
        "productCode": rec.get("productCode") or rec.get("productId") or "",
        "enable": rec.get("qualificationEnableDate") or rec.get("enableDate") or "",
        "disable": rec.get("qualificationDisableDate") or rec.get("disableDate") or rec.get("expireDate") or "",
        "company": rec.get("company") or rec.get("companyName") or "",
        "supplier": rec.get("supplier") or rec.get("supplierName") or "",
        "files": _files(rec),
        "createTime": rec.get("createTime") or rec.get("create") or "",
        "updateTime": rec.get("updateTime") or rec.get("update") or "",
        "remark": rec.get("remark") or "",
    }
    # 状态计算
    if out["disable"]:
        try:
            exp = out["disable"][:10]
            exp_dt = exp
            today = rec.get("_capturedAt", "")[:10] or "2099-01-01"
            if exp_dt < today:
                out["flag"] = "expired"
                out["flagText"] = "已失效"
            else:
                out["flag"] = "valid"
                out["flagText"] = "有效"
        except Exception:
            out["flag"] = "valid"
            out["flagText"] = "有效"
    else:
        out["flag"] = "valid"
        out["flagText"] = "有效"
    return out

def load_history(path):
    if not Path(path).exists():
        return {}
    return {r["_id"]: r for r in json.loads(Path(path).read_text(encoding="utf-8")).get("records", [])}

def merge(today_path, history_path, out_history, out_index, shard_dir, shard_size=2000):
    today = json.loads(Path(today_path).read_text(encoding="utf-8"))
    today_recs = today.get("records", [])
    captured_at = today.get("capturedAt", "")
    history_map = load_history(history_path)

    added = 0
    updated = 0
    for r in today_recs:
        rid = _record_id(r)
        if not rid: continue
        r["_capturedAt"] = captured_at
        norm = normalize(r)
        norm["_id"] = rid
        norm["_firstSeen"] = history_map.get(rid, {}).get("_firstSeen") or captured_at
        norm["_lastSeen"] = captured_at
        if rid in history_map:
            updated += 1
        else:
            added += 1
        history_map[rid] = norm

    merged = list(history_map.values())
    print(f"今日新增 {added} 条，更新 {updated} 条，库内总 {len(merged)} 条")

    by_type = defaultdict(int)
    by_brand = defaultdict(int)
    by_status = defaultdict(int)
    for r in merged:
        by_type[r["type"]] += 1
        by_brand[r["brand"]] += 1
        by_status[r["flag"]] += 1

    # 写历史
    Path(out_history).parent.mkdir(parents=True, exist_ok=True)
    Path(out_history).write_text(
        json.dumps({
            "lastUpdated": captured_at,
            "total": len(merged),
            "byType": dict(by_type),
            "byBrand": dict(by_brand),
            "records": merged,
        }, ensure_ascii=False),
        encoding="utf-8"
    )

    # 分片
    shard_dir = Path(shard_dir)
    shard_dir.mkdir(parents=True, exist_ok=True)
    for f in shard_dir.glob("*.json"):
        f.unlink()
    sorted_recs = sorted(merged, key=lambda r: r["brand"])
    shards = []
    for i in range(0, len(sorted_recs), shard_size):
        shard = sorted_recs[i:i+shard_size]
        p = shard_dir / f"{len(shards)}.json"
        p.write_text(json.dumps(shard, ensure_ascii=False), encoding="utf-8")
        shards.append({"file": p.name, "count": len(shard)})
    print(f"分片 {len(shards)} 个，每片 {shard_size} 条")

    # 索引
    index = {
        "today": captured_at[:10] if captured_at else "",
        "generated": captured_at,
        "shardCount": len(shards),
        "recordCount": len(merged),
        "brandCount": len(by_brand),
        "byType": dict(by_type),
        "byStatus": dict(by_status),
        "brands": dict(sorted(by_brand.items(), key=lambda x: -x[1])[:50]),
        "shards": shards,
    }
    Path(out_index).write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"索引: {out_index}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default="api/qual-today.json")
    ap.add_argument("--history", default="api/qual-history.json")
    ap.add_argument("--out-history", default="api/qual-history.json")
    ap.add_argument("--index", default="api/index.json")
    ap.add_argument("--shard-dir", default="api/shard")
    ap.add_argument("--shard-size", type=int, default=2000)
    args = ap.parse_args()
    merge(args.today, args.history, args.out_history, args.index, args.shard_dir, args.shard_size)
