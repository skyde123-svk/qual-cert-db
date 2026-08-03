"""
push.py - 推送到 GitHub 仓库
用法：
  1. 在 GitHub 创建 qual-cert-db 仓库（账号 suzyzaq）
  2. 拿到 Personal Access Token (PAT)，勾选 repo 权限
  3. 设置环境变量 GITHUB_TOKEN 和 GITHUB_REPO
     或 .env 文件
"""
import argparse
import base64
import json
import os
import sys
from pathlib import Path
import urllib.request
import urllib.error

API_BASE = "https://api.github.com"
BRANCH = "main"

def _load_config():
    cfg = {}
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("GITHUB_TOKEN", "GITHUB_REPO", "GITHUB_USER", "GITHUB_EMAIL"):
        if k in os.environ:
            cfg[k] = os.environ[k]
    return cfg

def _req(path, method="GET", data=None, token=None):
    url = f"{API_BASE}{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "qual-cert-db-pusher",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")

def get_file_sha(repo, token, path, branch=BRANCH):
    code, data = _req(f"/repos/{repo}/contents/{path}?ref={branch}", token=token)
    if code == 200:
        return data.get("sha"), data.get("content", "")
    return None, None

def upload_file(repo, token, path, content_str, message, branch=BRANCH):
    sha, _ = get_file_sha(repo, token, path, branch)
    payload = {
        "message": message,
        "branch": branch,
        "content": base64.b64encode(content_str.encode("utf-8")).decode("ascii"),
    }
    if sha:
        payload["sha"] = sha
    code, data = _req(f"/repos/{repo}/contents/{path}", method="PUT", data=payload, token=token)
    return code, data

def upload_all(repo, token, local_dir, prefix="api", message="update data"):
    local_dir = Path(local_dir)
    files = []
    for p in local_dir.rglob("*"):
        if p.is_file():
            rel = p.relative_to(local_dir).as_posix()
            files.append((p, f"{prefix}/{rel}"))
    print(f"推送 {len(files)} 个文件到 {repo}")
    ok = 0
    fail = 0
    for local, remote in files:
        try:
            content = local.read_text(encoding="utf-8")
            code, data = upload_file(repo, token, remote, content, message)
            if 200 <= code < 300:
                ok += 1
            else:
                fail += 1
                print(f"  ❌ {remote}: {code} {data.get('message', '')}")
        except Exception as e:
            fail += 1
            print(f"  ❌ {remote}: {e}")
    print(f"推送结果: {ok} 成功, {fail} 失败")

def main():
    cfg = _load_config()
    token = cfg.get("GITHUB_TOKEN")
    repo = cfg.get("GITHUB_REPO", "suzyzaq/qual-cert-db")
    if not token:
        print("❌ 未找到 GITHUB_TOKEN")
        print("请在 .env 或环境变量设置：")
        print("  GITHUB_TOKEN=ghp_xxxxx")
        print("  GITHUB_REPO=suzyzaq/qual-cert-db")
        sys.exit(1)

    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="api", help="本地目录")
    ap.add_argument("--prefix", default="api", help="远端路径前缀")
    ap.add_argument("--message", default="chore: daily qualification scrape")
    args = ap.parse_args()

    upload_all(repo, token, args.dir, args.prefix, args.message)

if __name__ == "__main__":
    main()
