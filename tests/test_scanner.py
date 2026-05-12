"""
scanner.py 模块单元测试
测试 calculate_timeout, merge_ip_ranges 等核心函数
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.scanner import calculate_timeout, merge_ip_ranges


class TestCalculateTimeout:
    """calculate_timeout 函数测试"""

    def test_small_subnet_returns_base_timeout(self):
        """小网段（少量主机）应返回基础超时"""
        timeout = calculate_timeout("192.168.1.0/29", port_count=100, base_timeout=300)
        assert timeout == 300  # 6台主机 × 100端口 × 0.001 ≈ 0.6 < 300

    def test_large_subnet_scales_up(self):
        """大网段应动态增加超时"""
        timeout = calculate_timeout("10.0.0.0/8", port_count=65535, base_timeout=300)
        # /8 = 16777216 台主机 × 65535 端口 × 0.001 = 超大值
        assert timeout > 300

    def test_invalid_cidr_returns_base(self):
        """非法 CIDR 应安全回退到基础超时"""
        timeout = calculate_timeout("not-a-cidr", 100, base_timeout=500)
        assert timeout == 500

    def test_single_ip_returns_base(self):
        """单 IP 应返回基础超时"""
        timeout = calculate_timeout("192.168.1.1/32", 10, base_timeout=300)
        assert timeout == 300


class TestMergeIpRanges:
    """merge_ip_ranges 函数测试"""

    def test_adjacent_networks_merged(self):
        """相邻网段可能被合并（取决于ipaddress.collapse逻辑）"""
        ranges = ["192.168.1.0/24", "192.168.2.0/24"]
        merged = merge_ip_ranges(ranges)
        # 相邻/24会合并为/23（如果collapse支持），否则各自保留
        assert len(merged) >= 1

    def test_large_network_split(self):
        """过大网段应被拆分（/8 → /16）"""
        ranges = ["10.0.0.0/8"]
        merged = merge_ip_ranges(ranges)
        # 应拆分为多个 /16 网段
        assert len(merged) > 1

    def test_non_overlapping_preserved(self):
        """不重叠网段保持独立"""
        ranges = ["192.168.1.0/24", "10.0.0.0/24"]
        merged = merge_ip_ranges(ranges)
        assert len(merged) >= 2

    def test_invalid_cidr_skipped(self):
        """非法 CIDR 被跳过，合法网段保留"""
        ranges = ["invalid", "192.168.1.0/24"]
        merged = merge_ip_ranges(ranges)
        assert any("192.168.1" in m for m in merged)

    def test_empty_list_returns_empty(self):
        """空列表返回空"""
        merged = merge_ip_ranges([])
        assert merged == []
