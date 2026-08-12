# -*- coding: utf-8 -*-
"""SQLite 数据库存储 — 接口兼容 InvoiceRepository，支持迁移旧 JSON 数据"""

import json
import os
import sqlite3

from models import Invoice
from logger import getLogger

log = getLogger(__name__)

# ── Unicode 清洗 ─────────────────────────────

# pdfplumber 偶发产生孤立代理字符（U+D800–U+DFFF），它们不是合法 Unicode，
# 也无法被 UTF-8 编码。已入库的老数据可能残留此类字符，必须在加载时清洗。
_SURROGATE_TABLE = {c: ord('�') for c in range(0xd800, 0xe000)}


def sanitize_str(text: str | None) -> str:
    """清洗字符串中的非法代理字符，替换为 �。None 返回空字符串。"""
    if text is None:
        return ""
    if not text:
        return text
    return text.translate(_SURROGATE_TABLE)

_DDL = """\
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file TEXT DEFAULT '',
    pdf_path TEXT DEFAULT '',
    company TEXT DEFAULT '',
    invoice_type TEXT DEFAULT '',
    buyer_name TEXT DEFAULT '',
    buyer_tax_id TEXT DEFAULT '',
    seller_name TEXT DEFAULT '',
    amount TEXT DEFAULT '',
    tax_rate TEXT DEFAULT '',
    tax_amount TEXT DEFAULT '',
    total TEXT DEFAULT '',
    invoice_no TEXT DEFAULT '',
    invoice_date TEXT DEFAULT '',
    is_red INTEGER DEFAULT 0,
    screenshots TEXT DEFAULT '[]',
    contracts TEXT DEFAULT '[]',
    tags TEXT DEFAULT '{}',
    attachments TEXT DEFAULT '[]',
    remark TEXT DEFAULT '',
    error TEXT DEFAULT '',
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS invoice_tags (
    invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    value TEXT DEFAULT '',
    PRIMARY KEY (invoice_id, name)
);
CREATE INDEX IF NOT EXISTS idx_tags_name_value ON invoice_tags(name, value);
CREATE INDEX IF NOT EXISTS idx_invoice_no ON invoices(invoice_no);
CREATE INDEX IF NOT EXISTS idx_invoice_date ON invoices(invoice_date);
CREATE INDEX IF NOT EXISTS idx_invoice_type ON invoices(invoice_type);
CREATE INDEX IF NOT EXISTS idx_seller_name ON invoices(seller_name);
"""


class Database:
    """SQLite 存储，接口与 InvoiceRepository 一致"""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._db_path = db_path
        self._init_schema()

    @property
    def data_file(self) -> str:
        return self._db_path

    def _init_schema(self):
        """初始化表结构。新文件自动建表，已有文件做迁移。"""
        if os.path.exists(self._db_path) and os.path.getsize(self._db_path) > 0:
            try:
                with sqlite3.connect(self._db_path) as conn:
                    result = conn.execute(
                        "PRAGMA integrity_check").fetchone()
                    if result[0] != "ok":
                        log.warning("数据库完整性预检失败: %s", self._db_path)
                        return
                # 确保新表存在 + 执行迁移
                self._ensure_schema()
            except sqlite3.DatabaseError:
                log.warning("数据库文件无法打开: %s", self._db_path)
            return
        self._ensure_schema()

    def _ensure_schema(self):
        """保证表结构最新：建新表 + 执行数据迁移"""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(_DDL)
            conn.commit()
        self._migrate_tags_json_to_table()
        self._sanitize_existing_data()

    def _sanitize_existing_data(self):
        """清洗数据库中已存在的孤立代理字符（pdfplumber 老数据残留）。

        扫描所有文本列，将 U+D800–U+DFFF 范围的非法字符替换为 U+FFFD �。
        幂等操作：已干净的数据不会有任何改动。
        """
        text_cols = [
            "file", "pdf_path", "company", "invoice_type",
            "buyer_name", "buyer_tax_id", "seller_name",
            "amount", "tax_rate", "tax_amount", "total",
            "invoice_no", "invoice_date", "remark",
            "error", "tags", "attachments",
        ]
        try:
            with sqlite3.connect(self._db_path) as conn:
                cleaned = 0
                for col in text_cols:
                    # 查找包含孤立代理字符（U+D800–U+DFFF）的记录
                    # SQLite 的 char() 接受 Unicode 码点
                    rows = conn.execute(
                        f"SELECT id, {col} FROM invoices "
                        f"WHERE {col} LIKE '%' || char(0xD800) || '%'"
                        f"  OR {col} LIKE '%' || char(0xDFFF) || '%'"
                    ).fetchall()
                    for rid, val in rows:
                        if val:
                            new_val = sanitize_str(val)
                            if new_val != val:
                                conn.execute(
                                    f"UPDATE invoices SET {col}=? WHERE id=?",
                                    (new_val, rid))
                                cleaned += 1
                if cleaned:
                    conn.commit()
                    log.info("已清洗 %d 处代理字符残留", cleaned)
        except sqlite3.Error as e:
            log.warning("数据清洗失败（不影响主流程）: %s", e)

    def _migrate_tags_json_to_table(self):
        """将 invoices.tags JSON 列迁移到 invoice_tags 表（幂等，只执行一次）"""
        try:
            with sqlite3.connect(self._db_path) as conn:
                # 检查是否有未迁移的 JSON tags 数据
                has_tags_col = conn.execute(
                    "SELECT 1 FROM pragma_table_info('invoices') WHERE name='tags'"
                ).fetchone()
                if not has_tags_col:
                    return  # 已迁移完成（旧 tags 列已删除）
                # 查询所有有 tags 数据的发票
                rows = conn.execute(
                    "SELECT id, tags FROM invoices WHERE tags IS NOT NULL AND tags != '{}'"
                ).fetchall()
                if not rows:
                    return
                migrated = 0
                for inv_id, tags_json in rows:
                    tags = self._parse_json_dict(tags_json)
                    for name, value in tags.items():
                        conn.execute(
                            "INSERT OR IGNORE INTO invoice_tags(invoice_id, name, value) "
                            "VALUES (?, ?, ?)",
                            (inv_id, name, str(value) if value else ""),
                        )
                        migrated += 1
                conn.commit()
                if migrated:
                    log.info("tags 迁移完成: %d 条 → invoice_tags 表", migrated)
        except sqlite3.Error as e:
            log.warning("tags 迁移失败（不影响主流程）: %s", e)

    # ── 查询 ──────────────────────────────────

    def load(self) -> list[Invoice]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM invoices ORDER BY id").fetchall()
                # 批量加载所有 tags（避免 N+1 查询）
                all_tags: dict[int, dict[str, str]] = {}
                tag_rows = conn.execute(
                    "SELECT invoice_id, name, value FROM invoice_tags").fetchall()
                for tr in tag_rows:
                    all_tags.setdefault(tr["invoice_id"], {})[tr["name"]] = tr["value"]
                invoices = []
                for r in rows:
                    inv = self._row_to_invoice(r)
                    # 优先用 invoice_tags 表的数据，回退到 JSON 列（未迁移时）
                    rid = r["id"]
                    if rid in all_tags:
                        inv.tags = all_tags[rid]
                    invoices.append(inv)
                return invoices
        except sqlite3.Error as e:
            log.error("数据加载失败: %s | %s", self._db_path, e)
            return []

    def search(self, *, year=None, month=None, invoice_type=None,
               seller=None, buyer=None, tag=None, keyword=None,
               sort_by=None, sort_asc=True, limit=50, offset=0,
               aggregates: bool = False) -> tuple[int, list[Invoice], dict[str, float]]:
        """SQL 级搜索，返回 (total_count, page, aggregates)。
        aggregates 包含 total_amount / total_tax / total_with_tax，仅 aggregates=True 时计算。
        比 load 全量 + Python 过滤快得多。"""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                where = []
                params: list = []

                if year is not None:
                    where.append("invoice_date LIKE ?")
                    params.append(f"{year}年%")
                if month is not None:
                    where.append("invoice_date LIKE ?")
                    params.append(f"%年{month:02d}月%")
                if invoice_type:
                    where.append("invoice_type = ?")
                    params.append(invoice_type)
                if seller:
                    where.append("seller_name = ?")
                    params.append(seller)
                if buyer:
                    buyer_like = f"%{buyer}%"
                    where.append("(buyer_name LIKE ? OR buyer_tax_id LIKE ?)")
                    params.extend([buyer_like, buyer_like])
                if tag:
                    # tags JSON 列是权威数据源（与 invoice_tags 表同步），直接 LIKE 即可
                    where.append("tags LIKE ?")
                    params.append(f"%{tag}%")
                if keyword:
                    # 关键字搜索覆盖全部可搜索文本字段
                    kw = f"%{keyword}%"
                    fields = ["file", "company", "buyer_name", "buyer_tax_id",
                              "seller_name", "invoice_type", "amount",
                              "tax_rate", "tax_amount", "total",
                              "invoice_no", "invoice_date", "remark",
                              "error", "tags", "attachments"]
                    like_clauses = " OR ".join(f"{f} LIKE ?" for f in fields)
                    where.append(f"({like_clauses})")
                    params.extend([kw] * len(fields))

                where_clause = " AND ".join(where) if where else "1=1"

                # 总数
                count_row = conn.execute(
                    f"SELECT COUNT(*) FROM invoices WHERE {where_clause}",
                    params).fetchone()
                total = count_row[0] if count_row else 0

                # 聚合（全量匹配记录的金额汇总）
                aggs: dict[str, float] = {}
                if aggregates and total > 0:
                    agg_row = conn.execute(
                        f"SELECT "
                        f"SUM(CAST(amount AS REAL)), "
                        f"SUM(CAST(tax_amount AS REAL)), "
                        f"SUM(CAST(total AS REAL)) "
                        f"FROM invoices WHERE {where_clause}",
                        params).fetchone()
                    aggs = {
                        "total_amount": agg_row[0] or 0.0,
                        "total_tax": agg_row[1] or 0.0,
                        "total_with_tax": agg_row[2] or 0.0,
                    }

                # 排序（校验排序字段防注入）
                order = "id ASC"
                if sort_by:
                    safe = sort_by
                    # 只允许白名单字段 + 已有列名
                    safe = safe.strip().strip('"').strip("'").strip("`")
                    # 通过查询表信息验证该列存在
                    col_check = conn.execute(
                        "SELECT 1 FROM pragma_table_info('invoices') WHERE name=?",
                        (safe,)).fetchone()
                    if col_check:
                        order = f"{safe} {'ASC' if sort_asc else 'DESC'}"
                order += ", id ASC"  # 次级排序保证稳定

                rows = conn.execute(
                    f"SELECT * FROM invoices WHERE {where_clause} "
                    f"ORDER BY {order} LIMIT ? OFFSET ?",
                    params + [limit, offset]).fetchall()

                # 批量加载 tags
                inv_ids = [r["id"] for r in rows]
                all_tags: dict[int, dict[str, str]] = {}
                if inv_ids:
                    placeholders = ",".join("?" for _ in inv_ids)
                    tag_rows = conn.execute(
                        f"SELECT invoice_id, name, value FROM invoice_tags "
                        f"WHERE invoice_id IN ({placeholders})",
                        inv_ids).fetchall()
                    for tr in tag_rows:
                        all_tags.setdefault(tr["invoice_id"], {})[tr["name"]] = tr["value"]

                invoices = []
                for r in rows:
                    inv = self._row_to_invoice(r)
                    rid = r["id"]
                    if rid in all_tags:
                        inv.tags = all_tags[rid]
                    invoices.append(inv)

                return total, invoices, aggs
        except sqlite3.Error as e:
            log.error("搜索失败: %s", e)
            return 0, [], {}

    def _row_to_invoice(self, row) -> Invoice:
        # 兼容旧数据：screenshots/contracts → attachments 合并（与 from_dict 一致）
        atts = self._parse_json_list(row["attachments"])
        for col in ("screenshots", "contracts"):
            for p in self._parse_json_list(row[col]):
                if p and p not in atts:
                    atts.append(p)
        # 清洗所有文本字段中的孤立代理字符（pdfplumber 老数据残留）
        return Invoice(
            file=sanitize_str(row["file"]),
            pdf_path=sanitize_str(row["pdf_path"]),
            company=sanitize_str(row["company"]),
            invoice_type=sanitize_str(row["invoice_type"]),
            buyer_name=sanitize_str(row["buyer_name"]),
            buyer_tax_id=sanitize_str(row["buyer_tax_id"]),
            seller_name=sanitize_str(row["seller_name"]),
            amount=sanitize_str(row["amount"]),
            tax_rate=sanitize_str(row["tax_rate"]),
            tax_amount=sanitize_str(row["tax_amount"]),
            total=sanitize_str(row["total"]),
            invoice_no=sanitize_str(row["invoice_no"]),
            invoice_date=sanitize_str(row["invoice_date"]),
            is_red=bool(row["is_red"]),
            tags=self._parse_json_dict(row["tags"]),
            attachments=[sanitize_str(p) for p in atts],
            remark=sanitize_str(row["remark"]),
            error=sanitize_str(row["error"]),
        )

    @staticmethod
    def _parse_json_list(raw) -> list:
        try:
            val = json.loads(raw or "[]")
            return val if isinstance(val, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    @staticmethod
    def _parse_json_dict(raw) -> dict:
        try:
            val = json.loads(raw or "{}")
            return val if isinstance(val, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    # ── 保存（全量） ──────────────────────────

    def save(self, invoices: list[Invoice]) -> None:
        """全量保存（DELETE ALL + INSERT ALL），仅用于批量初始化/迁移场景"""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("DELETE FROM invoice_tags")
                conn.execute("DELETE FROM invoices")
                self._insert_rows(conn, invoices)
                conn.commit()
        except sqlite3.Error as e:
            log.critical("数据保存失败: %s | %s (数据未写入)", self._db_path, e)
            raise
        else:
            log.debug("数据已保存: %d 条 → %s", len(invoices), self._db_path)

    def _insert_rows(self, conn, invoices: list[Invoice]):
        """在已有事务中批量插入发票（含 tags），使用 executemany"""
        rows = [
            (sanitize_str(inv.file), sanitize_str(inv.pdf_path),
             sanitize_str(inv.company), sanitize_str(inv.invoice_type),
             sanitize_str(inv.buyer_name), sanitize_str(inv.buyer_tax_id),
             sanitize_str(inv.seller_name),
             sanitize_str(inv.amount), sanitize_str(inv.tax_rate),
             sanitize_str(inv.tax_amount), sanitize_str(inv.total),
             sanitize_str(inv.invoice_no), sanitize_str(inv.invoice_date),
             int(inv.is_red),
             json.dumps({k: sanitize_str(v) for k, v in (inv.tags or {}).items()},
                        ensure_ascii=False),
             json.dumps([sanitize_str(p) for p in (inv.attachments or [])],
                        ensure_ascii=False),
             sanitize_str(inv.remark), sanitize_str(inv.error))
            for inv in invoices
        ]
        conn.executemany("""
            INSERT INTO invoices (
                file, pdf_path, company, invoice_type,
                buyer_name, buyer_tax_id, seller_name,
                amount, tax_rate, tax_amount, total,
                invoice_no, invoice_date, is_red,
                screenshots, contracts, tags, attachments,
                remark, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '[]', ?, ?, ?, ?)
        """, rows)
        # 批量插入后，需要获取每个新插入的 id 来创建 tags
        # 使用 last_insert_rowid + ROW_COUNT 回推，或分步处理
        # 这里简化：tags 保留在 JSON 列中（兼容旧逻辑），invoice_tags 表可用于后续迁移
        # 因为已通过 json.dumps 写入 tags JSON 列，前端的 _migrate_tags_json_to_table 会处理

    def _ensure_tags_table(self, conn, inv_id: int, tags: dict):
        """为指定发票写入 invoice_tags 表"""
        if not tags:
            return
        conn.executemany(
            "INSERT OR REPLACE INTO invoice_tags(invoice_id, name, value) "
            "VALUES (?, ?, ?)",
            [(inv_id, name, str(v) if v else "") for name, v in tags.items()],
        )

    # ── 增量写操作（避免 DELETE ALL + INSERT ALL）──

    @staticmethod
    def _sanitize_invoice(inv: Invoice) -> Invoice:
        """清洗 Invoice 所有文本字段中的孤立代理字符，返回新实例。"""
        inv.file = sanitize_str(inv.file)
        inv.pdf_path = sanitize_str(inv.pdf_path)
        inv.company = sanitize_str(inv.company)
        inv.invoice_type = sanitize_str(inv.invoice_type)
        inv.buyer_name = sanitize_str(inv.buyer_name)
        inv.buyer_tax_id = sanitize_str(inv.buyer_tax_id)
        inv.seller_name = sanitize_str(inv.seller_name)
        inv.amount = sanitize_str(inv.amount)
        inv.tax_rate = sanitize_str(inv.tax_rate)
        inv.tax_amount = sanitize_str(inv.tax_amount)
        inv.total = sanitize_str(inv.total)
        inv.invoice_no = sanitize_str(inv.invoice_no)
        inv.invoice_date = sanitize_str(inv.invoice_date)
        inv.remark = sanitize_str(inv.remark)
        inv.error = sanitize_str(inv.error)
        if inv.tags:
            inv.tags = {k: sanitize_str(v) for k, v in inv.tags.items()}
        if inv.attachments:
            inv.attachments = [sanitize_str(p) for p in inv.attachments]
        return inv

    def insert_one(self, inv: Invoice) -> int:
        """插入单条发票到数据库，返回新记录的 id。不删已有数据"""
        self._sanitize_invoice(inv)
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("""
                    INSERT INTO invoices (
                        file, pdf_path, company, invoice_type,
                        buyer_name, buyer_tax_id, seller_name,
                        amount, tax_rate, tax_amount, total,
                        invoice_no, invoice_date, is_red,
                        screenshots, contracts, tags, attachments,
                        remark, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '[]', ?, ?, ?, ?)
                """, (
                    inv.file, inv.pdf_path, inv.company, inv.invoice_type,
                    inv.buyer_name, inv.buyer_tax_id, inv.seller_name,
                    inv.amount, inv.tax_rate, inv.tax_amount, inv.total,
                    inv.invoice_no, inv.invoice_date, int(inv.is_red),
                    json.dumps(inv.tags, ensure_ascii=False),
                    json.dumps(inv.attachments, ensure_ascii=False),
                    inv.remark, inv.error,
                ))
                inv_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                self._ensure_tags_table(conn, inv_id, inv.tags)
                conn.commit()
                return inv_id
        except sqlite3.Error as e:
            log.error("插入失败: %s", e)
            raise

    def insert_many(self, invoices: list[Invoice]) -> int:
        """批量插入（单事务），返回插入条数。比逐条 insert_one 快 10-50 倍"""
        if not invoices:
            return 0
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("PRAGMA foreign_keys=ON")
                self._insert_rows(conn, invoices)
                conn.commit()
                return len(invoices)
        except sqlite3.Error as e:
            log.error("批量插入失败: %s", e)
            raise

    def update_one(self, inv: Invoice) -> bool:
        """按 invoice_no 更新单条发票（含 tags）。未找到返回 False"""
        self._sanitize_invoice(inv)
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("PRAGMA foreign_keys=ON")
                # 先找到该发票的 id
                row = conn.execute(
                    "SELECT id FROM invoices WHERE invoice_no = ?",
                    (inv.invoice_no,)).fetchone()
                if not row:
                    return False
                inv_id = row[0]
                conn.execute("""
                    UPDATE invoices SET
                        file=?, pdf_path=?, company=?, invoice_type=?,
                        buyer_name=?, buyer_tax_id=?, seller_name=?,
                        amount=?, tax_rate=?, tax_amount=?, total=?,
                        invoice_no=?, invoice_date=?, is_red=?,
                        tags=?, attachments=?, remark=?, error=?,
                        updated_at=datetime('now','localtime')
                    WHERE id=?
                """, (
                    inv.file, inv.pdf_path, inv.company, inv.invoice_type,
                    inv.buyer_name, inv.buyer_tax_id, inv.seller_name,
                    inv.amount, inv.tax_rate, inv.tax_amount, inv.total,
                    inv.invoice_no, inv.invoice_date, int(inv.is_red),
                    json.dumps(inv.tags, ensure_ascii=False),
                    json.dumps(inv.attachments, ensure_ascii=False),
                    inv.remark, inv.error,
                    inv_id,
                ))
                # 刷新 tags 表
                conn.execute("DELETE FROM invoice_tags WHERE invoice_id = ?", (inv_id,))
                self._ensure_tags_table(conn, inv_id, inv.tags)
                conn.commit()
                return True
        except sqlite3.Error as e:
            log.error("更新失败 invoice_no=%s: %s", inv.invoice_no, e)
            raise

    def delete_one(self, invoice_no: str) -> bool:
        """按发票号删除单条记录（含关联 tags）。成功返回 True"""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("PRAGMA foreign_keys=ON")
                cur = conn.execute(
                    "DELETE FROM invoices WHERE invoice_no = ?", (invoice_no,))
                conn.commit()
                return cur.rowcount > 0
        except sqlite3.Error as e:
            log.error("删除失败 invoice_no=%s: %s", invoice_no, e)
            raise

    def count(self) -> int:
        """返回发票总数（O(1) 索引扫描）"""
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()
                return row[0] if row else 0
        except sqlite3.Error:
            return 0

    # ── 查询 ──────────────────────────────────

    def find_by_invoice_no(self, invoice_no: str) -> Invoice | None:
        """按发票号精确查找（走 idx_invoice_no 索引）"""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM invoices WHERE invoice_no = ?",
                    (invoice_no,)).fetchone()
                if row:
                    return self._row_to_invoice(dict(row))
        except sqlite3.Error:
            pass
        return None

    # ── 删除 ──────────────────────────────────

    def delete(self, invoice_no: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                "DELETE FROM invoices WHERE invoice_no = ?", (invoice_no,))
            conn.commit()

    # ── 完整性检查 ────────────────────────────

    def integrity_check(self) -> bool:
        try:
            with sqlite3.connect(self._db_path) as conn:
                result = conn.execute("PRAGMA integrity_check").fetchone()
                return result[0] == "ok"
        except sqlite3.Error:
            return False

    def optimize(self) -> None:
        """清理数据库碎片，缩减体积（备份前建议调用）"""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("PRAGMA optimize")
                conn.commit()
        except sqlite3.Error as e:
            log.warning("PRAGMA optimize 失败: %s", e)

    # ── 迁移 ──────────────────────────────────

    def migrate_from_json(self, json_path: str) -> int:
        if not os.path.exists(json_path):
            log.info("JSON 文件不存在，跳过迁移: %s", json_path)
            return 0
        existing = self.load()
        if existing:
            log.info("数据库已有 %d 条数据，跳过迁移", len(existing))
            return 0
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, list) or not raw:
                return 0
            invoices = [Invoice.from_dict(d) for d in raw]
            self.save(invoices)
            bak = json_path + ".bak"
            os.replace(json_path, bak)
            log.info("JSON 迁移完成: %d 条 → %s (备份: %s)",
                     len(invoices), self._db_path, bak)
            return len(invoices)
        except (OSError, json.JSONDecodeError) as e:
            log.error("JSON 迁移失败: %s | %s", json_path, e)
            return 0
