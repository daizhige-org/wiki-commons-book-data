#!/usr/bin/env python3
"""驗一份快照：manifest 對不對得上磁碟上的檔案。

    python3 scripts/verify.py

分享出去的資料集,最容易出的事故不是格式錯,是**悄悄少了一片**——git-lfs 沒拉、
clone 中斷、某片重壓過。這幾項都不會讓 json.loads 失敗,只會讓下游少幾萬筆而
毫無徵兆。所以逐檔比對 sha256 與行數,任何一項對不上就非 0 離開。

不檢查內容品質(那是 harvest 端的事),只檢查「你拿到的和我匯出的是同一份」。
"""
import gzip
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def main():
    with open(os.path.join(DATA, "manifest.json"), encoding="utf-8") as f:
        man = json.load(f)

    bad = 0
    total_rows = 0
    for rel, want in man["files"].items():
        path = os.path.join(DATA, rel)
        if not os.path.exists(path):
            print(f"缺檔  {rel}")
            bad += 1
            continue
        blob = open(path, "rb").read()
        got_sha = hashlib.sha256(blob).hexdigest()
        opener = gzip.open if rel.endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8") as f:
            got_rows = sum(1 for _ in f)
        total_rows += got_rows
        if len(blob) != want["bytes"] or got_sha != want["sha256"]:
            print(f"位元組不符  {rel}\n  manifest {want['sha256'][:16]}… "
                  f"{want['bytes']:,} B\n  磁碟     {got_sha[:16]}… {len(blob):,} B")
            bad += 1
        elif got_rows != want["rows"]:
            print(f"行數不符  {rel}: {got_rows:,} ≠ {want['rows']:,}")
            bad += 1

    # 分片行數的總和要等於宣稱的檔案總數。單片都對、加起來不對,
    # 代表 manifest 漏列了一片——只比對逐檔 sha 抓不到這種漏。
    shards = sum(v["rows"] for k, v in man["files"].items()
                 if k.startswith("files/"))
    if shards != man["counts"]["files"]:
        print(f"分片行數合計 {shards:,} ≠ counts.files {man['counts']['files']:,}")
        bad += 1

    c = man["counts"]
    print(f"\n{len(man['files'])} 個檔案,{total_rows:,} 列 "
          f"({c['files']:,} 檔 / {c['books']:,} 部書 / {c['sources']} 個來源 / "
          f"{c['kanripo']:,} 筆漢籍對照)")
    if bad:
        print(f"→ {bad} 項不符")
        return 1
    print("→ 全部相符")
    return 0


if __name__ == "__main__":
    sys.exit(main())
