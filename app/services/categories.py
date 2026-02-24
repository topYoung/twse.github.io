import twstock

# 手動維護的精細分類 (優先級最高)
MANUAL_SUB_CATEGORIES = {
    # === 半導體產業細分 ===
    # 晶圓代工 (Foundry)
    '2330': '晶圓代工', '2303': '晶圓代工', '6770': '晶圓代工', '5347': '晶圓代工',
    # ... (保留原本的字典內容，但在程式碼中用變數區隔) ...
}
# 為了避免 replace_file_content 太大，這裡我採取 "Append Strategy" 或是 "Full Rewrite if file small enough".
# The file is ~120 lines. I can rewrite the top part and add the logic at the bottom.

# Plan:
# 1. Keep manual lists as "MANUAL_..."
# 2. Add logic to build the final lists.

# Technology Sector Categories to include
TECH_SECTOR_NAMES = [
    '半導體業', '電腦及週邊設備業', '光電業', '通信網路業', 
    '電子零組件業', '電子通路業', '資訊服務業', '其他電子業'
]

DELISTED_STOCKS = [
    '3698', '4945', '5383', '6457', '3202', '2311', '6514', '6404'
]

def get_all_tech_stocks():
    stocks = []
    # Dynamic Map for fallback categories
    dynamic_map = {}
    
    for code, info in twstock.codes.items():
        if info.type == '股票' and code not in DELISTED_STOCKS:
            # Check if in tech sectors
            if info.group in TECH_SECTOR_NAMES:
                # Add suffix for yfinance
                # Actually our system uses pure codes in these lists usually, and adds suffix in stock_data.py?
                # Let's check `categories.py` format. It uses strings like '2330'.
                stocks.append(code)
                
                # Create shorthand category (remove '業')
                cat_name = info.group.replace('業', '')
                dynamic_map[code] = cat_name
                
    return stocks, dynamic_map

_tech_stocks, _tech_category_map = get_all_tech_stocks()

# Public Lists
TECH_STOCKS = _tech_stocks

# Traditional Sector (Cement, Plastics, Steel, Finance, Shipping, etc.)
TRAD_STOCKS = [
    '1101', '1301', '1303', '2002', '2881', '2882', '2891', '2886', '2884', '2885',
    '2890', '2892', '5880', '2880', '2883', '2887', '1102', '1216', '1402', '1326',
    '2105', '2603', '2609', '2615', '2912', '9904', '2049', '1907', '1717',
    '2801', '2812', '2834', '2838', '2845', '2849', '2850', '2851', '2852', '2855',
    '1103', '1104', '1108', '1109', '1110', '1201', '1203', '1210', '1213', '1215',
    '1304', '1305', '1307', '1308', '1309', '1310', '1312', '1313', '1314', '1315',
    '1409', '1410', '1413', '1414', '1416', '1417', '1418', '1419', '1423', '1432',
    '1503', '1504', '1506', '1512', '1513', '1514', '1515', '1516', '1517'
]

MANUAL_SUB_CATEGORIES = {
    # === 半導體產業細分 ===
    # 晶圓代工 (Foundry)
    '2330': '晶圓代工', '2303': '晶圓代工', '6770': '晶圓代工', '5347': '晶圓代工',
    
    # 記憶體 (Memory)
    '2408': '記憶體', '2344': '記憶體', '2337': '記憶體', '3260': '記憶體', '8299': '記憶體',
    
    # IC設計 (IC Design)
    '2454': 'IC設計', '3443': 'IC設計', '3034': 'IC設計', '2379': 'IC設計', '3661': 'IC設計',
    '3035': 'IC設計', '6415': 'IC設計', '6285': 'IC設計', '3529': 'IC設計',
    '6488': 'IC設計', '3169': 'IC設計', '4966': 'IC設計', '6271': 'IC設計',
    
    # IC通路 (IC Distributor)
    '8096': 'IC通路', '3702': 'IC通路', '3036': 'IC通路', '8112': 'IC通路',
    '3048': 'IC通路', '3055': 'IC通路',
    
    # 封測 (Package & Test)
    '3711': '封測', '2369': '封測', '3450': '封測', '3481': '封測',
    
    # 半導體設備/材料 (Equipment)
    '3707': '半導體設備', '5274': '半導體設備', '3227': '半導體設備', '4979': '半導體設備',
    
    # === 電子產業細分 ===
    # 被動元件 (Passive Components)
    '2327': '被動元件', '2329': '被動元件', '2331': '被動元件', '3481': '被動元件',
    
    # PCB
    '2313': 'PCB', '3008': 'PCB', '8046': 'PCB', '3006': 'PCB', '6269': 'PCB',
    
    # 面板 (Display)
    '2409': '面板', '3481': '面板', '6116': '面板',
    
    # 光學/鏡頭 (Optics)
    '3008': '光學', '3673': '光學', '2317': '光學', '6464': '光學',
    
    # 連接器/線材 (Connector)
    '2049': '連接器', '3706': '連接器', '6414': '連接器',
    
    # === 電腦/網通 ===
    # AI伺服器/組裝 (AI Server)
    '2382': 'AI伺服器', '3231': 'AI伺服器', '2356': 'AI伺服器', '2301': 'AI伺服器', 
    '6669': 'AI伺服器', '2324': 'AI伺服器', '2357': 'AI伺服器',
    
    # 矽光子/CPO (Silicon Photonics)
    '2345': '矽光子', '3081': '矽光子', '3363': '矽光子', '6451': '矽光子', '4908': '矽光子',
    
    # 網通設備 (Networking)
    '2345': '網通', '2340': '網通', '3044': '網通', '2393': '網通',
    
    # === 金融產業細分 ===
    # 銀行 (Banking)
    '2881': '銀行', '2882': '銀行', '2883': '銀行', '2884': '銀行', '2885': '銀行',
    '2886': '銀行', '2887': '銀行', '2888': '銀行', '2889': '銀行', '2890': '銀行',
    '2891': '銀行', '2892': '銀行', '5880': '銀行', '2880': '銀行',
    
    # 保險 (Insurance)
    '2801': '保險', '2823': '保險', '2832': '保險', '2834': '保險', '2851': '保險',
    '2867': '保險', '2812': '保險',
    
    # 證券 (Securities)
    '2855': '證券', '2856': '證券', '6024': '證券',
    
    # === 傳統產業細分 ===
    # 航運 (Shipping)
    '2603': '航運', '2609': '航運', '2615': '航運', '2605': '航運', '2606': '航運',
    '2607': '航運', '2608': '航運', '2610': '航運', '2618': '航運',
    
    # 塑化 (Petrochemical)
    '1301': '塑化', '1303': '塑化', '1326': '塑化', '6505': '塑化', '1308': '塑化',
    
    # 鋼鐵 (Steel)
    '2002': '鋼鐵', '2006': '鋼鐵', '2024': '鋼鐵', '2027': '鋼鐵', '2029': '鋼鐵',
    
    # 水泥 (Cement)
    '1101': '水泥', '1102': '水泥', '1103': '水泥', '1104': '水泥',
    
    # 重電/機電 (Heavy Electric)
    '1513': '重電', '1519': '重電', '1503': '重電', '1514': '重電', '1504': '重電',
    
    # 食品 (Food)
    '1216': '食品', '1229': '食品', '1231': '食品', '1232': '食品', '1233': '食品',
    
    # === 能源/電力 ===
    '9958': '能源', '3708': '能源', '6806': '能源', '6443': '能源', '6412': '能源',
    
    # === 生技醫療 ===
    '4174': '生技', '6446': '生技', '6547': '生技', '4107': '生技', '6496': '生技',
    
    # === 營建/地產 ===
    '2542': '營建', '5522': '營建', '2548': '營建', '2501': '營建', '9945': '營建',
}


# Final Category Map (Merge dynamic and manual)
# Priority: Manual > Dynamic
STOCK_SUB_CATEGORIES = _tech_category_map.copy()
STOCK_SUB_CATEGORIES.update(MANUAL_SUB_CATEGORIES)
