"""
RustScan API 封装模块
修复了原版的参数不一致问题
"""
import subprocess
import ast
import logging
import re
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum


class ScanMode(Enum):
    """扫描模式"""
    PORTS = "ports"      # 指定端口扫描
    RANGE = "range"      # 全端口范围扫描 (1-65535)


@dataclass
class ScanResult:
    """扫描结果数据结构"""
    ip: str
    ports: List[int]
    
    def to_dict(self) -> Dict[str, List[int]]:
        return {self.ip: self.ports}


class RustScanAPI:
    """
    RustScan API 封装类
    
    修复问题:
    1. 明确区分 ports 和 range 参数的使用场景
    2. 统一参数命名，避免混淆
    3. 增强错误处理和日志记录
    """
    
    def __init__(
        self,
        target: str,
        ports: Optional[str] = None,
        scan_range: Optional[str] = None,  # 重命名避免与 Python range 冲突
        ulimit: int = 5000,
        greppable: bool = True,
        exclude_ip: Optional[str] = None,
        nmap_enable: bool = False,
        nmap_param: Optional[str] = None,
        rustscan_path: str = "./rustscan",
        timeout: Optional[int] = None,
    ):
        """
        初始化扫描参数
        
        :param target: 扫描目标（IP/CIDR/域名）
        :param ports: 端口范围（示例: "80,443" 或 "1-1000"）
        :param scan_range: IP范围（示例: "10.0.0.0-10.0.0.255"），用于全端口扫描
        :param ulimit: 文件描述符限制（默认5000）
        :param greppable: 启用易解析输出格式
        :param exclude_ip: 排除的IP地址，多个IP用逗号分隔
        :param nmap_enable: 是否启用nmap进行深度扫描
        :param nmap_param: nmap的额外参数
        :param rustscan_path: rustscan可执行文件路径
        :param timeout: 扫描超时时间（秒）
        """
        # 参数验证
        if not target:
            raise ValueError("target 参数不能为空")
        
        # 明确扫描模式验证
        if ports and scan_range:
            raise ValueError("ports 和 scan_range 参数不能同时指定")
        
        if not ports and not scan_range:
            # 默认使用全端口扫描
            self.scan_mode = ScanMode.RANGE
            self.scan_range = "1-65535"
            self.ports = None
        elif ports:
            self.scan_mode = ScanMode.PORTS
            self.ports = ports
            self.scan_range = None
        else:
            self.scan_mode = ScanMode.RANGE
            self.scan_range = scan_range
            self.ports = None
        
        self.target = target
        self.ulimit = ulimit
        self.greppable = greppable
        self.exclude_ip = exclude_ip or ""
        self.nmap_enable = nmap_enable
        self.nmap_param = nmap_param or ""
        self.rustscan_path = rustscan_path
        self.timeout = timeout
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def scan(self) -> Dict[str, List[int]]:
        """
        执行扫描并返回开放端口列表
        
        :return: 字典 {IP: [端口列表]}
        :raises RuntimeError: 扫描失败时抛出异常
        """
        try:
            cmd = self._build_command()
            self.logger.info(f"执行扫描命令: {' '.join(cmd)}")
            
            # 执行扫描
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=self.timeout,
            )
            
            # 解析输出
            if self.nmap_enable:
                return {"nmap_output": result.stdout}
            
            if not result.stdout.strip():
                self.logger.info("扫描结果为空（未发现开放端口）")
                return {}
            
            return self._parse_ports(result.stdout)
            
        except subprocess.CalledProcessError as e:
            err_msg = f"扫描失败！退出码: {e.returncode}\n错误输出: {e.stderr.strip() or '无'}"
            self.logger.error(err_msg)
            raise RuntimeError(err_msg) from e
        except FileNotFoundError:
            err_msg = f"未找到 rustscan 可执行文件: {self.rustscan_path}"
            self.logger.error(err_msg)
            raise RuntimeError(err_msg)
        except subprocess.TimeoutExpired:
            err_msg = f"扫描超时（超过 {self.timeout} 秒）"
            self.logger.error(err_msg)
            raise RuntimeError(err_msg)
    
    def _build_command(self) -> List[str]:
        """
        构建 rustscan 命令
        
        :return: 命令列表
        """
        cmd = [
            self.rustscan_path,
            "-a", self.target,
            "-u", str(self.ulimit),
        ]
        
        # 根据扫描模式添加参数
        if self.scan_mode == ScanMode.PORTS and self.ports:
            cmd.extend(["-p", self.ports])
            cmd.append("-n")  # 禁用 nmap 集成
        elif self.scan_mode == ScanMode.RANGE and self.scan_range:
            cmd.extend(["--range", self.scan_range])
        
        # 添加排除IP
        if self.exclude_ip:
            cmd.extend(["-x", self.exclude_ip])
        
        # nmap 集成选项
        if self.nmap_enable:
            cmd.append("--")
            if self.nmap_param:
                cmd.append(self.nmap_param)
        else:
            if self.greppable:
                cmd.append("-g")
        
        return cmd
    
    def _parse_ports(self, output: str) -> Dict[str, List[int]]:
        """
        解析 rustscan 的 greppable 输出格式
        
        :param output: rustscan的输出字符串（格式: "IP -> [端口列表]"）
        :return: 字典 {IP: [端口列表]}，按IP排序
        """
        scan_result = {}
        lines = output.strip().splitlines()
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            try:
                # 检查行格式
                if "->" not in line:
                    self.logger.warning(f"跳过格式不正确的行: {line}")
                    continue
                
                ip_part, ports_part = line.split("->", 1)
                ip = ip_part.strip()
                ports_str = ports_part.strip()
                
                # 验证 IP 格式
                if not self._is_valid_ip(ip):
                    self.logger.warning(f"无效的 IP 地址: {ip}")
                    continue
                
                # 安全解析端口列表
                opening_ports = ast.literal_eval(ports_str)
                
                if not isinstance(opening_ports, (list, tuple)):
                    self.logger.warning(f"端口数据格式错误: {ports_str}")
                    continue
                
                # 确保所有端口都是整数
                ports = [int(p) for p in opening_ports if isinstance(p, (int, str))]
                scan_result[ip] = sorted(ports)
                
            except (ValueError, SyntaxError) as e:
                self.logger.error(f"解析行失败: {line}, 错误: {e}")
                continue
        
        # 按IP地址排序返回
        return {k: scan_result[k] for k in sorted(scan_result)}
    
    @staticmethod
    def _is_valid_ip(ip: str) -> bool:
        """验证 IP 地址格式"""
        # 简单验证 IPv4 格式
        pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if not re.match(pattern, ip):
            return False
        
        # 验证每个段是否在 0-255 范围内
        parts = ip.split('.')
        return all(0 <= int(part) <= 255 for part in parts)
    
    def __repr__(self) -> str:
        return (
            f"RustScanAPI("
            f"target='{self.target}', "
            f"mode={self.scan_mode.value}, "
            f"ports={self.ports or self.scan_range}, "
            f"ulimit={self.ulimit}"
            f")"
        )


# 便捷函数
def quick_scan(
    target: str,
    ports: str = "1-65535",
    **kwargs
) -> Dict[str, List[int]]:
    """
    快速扫描函数
    
    :param target: 扫描目标
    :param ports: 端口范围
    :param kwargs: 其他参数传递给 RustScanAPI
    :return: 扫描结果
    """
    scanner = RustScanAPI(target=target, ports=ports, **kwargs)
    return scanner.scan()


def full_scan(
    target: str,
    **kwargs
) -> Dict[str, List[int]]:
    """
    全端口扫描函数（1-65535）
    
    :param target: 扫描目标
    :param kwargs: 其他参数传递给 RustScanAPI
    :return: 扫描结果
    """
    scanner = RustScanAPI(target=target, scan_range="1-65535", **kwargs)
    return scanner.scan()
