import time

from report import Report

scan_data = {
    "scan_start_time": "2025-10-14 15:12:06",
    "scan_end_time": "2025-10-14 19:58:07",
    "scan_duration": "4小时46分钟",
    "ip_range": "10.0.0.0/8\n172.16.0.0/12\n192.168.0.0/16",
    "ports": "21,22,23,80,443,445,873,1433,1521,1883,2181,2375,3306,3389,5236,5432,\n5672,5900,5901,5902,5903,5904,5905,6379,7001,8080,8081,8082,8088,11211,\n8161,8443,8848,8888,9200,15672,27017,54321,61616"
}
output_file = f"{time.strftime('%Y.%m.%d')}网络高危端口扫描报告.docx"
report = Report(scan_data, "scan_results.txt", "template.docx", output_file, "redArea_ips.txt")
report.generate_report()
