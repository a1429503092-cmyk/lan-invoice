# -*- coding: utf-8 -*-
"""SQLite 数据库存储 — 接口兼容 InvoiceRepository，支持迁移旧 JSON 数据"""

import json
import os
import sqlite3

from models import Invoice
from logger import getLogger

log = getLogger(__name__)

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

    def _row_to_invoice(self, row) -> Invoice:
        # 兼容旧数据：screenshots/contracts → attachments 合并（与 from_dict 一致）
        atts = self._parse_json_list(row["attachments"])
        for col in ("screenshots", "contracts"):
            for p in self._parse_json_list(row[col]):
                if p and p not in atts:
                    atts.append(p)
        return Invoice(
            file=row["file"] or "",
            pdf_path=row["pdf_path"] or "",
            company=row["company"] or "",
            invoice_type=row["invoice_type"] or "",
            buyer_name=row["buyer_name"] or "",
            buyer_tax_id=row["buyer_tax_id"] or "",
            seller_name=row["seller_name"] or "",
            amount=row["amount"] or "",
            tax_rate=row["tax_rate"] or "",
            tax_amount=row["tax_amount"] or "",
            total=row["total"] or "",
            invoice_no=row["invoice_no"] or "",
            invoice_date=row["invoice_date"] or "",
            is_red=bool(row["is_red"]),
            tags=self._parse_json_dict(row["tags"]),
            attachments=atts,
            remark=row["remark"] or "",
            error=row["error"] or "",
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

    # ── 保存 ──────────────────────────────────

    def save(self, invoices: list[Invoice]) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("DELETE FROM invoices")
                conn.execute("DELETE FROM invoice_tags")
                for inv in invoices:
                    conn.execute("""
                        INSERT INTO invoices (
                            file, pdf_path, company, invoice_type,
                            buyer_name, buyer_tax_id, seller_name,
                            amount, tax_rate, tax_amount, total,
                            invoice_no, invoice_date, is_red,
                            screenshots, contracts, tags, attachments,
                            remark, error
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        inv.file, inv.pdf_path, inv.company, inv.invoice_type,
                        inv.buyer_name, inv.buyer_tax_id, inv.seller_name,
                        inv.amount, inv.tax_rate, inv.tax_amount, inv.total,
                        inv.invoice_no, inv.invoice_date, int(inv.is_red),
                        "[]", "[]",
                        json.dumps(inv.tags, ensure_ascii=False),
                        json.dumps(inv.attachments, ensure_ascii=False),
                        inv.remark, inv.error,
                    ))
                    inv_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    for name, value in (inv.tags or {}).items():
                        conn.execute(
                            "INSERT INTO invoice_tags(invoice_id, name, value) "
                            "VALUES (?, ?, ?)",
                            (inv_id, name, str(value) if value else ""),
                        )
                conn.commit()
        except sqlite3.Error as e:
            log.critical("数据保存失败: %s | %s (数据未写入)", self._db_path, e)
            raise
        else:
            log.debug("数据已保存: %d 条 → %s", len(invoices), self._db_path)

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
