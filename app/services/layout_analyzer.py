"""
三大法人佈局分析模組
分析法人對個股的買賣模式，識別長期佈局的股票
"""

from typing import Dict, List, Tuple
from collections import defaultdict
import statistics
from .institutional_data import fetch_historical_data, INVESTOR_NAMES
from .categories import STOCK_SUB_CATEGORIES
import twstock


def analyze_stock_pattern(stock_code: str, historical_data: Dict[str, List[Dict]]) -> Dict:
    """
    分析特定股票的法人買賣模式
    
    Args:
        stock_code: 股票代碼
        historical_data: 歷史資料字典 {date: [股票資料]}
    
    Returns:
        分析結果字典
    """
    buy_days = 0
    sell_days = 0
    neutral_days = 0
    buy_volumes = []
    sell_volumes = []
    total_net = 0
    stock_name = ""
    
    total_trading_days = len(historical_data)
    
    for date_str, stocks in historical_data.items():
        # 找到該股票在當日的資料
        stock_data = next((s for s in stocks if s['stock_code'] == stock_code), None)
        
        if stock_data:
            stock_name = stock_data['stock_name']
            net = stock_data['net']
            total_net += net
            
            if net > 0:
                buy_days += 1
                buy_volumes.append(net)
            elif net < 0:
                sell_days += 1
                sell_volumes.append(abs(net))
            else:
                neutral_days += 1
    
    # 計算統計指標
    avg_buy_volume = statistics.mean(buy_volumes) if buy_volumes else 0
    avg_sell_volume = statistics.mean(sell_volumes) if sell_volumes else 0
    buy_volume_std = statistics.stdev(buy_volumes) if len(buy_volumes) > 1 else 0
    
    # 買入穩定性：標準差越小，穩定性越高
    stability = 1 / (1 + buy_volume_std / avg_buy_volume) if avg_buy_volume > 0 else 0
    
    return {
        'stock_code': stock_code,
        'stock_name': stock_name,
        'total_trading_days': total_trading_days,
        'buy_days': buy_days,
        'sell_days': sell_days,
        'neutral_days': neutral_days,
        'total_net': total_net,
        'avg_buy_volume': round(avg_buy_volume, 2),
        'avg_sell_volume': round(avg_sell_volume, 2),
        'stability': round(stability, 4)
    }


def calculate_layout_score(pattern: Dict) -> float:
    """
    計算佈局評分（0-100分）
    
    評分標準：
    - 買入頻率分數（40%）：買入天數 / 總交易天數
    - 累積買超分數（30%）：總淨買超 > 0 得分，越大越高
    - 穩定性分數（20%）：買入量標準差的倒數
    - 持續性分數（10%）：總淨買超必須 > 0
    """
    total_days = pattern['total_trading_days']
    buy_days = pattern['buy_days']
    sell_days = pattern['sell_days']
    total_net = pattern['total_net']
    stability = pattern['stability']
    
    if total_days == 0:
        return 0
    
    # 1. 買入頻率分數（0-40分）
    buy_frequency = buy_days / total_days
    frequency_score = buy_frequency * 40
    
    # 2. 累積買超分數（0-30分）
    # 只有淨買超才給分
    if total_net > 0:
        # 正規化：假設買超 10 萬張為滿分
        net_score = min(total_net / 100000, 1.0) * 30
    else:
        net_score = 0
    
    # 3. 穩定性分數（0-20分）
    stability_score = stability * 20
    
    # 4. 持續性分數（0-10分）
    # 檢查是否有持續買超（買入天數 > 賣出天數）
    if buy_days > sell_days and total_net > 0:
        consistency_score = 10
    else:
        consistency_score = 0
    
    total_score = frequency_score + net_score + stability_score + consistency_score
    
    return round(total_score, 2)


def get_layout_stocks(investor_type: str, days: int = 90, min_score: float = 30.0, top_n: int = 50) -> List[Dict]:
    """
    取得被法人佈局的股票清單
    
    Args:
        investor_type: 'foreign', 'trust', 或 'dealer'
        days: 回溯天數（預設90天）
        min_score: 最低評分門檻
        top_n: 回傳前N檔股票
    
    Returns:
        股票清單，依評分排序
    """
    # 獲取歷史資料
    historical_data = fetch_historical_data(investor_type, days)
    
    if not historical_data:
        return []
    
    # 收集所有股票代碼
    all_stocks = set()
    for stocks in historical_data.values():
        for stock in stocks:
            all_stocks.add(stock['stock_code'])
    
    print(f"分析 {len(all_stocks)} 檔股票的 {INVESTOR_NAMES[investor_type]} 佈局模式...")
    
    # 分析每檔股票
    results = []
    for stock_code in all_stocks:
        pattern = analyze_stock_pattern(stock_code, historical_data)
        score = calculate_layout_score(pattern)
        
        # 只保留評分達標的股票
        if score >= min_score:
            pattern['layout_score'] = score
            
            # Add Category
            category = '其他'
            if stock_code in STOCK_SUB_CATEGORIES:
                category = STOCK_SUB_CATEGORIES[stock_code]
            elif stock_code in twstock.codes:
                 category_info = twstock.codes[stock_code]
                 if category_info.group:
                     category = category_info.group.replace('業', '')
            
            pattern['category'] = category
            
            results.append(pattern)
    
    # 依評分排序
    results.sort(key=lambda x: x['layout_score'], reverse=True)
    
    print(f"找到 {len(results)} 檔評分 >= {min_score} 的股票")
    
    # 回傳前N檔
    return results[:top_n]


def get_stock_layout_detail(stock_code: str, investor_type: str, days: int = 90) -> Dict:
    """
    取得特定股票的詳細佈局資訊
    
    Returns:
        {
            'stock_code': 股票代碼,
            'stock_name': 股票名稱,
            'investor_type': 法人類型,
            'investor_name': 法人名稱,
            'pattern': 買賣模式,
            'layout_score': 佈局評分,
            'daily_data': 每日買賣資料
        }
    """
    historical_data = fetch_historical_data(investor_type, days)
    
    pattern = analyze_stock_pattern(stock_code, historical_data)
    score = calculate_layout_score(pattern)
    
    # 收集每日資料
    daily_data = []
    for date_str, stocks in sorted(historical_data.items()):
        stock_data = next((s for s in stocks if s['stock_code'] == stock_code), None)
        if stock_data:
            daily_data.append({
                'date': date_str,
                'net': stock_data['net'],
                'buy': stock_data['buy'],
                'sell': stock_data['sell']
            })
    
    return {
        'stock_code': stock_code,
        'stock_name': pattern['stock_name'],
        'investor_type': investor_type,
        'investor_name': INVESTOR_NAMES[investor_type],
        'pattern': pattern,
        'layout_score': score,
        'daily_data': daily_data
    }


def get_all_investors_summary(days: int = 30) -> List[Dict]:
    """
    取得所有法人的摘要資訊
    
    Returns:
        [
            {
                'type': 'foreign',
                'name': '外資',
                'total_net_shares': 總買超股數,
                'active_stocks': 活躍股票數,
                'buy_days': 買超天數,
                'sell_days': 賣超天數
            },
            ...
        ]
    """
    from .institutional_data import get_investor_summary
    
    investors = ['foreign', 'trust', 'dealer']
    summaries = []
    
    for investor_type in investors:
        try:
            summary = get_investor_summary(investor_type, days)
            summaries.append(summary)
        except Exception as e:
            print(f"獲取 {investor_type} 摘要失敗: {e}")
            continue
    
    return summaries


def get_multi_investor_layout(mode: str = 'all-3', days: int = 90, min_score: float = 30.0, top_n: int = 50) -> List[Dict]:
    """
    取得多法人同時佈局的股票
    
    Args:
        mode: 'all-3' (三法人同買) 或 'any-2' (任二法人同買)
    """
    investors = ['foreign', 'trust', 'dealer']
    layout_results = {}
    
    # 1. 獲取所有法人的佈局清單
    for inv in investors:
        # 使用稍低的門檻來獲取候選名單，確保交集能找到
        # 若個別評分太高，交集會很少
        stocks = get_layout_stocks(inv, days, min_score, top_n=200) # 先拿多一點做交集
        
        # 建立 map {code: data}
        stock_map = {}
        for s in stocks:
            stock_map[s['stock_code']] = s
        layout_results[inv] = stock_map
            
    # 2. 尋找交集
    all_codes = set()
    for inv in investors:
        all_codes.update(layout_results[inv].keys())
        
    final_results = []
    
    for code in all_codes:
        active_investors = []
        combined_score = 0
        combined_net = 0
        stock_name = ""
        category = "其他"
        
        for inv in investors:
            if code in layout_results[inv]:
                data = layout_results[inv][code]
                active_investors.append(INVESTOR_NAMES[inv])
                combined_score += data['layout_score']
                combined_net += data['total_net']
                stock_name = data['stock_name'] # 任意一個有名稱就好
                category = data.get('category', '其他')
        
        # 判斷條件
        is_match = False
        if mode == 'all-3':
            if len(active_investors) == 3:
                is_match = True
        elif mode == 'any-2':
            if len(active_investors) >= 2: # 包含 3 的情況
                is_match = True
                
        if is_match:
            final_results.append({
                'stock_code': code,
                'stock_name': stock_name,
                'category': category,
                'active_investors': active_investors,
                'investor_count': len(active_investors),
                'combined_score': round(combined_score, 1),
                'total_net': combined_net,
                'details': {inv: layout_results[inv][code] for inv in investors if code in layout_results[inv]}
            })
            
    # 3. 排序 (依據參與法人數、總分)
    final_results.sort(key=lambda x: (x['investor_count'], x['combined_score']), reverse=True)
    
    return final_results[:top_n]
