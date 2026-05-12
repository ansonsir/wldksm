"""
RustScan API 封装模块
基于 Version2 进一步优化
"""
import subprocess
import os
import signal
import json
import logging
import re
import shutil
import resource
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class ScanMode(Enum):
    """扫描模式"""
    PORTS = "ports"
    RANGE = "range"


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
    """

    @staticmethod
    def _find_rustscan_path() -> str:
        """查找 rustscan 可执行文件路径"""
        # 1. 先尝试项目目录
        local_path = "./rustscan"
        import os
        if os.path.exists(local_path):
            return local_path
        
        # 2. 尝试系统 PATH
        system_path = shutil.which("rustscan")
        if system_path:
            return system_path
        
        # 3. 返回默认值（会在使用时报错）
        return local_path

    def __init__(
        self,
        target: str,
        ports: Optional[str] = None,
        scan_range: Optional[str] = None,
        ulimit: int = 5000,
        greppable: bool = True,
        exclude_ip: Optional[str] = None,
        nmap_enable: bool = False,
        nmap_param: Optional[str] = None,
        rustscan_path: Optional[str] = None,
        timeout: Optional[int] = None,
        batch_size: Optional[int] = None,
    ):
        """
        初始化扫描参数

        :param target: 扫描目标（IP/CIDR/域名）
        :param ports: 端口范围（示例: "80,443" 或 "1-1000" 或 "1-65535"）
        :param scan_range: 全端口范围（"1-65535"）
        :param ulimit: 文件描述符限制
        :param greppable: 启用易解析输出格式
        :param exclude_ip: 排除的IP地址
        :param nmap_enable: 是否启用nmap
        :param nmap_param: nmap参数
        :param rustscan_path: rustscan可执行文件路径（可选，自动查找）
        :param timeout: 扫描超时时间（秒）
        """
        if not target:
            raise ValueError("target 参数不能为空")

        if ports and scan_range:
            raise ValueError("ports 和 scan_range 参数不能同时指定")

        # 智能检测 ports 格式
        if ports:
            # 检测是否为纯端口段格式（如 1-65535）
            if '-' in ports and ',' not in ports:
                parts = ports.split('-')
                if len(parts) == 2:
                    try:
                        start = int(parts[0].strip())
                        end = int(parts[1].strip())
                        if 1 <= start <= 65535 and 1 <= end <= 65535:
                            # 这是端口段格式，使用 scan_range
                            self.scan_mode = ScanMode.RANGE
                            self.scan_range = ports
                            self.ports = None
                        else:
                            # 无效的端口段，使用 ports
                            self.scan_mode = ScanMode.PORTS
                            self.ports = ports
                            self.scan_range = None
                    except ValueError:
                        # 解析失败，使用 ports
                        self.scan_mode = ScanMode.PORTS
                        self.ports = ports
                        self.scan_range = None
                else:
                    self.scan_mode = ScanMode.PORTS
                    self.ports = ports
                    self.scan_range = None
            else:
                # 包含逗号或其他格式，使用 ports
                self.scan_mode = ScanMode.PORTS
                self.ports = ports
                self.scan_range = None
        elif scan_range:
            self.scan_mode = ScanMode.RANGE
            self.scan_range = scan_range
            self.ports = None
        else:
            # 默认全端口扫描
            self.scan_mode = ScanMode.RANGE
            self.scan_range = "1-65535"
            self.ports = None

        self.target = target
        self.ulimit = ulimit
        self.greppable = greppable
        self.exclude_ip = exclude_ip or ""
        self.nmap_enable = nmap_enable
        self.nmap_param = nmap_param or ""
        # 自动查找 rustscan 路径
        self.rustscan_path = rustscan_path or self._find_rustscan_path()
        self.timeout = timeout
        self.batch_size = batch_size
        self.logger = logging.getLogger(self.__class__.__name__)

    def scan(self) -> Dict[str, List[int]]:
        """
        执行扫描并返回开放端口列表
        使用 start_new_session 创建独立进程组，支持精确的进程终止

        :return: 字典 {IP: [端口列表]}
        :raises RuntimeError: 扫描失败时抛出异常
        """
        self._process = None  # 存储子进程引用，供外部终止
        try:
            cmd = self._build_command()
            self.logger.info(f"执行扫描命令: {' '.join(cmd)}")

            # 使用 Popen + start_new_session 创建独立进程组
            # shell=False 防止命令注入，preexec_fn 限制子进程资源
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                start_new_session=True,  # 创建独立进程组，便于精确终止
                preexec_fn=self._set_process_limits,  # 资源限制
            )

            try:
                stdout, stderr = self._process.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                # 超时：终止进程组
                self._kill_process_group()
                err_msg = f"扫描超时（超过 {self.timeout} 秒）"
                self.logger.error(err_msg)
                raise RuntimeError(err_msg)

            if self._process.returncode != 0:
                err_msg = f"扫描失败！退出码: {self._process.returncode}\n错误输出: {stderr.strip() or '无'}"
                self.logger.error(err_msg)
                raise RuntimeError(err_msg)

            if self.nmap_enable:
                return {"nmap_output": stdout}

            if not stdout.strip():
                self.logger.info("扫描结果为空（未发现开放端口）")
                return {}

            return self._parse_ports(stdout)

        except subprocess.CalledProcessError as e:
            err_msg = f"扫描失败！退出码: {e.returncode}\n错误输出: {e.stderr.strip() if hasattr(e, 'stderr') and e.stderr else '无'}"
            self.logger.error(err_msg)
            raise RuntimeError(err_msg) from e
        except FileNotFoundError:
            err_msg = f"未找到 rustscan 可执行文件: {self.rustscan_path}"
            self.logger.error(err_msg)
            raise RuntimeError(err_msg)
        except RuntimeError:
            raise
        finally:
            self._process = None

    def _kill_process_group(self):
        """终止子进程及其进程组中的所有进程"""
        if self._process and self._process.pid:
            try:
                pgid = os.getpgid(self._process.pid)
                self.logger.info(f"终止进程组: pgid={pgid}, pid={self._process.pid}")
                os.killpg(pgid, signal.SIGKILL)
                self._process.wait(timeout=3)
            except ProcessLookupError:
                self.logger.info("进程已退出")
            except Exception as e:
                self.logger.warning(f"终止进程组失败: {e}")
                # 回退：直接终止进程
                try:
                    self._process.kill()
                except Exception:
                    pass

    @staticmethod
    def _set_process_limits():
        """限制子进程资源使用（防止资源耗尽）"""
        try:
            # CPU 时间限制: 最多 3600 秒 (1小时)
            resource.setrlimit(resource.RLIMIT_CPU, (3600, 3600))
        except (ValueError, resource.error):
            pass  # 在某些系统上可能不支持
        try:
            # 内存限制: 最多 4GB
            mem_limit = 4 * 1024 * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
        except (ValueError, resource.error):
            pass

    def terminate(self):
        """外部终止扫描进程（由 ScanOrchestrator 调用）"""
        self._kill_process_group()

    def _build_command(self) -> List[str]:
        """构建 rustscan 命令"""
        cmd = [
            self.rustscan_path,
            "-a", self.target,
            "-u", str(self.ulimit),
        ]

        if self.batch_size:
            cmd.extend(["-b", str(self.batch_size)])

        if self.scan_mode == ScanMode.PORTS and self.ports:
            cmd.extend(["-p", self.ports])
            cmd.append("-n")
        elif self.scan_mode == ScanMode.RANGE and self.scan_range:
            cmd.extend(["--range", self.scan_range])

        if self.exclude_ip:
            cmd.extend(["-x", self.exclude_ip])

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

        :param output: rustscan的输出字符串
        :return: 字典 {IP: [端口列表]}
        """
        scan_result = {}
        lines = output.strip().splitlines()

        for line in lines:
            line = line.strip()
            if not line:
                continue

            try:
                if "->" not in line:
                    self.logger.warning(f"跳过格式不正确的行: {line}")
                    continue

                ip_part, ports_part = line.split("->", 1)
                ip = ip_part.strip()
                ports_str = ports_part.strip()

                if not self._is_valid_ip(ip):
                    self.logger.warning(f"无效的 IP 地址: {ip}")
                    continue

                # 安全解析端口列表：优先用 json.loads，回退到手动解析
                opening_ports = self._safe_parse_ports(ports_str)
                if opening_ports is None:
                    self.logger.warning(f"端口数据格式错误: {ports_str}")
                    continue

                ports = [int(p) for p in opening_ports if isinstance(p, (int, str))]
                # 验证端口号范围
                ports = [p for p in ports if 1 <= int(p) <= 65535]
                scan_result[ip] = sorted(ports)

            except (ValueError, SyntaxError) as e:
                self.logger.error(f"解析行失败: {line}, 错误: {e}")
                continue

        return {k: scan_result[k] for k in sorted(scan_result)}

    @staticmethod
    def _safe_parse_ports(ports_str: str) -> Optional[List]:
        """
        安全解析端口列表，避免代码执行风险
        优先使用 json.loads，回退到逗号分隔手动解析
        """
        if not ports_str or not ports_str.strip():
            return None
        ports_str = ports_str.strip()
        
        # 尝试 JSON 解析（最安全）
        if ports_str.startswith('[') and ports_str.endswith(']'):
            try:
                parsed = json.loads(ports_str)
                if isinstance(parsed, list):
                    # 验证所有元素都是数字
                    result = []
                    for item in parsed:
                        try:
                            port = int(item)
                            if 1 <= port <= 65535:
                                result.append(port)
                        except (ValueError, TypeError):
                            continue
                    return result if result else None
            except json.JSONDecodeError:
                pass
        
        # 回退：逗号分隔手动解析
        try:
            result = []
            for part in ports_str.strip('[]').split(','):
                part = part.strip()
                if not part:
                    continue
                port = int(part)
                if 1 <= port <= 65535:
                    result.append(port)
            return result if result else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _is_valid_ip(ip: str) -> bool:
        """验证 IP 地址格式"""
        pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if not re.match(pattern, ip):
            return False
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


def quick_scan(
    target: str,
    ports: str = "1-65535",
    **kwargs
) -> Dict[str, List[int]]:
    """快速扫描函数"""
    scanner = RustScanAPI(target=target, ports=ports, **kwargs)
    return scanner.scan()


def full_scan(
    target: str,
    **kwargs
) -> Dict[str, List[int]]:
    """全端口扫描函数"""
    scanner = RustScanAPI(target=target, scan_range="1-65535", **kwargs)
    return scanner.scan()
