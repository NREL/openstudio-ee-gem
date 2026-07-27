import csv
from collections import defaultdict

# 读取emissions.csv
emissions_file = r'c:\All repos\openstudio-ee-gem\lib\measures\OperatingCostCarbonReportingMeasure\resources\emissions.csv'

with open(emissions_file, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    data = list(reader)

print(f'emissions.csv 包含 {len(data)} 行BA数据\n')

# 按weather_file_location分组
location_to_bas = defaultdict(list)

for row in data:
    location = row.get('weather_file_location', '').strip()
    ba_code = row.get('Balancing Authority Code', '').strip()
    ba_name = row.get('Balancing Authority Name', '').strip()
    emission_rate = row.get('BA annual CO2 equivalent total output emission rate (lb/MWh)', '').strip()
    
    if location and ba_code and ba_code != 'BACODE':  # 跳过表头
        location_to_bas[location].append({
            'ba_code': ba_code,
            'ba_name': ba_name,
            'emission_rate': emission_rate
        })

print(f'不同的城市位置数量: {len(location_to_bas)}\n')

# 找出有多个BA的城市
print('有多个BA的城市:')
print('=' * 100)
multi_ba_count = 0
for location, bas in sorted(location_to_bas.items()):
    if len(bas) > 1:
        multi_ba_count += 1
        print(f'\n{location}:')
        for ba in bas[:10]:  # 只显示前10个
            print(f'  - {ba["ba_code"]:10s} {ba["ba_name"][:50]:50s} (排放率: {ba["emission_rate"]})')
        if len(bas) > 10:
            print(f'  ... 还有 {len(bas) - 10} 个BA')
        
if multi_ba_count == 0:
    print('  （没有城市有多个BA）')

print(f'\n总共有 {multi_ba_count} 个城市对应多个BA')
print(f'平均每个城市有 {sum(len(bas) for bas in location_to_bas.values()) / len(location_to_bas):.2f} 个BA')
