import subprocess


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
    ):
        """
        初始化扫描参数
        :param target: 扫描目标（IP/CIDR/域名）
        :param ports: 端口范围（示例: "80,443" 或 "1-1000"）
        :param ulimit: 文件描述符限制（避免资源不足）
        :param greppable: 启用易解析输出格式（避免ASCII艺术干扰）
        :param exclude_ip: 排除IP
        """
        self.rustscan_path = "./rustscan"
        self.target = target
        self.ports = ports
        self.ulimit = ulimit
        self.greppable = greppable
        self.exclude_ip = exclude_ip
        self.range = range
        self.nmap_enable = nmap_enable
        self.nmap_param = nmap_param

    def scan(self):
        """
        执行扫描并返回开放端口列表
        :return: 开放端口列表（如 [22, 80]）
        :raises RuntimeError: 扫描失败时抛出异常
        """
        try:
            if self.ports != "" and self.range == "":
                # 1. 构建命令
                cmd = [
                    self.rustscan_path,
                    "-a", self.target,
                    "-p", self.ports,
                    "-u", str(self.ulimit),
                    "-x", str(self.exclude_ip),
                    "-n"
                ]
            elif self.ports == "" and self.range != "":
                cmd = [
                    self.rustscan_path,
                    "-a", self.target,
                    "--range", self.range,
                    "-u", str(self.ulimit),
                    "-x", str(self.exclude_ip),
                ]
            else:
                raise ValueError("请指定端口范围或IP范围,端口范围和端口不能同时存在")

            if self.nmap_enable:
                cmd.append("--")
                if self.nmap_param != "":
                    cmd.append(self.nmap_param)
            else:
                if self.greppable:
                    cmd.append("-g")
            # 2. 执行扫描（禁用shell=True以提升安全性）[6](@ref)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,  # 非零退出码时抛出异常
            )

            # 3. 解析输出
            if not self.nmap_enable:
                opening_ports = self._parse_ports(result.stdout)
                return opening_ports
            else:
                return result.stdout

        except subprocess.CalledProcessError as e:
            err_msg = f"扫描失败！退出码: {e.returncode}\n错误输出: {e.stderr.strip() or '无'}"
            raise RuntimeError(err_msg) from e
        except FileNotFoundError:
            err_msg = "未在当前目录找到rustscan文件! "
            raise RuntimeError(err_msg)

    def _parse_ports(self, output: str):

        # 10.60.10.41 -> [8080,80,443,8081]

        import ast
        test = output.strip().splitlines()
        scan_result = {}
        for res in test:
            ip_port = res.split("->")
            ip, opening_ports = ip_port[0].strip(), ast.literal_eval(ip_port[1].strip())
            scan_result[ip] = sorted(opening_ports)
        scan_result = {k: scan_result[k] for k in sorted(scan_result)}
        return scan_result
