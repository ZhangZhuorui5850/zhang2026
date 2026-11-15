#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
netsearch.py · 零依赖检索工具
=============================

给编排器和 agent 用的最小检索层：只用标准库，不需要 key，失败就降级。

三个后端，按可用性自动选择：
  1. MARS_SEARXNG_URL  自建/公共 SearXNG，最稳（返回 JSON）
  2. DuckDuckGo HTML   无 key，境内常被墙 → 失败即降级
  3. 全失败            返回 []，调用方走 D1（靠模型自身知识 + 标 confidence≤0.5）

命令行也能直接用：
    python3 tools/netsearch.py "protein solubility prediction benchmark"
    python3 tools/netsearch.py --fetch https://example.com
"""

import argparse
import ipaddress
import json
import os
import re
import socket
import sys
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
DDG_HTML = "https://html.duckduckgo.com/html/?q=%s"
MAX_BYTES = 2 * 1024 * 1024


# ---------------------------------------------------------------------------
# 基础
# ---------------------------------------------------------------------------

def _get(url, timeout=12, headers=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        **(headers or {}),
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(MAX_BYTES)
    for enc in ("utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _is_private_host(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return True
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return True
    return False


# ---------------------------------------------------------------------------
# 后端 1：SearXNG
# ---------------------------------------------------------------------------

def _search_searxng(query, limit, timeout):
    base = os.environ.get("MARS_SEARXNG_URL", "").rstrip("/")
    if not base:
        return None
    url = "%s/search?q=%s&format=json&language=zh-CN" % (
        base, urllib.parse.quote(query))
    try:
        data = json.loads(_get(url, timeout))
    except Exception:  # noqa: BLE001
        return None
    out = []
    for item in data.get("results", [])[:limit]:
        out.append({
            "title": (item.get("title") or "").strip(),
            "url": item.get("url") or "",
            "snippet": re.sub(r"\s+", " ", item.get("content") or "").strip()[:400],
            "backend": "searxng",
        })
    return out


# ---------------------------------------------------------------------------
# 后端 2：DuckDuckGo HTML（无 key）
# ---------------------------------------------------------------------------

RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.S)
SNIPPET_RE = re.compile(r'class="result__snippet"[^>]*>(?P<s>.*?)</a>', re.S)


def _clean(html):
    text = re.sub(r"<[^>]+>", "", html)
    text = (text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&#x27;", "'").replace("&nbsp;", " "))
    return re.sub(r"\s+", " ", text).strip()


def _unwrap_ddg(href):
    """DDG 会把结果包成 //duckduckgo.com/l/?uddg=<真实地址>"""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlparse(href)
    qs = urllib.parse.parse_qs(parsed.query)
    if "uddg" in qs:
        return qs["uddg"][0]
    return href


def _search_ddg(query, limit, timeout):
    try:
        html = _get(DDG_HTML % urllib.parse.quote(query), timeout)
    except Exception:  # noqa: BLE001
        return None
    links = RESULT_RE.findall(html)
    if not links:
        return None
    snippets = SNIPPET_RE.findall(html)
    out = []
    for i, (href, title) in enumerate(links[:limit]):
        out.append({
            "title": _clean(title),
            "url": _unwrap_ddg(href),
            "snippet": _clean(snippets[i])[:400] if i < len(snippets) else "",
            "backend": "ddg",
        })
    return out


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------

def search(query, limit=5, timeout=12):
    """返回 [{"title","url","snippet","backend"}]；全失败返回 []。"""
    query = (query or "").strip()
    if not query:
        return []
    for fn in (_search_searxng, _search_ddg):
        try:
            res = fn(query, limit, timeout)
        except Exception:  # noqa: BLE001
            res = None
        if res:
            return res
    return []


def fetch(url, max_chars=8000, timeout=15):
    """取网页正文（粗提纯，去掉 script/style），失败返回空串。"""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return ""
    if parsed.hostname and _is_private_host(parsed.hostname):
        return ""
    try:
        html = _get(url, timeout)
    except Exception:  # noqa: BLE001
        return ""
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    text = _clean(html)
    return text[:max_chars]


def format_results(results, max_items=5):
    """把结果压成给模型看的紧凑文本。"""
    if not results:
        return "(无结果：检索不可用，按 D1 降级，结论标 confidence<=0.5)"
    lines = []
    for i, r in enumerate(results[:max_items], 1):
        lines.append("%d. %s\n   %s\n   %s" % (i, r["title"], r["url"], r["snippet"][:200]))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default="")
    ap.add_argument("--fetch", default="")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.fetch:
        text = fetch(a.fetch)
        print(text if text else "× 抓取失败或被拒绝（内网/超时/非 http）")
        return 0 if text else 1

    if not a.query:
        ap.print_help()
        return 2

    res = search(a.query, a.limit)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(format_results(res))
    return 0 if res else 1


if __name__ == "__main__":
    sys.exit(main())
