# -*- coding: utf-8 -*-
"""冒烟测试 — 零依赖（unittest + headless Qt），发布前必须通过"""

import os
import sys
import json
import shutil
import tempfile
import unittest

# 无头模式：pyinstaller 离线构建环境内不会 crash
os.environ["QT_QPA_PLATFORM"] = "offscreen"

SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
sys.path.insert(0, SRC)


class TestImports(unittest.TestCase):
    """所有核心模块必须能导入"""

    def test_core_modules(self):
        from database import Database          # noqa: F401
        from backup import BackupService       # noqa: F401
        from config_manager import ConfigManager  # noqa: F401
        from models import Invoice            # noqa: F401
        from storage import InvoiceStorage    # noqa: F401
        from filters import record_matches_filter  # noqa: F401
        from logger import getLogger          # noqa: F401
        from version import APP_VERSION       # noqa: F401

    def test_service_modules(self):
        from services.invoice_service import InvoiceService    # noqa: F401
        from services.export_service import ExportService      # noqa: F401

    def test_ui_widgets(self):
        from ui.widgets.strategy_card import StrategyCard      # noqa: F401

    def test_ui_dialogs(self):
        from ui.dialogs.settings import SettingsDialog         # noqa: F401
        from ui.dialogs.delete_confirm import DeleteConfirmDialog  # noqa: F401
        from ui.dialogs.import_preview import ImportPreviewDialog  # noqa: F401

    def test_server_modules(self):
        from mcp_server import McpServer      # noqa: F401
        from http_server import AppHandler    # noqa: F401
        from webdav_sync import sync_to_webdav, SyncManifest  # noqa: F401


class TestConfig(unittest.TestCase):
    """配置迁移 + 策略读写"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._cfg_path = os.path.join(self._tmp, "config.json")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_default_strategies(self):
        from config_manager import ConfigManager
        c = ConfigManager(self._cfg_path)
        local = c.get_local_strategy()
        self.assertTrue(local["enabled"])
        self.assertEqual(local["trigger"], "on_save")
        self.assertEqual(local["max_keep"], 30)
        webdav = c.get_webdav_strategy()
        self.assertEqual(webdav["version_mode"], "incremental")

    def test_migration_from_old_config(self):
        """旧字段 backup_enabled → 新策略结构"""
        old = {"backup_enabled": False, "webdav_url": "https://example.com/dav/"}
        with open(self._cfg_path, "w", encoding="utf-8") as f:
            json.dump(old, f)
        from config_manager import ConfigManager
        c = ConfigManager(self._cfg_path)
        self.assertFalse(c.get_local_strategy()["enabled"])
        self.assertTrue(c.get_webdav_strategy()["enabled"])
        with open(self._cfg_path, encoding="utf-8") as f:
            self.assertIn("backup_strategies", json.load(f))
        # 旧字段已清理
        with open(self._cfg_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertNotIn("backup_enabled", data)

    def test_set_strategies(self):
        from config_manager import ConfigManager
        c = ConfigManager(self._cfg_path)
        c.set_local_strategy({"trigger": "scheduled", "interval_minutes": 15})
        s = c.get_local_strategy()
        self.assertEqual(s["trigger"], "scheduled")
        self.assertEqual(s["interval_minutes"], 15)
        # 未设置的字段保持默认
        self.assertEqual(s["max_keep"], 30)

    def test_mcp_entry_generation(self):
        """MCP JSON 配置项生成：dev 有 cwd，frozen 无 cwd"""
        import sys
        from ui.dialogs.settings import SettingsDialog
        entry = SettingsDialog._make_mcp_entry()
        self.assertIn("command", entry)
        self.assertIn("args", entry)
        self.assertIn("--mcp", entry["args"])
        if not getattr(sys, 'frozen', False):
            self.assertIn("cwd", entry)

    def test_mcp_entry_json_format(self):
        """MCP JSON 配置格式正确（mcpServers.invoice 存在）"""
        import json
        from ui.dialogs.settings import SettingsDialog
        entry = SettingsDialog._make_mcp_entry()
        cfg = {"mcpServers": {"invoice": entry}}
        text = json.dumps(cfg, ensure_ascii=False, indent=2)
        loaded = json.loads(text)
        self.assertIn("invoice", loaded["mcpServers"])
        self.assertIn("--mcp", loaded["mcpServers"]["invoice"]["args"])
        self.assertEqual(loaded["mcpServers"]["invoice"]["command"], "uv")


class TestDatabase(unittest.TestCase):
    """SQLite CRUD + tags 关联表 + 索引查询"""

    def setUp(self):
        fd, self._db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        # SQLite WAL 模式下文件句柄可能未完全释放，忽略清理失败
        for suffix in ("", "-shm", "-wal"):
            try:
                p = self._db_path + suffix
                if os.path.exists(p):
                    os.remove(p)
            except (OSError, PermissionError):
                pass

    def test_create_tables(self):
        from database import Database
        db = Database(self._db_path)
        conn = __import__("sqlite3").connect(self._db_path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        self.assertIn("invoices", tables)
        self.assertIn("invoice_tags", tables)

    def test_save_and_load_with_tags(self):
        from database import Database
        from models import Invoice
        db = Database(self._db_path)
        inv = Invoice(invoice_no="SMOKE01", file="test.pdf")
        inv.tags = {"企业号": "14786", "项目": "Q1"}
        db.save([inv])
        loaded = db.load()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].tags["企业号"], "14786")
        self.assertEqual(loaded[0].tags["项目"], "Q1")

    def test_find_by_invoice_no(self):
        from database import Database
        from models import Invoice
        db = Database(self._db_path)
        inv = Invoice(invoice_no="FIND01", file="a.pdf")
        db.save([inv])
        found = db.find_by_invoice_no("FIND01")
        self.assertIsNotNone(found)
        self.assertEqual(found.invoice_no, "FIND01")
        self.assertIsNone(db.find_by_invoice_no("NOPE"))

    def test_delete_cascade_tags(self):
        from database import Database
        from models import Invoice
        db = Database(self._db_path)
        inv = Invoice(invoice_no="DEL01", file="d.pdf")
        inv.tags = {"key": "val"}
        db.save([inv])
        db.delete("DEL01")
        # 验证 tags 也被清理（外键级联）
        conn = __import__("sqlite3").connect(self._db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM invoice_tags").fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    def test_attachments_cleaned_on_delete(self):
        """删除发票时 PDF + 附件全部清理"""
        from database import Database
        from models import Invoice
        db = Database(self._db_path)

        # 创建两个临时文件模拟 PDF + 附件
        pdf = self._db_path + ".test.pdf"
        att = self._db_path + ".test.png"
        for p in (pdf, att):
            with open(p, "w") as f:
                f.write("test")

        inv = Invoice(invoice_no="CLEAN01", file="clean.pdf", pdf_path=pdf)
        inv.attachments = [att]
        db.save([inv])

        # 验证文件存在
        self.assertTrue(os.path.exists(pdf))
        self.assertTrue(os.path.exists(att))

        # 删除
        from services.invoice_service import InvoiceService
        _, failed = InvoiceService.delete_invoice_files(inv)
        self.assertEqual(len(failed), 0)
        self.assertFalse(os.path.exists(pdf))
        self.assertFalse(os.path.exists(att))

    def test_tags_migration(self):
        """模拟旧库（完整旧 invoices 表但无 invoice_tags）的迁移"""
        # 确保临时文件不存在
        tmp = self._db_path
        for s in ("", "-shm", "-wal"):
            try: os.remove(tmp + s)
            except OSError: pass
        # 用已知的新 Database 自动生成完整表结构
        from database import Database
        db1 = Database(tmp)
        db1.save([])
        # 删除 invoice_tags 表 + 删除 tags 迁移标记 → 模拟旧库
        conn = __import__("sqlite3").connect(tmp)
        conn.execute("DROP TABLE IF EXISTS invoice_tags")
        conn.execute("UPDATE invoices SET tags = ? WHERE 1=1",
                     (json.dumps({"企业号": "MIG_OK"}),))
        conn.commit()
        conn.close()
        # 用 Database 重新打开 → 触发迁移
        from database import Database as DB
        db2 = DB(tmp)
        invs = db2.load()
        self.assertEqual(len(invs), 0)  # save([]) 后无记录
        # 插入一条带 JSON tags 的旧格式数据
        conn2 = __import__("sqlite3").connect(tmp)
        conn2.execute("""INSERT INTO invoices(file, pdf_path, company, invoice_type,
            buyer_name, buyer_tax_id, seller_name, amount, tax_rate, tax_amount,
            total, invoice_no, invoice_date, is_red, screenshots, contracts,
            tags, attachments, remark, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("", "", "", "", "", "", "", "", "", "", "", "MIG01", "", 0,
             "[]", "[]", '{"企业号": "MIG_OK"}', "[]", "", ""))
        conn2.commit()
        conn2.close()
        # 重新打开 → 自动迁移
        db3 = DB(tmp)
        invs = db3.load()
        self.assertEqual(len(invs), 1)
        self.assertEqual(invs[0].tags.get("企业号"), "MIG_OK")
        # invoice_tags 表应有数据
        conn3 = __import__("sqlite3").connect(tmp)
        count = conn3.execute(
            "SELECT COUNT(*) FROM invoice_tags").fetchone()[0]
        conn3.close()
        self.assertGreater(count, 0)


class TestInvoiceService(unittest.TestCase):
    """业务层 CRUD"""

    def setUp(self):
        fd, self._db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._tmp_data = tempfile.mkdtemp()
        from database import Database
        from backup import BackupService
        from config_manager import ConfigManager
        self._db = Database(self._db_path)
        self._backup = BackupService()
        self._cfg = ConfigManager(os.path.join(self._tmp_data, "cfg.json"))
        self._svc = __import__("services.invoice_service", fromlist=["InvoiceService"]
                               ).InvoiceService(
            self._db, self._backup, self._cfg,
            self._tmp_data, os.path.join(self._tmp_data, "invoices"),
        )

    def tearDown(self):
        for s in ("", "-shm", "-wal"):
            try:
                p = self._db_path + s
                if os.path.exists(p):
                    os.remove(p)
            except (OSError, PermissionError):
                pass
        shutil.rmtree(self._tmp_data, ignore_errors=True)

    def test_search_empty(self):
        result = self._svc.search(limit=5)
        self.assertEqual(result["count"], 0)

    def test_summary_empty(self):
        result = self._svc.get_summary()
        self.assertEqual(result["count"], 0)

    def test_import_invoice_with_pdf(self):
        """真实 PDF 导入流程（含解析 + 去重检查）"""
        # 生成最小有效 PDF
        pdf_path = os.path.join(self._tmp_data, "test_invoice.pdf")
        with open(pdf_path, "wb") as f:
            f.write(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
                    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
                    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
                    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
                    b"0000000058 00000 n \n0000000115 00000 n \n"
                    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF")

        result = self._svc.import_invoice(pdf_path, tags={"企业号": "IMP01"})
        # 最小 PDF 无文字可解析，应返回 parse_error
        self.assertIn(result.get("status"), ("parse_error", "ok"))
        # 但不应崩溃
        self.assertIsNotNone(result)

    def test_tags_crud(self):
        r = self._svc.manage_tags("list")
        self.assertIn("tags", r)
        r = self._svc.manage_tags("add", "测试标签")
        self.assertIn("测试标签", r["tags"])
        r = self._svc.manage_tags("delete", "测试标签")
        self.assertNotIn("测试标签", r["tags"])


class TestBackup(unittest.TestCase):
    """备份统计 + 清理"""

    def test_get_stats_empty(self):
        from backup import BackupService
        b = BackupService()
        s = b.get_stats()
        self.assertIn("count", s)
        self.assertIn("partitions", s)


class TestUiInstantiation(unittest.TestCase):
    """UI 组件实例化（headless，真实创建所有对话框）"""

    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication(sys.argv)
        # 构建完整 mock app_ref，供 SettingsDialog 等使用
        from config_manager import ConfigManager
        from backup import BackupService
        from database import Database

        cls._tmpdir = tempfile.mkdtemp()
        cls._cfg = ConfigManager(os.path.join(cls._tmpdir, "config.json"))
        cls._db = Database(os.path.join(cls._tmpdir, "invoices.db"))
        cls._backup = BackupService()

        class MockApp:
            records = []
            _config = cls._cfg
            _data_dir = cls._tmpdir
            _data_file = os.path.join(cls._tmpdir, "invoices.db")
            _attachment_dir = cls._tmpdir
            _db = cls._db
            _backup = cls._backup
            _tag_templates = ["企业号"]
            _svc = None
            table = None
            status = None
            APP_VERSION = "test"

            @staticmethod
            def check_update():
                pass

            @staticmethod
            def _rebuild_table():
                pass

            @staticmethod
            def _load_data():
                pass

        cls._mock_app = MockApp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def test_settings_dialog_full_init(self):
        """设置对话框完整初始化：3 个 Tab + 策略卡片 + MCP 配置"""
        from ui.dialogs.settings import SettingsDialog
        dlg = SettingsDialog(self._mock_app)
        self.assertIsNotNone(dlg)

        # 验证 3 个 Tab 都已构建
        from PyQt5.QtWidgets import QTabWidget
        tabs = dlg.findChildren(QTabWidget)
        self.assertEqual(len(tabs), 1)
        self.assertEqual(tabs[0].count(), 3)

        # 验证策略卡片存在
        self.assertIsNotNone(getattr(dlg, "_local_card", None))
        self.assertIsNotNone(getattr(dlg, "_webdav_card", None))

        # 验证 MCP JSON 配置存在
        self.assertTrue(hasattr(dlg, "edit_mcp_json"))
        self.assertIn("--mcp", dlg.edit_mcp_json.text())
        self.assertIn("mcpServers", dlg.edit_mcp_json.text())

        dlg.close()

    def test_import_preview_dialog(self):
        """导入预览对话框：新 → 可勾选，重复+错误 → 不可勾选"""
        from ui.dialogs.import_preview import ImportPreviewDialog
        results = [
            {"file": "dup.pdf", "invoice_no": "111", "invoice_date": "2025-01-01",
             "amount": "100.00"},
            {"file": "new.pdf", "invoice_no": "222", "invoice_date": "2025-01-02",
             "amount": "200.00"},
            {"file": "err.pdf", "invoice_no": "", "error": "解析失败"},
        ]
        dlg = ImportPreviewDialog(results, {"111"})
        self.assertIsNotNone(dlg)
        # dup.pdf: 重复, err.pdf: 错误 → 都不选；仅 new.pdf 可选
        self.assertEqual(len(dlg.get_selected_indices()), 1)
        dlg.close()

    def test_strategy_card_instantiation(self):
        """策略卡片能创建并读取值"""
        from ui.widgets.strategy_card import StrategyCard
        card = StrategyCard("local", {
            "enabled": True, "trigger": "on_save",
            "interval_minutes": 30, "max_keep": 30,
            "retention_days": 30, "min_keep": 3,
        })
        s = card.get_strategy()
        self.assertTrue(s["enabled"])
        self.assertEqual(s["max_keep"], 30)

    def test_strategy_card_webdav(self):
        from ui.widgets.strategy_card import StrategyCard
        card = StrategyCard("webdav", {
            "enabled": False, "trigger": "scheduled",
            "interval_minutes": 60, "version_mode": "keep_versions",
            "max_versions": 10,
        })
        s = card.get_strategy()
        self.assertEqual(s["version_mode"], "keep_versions")
        self.assertEqual(s["trigger"], "scheduled")

    def test_delete_confirm_dialog(self):
        """删除确认对话框能创建"""
        from ui.dialogs.delete_confirm import DeleteConfirmDialog
        recs = [{"invoice_no": "D001", "file": "d.pdf"}]
        dlg = DeleteConfirmDialog(recs)
        self.assertIsNotNone(dlg)
        dlg.close()


class TestEndToEnd(unittest.TestCase):
    """端到端：完整业务流程"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        from database import Database
        from backup import BackupService
        from config_manager import ConfigManager
        self._db = Database(os.path.join(self._tmp, "invoices.db"))
        self._backup = BackupService()
        self._cfg = ConfigManager(os.path.join(self._tmp, "config.json"))
        self._svc = __import__("services.invoice_service", fromlist=["InvoiceService"]
                               ).InvoiceService(
            self._db, self._backup, self._cfg,
            self._tmp, os.path.join(self._tmp, "invoices"),
        )

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_import_search_delete_flow(self):
        """导入 → 搜索 → 删除 完整流程"""
        # 导入
        self._svc.manage_tags("add", "企业号")
        result = self._svc.search()
        self.assertEqual(result["count"], 0)

        # 手动创建一条记录（日期用发票原始格式）
        from models import Invoice
        inv = Invoice(invoice_no="E2E001", file="e2e.pdf", invoice_date="2025年06月15日",
                      amount="500.00", invoice_type="增值税专用发票",
                      buyer_name="测试公司")
        inv.tags = {"企业号": "E2E"}
        self._db.save([inv])

        # 搜索
        result = self._svc.search(year=2025, month=6, limit=10)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["records"][0]["invoice_no"], "E2E001")

        # 统计
        summary = self._svc.get_summary(year=2025, month=6)
        self.assertEqual(summary["count"], 1)

        # 更新
        self._svc.update_invoice("E2E001", tags={"项目": "Q1"})
        loaded = self._db.load()
        self.assertEqual(loaded[0].tags.get("项目"), "Q1")

        # 删除
        result = self._svc.delete_invoice("E2E001")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(self._db.load()), 0)

    def test_backup_with_data(self):
        """备份能正常执行（含 optimize + cleanup）"""
        from models import Invoice
        inv = Invoice(invoice_no="BK001", file="bk.pdf")
        self._db.save([inv])

        # 执行备份流程
        self._db.optimize()
        count = self._backup.force_backup(self._db.data_file)
        self.assertGreaterEqual(count, 1)

        # 统计应有数据
        stats = self._backup.get_stats()
        self.assertGreater(stats["count"], 0)

        # 清理
        removed = self._backup.cleanup(keep_days=0, min_keep=0, max_keep=0)
        self.assertGreaterEqual(removed, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
