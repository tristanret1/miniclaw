#!/usr/bin/env python3
"""
论坛图片爬虫脚本
爬取指定论坛板块的帖子图片并按帖子ID分类保存
支持断点续传、进度显示、请求延迟控制
"""

import os
import re
import sys
import time
import json
import random
import hashlib
import argparse
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ============ 配置 ============
BASE_URL = "https://t66y.com"
BOARD_PATH = "/thread0806.php"
DEFAULT_FID = "16"
DOWNLOAD_DIR = "./downloads"
MAX_RETRIES = 3
REQUEST_DELAY_MIN = 0.5
REQUEST_DELAY_MAX = 1.0
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": BASE_URL,
}


# ============ 进度条 ============
class ProgressBar:
    """简易终端进度条"""

    def __init__(self, total, prefix="", width=40):
        self.total = max(total, 1)
        self.prefix = prefix
        self.width = width
        self.current = 0

    def update(self, n=1):
        self.current += n
        self._draw()

    def _draw(self):
        pct = self.current / self.total
        filled = int(self.width * pct)
        bar = "█" * filled + "░" * (self.width - filled)
        line = f"\r{self.prefix} |{bar}| {self.current}/{self.total} ({pct:.0%})"
        sys.stdout.write(line)
        sys.stdout.flush()

    def finish(self):
        self._draw()
        print()


# ============ 断点续传管理 ============
class ProgressTracker:
    """记录已完成的下载，支持断点续传"""

    def __init__(self, filepath):
        self.filepath = filepath
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {"completed_threads": [], "completed_images": []}
        return {"completed_threads": [], "completed_images": []}

    def save(self):
        os.makedirs(os.path.dirname(self.filepath) or ".", exist_ok=True)
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def is_thread_done(self, thread_id):
        return thread_id in self.data["completed_threads"]

    def mark_thread_done(self, thread_id):
        if thread_id not in self.data["completed_threads"]:
            self.data["completed_threads"].append(thread_id)
            self.save()

    def is_image_done(self, url_hash):
        return url_hash in self.data["completed_images"]

    def mark_image_done(self, url_hash):
        if url_hash not in self.data["completed_images"]:
            self.data["completed_images"].append(url_hash)
            self.save()


# ============ 网络请求 ============
def create_session():
    """创建带有默认请求头的 Session"""
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def fetch_page(session, url, retries=MAX_RETRIES):
    """获取页面内容，带重试逻辑"""
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            # 尝试多种编码（该论坛常用 GBK）
            for enc in ("gbk", "gb2312", "utf-8", "latin-1"):
                try:
                    resp.encoding = enc
                    text = resp.text
                    # 简单验证解码是否合理
                    if "\ufffd" not in text[:500]:
                        return text
                except (UnicodeDecodeError, LookupError):
                    continue
            resp.encoding = "utf-8"
            return resp.text
        except requests.RequestException as e:
            print(f"\n  [!] 请求失败 (第{attempt}次): {url} -> {e}")
            if attempt < retries:
                wait = 2 ** attempt
                print(f"      等待 {wait}s 后重试...")
                time.sleep(wait)
    return None


def download_image(session, url, save_path, tracker, retries=MAX_RETRIES):
    """下载单张图片，支持断点续传"""
    url_hash = hashlib.md5(url.encode()).hexdigest()

    if tracker.is_image_done(url_hash):
        return "skipped"

    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        tracker.mark_image_done(url_hash)
        return "exists"

    headers = {
        "Referer": BASE_URL + "/",
        "User-Agent": HEADERS["User-Agent"],
    }

    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=headers, timeout=30, stream=True)
            if resp.status_code == 404:
                return "not_found"
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")
            if "text/html" in content_type:
                return "not_image"

            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            tmp_path = save_path + ".tmp"
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # 检查文件大小，过小可能是占位图
            if os.path.getsize(tmp_path) < 100:
                os.remove(tmp_path)
                return "too_small"

            os.rename(tmp_path, save_path)
            tracker.mark_image_done(url_hash)
            return "ok"

        except requests.RequestException:
            if attempt < retries:
                time.sleep(1)
            # 清理临时文件
            tmp_path = save_path + ".tmp"
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    return "failed"


# ============ 解析逻辑 ============
def parse_thread_list(html, base_url):
    """从列表页提取帖子链接和ID"""
    soup = BeautifulSoup(html, "html.parser")
    threads = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]

        # 模式1: htm_data/xxxx/xxxx/xxxx.html
        m = re.search(r"(htm_data/\S+?/(\d+)\.html)", href)
        if m:
            thread_id = m.group(2)
            full_url = urllib.parse.urljoin(base_url + "/", m.group(1))
            title = a_tag.get_text(strip=True)
            if title and len(title) > 2:
                threads.append({
                    "id": thread_id,
                    "url": full_url,
                    "title": title[:80],
                })
            continue

        # 模式2: read.php?tid=xxxx
        m2 = re.search(r"read\.php\?tid[=-](\d+)", href)
        if m2:
            thread_id = m2.group(1)
            full_url = urllib.parse.urljoin(base_url + "/", href)
            title = a_tag.get_text(strip=True)
            if title and len(title) > 2:
                threads.append({
                    "id": thread_id,
                    "url": full_url,
                    "title": title[:80],
                })

    # 去重
    seen = set()
    unique = []
    for t in threads:
        if t["id"] not in seen:
            seen.add(t["id"])
            unique.append(t)
    return unique


def extract_images_from_thread(html, page_url):
    """从帖子页面提取所有图片URL"""
    soup = BeautifulSoup(html, "html.parser")
    images = set()

    # 1. <img> 标签的各种属性
    for img in soup.find_all("img"):
        for attr in ("src", "data-src", "data-original", "data-lazy-src",
                      "data-echo", "file", "data-url", "lazysrc"):
            val = img.get(attr, "")
            if val:
                images.add(val.strip())

    # 2. <input> type=image
    for inp in soup.find_all("input", {"type": "image"}):
        src = inp.get("src", "")
        if src:
            images.add(src.strip())

    # 3. 行内 style 中的 background-image: url(...)
    for tag in soup.find_all(style=True):
        urls = re.findall(r"url\(['\"]?(.*?)['\"]?\)", tag["style"])
        images.update(u.strip() for u in urls)

    # 4. <a> 标签直接链接图片文件
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        ext = os.path.splitext(urllib.parse.urlparse(href).path)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            images.add(href)

    # 5. 在页面源码中正则搜索图片URL
    url_pattern = (
        r'https?://[^\s\'\"<>\)\]\}]+'
        r'\.(?:jpg|jpeg|png|gif|bmp|webp)'
        r'(?:\?[^\s\'\"<>\)\]\}]*)?'
    )
    for match in re.findall(url_pattern, str(soup), re.IGNORECASE):
        images.add(match.strip())

    # 过滤和规范化
    cleaned = set()
    for url in images:
        url = url.strip()
        if not url or url.startswith("data:") or len(url) < 10:
            continue

        # 跳过网站UI小图标/表情
        skip_patterns = [
            "/icon", "emoji", "smiley", "logo.", "avatar",
            "button", "/arrow", "dot.gif", "blank.gif",
            "/images/filetype/", "spacer.", "nophoto",
        ]
        lower_url = url.lower()
        if any(p in lower_url for p in skip_patterns):
            continue

        # 转为绝对URL
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = urllib.parse.urljoin(page_url, url)
        elif not url.startswith("http"):
            url = urllib.parse.urljoin(page_url, url)

        cleaned.add(url)

    return list(cleaned)


def get_filename_from_url(url, index):
    """从URL生成安全文件名"""
    parsed = urllib.parse.urlparse(url)
    path = urllib.parse.unquote(parsed.path)
    basename = os.path.basename(path)

    # 清理非法字符
    basename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', basename)

    if not basename or len(basename) < 3:
        ext = os.path.splitext(path)[1] or ".jpg"
        basename = f"image_{index:04d}{ext}"

    # 确保有扩展名
    _, ext = os.path.splitext(basename)
    if not ext or ext.lower() not in IMAGE_EXTENSIONS:
        basename += ".jpg"

    # 截断过长文件名
    if len(basename) > 200:
        name, ext = os.path.splitext(basename)
        basename = name[:190] + ext

    return basename


# ============ 主流程 ============
def scrape_forum(fid, pages, download_dir):
    """主爬取流程"""
    os.makedirs(download_dir, exist_ok=True)
    progress_file = os.path.join(download_dir, ".progress.json")
    tracker = ProgressTracker(progress_file)
    session = create_session()

    print("=" * 60)
    print("  📷 论坛图片爬虫")
    print(f"  板块 FID : {fid}")
    print(f"  爬取页数 : {pages}")
    print(f"  保存目录 : {os.path.abspath(download_dir)}")
    print("=" * 60)

    # --- 第1步：收集所有帖子链接 ---
    all_threads = []
    print(f"\n[1/3] 扫描列表页，收集帖子链接 (共 {pages} 页)...")
    bar = ProgressBar(pages, prefix="  列表页扫描")

    for page in range(1, pages + 1):
        url = f"{BASE_URL}{BOARD_PATH}?fid={fid}&page={page}"
        html = fetch_page(session, url)
        if html:
            threads = parse_thread_list(html, BASE_URL)
            all_threads.extend(threads)
        else:
            print(f"\n  [!] 第 {page} 页获取失败，跳过")
        bar.update()
        if page < pages:
            time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))
    bar.finish()

    # 去重
    seen = set()
    unique_threads = []
    for t in all_threads:
        if t["id"] not in seen:
            seen.add(t["id"])
            unique_threads.append(t)
    all_threads = unique_threads

    print(f"  ✓ 共找到 {len(all_threads)} 个帖子")
    if not all_threads:
        print("  [!] 未找到任何帖子，请检查网络连接或URL是否正确")
        return

    # --- 第2步：逐帖提取图片URL ---
    print(f"\n[2/3] 进入帖子页面，提取图片链接...")
    skipped_count = sum(1 for t in all_threads if tracker.is_thread_done(t["id"]))
    to_process = len(all_threads) - skipped_count
    if skipped_count > 0:
        print(f"  (已跳过 {skipped_count} 个已完成的帖子)")

    bar = ProgressBar(len(all_threads), prefix="  帖子解析  ")
    total_images = 0
    thread_images = {}  # {thread_id: [urls]}

    for t in all_threads:
        tid = t["id"]

        if tracker.is_thread_done(tid):
            bar.update()
            continue

        html = fetch_page(session, t["url"])
        if html:
            imgs = extract_images_from_thread(html, t["url"])
            if imgs:
                thread_images[tid] = imgs
                total_images += len(imgs)
        bar.update()
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))
    bar.finish()

    print(f"  ✓ 共找到 {total_images} 张图片待下载")
    if total_images == 0:
        print("  没有新图片需要下载。")
        return

    # --- 第3步：下载图片 ---
    print(f"\n[3/3] 开始下载图片...")
    bar = ProgressBar(total_images, prefix="  图片下载  ")
    stats = {
        "ok": 0, "skipped": 0, "exists": 0,
        "failed": 0, "not_found": 0, "not_image": 0, "too_small": 0,
    }

    for tid, urls in thread_images.items():
        thread_dir = os.path.join(download_dir, f"thread_{tid}")
        os.makedirs(thread_dir, exist_ok=True)

        for idx, img_url in enumerate(urls, 1):
            filename = get_filename_from_url(img_url, idx)
            save_path = os.path.join(thread_dir, filename)

            # 文件名冲突时添加序号
            if os.path.exists(save_path):
                name, ext = os.path.splitext(filename)
                save_path = os.path.join(thread_dir, f"{name}_{idx:03d}{ext}")

            result = download_image(session, img_url, save_path, tracker)
            stats[result] = stats.get(result, 0) + 1
            bar.update()

            # 图片下载间隔略短
            time.sleep(random.uniform(0.1, 0.3))

        tracker.mark_thread_done(tid)
    bar.finish()

    # --- 汇总统计 ---
    print()
    print("=" * 60)
    print("  ✅ 下载完成!")
    print(f"  新下载 : {stats['ok']} 张")
    print(f"  已跳过 : {stats['skipped']} 张 (断点续传)")
    print(f"  已存在 : {stats['exists']} 张")
    print(f"  失败   : {stats['failed']} 张")
    print(f"  404    : {stats['not_found']} 张")
    print(f"  非图片 : {stats['not_image']} 个")
    print(f"  过小   : {stats['too_small']} 个 (<100B, 可能是占位图)")
    print(f"  保存于 : {os.path.abspath(download_dir)}")
    print("=" * 60)


# ============ 入口 ============
def main():
    parser = argparse.ArgumentParser(
        description="论坛图片爬虫 - 爬取指定板块的帖子图片",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python forum_image_scraper.py                  # 默认爬取第1页
  python forum_image_scraper.py -p 5             # 爬取前5页
  python forum_image_scraper.py -p 3 -o ./imgs   # 爬取前3页，保存到 ./imgs
  python forum_image_scraper.py --fid 16 -p 10   # 指定板块，爬取前10页
        """,
    )
    parser.add_argument(
        "-p", "--pages", type=int, default=1,
        help="爬取的页数 (默认: 1)",
    )
    parser.add_argument(
        "-o", "--output", type=str, default=DOWNLOAD_DIR,
        help="保存目录 (默认: ./downloads)",
    )
    parser.add_argument(
        "--fid", type=str, default=DEFAULT_FID,
        help="板块ID (默认: 16)",
    )

    args = parser.parse_args()

    if args.pages < 1:
        print("[!] 页数必须 >= 1")
        sys.exit(1)

    try:
        scrape_forum(fid=args.fid, pages=args.pages, download_dir=args.output)
    except KeyboardInterrupt:
        print("\n\n[!] 用户中断 (Ctrl+C)，进度已保存。")
        print("    下次运行将自动跳过已完成的内容（断点续传）。")
        sys.exit(0)


if __name__ == "__main__":
    main()
