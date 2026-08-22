# wiki-commons-book-data

[Wikimedia Commons](https://commons.wikimedia.org/wiki/Commons:Library_back_up_project)
上中文古籍與民國文獻掃描件的**書目後設資料快照**,JSON Lines 格式。

**1,517,129 個掃描檔案 / 238,100 部書 / 39 個來源館藏**,共 41.3 TiB 的掃描件。
壓縮後 117 MB。

這裡放的是**後設資料,不是掃描件**——書名、撰者、年代、刊刻者、檔案 sha1、
所屬分類、各館藏的著錄欄位。掃描件本身在 Commons 上,連結由 `pageid` 與 `file`
算得出來。

## 快速上手

```bash
python3 scripts/verify.py          # 驗一遍拿到的是完整的一份
```

```python
import gzip, json

for line in gzip.open("data/files/books_in_the_zhejiang_library.jsonl.gz",
                      "rt", encoding="utf-8"):
    rec = json.loads(line)
    print(rec["file"], rec.get("author"))
```

**空值一律省略**,所以用 `rec.get("author")` 而不是 `rec["author"]`——
欄位不在,意思就是那筆沒有這個值。

回連 Commons：

```python
import urllib.parse
"https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(rec["file"])
"https://commons.wikimedia.org/wiki/" + urllib.parse.quote("Category:" + rec["book"])
```

## 內容

| 路徑 | 內容 | 大小 |
|---|---|---|
| `data/sources.jsonl` | 39 個來源館藏,以及各自的分片檔名 | 4 KB |
| `data/files/<來源>.jsonl.gz` | 檔案層,1,517,129 筆,一個來源一片 | 107 MB |
| `data/books.jsonl.gz` | 書籍層,238,100 筆(依書籍分類聚合) | 9.4 MB |
| `data/kanripo.jsonl.gz` | 10,141 筆漢籍リポジトリ書目對照 | 0.2 MB |
| `data/manifest.json` | 逐檔的行數 / 位元組 / sha256 | — |

欄位語意、不變量、各層怎麼對起來,全部寫在 [docs/schema.md](docs/schema.md)。

**檔案層按來源館藏分片**,不是按大小切。單一館藏重新收割時只有那一片變,
git 歷史不會每次多一份 117 MB。最大的一片 14 MB。

## 這份快照裡有什麼、沒有什麼

* **一個欄位都不丟。** sha1、全部分類、浙江圖的 `zj_attrs`、雲南中醫藥的
  `yn_attrs`、卷級篇目 `parts` 都在。正規欄位認不出來的鍵落到 `extra`。
* **書目欄位是原字串。** 刻本卷端印什麼就存什麼(`[萬曆]蘭谿縣志`),
  沒有正規化、沒有繁簡轉換。
* **不含任何衍生欄位。** 上游查詢站有一份 OpenCC 折疊過的檢索字串與 trigram
  索引,這裡一概不收——那是索引不是資料,而且挾帶一份過期的折疊字典只會讓
  下游安靜地搜不到東西。要做繁簡異體等價比對見最後一節。
* **一個檔案可以屬於多部書。** 71,372 個檔案掛在一個以上的書籍分類底下
  (叢書子目、合刻本)。只看 `book` 會漏掉,要完整就走 `book_categories`。
* **書籍層是聚合出來的,不是權威。** 代表性書名取各卷冊的 `MIN(...)`,叢書
  挑出來的那個未必有代表性。要精確就自己從檔案層按 `book` 重算(取眾數)。
  `files` 與 `bytes` 是實數,可以信。
* **只到掃描檔案這一層,沒有全文。** Commons 上這批書大多沒有文字層。

## 來源與重建

快照從 `library_backup_project` 的 `data/commons_books.sqlite` 匯出——那個庫由
Commons API 收割而來,是查詢站實際服務的那一份。匯出的是**正規化之後**的形狀,
不是收割的原始 jsonl：那邊 39 個來源的鍵名各寫各的(`Title` / `title` /
`byline`)、同一個 `pageid` 會出現在兩片裡(專屬來源與補漏批次各一份),
這裡都已經收斂與去重。

```bash
python3 scripts/export.py ../library_backup_project/data/commons_books.sqlite
```

匯出是**可重現的**：gzip 的 mtime 固定為 0、分類排序固定,同樣的輸入壓出
同樣的位元組。否則每次重跑都是一次全檔改動,git 存不下第二次。

`source_db.mtime` 記著這份快照對應的資料庫時間點。Commons 一直在長,要最新的
資料請走 [Commons API](https://commons.wikimedia.org/w/api.php) 或
[Wikimedia dumps](https://dumps.wikimedia.org/commonswiki/)。

## 相關

* [booksearch.toolforge.org](https://booksearch.toolforge.org/) — 拿這批資料做的
  檢索站,支援繁簡異體等價。源碼在
  [gitlab.wikimedia.org/toolforge-repos/booksearch](https://gitlab.wikimedia.org/toolforge-repos/booksearch)。
  它的書籍層 schema 與本快照的 `books.jsonl.gz` 是同一個形狀,多的是兩個折疊過的
  檢索欄位。
* 繁簡異體等價比對用 [OpenCC](https://github.com/BYVoid/OpenCC),折法是
  `jp2t` → `t2s`,而且**建索引與查詢必須用同一版字典**——字典漂移的症狀是
  「有些書搜不到」,不報錯。用官方 `opencc` 實作,別用
  `opencc-python-reimplemented`(它沒有 `jp2t`,遇到不認得的 config 是靜默 no-op)。
