datas = '''
Open 10.1.66.220:80
Open 10.1.66.228:80
Open 10.1.66.220:135
Open 10.1.66.221:135
Open 10.1.66.222:135
Open 10.1.66.228:135
Open 10.1.66.230:135
Open 10.1.66.229:135
Open 10.1.66.220:139
Open 10.1.66.221:139
Open 10.1.66.222:139
Open 10.1.66.228:139
Open 10.1.66.229:139
Open 10.1.66.230:139
Open 10.1.66.229:445
Open 10.1.66.220:997
Open 10.1.66.228:997
Open 10.1.66.220:1801
Open 10.1.66.220:2103
Open 10.1.66.220:2105
Open 10.1.66.220:2107
Open 10.1.66.221:4002
Open 10.1.66.229:4118
Open 10.1.66.230:4118
Open 10.1.66.221:5040
Open 10.1.66.228:5040
Open 10.1.66.229:5040
Open 10.1.66.230:5040
Open 10.1.66.222:5040
Open 10.1.66.220:5357
Open 10.1.66.221:5357
Open 10.1.66.222:5357
Open 10.1.66.228:5357
Open 10.1.66.220:5985
Open 10.1.66.229:6061
Open 10.1.66.221:6098
Open 10.1.66.229:6098
Open 10.1.66.221:6099
Open 10.1.66.229:6099
Open 10.1.66.220:6688
Open 10.1.66.228:6688
Open 10.1.66.230:7680
Open 10.1.66.228:8000
Open 10.1.66.220:15120
Open 10.1.66.228:15120
Open 10.1.66.221:18120
Open 10.1.66.229:18120
Open 10.1.66.221:18121
Open 10.1.66.229:18121
Open 10.1.66.220:47001
Open 10.1.66.220:47361
Open 10.1.66.228:47361
Open 10.1.66.220:47363
Open 10.1.66.228:47363
Open 10.1.66.221:49664
Open 10.1.66.220:49664
Open 10.1.66.222:49664
Open 10.1.66.228:49664
Open 10.1.66.229:49664
Open 10.1.66.230:49664
Open 10.1.66.220:49665
Open 10.1.66.221:49665
Open 10.1.66.222:49665
Open 10.1.66.228:49665
Open 10.1.66.229:49665
Open 10.1.66.230:49665
Open 10.1.66.220:49666
Open 10.1.66.222:49666
Open 10.1.66.221:49666
Open 10.1.66.229:49666
Open 10.1.66.228:49666
Open 10.1.66.230:49666
Open 10.1.66.220:49667
Open 10.1.66.221:49667
Open 10.1.66.222:49667
Open 10.1.66.228:49667
Open 10.1.66.229:49667
Open 10.1.66.230:49667
Open 10.1.66.220:49668
Open 10.1.66.222:49668
Open 10.1.66.221:49668
Open 10.1.66.229:49668
Open 10.1.66.228:49668
Open 10.1.66.230:49668
Open 10.1.66.220:49669
Open 10.1.66.221:49669
Open 10.1.66.222:49669
Open 10.1.66.229:49669
Open 10.1.66.228:49669
Open 10.1.66.230:49669
Open 10.1.66.220:49670
Open 10.1.66.222:49670
Open 10.1.66.221:49670
Open 10.1.66.230:49670
Open 10.1.66.222:49671
Open 10.1.66.228:49671
Open 10.1.66.230:49671
Open 10.1.66.221:49672
Open 10.1.66.229:49677
Open 10.1.66.229:49687
Open 10.1.66.220:49698
Open 10.1.66.228:49803
Open 10.1.66.220:49868
Open 10.1.66.222:63389
Open 10.1.66.221:63389
Open 10.1.66.229:63389
Open 10.1.66.230:63389
'''
data_line = datas.splitlines()
data_map = {}
ports = set()
ports_count = {}
for line in data_line:
    if len(line) == 0:
        continue
    data = line.split(' ')
    ip_port = data[1].split(':')
    ip = ip_port[0]
    port = ip_port[1]
    if ip not in data_map:
        data_map[ip] = []
    if port not in ports_count:
        ports_count[port] = 0
    data_map[ip].append(port)
    ports.add(int(port))
    ports_count[port] += 1
data_map = dict(sorted(data_map.items()))
for k,v in data_map.items():
    print(f'IP:{k}')
    print(f'Ports:')
    for port in v:
        print(f'{port}',end=' ')
    print()
ports = sorted(ports)
print(ports)
for port in ports:
    print(f'{port}:{ports_count[str(port)]}')