import twstock

def check_category():
    codes = ['2330', '2603', '2881', '1101'] # TSMC, Evergreen, Fubon, Cement
    print(f"Total codes known to twstock: {len(twstock.codes)}")
    
    for code in codes:
        if code in twstock.codes:
            stock_info = twstock.codes[code]
            print(f"{code} {stock_info.name}: Type={stock_info.type}, Concept={getattr(stock_info, 'concept', 'N/A')}, Group={getattr(stock_info, 'group', 'N/A')}")
        else:
            print(f"{code} not found")

if __name__ == "__main__":
    check_category()
