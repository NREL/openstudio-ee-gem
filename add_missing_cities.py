import csv

# 基于研究和现有数据的推断，为15个缺失城市添加信息
new_cities = [
    {
        'Location Name': 'Fairbanks',
        'State': 'AK',
        'BA Area': 'ALASKA SYSTEMS COORDINATING COUNCIL',
        'BA Area (Short)': 'ASCC',
        'CO2 Rate': '1,245.00',
        'Climate Zone': '8',
        'Weather File': 'weather/AK_Fairbanks/USA_AK_Fairbanks.Intl.AP.702610_TMYx.epw'
    },
    {
        'Location Name': 'San Francisco',
        'State': 'CA',
        'BA Area': 'CALIFORNIA INDEPENDENT SYSTEM OPERATOR',
        'BA Area (Short)': 'CISO',
        'CO2 Rate': '370.651',
        'Climate Zone': '3C',
        'Weather File': 'weather/CA_San_Francisco/USA_CA_San.Francisco.Intl.AP.724940_TMYx.epw'
    },
    {
        'Location Name': 'Denver',
        'State': 'CO',
        'BA Area': 'PUBLIC SERVICE COMPANY OF COLORADO',
        'BA Area (Short)': 'PSCO',
        'CO2 Rate': '806.261',
        'Climate Zone': '5B',
        'Weather File': 'weather/CO_Denver/USA_CO_Denver.Intl.AP.725650_TMYx.epw'
    },
    {
        'Location Name': 'Miami Executive',
        'State': 'FL',
        'BA Area': 'FLORIDA POWER & LIGHT COMPANY',
        'BA Area (Short)': 'FPL',
        'CO2 Rate': '598.609',
        'Climate Zone': '1A',
        'Weather File': 'weather/FL_Miami_Exec/USA_FL_Miami.Exec.AP.722029_TMYx.epw'
    },
    {
        'Location Name': 'Rockford',
        'State': 'IL',
        'BA Area': 'PJM INTERCONNECTION, LLC',
        'BA Area (Short)': 'PJM',
        'CO2 Rate': '719.405',
        'Climate Zone': '5A',
        'Weather File': 'weather/IL_Chicago_Rockford/USA_IL_Rockford-Chicago.Rockford.Intl.AP.725430_TMYx.epw'
    },
    {
        'Location Name': 'Baltimore',
        'State': 'MD',
        'BA Area': 'PJM INTERCONNECTION, LLC',
        'BA Area (Short)': 'PJM',
        'CO2 Rate': '719.405',
        'Climate Zone': '4A',
        'Weather File': 'weather/MD_Baltimore/USA_MD_Baltimore-Washington.Intl-Marshall.AP.724060_TMYx.epw'
    },
    {
        'Location Name': 'Bangor',
        'State': 'ME',
        'BA Area': 'ISO NEW ENGLAND INC.',
        'BA Area (Short)': 'ISNE',
        'CO2 Rate': '545.267',
        'Climate Zone': '6A',
        'Weather File': 'weather/ME_Bangor/USA_ME_Bangor.Intl.AP.726070_TMYx.epw'
    },
    {
        'Location Name': 'Duluth',
        'State': 'MN',
        'BA Area': 'MIDCONTINENT INDEPENDENT TRANSMISSION SYSTEM OPERATOR, INC..',
        'BA Area (Short)': 'MISO',
        'CO2 Rate': '987.438',
        'Climate Zone': '7',
        'Weather File': 'weather/MN_Duluth/USA_MN_Duluth.Intl.AP-Duluth.ANGB.727450_TMYx.epw'
    },
    {
        'Location Name': 'Minneapolis',
        'State': 'MN',
        'BA Area': 'MIDCONTINENT INDEPENDENT TRANSMISSION SYSTEM OPERATOR, INC..',
        'BA Area (Short)': 'MISO',
        'CO2 Rate': '987.438',
        'Climate Zone': '6A',
        'Weather File': 'weather/MN_Minneapolis/USA_MN_Minneapolis-Crystal.AP.726575_TMYx.epw'
    },
    {
        'Location Name': 'Helena',
        'State': 'MT',
        'BA Area': 'NORTHWESTERN ENERGY (NWMT)',
        'BA Area (Short)': 'NWMT',
        'CO2 Rate': '1,594.72',
        'Climate Zone': '6B',
        'Weather File': 'weather/MT_Helena/USA_MT_Helena.Rgnl.AP.727720_TMYx.epw'
    },
    {
        'Location Name': 'Buffalo',
        'State': 'NY',
        'BA Area': 'NEW YORK INDEPENDENT SYSTEM OPERATOR',
        'BA Area (Short)': 'NYIS',
        'CO2 Rate': '480.66',
        'Climate Zone': '5A',
        'Weather File': 'weather/NY_Buffalo/USA_NY_Buffalo-Greater.Buffalo.Intl.AP.725280_TMY3.epw'
    },
    {
        'Location Name': 'Portland',
        'State': 'OR',
        'BA Area': 'BONNEVILLE POWER ADMINISTRATION',
        'BA Area (Short)': 'BPAT',
        'CO2 Rate': '213.65',
        'Climate Zone': '4C',
        'Weather File': 'weather/OR_Portland/USA_OR_Portland.Intl.AP.726980_TMYx.epw'
    },
    {
        'Location Name': 'Amarillo',
        'State': 'TX',
        'BA Area': 'SOUTHWEST POWER POOL',
        'BA Area (Short)': 'SWPP',
        'CO2 Rate': '876.354',
        'Climate Zone': '3B',
        'Weather File': 'weather/TX_Amarillo/USA_TX_Amarillo-Husband.Amarillo.Intl.AP.723630_TMYx.epw'
    },
    {
        'Location Name': 'Port Angeles',
        'State': 'WA',
        'BA Area': 'BONNEVILLE POWER ADMINISTRATION',
        'BA Area (Short)': 'BPAT',
        'CO2 Rate': '213.65',
        'Climate Zone': '4C',
        'Weather File': 'weather/WA_Port_Angeles/USA_WA_Port.Angeles.994024_TMYx.epw'
    },
    {
        'Location Name': 'Seattle',
        'State': 'WA',
        'BA Area': 'BONNEVILLE POWER ADMINISTRATION',
        'BA Area (Short)': 'BPAT',
        'CO2 Rate': '213.65',
        'Climate Zone': '4C',
        'Weather File': 'weather/WA_Seattle/USA_WA_Seattle-Tacoma.Intl.AP.727930_TMYx.epw'
    }
]

# 读取现有CSV
csv_file = r'c:\All repos\openstudio-ee-gem\lib\measures\OperatingCostCarbonReportingMeasure\resources\BA_area_match_state_location.csv'

with open(csv_file, 'r', encoding='utf-8-sig') as f:  # 使用utf-8-sig处理BOM
    reader = csv.DictReader(f)
    existing_data = list(reader)
    fieldnames = reader.fieldnames

# 添加新城市
for city in new_cities:
    new_row = {
        'Location Name': city['Location Name'],
        'State': city['State'],
        'BA Area': city['BA Area'],
        'BA Area (Short)': city['BA Area (Short)'],
        'BA annual CO2 equivalent total output emission rate (lb/MWh)': city['CO2 Rate'],
        'Climate Zone': city['Climate Zone'],
        'Weather File Location': city['Weather File']
    }
    existing_data.append(new_row)

# 按州和城市名排序
existing_data.sort(key=lambda x: (x['State'], x['Location Name']))

# 写回CSV到临时文件
temp_file = csv_file.replace('.csv', '_updated.csv')
with open(temp_file, 'w', encoding='utf-8', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(existing_data)

print(f'已成功添加 {len(new_cities)} 个城市')
print(f'新CSV文件现在包含 {len(existing_data)} 个城市')
print(f'\n结果已保存到: {temp_file}')
print('请关闭原CSV文件后，用新文件替换它。')
print('\n新添加的城市:')
for i, city in enumerate(new_cities, 1):
    print(f'{i:2d}. {city["Location Name"]:20s} {city["State"]} - BA: {city["BA Area (Short)"]:6s} - CZ: {city["Climate Zone"]:3s}')
