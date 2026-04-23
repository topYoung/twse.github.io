from app.services.categories import TECH_STOCKS, TRAD_STOCKS, STOCK_SUB_CATEGORIES, TECH_SECTOR_NAMES, MANUAL_SUB_CATEGORIES
import twstock

group_count = {}
for code in TECH_STOCKS:
    if code in twstock.codes:
        g = twstock.codes[code].group
        group_count[g] = group_count.get(g, 0) + 1

print('=== TECH_STOCKS 來源分類（twstock.group）===')
for g, cnt in sorted(group_count.items(), key=lambda x: -x[1]):
    print(f'  {g}: {cnt}支')

print()
print('=== TECH_SECTOR_NAMES（目前掃描對象）===')
for n in TECH_SECTOR_NAMES:
    print(f'  {n}')

print()
print(f'TECH_STOCKS 總計: {len(TECH_STOCKS)} 支')
print(f'TRAD_STOCKS 總計: {len(TRAD_STOCKS)} 支')

tech_sub = ['晶圓代工','IC設計','IC通路','記憶體','封測','半導體設備',
            'AI伺服器','被動元件','PCB','矽光子','網通','光學','連接器','面板']
tech_manual = {k: v for k, v in MANUAL_SUB_CATEGORIES.items() if v in tech_sub}
print()
print(f'MANUAL_SUB_CATEGORIES 中科技子類股數: {len(tech_manual)} 支')

print()
print('=== MANUAL_SUB_CATEGORIES 所有子分類統計 ===')
sub_count = {}
for v in MANUAL_SUB_CATEGORIES.values():
    sub_count[v] = sub_count.get(v, 0) + 1
for k, cnt in sorted(sub_count.items(), key=lambda x: -x[1]):
    print(f'  {k}: {cnt}支')
