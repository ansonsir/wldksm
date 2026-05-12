import ast
import time
from pathlib import Path
from docxtpl import DocxTemplate
from ipaddress import ip_network, ip_address


class Report:
    def __init__(self, scan_datas, result_file, template_file, output_file):
        self.template_file = str(Path(__file__).parent / template_file)
        self.output_file = output_file
        self.result_file = result_file
        self.scan_datas = scan_datas
        self.ip_ports_dict = {}
        self.template_fields = {
            'report_date': "",
            'scan_start_time': "",
            'scan_end_time': "",
            'scan_duration': "",
            'ip_range': '',
            'ports': '',
            'total_devices_num': 0,
            'p_ftp_devices_num': 0,
            'p_ssh_devices_num': 0,
            'p_rdp_devices_num': 0,
            'p_db_devices_num': 0,
            'p_mqtt_devices_num': 0,
            'p_ftp_devices_info': '',
            'p_ssh_devices_info': '',
            'p_rdp_devices_info': '',
            'p_db_devices_info': '',
            'p_mqtt_devices_info': '',
        }
        self.ftp_port = {21}
        self.ssh_port = {22}
        self.rdp_port = {3389}
        self.db_port = {1433, 1521, 2181, 3306, 5432, 6379, 15672, 27017, }
        self.smb_port = {445}
        
        self.mqtt_port = {1883, 5672, 8161, 61616}

    def load_result_data(self):
        with open(self.result_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    # 分割 IP 和端口部分
                    if '  ' not in line:
                        continue
                    line_split = line.split('  ')
                    ip, ports_str = line_split[0], line_split[1]
                    ip = ip.strip()
                    ports = ast.literal_eval(ports_str.strip())

                    # 确保 ports 是列表或元组
                    if isinstance(ports, (list, tuple)):
                        self.ip_ports_dict.update({ip: ports})
                except (SyntaxError, ValueError) as e:
                    print(f"无法解析行: {line} -> 错误: {e}")
                    continue

    def Analysis_data(self):
        for ip, ports in self.ip_ports_dict.items():
            self.template_fields['total_devices_num'] += 1
            ports = set(ports)
            ftp_port_judge = ports & self.ftp_port
            ssh_port_judge = ports & self.ssh_port
            rdp_port_judge = ports & self.rdp_port
            db_port_judge = ports & self.db_port
            mqtt_port_judge = ports & self.mqtt_port
            if ftp_port_judge:
                self.template_fields['p_ftp_devices_num'] += 1
                self.template_fields['p_ftp_devices_info'] += f'{ip}\n'
            if ssh_port_judge:
                self.template_fields['p_ssh_devices_num'] += 1
                self.template_fields['p_ssh_devices_info'] += f'{ip}\n'
            if rdp_port_judge:
                self.template_fields['p_rdp_devices_num'] += 1
                self.template_fields['p_rdp_devices_info'] += f'{ip}\n'
            if db_port_judge:
                self.template_fields['p_db_devices_num'] += 1
                self.template_fields['p_db_devices_info'] += f'{ip}\n'
            if mqtt_port_judge:
                self.template_fields['p_mqtt_devices_num'] += 1
                self.template_fields['p_mqtt_devices_info'] += f'{ip}\n'
        if self.template_fields['p_ftp_devices_num'] == 0:
            self.template_fields['p_ftp_devices_num'] = "没有设备"
            self.template_fields['p_ftp_devices_info'] = "没有设备\n"
        else:
            self.template_fields['p_ftp_devices_num'] = f"共检测到{self.template_fields['p_ftp_devices_num']}台设备"
        if self.template_fields['p_ssh_devices_num'] == 0:
            self.template_fields['p_ssh_devices_num'] = "没有设备"
            self.template_fields['p_ssh_devices_info'] = "没有设备\n"
        else:
            self.template_fields['p_ssh_devices_num'] = f"共检测到{self.template_fields['p_ssh_devices_num']}台设备"
        if self.template_fields['p_rdp_devices_num'] == 0:
            self.template_fields['p_rdp_devices_num'] = "没有设备"
            self.template_fields['p_rdp_devices_info'] = "没有设备\n"
        else:
            self.template_fields['p_rdp_devices_num'] = f"共检测到{self.template_fields['p_rdp_devices_num']}台设备"
        if self.template_fields['p_db_devices_num'] == 0:
            self.template_fields['p_db_devices_num'] = "没有设备"
            self.template_fields['p_db_devices_info'] = "没有设备\n"
        else:
            self.template_fields['p_db_devices_num'] = f"共检测到{self.template_fields['p_db_devices_num']}台设备"
        if self.template_fields['p_mqtt_devices_num'] == 0:
            self.template_fields['p_mqtt_devices_num'] = "没有设备"
            self.template_fields['p_mqtt_devices_info'] = "没有设备\n"
        else:
            self.template_fields['p_mqtt_devices_num'] = f"共检测到{self.template_fields['p_mqtt_devices_num']}台设备"

        self.template_fields['scan_start_time'] = self.scan_datas["scan_start_time"]
        self.template_fields['scan_end_time'] = self.scan_datas["scan_end_time"]
        self.template_fields['scan_duration'] = self.scan_datas["scan_duration"]
        self.template_fields['ip_range'] = self.scan_datas["ip_range"]
        self.template_fields['ports'] = self.scan_datas["ports"]

    def generate_report(self):
        self.template_fields['report_date'] = time.strftime('%Y.%m.%d')
        self.load_result_data()
        self.Analysis_data()
        docx = DocxTemplate(self.template_file)
        docx.render(self.template_fields)
        docx.save(self.output_file)
