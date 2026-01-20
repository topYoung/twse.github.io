import twstock

def check_groups():
    target_stocks = {
        '2330': 'TSMC (Semi)',
        '2408': 'Nanya (Memory)',
        '2344': 'Winbond (Memory)', 
        '1513': 'Chung Hsin (Heavy Electric)',
        '1519': 'Fortune (Heavy Electric)',
        '3711': 'ASE (Semi/SiC?)',
        '2303': 'UMC (Semi)',
        '6805': 'Frontera (Energy?)',
        '3023': 'Sinbon (Component)',
    }
    
    print("Checking twstock groups:")
    for code, desc in target_stocks.items():
        if code in twstock.codes:
            print(f"{code} ({desc}): {twstock.codes[code].group}")
        else:
            print(f"{code} ({desc}): Not found in twstock")

if __name__ == "__main__":
    check_groups()
