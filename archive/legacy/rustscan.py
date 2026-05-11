import subprocess
import ast
import logging


class RustScanAPI:
    def __init__(
            self,
            target: str,
            ports: str = "",
            range: str = "",
            ulimit: int = 5000,
            greppable: bool = True,
            exclude_ip: str = "",
            nmap_enable: bool = False,
            nmap_param: str = "",
            rustscan_path: str = "./rustscan"
    ):
        """
        初始化扫描参数
        :param target: 扫描目标（IP/CIDR/域名）
        :param ports: 端口范围（示例: "80,443" 或 "1-1000"）
        :param range: IP范围（示例: "10.0.0.0-10.0.0.255"）
        :param ulimit: 文件描述符限制（避免资源不足，默认5000）
        :param greppable: 启用易解析输出格式（避免ASCII艺术干扰）
        :param exclude_ip: 排除的IP地址，多个IP用逗号分隔
        :param nmap_enable: 是否启用nmap进行深度扫描
        :param nmap_param: nmap的额外参数
        :param rustscan_path: rustscan可执行文件路径
        """
        # 参数验证
        if not target:
            raise ValueError("target参数不能为空")
        if not ports and not range:
            raise ValueError("必须指定ports或range参数之一")
        if ports and range:
            raise ValueError("ports和range参数不能同时指定")
        
        self.rustscan_path = rustscan_path
        self.target = target
        self.ports = ports
        self.ulimit = ulimit
        self.greppable = greppable
        self.exclude_ip = exclude_ip
        self.range = range
        self.nmap_enable = nmap_enable
        self.nmap_param = nmap_param
        self.logger = logging.getLogger(self.__class__.__name__)

    def scan(self):
        """
        执行扫描并返回开放端口列表
        :return: 如果nmap_enable=False，返回字典{IP: [端口列表]}；否则返回nmap原始输出
        :raises RuntimeError: 扫描失败时抛出异常
        """
        try:
            # 构建基础命令
            cmd = self._build_command()
            
            self.logger.info(f"执行扫描命令: {' '.join(cmd)}")
            
            # 执行扫描（禁用shell=True以提升安全性）
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,  # 非零退出码时抛出异常
            )

            # 解析输出
            if not self.nmap_enable:
                if not result.stdout.strip():
                    self.logger.warning("扫描结果为空")
                    return {}
                opening_ports = self._parse_ports(result.stdout)
                return opening_ports
            else:
                return result.stdout

        except subprocess.CalledProcessError as e:
            err_msg = f"扫描失败！退出码: {e.returncode}\n错误输出: {e.stderr.strip() or '无'}"
            self.logger.error(err_msg)
            raise RuntimeError(err_msg) from e
        except FileNotFoundError:
            err_msg = f"未找到rustscan文件: {self.rustscan_path}"
            self.logger.error(err_msg)
            raise RuntimeError(err_msg)
    
    def _build_command(self):
        """
        构建rustscan命令
        :return: 命令列表
        """
        # 基础命令
        cmd = [
            self.rustscan_path,
            "-a", self.target,
            "-u", str(self.ulimit),
        ]
        
        # 添加端口或范围参数
        if self.ports:
            cmd.extend(["-p", self.ports])
            cmd.append("-n")  # 禁用端口扫描的nmap集成
        elif self.range:
            cmd.extend(["--range", self.range])
        
        # 添加排除IP（仅当非空时）
        if self.exclude_ip:
            cmd.extend(["-x", self.exclude_ip])
        
        # nmap集成选项
        if self.nmap_enable:
            cmd.append("--")
            if self.nmap_param:
                cmd.append(self.nmap_param)
        else:
            if self.greppable:
                cmd.append("-g")
        
        return cmd

    def _parse_ports(self, output: str):
        """
        解析rustscan的greppable输出格式
        :param output: rustscan的输出字符串（格式: "IP -> [端口列表]"）
        :return: 字典{IP: [端口列表]}，按IP排序
        """
        # 示例输出格式: 10.60.10.41 -> [8080,80,443,8081]
        scan_lines = output.strip().splitlines()
        scan_result = {}
        
        for line in scan_lines:
            try:
                # 检查行格式
                if "->" not in line:
                    self.logger.warning(f"跳过格式不正确的行: {line}")
                    continue
                
                ip_port_parts = line.split("->", 1)
                if len(ip_port_parts) != 2:
                    self.logger.warning(f"跳过无法解析的行: {line}")
                    continue
                
                ip = ip_port_parts[0].strip()
                ports_str = ip_port_parts[1].strip()
                
                # 使用ast.literal_eval安全解析端口列表
                opening_ports = ast.literal_eval(ports_str)
                
                # 确保端口列表是有效的
                if not isinstance(opening_ports, (list, tuple)):
                    self.logger.warning(f"端口数据格式错误: {ports_str}")
                    continue
                
                scan_result[ip] = sorted(opening_ports)
                
            except (ValueError, SyntaxError) as e:
                self.logger.error(f"解析行失败: {line}, 错误: {e}")
                continue
        
        # 按IP地址排序返回
        scan_result = {k: scan_result[k] for k in sorted(scan_result)}
        return scan_result
