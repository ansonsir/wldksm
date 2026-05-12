"""
config.py 模块单元测试
测试 ConfigManager, ScanConfig 核心逻辑
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.config import ScanConfig, ConfigManager, DEFAULT_BASE_DIR, DEFAULT_CONFIG_PATH


class TestScanConfig:
    """ScanConfig 数据类测试"""

    def test_default_values(self):
        """默认值检查"""
        config = ScanConfig()
        assert config.max_workers == 32
        assert config.ulimit == 32768
        assert config.timeout == 300
        assert config.batch_size == 10000
        assert config.scan_mode == "normal"

    def test_custom_values(self):
        """自定义值覆盖"""
        config = ScanConfig(
            max_workers=16,
            scan_mode="redarea",
            smtp_server="smtp.example.com"
        )
        assert config.max_workers == 16
        assert config.scan_mode == "redarea"
        assert config.smtp_server == "smtp.example.com"

    def test_post_init_resolves_paths(self):
        """__post_init__ 应设置 work_dir 和解析安全路径"""
        config = ScanConfig()
        assert config.work_dir is not None
        assert config.template_dir is not None
        assert config.report_dir is not None


class TestConfigManager:
    """ConfigManager 测试"""

    def test_get_config_returns_scan_config(self):
        """get_config 应返回 ScanConfig 实例"""
        mgr = ConfigManager()
        config = mgr.get_config()
        assert isinstance(config, ScanConfig)

    def test_save_and_reload_yaml(self, tmp_path):
        """保存 YAML 后重新加载验证"""
        import shutil
        # 使用临时目录
        cfg_path = tmp_path / "test_config.yaml"
        mgr = ConfigManager(config_path=str(cfg_path))
        config = mgr.get_config()
        config.max_workers = 48
        mgr.save_to_yaml()

        # 重新加载
        mgr2 = ConfigManager(config_path=str(cfg_path))
        config2 = mgr2.get_config()
        assert config2.max_workers == 48
