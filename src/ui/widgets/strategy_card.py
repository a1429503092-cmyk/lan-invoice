# -*- coding: utf-8 -*-
"""备份策略卡片组件 — 封装触发时机、保留规则等策略配置 UI"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QComboBox, QSpinBox,
    QLabel
)
from PyQt5.QtCore import pyqtSignal

TRIGGER_LABELS = {
    "on_save": "每次保存时",
    "scheduled": "定时",
    "on_close": "仅关闭时",
    "manual": "纯手动",
}


class StrategyCard(QWidget):
    """备份策略卡片：启用开关 + 触发时机 + 定时间隔 + 保留规则"""

    strategy_changed = pyqtSignal()  # 任何控件变更时发射

    def __init__(self, key: str, strategy: dict, parent=None):
        super().__init__(parent)
        self._key = key
        self._strategy = dict(strategy)
        self._build()
        self._update_visibility()

    # ── 值获取 ──────────────────────────────

    def get_strategy(self) -> dict:
        """返回当前 UI 控件值的策略 dict（更新内部缓存并返回）"""
        s = self._strategy
        s["enabled"] = self.cb_enabled.isChecked()
        s["trigger"] = self.cmb_trigger.currentData()
        if self._key == "local":
            s["interval_minutes"] = self.sp_interval.value()
            s["max_keep"] = self.sp_max_keep.value()
            s["min_keep"] = self.sp_min_keep.value()
            s["retention_days"] = self.sp_retention_days.value()
        else:
            s["interval_minutes"] = self.sp_interval.value()
            s["version_mode"] = self.cmb_version_mode.currentData()
            s["max_versions"] = self.sp_max_versions.value()
        return s

    @property
    def key(self) -> str:
        return self._key

    # ── 构建 ────────────────────────────────

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(6)

        s = self._strategy

        # 启用
        label = "本地多盘备份" if self._key == "local" else "WebDAV 远程同步"
        self.cb_enabled = QCheckBox(label)
        self.cb_enabled.setChecked(s["enabled"])
        self.cb_enabled.toggled.connect(self._emit_changed)
        layout.addWidget(self.cb_enabled)

        # 触发时机
        trig_row = QHBoxLayout()
        trig_row.setSpacing(8)
        trig_row.addWidget(QLabel("触发时机"))
        self.cmb_trigger = QComboBox()
        for val, label in TRIGGER_LABELS.items():
            self.cmb_trigger.addItem(label, val)
        idx = self.cmb_trigger.findData(s["trigger"])
        if idx >= 0:
            self.cmb_trigger.setCurrentIndex(idx)
        self.cmb_trigger.currentIndexChanged.connect(self._on_trigger_changed)
        trig_row.addWidget(self.cmb_trigger, 1)
        layout.addLayout(trig_row)

        # 定时间隔
        self._interval_row = QHBoxLayout()
        self._interval_row.setSpacing(8)
        self._interval_row.addWidget(QLabel("定时间隔"))
        self.sp_interval = QSpinBox()
        self.sp_interval.setRange(1, 1440)
        self.sp_interval.setValue(s["interval_minutes"])
        self.sp_interval.setSuffix(" 分钟")
        self.sp_interval.valueChanged.connect(self._emit_changed)
        self._interval_row.addWidget(self.sp_interval, 1)
        layout.addLayout(self._interval_row)

        # 保留规则
        retain_row = QHBoxLayout()
        retain_row.setSpacing(8)
        if self._key == "local":
            self._build_local_retention(retain_row, s)
        else:
            self._build_webdav_retention(retain_row, s)
        layout.addLayout(retain_row)

    def _build_local_retention(self, row: QHBoxLayout, s: dict):
        row.addWidget(QLabel("最多"))
        self.sp_max_keep = QSpinBox()
        self.sp_max_keep.setRange(3, 200)
        self.sp_max_keep.setValue(s["max_keep"])
        self.sp_max_keep.setSuffix(" 份")
        self.sp_max_keep.valueChanged.connect(self._emit_changed)
        row.addWidget(self.sp_max_keep)

        row.addWidget(QLabel("最少"))
        self.sp_min_keep = QSpinBox()
        self.sp_min_keep.setRange(1, 50)
        self.sp_min_keep.setValue(s["min_keep"])
        self.sp_min_keep.setSuffix(" 份")
        self.sp_min_keep.valueChanged.connect(self._emit_changed)
        row.addWidget(self.sp_min_keep)

        row.addWidget(QLabel("保留"))
        self.sp_retention_days = QSpinBox()
        self.sp_retention_days.setRange(1, 365)
        self.sp_retention_days.setValue(s["retention_days"])
        self.sp_retention_days.setSuffix(" 天")
        self.sp_retention_days.valueChanged.connect(self._emit_changed)
        row.addWidget(self.sp_retention_days)
        row.addStretch()

    def _build_webdav_retention(self, row: QHBoxLayout, s: dict):
        row.addWidget(QLabel("版本模式"))
        self.cmb_version_mode = QComboBox()
        self.cmb_version_mode.addItem("增量覆盖", "incremental")
        self.cmb_version_mode.addItem("保留版本", "keep_versions")
        idx = self.cmb_version_mode.findData(s.get("version_mode", "incremental"))
        if idx >= 0:
            self.cmb_version_mode.setCurrentIndex(idx)
        self.cmb_version_mode.currentIndexChanged.connect(self._emit_changed)
        row.addWidget(self.cmb_version_mode, 1)

        row.addWidget(QLabel("最多"))
        self.sp_max_versions = QSpinBox()
        self.sp_max_versions.setRange(3, 100)
        self.sp_max_versions.setValue(s.get("max_versions", 10))
        self.sp_max_versions.setSuffix(" 版")
        self.sp_max_versions.valueChanged.connect(self._emit_changed)
        row.addWidget(self.sp_max_versions)

    # ── 信号/可见性 ──────────────────────────

    def _on_trigger_changed(self):
        self._update_visibility()
        self._emit_changed()

    def _update_visibility(self):
        visible = self.cmb_trigger.currentData() == "scheduled"
        for i in range(self._interval_row.count()):
            w = self._interval_row.itemAt(i).widget()
            if w:
                w.setVisible(visible)

    def _emit_changed(self):
        self._strategy = self.get_strategy()
        self.strategy_changed.emit()
