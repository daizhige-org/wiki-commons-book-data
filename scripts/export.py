#!/usr/bin/env python3
"""commons_books.sqlite → data/：可分享、可重建的 JSONL 快照。

    python3 scripts/export.py ../library_backup_project/data/commons_books.sqlite

匯出的是**正規化之後**的形狀,不是 harvest 的原始 jsonl：那邊 39 個來源的鍵名
各寫各的（`Title` / `title` / `byline`）、同一個 pageid 會出現在兩片裡（專屬來源
與補缺口的佔位來源各一份）。查詢站吃的是收斂過的那份,分享出去的也該是那份。

**衍生欄位一律不匯出**：`files.blob`、`books.blob`、兩個 fts5 表都是折疊與索引的
產物,由 `build_sqlite.py` 用當下的 OpenCC 重算。匯出它們只會讓快照挾帶一份
過期的折疊字典——而字典漂移的症狀是「有些書搜不到」,不報錯（見 docs/schema.md）。

檔案層按**來源館藏**分片。分片鍵是 `files.source_id` 解出來的來源,不是 harvest
的檔名,所以 `by_title_gap` 那種補漏批次會落回它各自真正的來源。單一館藏重新
收割時只有那一片變,git 歷史不會每次多一份 160 MB。
"""
import argparse
import gzip
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
import datetime

# files 的欄位順序。與 sqlite 的欄位同名,少了 source_id（換成來源名字串,
# 因為 id 每次重建都可能變）與 blob（衍生）。
FILE_COLUMNS = [
    "title", "author", "date", "publisher", "edition", "city", "language",
    "volume", "volumes", "subtitle", "editor", "translator", "printer",
    "wikidata", "description", "abstract", "note",
    "src_ref", "src_db", "src_dbid", "src_bookid", "src_volumeid", "src_catid",
]
BOOK_COLUMNS = ["title", "author", "date", "publisher", "edition"]
KANRIPO_COLUMNS = ["title", "dynasty", "author", "extent", "edition",
                   "part", "part_name", "class", "class_name",
                   "status", "author_agrees"]


def slug(name):
    """來源名 → 分片檔名。與 harvest 的命名同一套規則,但不截斷。

    截斷是 harvest 那邊的包袱（`…national_centr.jsonl.gz`）,分享出去的檔名
    沒有理由讓人猜是哪個館藏。全名照樣不會撞,manifest 裡也有對照。
    """
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "unnamed"


def jsonl_gz(path, records):
    """寫一片 jsonl.gz,回傳 (行數, 位元組數, sha256)。

    `mtime=0` 是為了可重現：同樣的資料要壓出同樣的位元組,否則每次匯出
    都是一次全檔改動,git 存不下第二次。
    """
    buf = io.BytesIO()
    n = 0
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as gz:
        with io.TextIOWrapper(gz, encoding="utf-8", newline="\n") as out:
            for rec in records:
                out.write(json.dumps(rec, ensure_ascii=False,
                                     separators=(",", ":")) + "\n")
                n += 1
    blob = buf.getvalue()
    with open(path, "wb") as f:
        f.write(blob)
    return n, len(blob), hashlib.sha256(blob).hexdigest()


def trim(rec):
    """丟掉空值。1,517,129 列 × 30 個欄位,絕大多數是 null。"""
    return {k: v for k, v in rec.items() if v not in (None, "", [], {})}


def file_records(con, source_id, source_name):
    """一個來源的檔案,附上分類。

    兩個游標各自按 pageid 排序後併流,而不是把 2,056,199 條關聯讀進 dict：
    這支要能在小機器上跑,而分類表比檔案表還長。
    """
    files = con.execute(
        f"SELECT pageid, file, size, mime, sha1, book, "
        f"{','.join(FILE_COLUMNS)}, extra FROM files "
        "WHERE source_id=? ORDER BY pageid", (source_id,))
    cats = con.execute(
        "SELECT fc.pageid, c.name, fc.is_book FROM file_category fc "
        "JOIN categories c ON c.id = fc.category_id "
        "JOIN files f ON f.pageid = fc.pageid "
        "WHERE f.source_id=? ORDER BY fc.pageid", (source_id,))

    pending = next(cats, None)
    for row in files:
        pageid = row["pageid"]
        book_cats, other_cats = [], []
        while pending is not None and pending[0] < pageid:
            pending = next(cats, None)          # 分類指向的檔案不在這一片
        while pending is not None and pending[0] == pageid:
            (book_cats if pending[2] else other_cats).append(pending[1])
            pending = next(cats, None)

        # `book` 是查詢站的聚合鍵（harvest 的 book_categories[0]）。
        # file_category 是集合,取回來沒有順序,所以把主分類固定放第一個,
        # 其餘排序——不然每次匯出的位元組都不一樣。
        book = row["book"]
        rest = sorted(c for c in book_cats if c != book)
        rec = {"pageid": pageid, "file": row["file"], "source": source_name,
               "size": row["size"], "mime": row["mime"], "sha1": row["sha1"],
               "book": book}
        rec.update({c: row[c] for c in FILE_COLUMNS})
        rec["book_categories"] = ([book] + rest) if book else rest
        rec["other_categories"] = sorted(other_cats)
        # extra 在庫裡是 JSON 字串,這裡還原成物件——快照是資料不是欄位傾印,
        # 讀的人不該再解一層。
        if row["extra"]:
            rec["extra"] = json.loads(row["extra"])
        yield trim(rec)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("db", help="commons_books.sqlite 的路徑")
    ap.add_argument("-o", "--out", default=None, help="輸出目錄(預設 <repo>/data)")
    args = ap.parse_args()

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = args.out or os.path.join(repo, "data")
    os.makedirs(os.path.join(out, "files"), exist_ok=True)

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    manifest = {
        "dataset": "wiki-commons-book-data",
        "schema_version": 1,
        "exported": datetime.datetime.now(datetime.timezone.utc)
                            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_db": {
            "name": os.path.basename(args.db),
            "mtime": datetime.datetime.fromtimestamp(
                os.path.getmtime(args.db), datetime.timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "bytes": os.path.getsize(args.db),
        },
        "counts": {}, "files": {},
    }

    def record(rel, n, size, digest):
        manifest["files"][rel] = {"rows": n, "bytes": size, "sha256": digest}
        print(f"  {rel:<62} {n:>9,} 列  {size/1048576:>7.1f} MB", file=sys.stderr)

    # ── sources：不壓縮,39 行,要能直接在網頁上看
    sources = [dict(r) for r in con.execute("SELECT id, name FROM sources ORDER BY name")]
    for s in sources:
        s["shard"] = f"files/{slug(s['name'])}.jsonl.gz"
        del s["id"]                    # id 每次重建都會變,不是可依賴的識別碼
    path = os.path.join(out, "sources.jsonl")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for s in sources:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    blob = open(path, "rb").read()
    record("sources.jsonl", len(sources), len(blob),
           hashlib.sha256(blob).hexdigest())

    # ── books
    n, size, digest = jsonl_gz(os.path.join(out, "books.jsonl.gz"), (
        trim({"name": r["name"], **{c: r[c] for c in BOOK_COLUMNS},
              "source": r["source"], "files": r["files"], "bytes": r["bytes"]})
        for r in con.execute(
            f"SELECT b.name, {','.join('b.' + c for c in BOOK_COLUMNS)}, "
            "s.name AS source, b.files, b.bytes FROM books b "
            "LEFT JOIN sources s ON s.id = b.source_id ORDER BY b.name")))
    record("books.jsonl.gz", n, size, digest)
    manifest["counts"]["books"] = n

    # ── kanripo：外部對照（漢籍リポジトリ ↔ Commons 分類）
    krbooks = {}
    for kr_id, name in con.execute("SELECT kr_id, name FROM kanripo_book"):
        krbooks.setdefault(kr_id, []).append(name)
    n, size, digest = jsonl_gz(os.path.join(out, "kanripo.jsonl.gz"), (
        trim({"kr_id": r["kr_id"], **{c: r[c] for c in KANRIPO_COLUMNS},
              "books": sorted(krbooks.get(r["kr_id"], []))})
        for r in con.execute(
            f"SELECT kr_id, {','.join(KANRIPO_COLUMNS)} FROM kanripo "
            "ORDER BY kr_id")))
    record("kanripo.jsonl.gz", n, size, digest)
    manifest["counts"]["kanripo"] = n

    # ── files：一個來源一片
    total = 0
    for sid, name in con.execute("SELECT id, name FROM sources ORDER BY name"):
        rel = f"files/{slug(name)}.jsonl.gz"
        n, size, digest = jsonl_gz(os.path.join(out, rel),
                                   file_records(con, sid, name))
        record(rel, n, size, digest)
        total += n
    manifest["counts"]["files"] = total
    manifest["counts"]["sources"] = len(sources)

    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")

    grand = sum(v["bytes"] for v in manifest["files"].values())
    print(f"\n→ {out}  {grand/1048576:.0f} MB  "
          f"({total:,} 檔 / {manifest['counts']['books']:,} 部書 / "
          f"{len(sources)} 個來源)", file=sys.stderr)


if __name__ == "__main__":
    main()
