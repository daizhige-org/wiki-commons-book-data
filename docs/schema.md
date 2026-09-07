# 資料格式

每個檔案都是 **JSON Lines**：一行一筆 JSON 物件,UTF-8,`\n` 換行。除
`sources.jsonl` 外都用 gzip 壓縮。

**空值一律省略**。1,529,485 列 × 30 個欄位,絕大多數是 null——省掉 null、空字串、
空陣列讓快照少掉一半體積。所以讀的時候要用 `rec.get("author")`,不要
`rec["author"]`：欄位不在,意思就是那筆沒有這個值。

---

## `sources.jsonl`

41 個來源館藏／掃描計畫,不壓縮(小到可以直接在網頁上看)。

```json
{"name": "Books in the Zhejiang Library", "shard": "files/books_in_the_zhejiang_library.jsonl.gz"}
```

| 欄位 | 說明 |
|---|---|
| `name` | 來源名,與 Commons 上的分類名一致,也是 `files` 每筆的 `source` 值 |
| `shard` | 這個來源的檔案層分片路徑 |

**這裡沒有數字 id。** 上游 sqlite 的 `sources.id` 每次重建都可能變,不是可依賴
的識別碼,所以快照一律用名字當鍵。

`（來源不明）` 是個佔位來源,不是真的館藏：那 57,441 個檔案是
按書名補漏抓到的,沒掛在任何來源分類底下。

---

## `files/<來源>.jsonl.gz`

檔案層,1,529,485 筆,**一個來源一片**。一筆是 Commons 上的一個 `File:` 頁,
通常是一部書的一卷／一冊。

```json
{"pageid":148329734,
 "file":"ZJLib-65e6fe81969db848e322aa7a 杭州中華基督教青年會復會二周年紀念特刊.pdf",
 "source":"Books in the Zhejiang Library",
 "size":20597847,"mime":"application/pdf","sha1":"d390296a…",
 "book":"杭州中華基督教青年會復會二周年紀念特刊",
 "title":"杭州中華基督教青年會復會二周年紀念特刊",
 "author":"李萍仙總編輯","date":"1948","publisher":"杭州中華基督教青年會",
 "volume":"1","volumes":"1","src_bookid":"65e6fe81969db848e322aa7a",
 "book_categories":["杭州中華基督教青年會復會二周年紀念特刊"],
 "extra":{"zj_attrs":{…},"parts":[…]}}
```

### 檔案本身

| 欄位 | 說明 |
|---|---|
| `pageid` | Commons 的頁面 id。**全域唯一,跨分片也不重複**,是這份資料集的主鍵 |
| `file` | 檔名,不帶 `File:` 前綴。連結是 `https://commons.wikimedia.org/wiki/File:` + urlencode |
| `source` | 來源館藏,對到 `sources.jsonl` 的 `name` |
| `size` `mime` `sha1` | 檔案大小(位元組)、MIME、SHA-1。`sha1` 可以用來找 Commons 上的重複檔 |

### 書目欄位

全部是**原字串**——刻本卷端印什麼就是什麼(`[萬曆]蘭谿縣志`),沒有正規化、
沒有繁簡轉換。要做繁簡異體等價比對是下游的事(見 README 末節)。

`title` `author` `date` `publisher` `edition` `city` `language` `volume`
`volumes` `subtitle` `editor` `translator` `printer` `wikidata`
`description` `abstract` `note`

這些是**收斂過的欄位名**。上游 41 個來源各寫各的鍵名(`Title` / `title`、
`Author` / `byline`、`Publication date` / `date`),這裡統一成一套。

### 館藏索引

`src_ref` `src_db` `src_dbid` `src_bookid` `src_volumeid` `src_catid`
——回指原館藏系統的識別碼。`src_ref` 常是 Commons 的 `{{…link|…}}` 模板原文。

### 分類

| 欄位 | 說明 |
|---|---|
| `book` | **主要書籍分類,聚合鍵**。「這個檔案屬於哪部書」就看它,對到 `books.jsonl.gz` 的 `name` |
| `book_categories` | 這個檔案掛的所有書籍分類。**第一個恆等於 `book`**,其餘按字典序 |
| `other_categories` | 授權、來源、維護等非書籍分類,按字典序 |

**一個檔案可以屬於多部書**：31,199 個檔案掛在一個以上的書籍分類底下(叢書子目、
合刻本)。只認 `book` 會漏掉這些,要完整就走 `book_categories`。

分類名都**不帶 `Category:` 前綴**。

`book_categories` 恆含 `book`(而且在第一個),這是匯出時保證的。上游那邊
`book` 與分類關聯是兩條路來的——前者取收割到的 `book_categories[0]`,後者建自
`all_categories`,兩邊偶爾對不上,`book` 可能沒有對應的關聯列。
匯出時把 `book` 補回陣列開頭,所以每一筆自己是自洽的,不必再交叉比對。

目前每筆都有 `book`(也就有 `book_categories`);之前沒掛任何書籍分類的檔案
已經全部補上分類。

### `extra`

各來源自己的欄位,原樣保留,是**物件不是字串**(上游 sqlite 裡它是 JSON 字串,
匯出時已經解開)。目前有幾種鍵：

* `zj_attrs` — 浙江圖書館的著錄欄位(版本類型、索書號、尺寸、版本附註…)
* `yn_attrs` — 雲南中醫藥大學的著錄欄位(行款字數、開本、內容提要…)
* `parts` — 卷級篇目／子目清單
* `toc` — 目錄(HTML 片段,原樣保留,可能帶 `<br/>`、HTML 註解)
* `Series` — 韓國國立中央圖書館著錄裡的叢書名

這裡是「一個欄位都不丟」的兜底：正規欄位認不出來的鍵全部落到這裡。

---

## `books.jsonl.gz`

書籍層,236,505 筆。一筆是 Commons 上的一個**書籍分類頁**——Commons 上「一本書」
的載體就是那個分類,底下掛著該書所有卷冊的掃描件。

```json
{"name":"管窺緝要","title":"管窺緝要","author":"黄鼎纂","date":"清代（1644-1911）",
 "publisher":"清善成堂","source":"Scans from the China Academic Digital Associative Library",
 "files":48,"bytes":1069357284}
```

| 欄位 | 說明 |
|---|---|
| `name` | 分類頁名,不帶 `Category:` 前綴。主鍵,也是回連 Commons 的鍵 |
| `title` `author` `date` `publisher` `edition` | 代表性書目,原字串。可缺 |
| `source` | 代表性來源 |
| `files` `bytes` | 底下的檔案數與總位元組數 |

**這一層是聚合出來的,不是抄來的。** 上游的聚合方式是「取該書各卷冊的
`MIN(...)`」,叢書與多卷套書的卷端題名各不相同,挑出來的那個未必有代表性
(《民國叢書》19,218 冊)。要精確就自己從檔案層按 `book` 重算——取眾數比取
字典序最小合理得多。這一層放進來是為了方便,不是為了當權威。

`files` 與 `bytes` 是實數,可以信。

---

## `kanripo.jsonl.gz`

10,141 筆[漢籍リポジトリ](https://www.kanripo.org/)(Kanseki Repository)書目,
以及它們對到本資料集哪些書——古籍目錄學的外部對照,用來看 Commons 這批掃描件
覆蓋了四庫系統的哪些部分。

```json
{"kr_id":"KR1a0002","title":"子夏易傳","dynasty":"周","author":"卜商",
 "extent":"11 卷","edition":"四庫全書 文淵閣版, V7.1, p1",
 "part":"KR1","part_name":"經部","class":"KR1a","class_name":"易類",
 "status":"has_category","author_agrees":1,"books":["子夏易傳"]}
```

| 欄位 | 說明 |
|---|---|
| `kr_id` | 漢籍リポジトリ的書號,主鍵 |
| `title` `dynasty` `author` `extent` `edition` | KR 那邊的著錄 |
| `part` `part_name` `class` `class_name` | 四部分類(`KR1`／經部,`KR1a`／易類) |
| `status` | 比對結果的分桶,`has_category` 表示 Commons 上找得到對應的書 |
| `author_agrees` | 撰者對不對得上。**缺這個欄位表示 KR 沒記撰者,無從比對**,不是「對不上」 |
| `books` | 對到的 `books.jsonl.gz` 的 `name`,可能不只一個。可缺 |

`status` 是上游分析腳本的產物,語意隨那邊的分桶邏輯走,不是穩定契約。

---

## `manifest.json`

清單與校驗。`files` 底下逐檔記 `rows` / `bytes` / `sha256`,
`scripts/verify.py` 照它驗。`counts` 是總量,`source_db` 記這份快照是從哪個
資料庫、什麼時間點匯出的。
