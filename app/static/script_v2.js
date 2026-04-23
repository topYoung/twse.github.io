// DOM Elements
const indexPriceEl = document.getElementById('index-price');
const indexChangeEl = document.getElementById('index-change');
const stockListEl = document.getElementById('stock-list');
const loadingMsg = document.getElementById('loading-msg');
const chartSection = document.getElementById('chart-container-wrapper');
const chartContainer = document.getElementById('chart-container');
const chartTitle = document.getElementById('chart-title');
const closeChartBtn = document.getElementById('close-chart');
const reboundModal = document.getElementById('rebound-modal');

// State
let chart = null;
let currentStock = null;
let candlestickSeries = null;
let candlestickSeriesRight = null; // Phantom series for Right Axis
let ma5Series = null;
let ma10Series = null;
let ma20Series = null;
let ma60Series = null;
let chartIntervalId = null;
let breakoutRefreshId = null;
let _chartReturnModalId = null;  // 記住開圖前的來源 modal，關圖後自動還原

// --- 只掃科技股 checkbox ---
function isTechOnly() {
    const cb = document.getElementById('tech-only-checkbox');
    return cb ? cb.checked : true;
}
function getTechParam() {
    return `tech_only=${isTechOnly()}`;
}

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    fetchMarketIndex();
    fetchStocks();
    setInterval(fetchMarketIndex, 5000); // Update index every 5 seconds

    closeChartBtn.addEventListener('click', closeChart);

    window.addEventListener('click', (event) => {
        const investorModal = document.getElementById('investor-modal');
        const layoutStocksModal = document.getElementById('layout-stocks-modal');
        const breakoutModal = document.getElementById('breakout-modal');

        if (event.target === investorModal) {
            closeInvestorModal();
        }
        if (event.target === layoutStocksModal) {
            closeLayoutStocksModal();
        }
        if (event.target === breakoutModal) {
            closeBreakoutModal();
        }

        if (event.target === reboundModal) {
            closeReboundModal();
        }

        const downtrendModal = document.getElementById('downtrend-modal');
        if (event.target === downtrendModal) {
            closeDowntrendModal();
        }

        const multiInvestorModal = document.getElementById('multi-investor-modal');
        if (event.target === multiInvestorModal) {
            closeMultiInvestorModal();
        }

        const highDividendModal = document.getElementById('high-dividend-modal');
        if (event.target === highDividendModal) {
            closeHighDividendModal();
        }

        const divergenceModal = document.getElementById('divergence-modal');
        if (event.target === divergenceModal) {
            closeDivergenceModal();
        }

        const intradayModal = document.getElementById('intraday-modal');
        if (event.target === intradayModal) {
            closeIntradayModal();
        }
    });

    // Check for specific buttons if they exist (legacy support)
    const layoutAnalysisBtn = document.getElementById('layout-analysis-btn');
    if (layoutAnalysisBtn) {
        layoutAnalysisBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            openInvestorModal();
        });
    }
});



// --- Market Index ---
async function fetchMarketIndex() {
    try {
        const response = await fetch('/api/market-index');
        const data = await response.json();
        renderIndex(data);
    } catch (error) {
        console.error('Error fetching index:', error);
        renderIndex({ price: 0, change: 0, percent_change: 0, error: '無法取得' });
    }
}

function renderIndex(data) {
    if (!data || (data.price === 0 && !data.from_cache)) {
        indexPriceEl.textContent = '--';
        indexChangeEl.textContent = '資料取得失敗';
        indexChangeEl.className = 'index-change';
        return;
    }
    indexPriceEl.textContent = Number(data.price).toLocaleString();
    const sign = data.change >= 0 ? '+' : '';
    const colorClass = data.change >= 0 ? 'up' : 'down';
    indexChangeEl.textContent = `${sign}${data.change} (${data.percent_change}%)`;
    indexChangeEl.className = `index-change ${colorClass}`;

    // 非即時：顯示日期標籤
    const subtitleEl = document.getElementById('index-subtitle');
    if (subtitleEl) {
        if (data.is_realtime) {
            subtitleEl.textContent = '即時';
            subtitleEl.style.color = '#3fb950';
        } else {
            const label = data.date ? `${data.date} 收盤` : '前一交易日';
            subtitleEl.textContent = label;
            subtitleEl.style.color = '#8b949e';
        }
    }
}

// --- Stock List ---
async function fetchStocks() {
    try {
        const response = await fetch('/api/stocks');
        const stocks = await response.json();
        renderStocks(stocks);
    } catch (error) {
        console.error('Error fetching stocks:', error);
        loadingMsg.textContent = '載入失敗，請刷新頁面重試。';
    }
}

const categoryFilterEl = document.getElementById('category-filter');
let currentCategory = 'All';

let allStocksCache = null; // 全市場快取

function renderStocks(stocks) {
    loadingMsg.style.display = 'none';
    stockListEl.innerHTML = '';
    categoryFilterEl.innerHTML = '';

    if (stocks.length === 0) {
        stockListEl.innerHTML = '<div style="grid-column: 1/-1; text-align: center;">目前沒有符合條件的股票。</div>';
        return;
    }

    // 初次載入如果是大表，備份一下
    if (!allStocksCache && stocks.length > 500) {
        allStocksCache = stocks;
    }

    // 1. Extract Unique Categories
    const categories = ['全部', ...new Set(stocks.map(s => s.category))];

    // 2. Generate Filter Buttons
    categories.forEach(cat => {
        const btn = document.createElement('button');
        btn.textContent = cat === 'All' ? '全部' : cat; // '全部' is already in list
        btn.className = 'filter-btn';
        if (cat === '全部') btn.classList.add('active'); // Default active

        btn.onclick = () => {
            // Remove active class from all
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            filterStocks(stocks, cat);
        };
        categoryFilterEl.appendChild(btn);
    });

    // Initial Render (All)
    filterStocks(stocks, '全部');
}

function filterStocks(stocks, category) {
    stockListEl.innerHTML = '';

    const filtered = category === '全部' ? stocks : stocks.filter(s => s.category === category);

    if (filtered.length === 0) {
        stockListEl.innerHTML = '<div style="grid-column: 1/-1; text-align: center;">此分類下無符合股票。</div>';
        return;
    }

    filtered.forEach(stock => {
        const card = document.createElement('div');
        card.className = 'stock-card';
        // Pass category to openChart
        card.onclick = () => openChart(stock.code, stock.name, stock.category);

        const priceClass = stock.change >= 0 ? 'up' : 'down';
        const categoryName = stock.category;
        const categoryClass = 'tech';

        // Sparkline SVG
        const sparklineSvg = generateSparkline(stock.sparkline, stock.change >= 0);

        card.innerHTML = `
            <div class="card-header">
                <div class="stock-identity">
                    <span class="stock-name">${stock.name}</span>
                    <span class="stock-code-small">${stock.code}</span>
                </div>
                <span class="badge ${categoryClass}">${categoryName}</span>
            </div>
            <div class="card-body">
                <div class="price-info">
                    <div class="stock-price">${stock.price}</div>
                    <div class="stock-change ${priceClass}">
                         ${renderStockDetailLine(stock)}
                    </div>
                </div>
                <div class="sparkline-container">
                    ${sparklineSvg}
                </div>
            </div>
        `;
        stockListEl.appendChild(card);
    });
}

function generateSparkline(data, isUp) {
    if (!data || data.length < 2) return '';

    const width = 100;
    const height = 40;
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;

    // Create points
    const points = data.map((val, index) => {
        const x = (index / (data.length - 1)) * width;
        const y = height - ((val - min) / range) * height; // Invert y because SVG y goes down
        return `${x},${y}`;
    }).join(' ');

    // Taiwan: Red = Up, Green = Down
    const color = isUp ? '#da3633' : '#238636';
    return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" fill="none">
        <polyline points="${points}" stroke="${color}" stroke-width="2" fill="none" vector-effect="non-scaling-stroke" />
    </svg>`;
}

async function openChart(stockCode, stockName, category) {
    currentStock = stockCode;
    // Format: "[Category] Code (Name) 走勢圖"
    const categoryLabel = category ? `[${category}] ` : '';
    chartTitle.textContent = `${categoryLabel}${stockCode} (${stockName}) 走勢圖`;
    chartSection.classList.remove('hidden');

    // Reset Header Info (Clear Stale Data)
    document.getElementById('chart-price').textContent = '---';
    document.getElementById('chart-change').textContent = '---';

    if (!chart) {
        initChart();
    }

    // Force resize calculation after modal is shown to ensure chart renders
    const resizeChart = () => {
        if (chart && chartContainer) {
            const width = chartContainer.clientWidth;
            const height = chartContainer.clientHeight;
            console.log(`[Chart Resize] New dimensions: ${width}x${height}`);
            if (width > 0 && height > 0) {
                chart.resize(width, height);
                chart.timeScale().fitContent();
            }
        }
    };

    // Try multiple resize attempts to ensure it catches the layout
    setTimeout(resizeChart, 50);
    setTimeout(resizeChart, 200);
    setTimeout(resizeChart, 500);
    setTimeout(resizeChart, 1000); // Extra safety for slow transitions

    // Reset to "Day" view by default
    currentInterval = '1d';

    // Clear previous data to avoid confusion while loading
    if (candlestickSeries) candlestickSeries.setData([]);
    if (candlestickSeriesRight) candlestickSeriesRight.setData([]);
    if (ma5Series) ma5Series.setData([]);
    if (ma10Series) ma10Series.setData([]);
    if (ma20Series) ma20Series.setData([]);
    if (ma60Series) ma60Series.setData([]);

    // Manually trigger UI update for 'D'
    setChartInterval('D', null); // null will trigger text-based lookup

    // await loadChartData(stockCode, '1d'); // setChartInterval already calls this

    // One more resize after data load
    setTimeout(resizeChart, 100);

    // Start polling for real-time updates
    if (chartIntervalId) clearInterval(chartIntervalId);
    chartIntervalId = setInterval(() => {
        loadChartData(currentStock, currentInterval || '1d');
    }, 5000);
}

function closeChart() {
    chartSection.classList.add('hidden');
    currentStock = null;
    if (chartIntervalId) {
        clearInterval(chartIntervalId);
        chartIntervalId = null;
    }
    // 回到來源 modal（只顯示，不重新 fetch）
    if (_chartReturnModalId) {
        const m = document.getElementById(_chartReturnModalId);
        if (m) m.classList.remove('hidden');
        _chartReturnModalId = null;
    }
}

function initChart() {
    console.log('[Chart Init] Container dimensions:', chartContainer.clientWidth, 'x', chartContainer.clientHeight);
    if (chartContainer.clientWidth === 0 || chartContainer.clientHeight === 0) {
        console.warn('[Chart Init] Warning: Container has 0 dimensions!');
    }

    chart = LightweightCharts.createChart(chartContainer, {
        width: chartContainer.clientWidth || 800, // Fallback
        height: chartContainer.clientHeight || 500, // Fallback
        layout: {
            background: { type: 'solid', color: '#161b22' },
            textColor: '#c9d1d9',
        },
        grid: {
            vertLines: { color: '#30363d' },
            horzLines: { color: '#30363d' },
        },
        // Enable Right scale for dual-axis view
        rightPriceScale: {
            visible: true,
            borderColor: '#30363d',
        },
        leftPriceScale: {
            visible: true,
            borderColor: '#30363d',
        },
        timeScale: {
            borderColor: '#30363d',
            timeVisible: true,
            secondsVisible: false,
            rightOffset: 5,
            barSpacing: 12, // Default wider spacing
            minBarSpacing: 1,
            fixLeftEdge: true,
            fixRightEdge: true,
        },
    });

    candlestickSeries = chart.addCandlestickSeries({
        upColor: '#da3633',        // Red for up
        downColor: '#238636',      // Green for down
        borderVisible: false,
        wickUpColor: '#da3633',    // Red for up
        wickDownColor: '#238636',  // Green for down
        priceScaleId: 'left',      // Associate with left scale
    });

    // Phantom Series for Right Axis (Transparent)
    // This allows the Right Axis to show Ticks synchronized with Left Axis
    candlestickSeriesRight = chart.addCandlestickSeries({
        upColor: 'rgba(255, 0, 0, 0.01)',      // Very faint/invisible
        downColor: 'rgba(0, 255, 0, 0.01)',
        borderVisible: false,
        wickUpColor: 'rgba(255, 0, 0, 0.01)',
        wickDownColor: 'rgba(0, 255, 0, 0.01)',
        priceScaleId: 'right',
        priceLineVisible: false, // Don't show price line
        lastValueVisible: false, // Don't show label tag
    });

    // Add MA line series with different colors
    // Line Width reduced to 1
    ma5Series = chart.addLineSeries({
        color: '#FFA500',  // Orange for MA5
        lineWidth: 1,
        title: 'MA5',
        priceScaleId: 'left',
    });
    ma10Series = chart.addLineSeries({
        color: '#00CED1',  // DarkTurquoise for MA10
        lineWidth: 1,
        title: 'MA10',
        priceScaleId: 'left',
    });
    ma20Series = chart.addLineSeries({
        color: '#FF1493',  // DeepPink for MA20
        lineWidth: 1,
        title: 'MA20',
        priceScaleId: 'left',
    });
    ma60Series = chart.addLineSeries({
        color: '#FFD700',  // Gold for MA60
        lineWidth: 1,
        title: 'MA60',
        priceScaleId: 'left',
    });

    new ResizeObserver(entries => {
        if (entries.length === 0 || entries[0].target !== chartContainer) { return; }
        const newRect = entries[0].contentRect;
        chart.applyOptions({ width: newRect.width, height: newRect.height });
    }).observe(chartContainer);
}

let currentInterval = '1d';

// DOM Elements for Interval Label
const chartIntervalLabel = document.getElementById('chart-interval-label');

async function setChartInterval(interval, btnElement) {
    if (!currentStock) return;

    // Map Chinese UI to backend interval
    const map = { 'D': '1d', 'W': '1wk', 'M': '1mo' };
    const labelMap = { 'D': '日線', 'W': '周線', 'M': '月線' };

    currentInterval = map[interval] || '1d';

    // update buttons state
    const buttons = document.querySelectorAll('.chart-controls button');
    buttons.forEach(btn => btn.classList.remove('active'));
    if (btnElement) {
        btnElement.classList.add('active');
    } else {
        // Find by text content if no element passed (initial load)
        const text = labelMap[interval] || '日線';
        buttons.forEach(btn => {
            if (btn.textContent === text) btn.classList.add('active');
        });
    }

    // Update Label
    if (chartIntervalLabel) {
        chartIntervalLabel.textContent = labelMap[interval] || '日線';
    }

    /* Temporarily removed for stability testing
    chart.applyOptions({
        timeScale: {
            tickMarkFormatter: (time, tickMarkType, locale) => {
                 return null;
            }
        }
    });
    */

    await loadChartData(currentStock, currentInterval);
}

async function loadChartData(stockCode, interval) {
    try {
        const response = await fetch(`/api/history/${stockCode}?interval=${interval}`);
        const data = await response.json();
        console.log(`[Chart Data] ${stockCode} (${interval}):`, data);

        // Race Condition Check: Ensure current stock hasn't changed while fetching
        if (currentStock !== stockCode) {
            console.warn(`[Chart Data] Ignored data for ${stockCode}, user switched to ${currentStock}`);
            return;
        }

        // Handle new response format with separate arrays
        if (!data || !data.candlestick || data.candlestick.length === 0) {
            console.warn(`[Chart Data] No data received for ${stockCode}`);
            return;
        }

        // Update Chart Config for Density
        // Increase barSpacing for clearer, wider candles (User Request)
        chart.applyOptions({
            timeScale: {
                barSpacing: 12, // Increased from 2 to 12 for better visibility
                minBarSpacing: 1,
            }
        });

        candlestickSeries.setData(data.candlestick);

        // Clone data for Phantom Series (Safety Ensure)
        if (candlestickSeriesRight) {
            const phantomData = data.candlestick.map(item => ({ ...item }));
            candlestickSeriesRight.setData(phantomData);
        }

        ma5Series.setData(data.ma5 || []);
        ma10Series.setData(data.ma10 || []);
        ma20Series.setData(data.ma20 || []);
        ma60Series.setData(data.ma60 || []);

        // Explicitly enforce Right Scale Visibility again
        chart.applyOptions({
            rightPriceScale: {
                visible: true,
                borderColor: '#30363d',
            }
        });

        // Update Header Info based on latest candlestick data
        updateChartHeader(data.candlestick);

        // Update Title if info is available (for Search feature)
        // Re-verify currentStock in case of very fast clicks
        if (data.info && currentStock === stockCode) {
            const categoryLabel = data.info.category ? `[${data.info.category}] ` : '';
            chartTitle.textContent = `${categoryLabel}${stockCode} (${data.info.name}) 走勢圖`;
        }

    } catch (error) {
        console.error('Error loading chart:', error);
    }
}

// --- Search Feature ---
const searchInput = document.getElementById('stock-search');
const searchBtn = document.getElementById('search-btn');

if (searchBtn && searchInput) {
    const handleSearch = async () => {
        const query = searchInput.value.trim();
        if (!query) return;

        // 1. Resolve stock code via Backend API
        try {
            const response = await fetch(`/api/search?query=${encodeURIComponent(query)}`);
            const result = await response.json();

            if (result.error || !Array.isArray(result) || result.length === 0) {
                alert(`找不到股票: ${query}`);
                return;
            }

            // 2. Open Chart with resolved Code (take the first result)
            const firstResult = result[0];
            const stockCode = firstResult.code;
            const stockName = firstResult.name;
            const category = firstResult.category || '搜尋';

            console.log(`[Search] Opening chart for: ${stockCode} (${stockName})`);
            openChart(stockCode, stockName, category);
            searchInput.value = '';

        } catch (error) {
            console.error('Search error:', error);
            alert('搜尋失敗，請稍後重試');
        }
    };

    searchBtn.addEventListener('click', handleSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSearch();
    });
}

function updateChartHeader(data) {
    const chartPriceEl = document.getElementById('chart-price');
    const chartChangeEl = document.getElementById('chart-change');

    if (!data || data.length < 2) return;

    const last = data[data.length - 1];
    const prev = data[data.length - 2];

    const price = last.close;
    const change = price - prev.close;
    const percent = (change / prev.close) * 100;

    const sign = change >= 0 ? '+' : '';
    const color = change >= 0 ? '#da3633' : '#238636'; // Taiwan colors

    chartPriceEl.textContent = price.toFixed(2);
    chartPriceEl.style.color = color;

    chartChangeEl.textContent = `${sign}${change.toFixed(2)} (${sign}${percent.toFixed(2)}%)`;
    chartChangeEl.style.color = color;
}

// --- 法人佈局分析功能 ---

// 法人名稱對應
const INVESTOR_NAMES = {
    'foreign': '外資',
    'trust': '投信',
    'dealer': '自營商'
};

// 法人類型圖示
const INVESTOR_ICONS = {
    'foreign': '🌍',
    'trust': '🏦',
    'dealer': '🏢'
};

// 開啟法人選擇 Modal
async function openInvestorModal() {
    const modal = document.getElementById('investor-modal');
    const investorList = document.getElementById('investor-list');

    // 顯示 Modal
    modal.classList.remove('hidden');

    // 顯示載入中
    investorList.innerHTML = '<div style="grid-column: 1/-1; text-align: center;">載入中...</div>';

    try {
        // 獲取法人摘要資訊
        const response = await fetch('/api/institutional-investors?days=30');
        const investors = await response.json();

        // 渲染法人卡片
        investorList.innerHTML = '';
        investors.forEach(investor => {
            const card = createInvestorCard(investor);
            investorList.appendChild(card);
        });
    } catch (error) {
        console.error('Error fetching investors:', error);
        investorList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #f85149;">載入失敗，請重試</div>';
    }
}

// 建立法人卡片
function createInvestorCard(investor) {
    const card = document.createElement('div');
    card.className = 'investor-card';
    card.onclick = () => openLayoutStocksModalV2(investor.type, investor.name);

    const netClass = investor.total_net_shares >= 0 ? 'up' : 'down';
    const netSign = investor.total_net_shares >= 0 ? '+' : '';

    card.innerHTML = `
        <div class="investor-card-header">
            <span class="investor-icon">${INVESTOR_ICONS[investor.type]}</span>
            <h3>${investor.name}</h3>
        </div>
        <div class="investor-card-body">
            <div class="investor-stat">
                <span class="stat-label">近${investor.days}日淨買超</span>
                <span class="stat-value ${netClass}">${netSign}${(investor.total_net_shares / 1000).toFixed(0)}千股</span>
            </div>
            <div class="investor-stat">
                <span class="stat-label">交易股票數</span>
                <span class="stat-value">${investor.active_stocks}檔</span>
            </div>
            <div class="investor-stat">
                <span class="stat-label">買超/賣超天數</span>
                <span class="stat-value">${investor.buy_days} / ${investor.sell_days}</span>
            </div>
        </div>
        <div class="investor-card-footer">
            <button class="view-layout-btn">查看佈局股票 →</button>
        </div>
    `;

    return card;
}

// 關閉法人選擇 Modal
function closeInvestorModal() {
    const modal = document.getElementById('investor-modal');
    modal.classList.add('hidden');
}

// 開啟股票清單 Modal (V2)
async function openLayoutStocksModalV2(investorType, investorName) {
    // Debug Alert (Temporary)
    // alert(`Debug: Opening for ${investorType} - ${investorName}`);
    console.log(`[UI] Opening Layout Modal V2 for: ${investorType} (${investorName})`);

    // 關閉法人選擇 Modal
    closeInvestorModal();

    const modal = document.getElementById('layout-stocks-modal');
    const title = document.getElementById('layout-stocks-title');
    const loading = document.getElementById('layout-loading');
    const stocksList = document.getElementById('layout-stocks-list');

    // 更新標題
    if (title) {
        title.textContent = `${investorName} 佈局股票`;
    } else {
        console.error('[UI] Error: Title element not found');
    }

    // 顯示 Modal 和載入中
    modal.classList.remove('hidden');
    loading.classList.remove('hidden');
    stocksList.innerHTML = '';

    try {
        console.log(`[UI] Fetching: /api/layout-stocks/${investorType}?days=90&min_score=30&top_n=50`);
        // 獲取佈局股票清單（90天，最低30分，前50檔）
        const response = await fetch(`/api/layout-stocks/${investorType}?days=90&min_score=30&top_n=50`);
        const stocks = await response.json();
        console.log(`[UI] Received ${stocks.length} stocks`);

        // 隱藏載入中
        loading.classList.add('hidden');

        // 檢查是否有錯誤
        if (stocks.error) {
            stocksList.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #f85149;">${stocks.error}</div>`;
            return;
        }

        // 渲染股票清單
        if (stocks.length === 0) {
            stocksList.innerHTML = '<div style="grid-column: 1/-1; text-align: center;">目前沒有符合條件的佈局股票 (Score < 30)</div>';
            return;
        }

        stocks.forEach(stock => {
            const card = createLayoutStockCard(stock, investorType);
            stocksList.appendChild(card);
        });
    } catch (error) {
        console.error('Error fetching layout stocks:', error);
        loading.classList.add('hidden');
        stocksList.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #f85149;">載入失敗: ${error.message}</div>`;
    }
}

// 建立佈局股票卡片
function createLayoutStockCard(stock, investorType) {
    const card = document.createElement('div');
    card.className = 'stock-card layout-stock-card';
    card.onclick = () => {
        // closeLayoutStocksModal(); // Maintain modal in background
        openChart(stock.stock_code, stock.stock_name, stock.category || '法人佈局');
    };

    const netClass = stock.total_net >= 0 ? 'up' : 'down';
    const netSign = stock.total_net >= 0 ? '+' : '';

    // 計算買入率
    const buyRate = ((stock.buy_days / stock.total_trading_days) * 100).toFixed(1);

    // 評分顏色
    let scoreClass = 'score-low';
    if (stock.layout_score >= 60) scoreClass = 'score-high';
    else if (stock.layout_score >= 40) scoreClass = 'score-medium';

    card.innerHTML = `
        <div class="card-header">
            <div class="stock-identity">
                <span class="stock-name">${stock.stock_name}</span>
                <span class="stock-code-small">${stock.stock_code}</span>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                 <span class="badge ${stock.category === '其他' ? 'trad' : 'tech'}">${stock.category}</span>
                 <span class="layout-score ${scoreClass}">${stock.layout_score}分</span>
            </div>
        </div>
        <div class="card-body">
            <div class="layout-stats">
                <div class="layout-stat-item">
                    <span class="stat-label">買入天數</span>
                    <span class="stat-value">${stock.buy_days}/${stock.total_trading_days} (${buyRate}%)</span>
                </div>
                <div class="layout-stat-item">
                    <span class="stat-label">累積淨買超</span>
                    <span class="stat-value ${netClass}">${netSign}${(stock.total_net / 1000).toFixed(1)}千股</span>
                </div>
                <div class="layout-stat-item">
                    <span class="stat-label">平均買入量</span>
                    <span class="stat-value">${(stock.avg_buy_volume / 1000).toFixed(1)}千股</span>
                </div>
                <div class="layout-stat-item">
                    <span class="stat-label">穩定性</span>
                    <span class="stat-value">${(stock.stability * 100).toFixed(1)}%</span>
                </div>
            </div>
        </div>
    `;

    return card;
}

// 關閉股票清單 Modal
function closeLayoutStocksModal() {
    const modal = document.getElementById('layout-stocks-modal');
    modal.classList.add('hidden');
}


// --- 起漲點偵測功能 (Breakout) ---

async function openBreakoutModal() {
    const modal = document.getElementById('breakout-modal');
    const loading = document.getElementById('breakout-loading');
    const container = document.getElementById('breakout-list');

    modal.classList.remove('hidden');
    loading.classList.remove('hidden');
    container.innerHTML = '';

    try {
        const response = await fetch(`/api/breakout-stocks?${getTechParam()}`);
        const data = await response.json();
        const stocks = data.stocks || (Array.isArray(data) ? data : []);

        loading.classList.add('hidden');

        if (data.is_pre_market) {
            const hint = document.createElement('div');
            hint.style = 'grid-column: 1/-1; background: rgba(56, 139, 253, 0.1); border: 1px solid rgba(56, 139, 253, 0.4); border-radius: 6px; padding: 12px; margin-bottom: 20px; font-size: 0.9em; color: #79c0ff; line-height: 1.5;';
            hint.innerHTML = '<strong>ℹ️ 盤前提醒</strong><br/>目前為盤前時段，系統顯示的是「昨日籌碼」與「技術面盤整」數據。<br/>09:00 開盤後，將會自動結合「即時買賣力道」進行更精確的過濾。';
            container.appendChild(hint);
        }

        if (!stocks || stocks.length === 0) {
            const emptyMsg = document.createElement('div');
            emptyMsg.style = 'grid-column: 1/-1; text-align: center; padding: 40px; color: #8b949e;';
            emptyMsg.innerText = '今日暫無明顯突破訊號';
            container.appendChild(emptyMsg);
            return;
        }

        stocks.forEach(stock => {
            const card = createBreakoutCard(stock);
            container.appendChild(card);
        });

    } catch (error) {
        console.error('Error fetching breakouts:', error);
        loading.classList.add('hidden');
        let errorMsg = '掃描失敗，請稍後重試';
        if (error instanceof SyntaxError) {
            errorMsg += ' (資料格式錯誤)';
        }
        container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #f85149;">${errorMsg}</div>`;
    }

    // Set auto-refresh
    if (!breakoutRefreshId) {
        breakoutRefreshId = setInterval(async () => {
            if (modal.classList.contains('hidden')) {
                clearInterval(breakoutRefreshId);
                breakoutRefreshId = null;
                return;
            }
            try {
                const response = await fetch(`/api/breakout-stocks?${getTechParam()}`);
                const data = await response.json();
                const stocks = data.stocks || (Array.isArray(data) ? data : []);

                if (stocks && !data.error) {
                    container.innerHTML = '';

                    if (data.is_pre_market) {
                        const hint = document.createElement('div');
                        hint.style = 'grid-column: 1/-1; background: rgba(56, 139, 253, 0.1); border: 1px solid rgba(56, 139, 253, 0.4); border-radius: 6px; padding: 12px; margin-bottom: 20px; font-size: 0.9em; color: #79c0ff; line-height: 1.5;';
                        hint.innerHTML = '<strong>ℹ️ 盤前提醒</strong><br/>目前為盤前時段，系統顯示的是「昨日籌碼」與「技術面盤整」數據。<br/>09:00 開盤後，將會自動結合「即時買賣力道」進行更精確的過濾。';
                        container.appendChild(hint);
                    }

                    if (stocks.length === 0) {
                        container.innerHTML += '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #8b949e;">今日暫無明顯突破訊號</div>';
                    } else {
                        stocks.forEach(stock => {
                            const card = createBreakoutCard(stock);
                            container.appendChild(card);
                        });
                    }
                }
            } catch (e) {
                console.error('Polling error:', e);
            }
        }, 15000); // 15 seconds
    }
}

// 隱藏 modal 以顯示走勢圖，關圖後自動還原（不清除資料）
function hideForChart(modalId) {
    _chartReturnModalId = modalId;
    const m = document.getElementById(modalId);
    if (m) m.classList.add('hidden');
}

function closeBreakoutModal() {
    const modal = document.getElementById('breakout-modal');
    modal.classList.add('hidden');
    if (breakoutRefreshId) {
        clearInterval(breakoutRefreshId);
        breakoutRefreshId = null;
    }
}

function createBreakoutCard(stock) {
    const card = document.createElement('div');
    card.className = 'stock-card breakout-card';
    card.style.borderLeft = '4px solid #da3633'; // Highlight Red
    card.onclick = () => {
        hideForChart('breakout-modal');
        openChart(stock.code, stock.name, stock.category || '起漲訊號');
    };

    // 根據訊號優先級設定邊框顏色
    const priorityColors = {
        1: '#f1c40f', // 營收爆發 - 黃金色
        2: '#da3633', // 底部起漲 - 紅色
        3: '#da3633', // 營收驅動 - 紅色
        4: '#238636', // 加速起漲 - 綠色
        5: '#388bfd', // 突破起漲 - 藍色
        99: '#8b949e'  // 其他 - 灰色
    };
    
    const priority = stock.signal_priority || 99;
    card.style.borderLeft = `4px solid ${priorityColors[priority] || '#da3633'}`;
    
    // 優先級較高的股票加背景漸變
    if (priority === 1) {
        card.style.background = 'linear-gradient(90deg, rgba(241, 196, 15, 0.08) 0%, rgba(13, 17, 23, 1) 100%)';
    } else if (priority === 2) {
        card.style.background = 'linear-gradient(90deg, rgba(218, 54, 51, 0.08) 0%, rgba(13, 17, 23, 1) 100%)';
    }

    const changeClass = stock.change_percent >= 0 ? 'up' : 'down';
    const sign = stock.change_percent >= 0 ? '+' : '';

    // Format helpers
    const fmtVol = (v) => {
        if (v === null || v === undefined) return '-';
        const n = Number(v);
        if (!Number.isFinite(n)) return '-';
        if (n >= 1e8) return (n / 1e8).toFixed(2) + '億';
        if (n >= 1e4) return (n / 1e4).toFixed(1) + '萬';
        return String(n);
    };

    const signalType = stock.signal_type || '-';
    const signalDesc = stock.signal_desc || '';

    // 布林數據
    const bb = stock.bollinger || {};
    const bbText = bb.percent_b != null
        ? `%B:${bb.percent_b}% BBW:${bb.bbw}% EMA:${bb.bbw_ema}%`
        : '-';

    // MACD 數據
    const macd = stock.macd || {};
    const macdText = macd.hist != null
        ? `DIF:${macd.dif} DEA:${macd.dea} OSC:${macd.hist}`
        : '-';

    // KD
    const kdText = stock.kd_d_value != null ? `D ${stock.kd_d_value}` : '-';

    // 三大法人（最新一日，單位：股 → 張）
    const inst = stock.institutional || {};
    const fmtInst = (v) => {
        if (v == null) return '-';
        const lots = Math.round(v / 1000);
        const sign = lots >= 0 ? '+' : '';
        const color = lots >= 0 ? '#3fb950' : '#f85149';
        return `<span style="color:${color}">${sign}${lots.toLocaleString()}張</span>`;
    };

    // 位階
    const pos = stock.position || {};
    const posLabel = pos.label || '-';
    const posPct   = pos.pct   != null ? pos.pct + '%' : '-';

    // 營收
    const rev = stock.revenue || {};
    const revText = (rev.mom != null || rev.yoy != null)
        ? `MOM: ${rev.mom != null ? rev.mom + '%' : 'N/A'}  |  YOY: ${rev.yoy != null ? rev.yoy + '%' : 'N/A'}`
        : null;

    card.innerHTML = `
        <div class="card-header">
            <div class="stock-identity">
                <div class="breakout-title">
                    <span class="stock-name">${stock.name}</span>
                    <span class="stock-code-small">${stock.code}</span>
                </div>
                <!-- 訊號徽章 + 位階 -->
                <div style="margin-top: 6px; display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
                    <span style="background:${priorityColors[priority]}; color:#fff; font-weight:700;
                                 padding:3px 10px; border-radius:4px; font-size:0.88em;">
                        ${signalType}
                    </span>
                    <span style="font-size:0.82em;">${posLabel} ${posPct}</span>
                </div>
                <!-- 訊號描述 -->
                ${signalDesc ? `<div style="margin-top:4px; font-size:0.77em; color:#8b949e;">${signalDesc}</div>` : ''}
                <!-- 技術指標 -->
                <div class="breakout-metrics" style="margin-top:8px;">
                    <div class="breakout-metric"><span class="metric-label">量比</span><span class="metric-value">${stock.vol_ratio}x</span></div>
                    <div class="breakout-metric"><span class="metric-label">KD D</span><span class="metric-value">${kdText}</span></div>
                    <div class="breakout-metric"><span class="metric-label">成交量</span><span class="metric-value">${fmtVol(stock.volume)}</span></div>
                </div>
                <!-- 布林 + MACD -->
                <div style="margin-top:5px; font-size:0.77em; color:#6e7681; line-height:1.6;">
                    <div>布林: ${bbText}</div>
                    <div>MACD: ${macdText}</div>
                </div>
                <!-- 三大法人（全為 0 時不顯示） -->
                ${(inst.foreign || inst.trust || inst.dealer) ? `
                <div style="margin-top:6px; font-size:0.80em; display:grid; grid-template-columns:1fr 1fr 1fr; gap:4px;
                            background:rgba(255,255,255,0.03); border-radius:4px; padding:5px 6px;">
                    <div>外資 ${fmtInst(inst.foreign)}</div>
                    <div>投信 ${fmtInst(inst.trust)}</div>
                    <div>自營 ${fmtInst(inst.dealer)}</div>
                </div>` : ''}
            </div>
        </div>
        <div class="card-body">
            <div class="price-info">
                <div class="stock-price">${stock.price}</div>
                <div class="stock-change ${changeClass}">${sign}${stock.change_percent}%</div>
            </div>
            <!-- 營收資料 -->
            ${revText ? `<div style="margin-top:8px; padding:5px 8px; background:rgba(35,134,54,0.1);
                              border-left:3px solid #238636; border-radius:3px;
                              font-size:0.80em; color:#3fb950;">
                💰 ${revText}
            </div>` : ''}
        </div>
    `;
    return card;
}


// --- 低檔轉強功能 (Rebound) ---

async function openReboundModal() {
    const modal = document.getElementById('rebound-modal');
    const loading = document.getElementById('rebound-loading');
    const container = document.getElementById('rebound-list');

    modal.classList.remove('hidden');
    loading.classList.remove('hidden');
    container.innerHTML = '';

    try {
        const response = await fetch('/api/rebound-stocks');
        const stocks = await response.json();

        loading.classList.add('hidden');

        if (!stocks || stocks.length === 0) {
            container.innerHTML = '<div style="grid-column: 1/-1; text-align: center;">目前無明顯低檔轉強訊號 (或無資料)</div>';
            return;
        }

        stocks.forEach(stock => {
            const card = createReboundCard(stock);
            container.appendChild(card);
        });

    } catch (error) {
        console.error('Error fetching rebounds:', error);
        loading.classList.add('hidden');
        container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #f85149;">掃描失敗，請稍後重試</div>';
    }
}

function closeReboundModal() {
    const modal = document.getElementById('rebound-modal');
    modal.classList.add('hidden');
}

function createReboundCard(stock) {
    const card = document.createElement('div');
    card.className = 'stock-card';
    card.style.borderLeft = '4px solid #d29922'; // Highlight Gold
    card.onclick = () => {
        openChart(stock.code, stock.name, stock.category || '低檔轉強');
    };

    // Calculate diff from low
    const lowDiffPct = ((stock.price - stock.low_60) / stock.low_60 * 100).toFixed(1);

    card.innerHTML = `
        <div class="card-header">
             <div class="stock-identity">
                <span class="stock-name">${stock.name}</span>
                <span class="stock-code-small">${stock.code}</span>
            </div>
            <span class="badge" style="background: #d29922; color: white;">低檔轉強</span>
        </div>
            <div class="card-body">
            <div class="price-info">
                 <div class="stock-price">${stock.price}</div>
                 <div class="stock-change up">
                      MA20與價差: +${stock.ma_diff_pct}%
                 </div>
            </div>
            <div class="layout-stats" style="margin-top: 10px; font-size: 0.9em; color: #8b949e;">
                <div class="layout-stat-item">
                     <span>近60日低: ${stock.low_60}</span>
                </div>
                <div class="layout-stat-item">
                     <span>距低點: +${lowDiffPct}%</span>
                </div>
                <div class="layout-stat-item">
                     <span>位階: ${stock.position_pct}%</span>
                </div>
            </div>
        </div>
    `;
    return card;
}

// --- 高檔轉弱 (Downtrend) ---

async function openDowntrendModal() {
    const modal = document.getElementById('downtrend-modal');
    const loading = document.getElementById('downtrend-loading');
    const container = document.getElementById('downtrend-list');

    modal.classList.remove('hidden');
    loading.classList.remove('hidden');
    container.innerHTML = '';

    try {
        const response = await fetch('/api/downtrend-stocks');
        const stocks = await response.json();

        loading.classList.add('hidden');

        if (!stocks || stocks.length === 0) {
            container.innerHTML = '<div style="grid-column: 1/-1; text-align: center;">目前無高檔轉弱訊號</div>';
            return;
        }

        stocks.forEach(stock => {
            const card = createDowntrendCard(stock);
            container.appendChild(card);
        });

    } catch (error) {
        console.error('Error fetching downtrends:', error);
        loading.classList.add('hidden');
        container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #f85149;">掃描失敗，請稍後重試</div>';
    }
}

function closeDowntrendModal() {
    const modal = document.getElementById('downtrend-modal');
    modal.classList.add('hidden');
}

function createDowntrendCard(stock) {
    const card = document.createElement('div');
    card.className = 'stock-card downtrend-card';
    card.style.borderLeft = '4px solid #238636'; // Green for Bearish/Drop
    card.onclick = () => {
        openChart(stock.code, stock.name, '高檔轉弱');
    };

    const changeClass = stock.change_percent >= 0 ? 'up' : 'down';
    const sign = stock.change_percent >= 0 ? '+' : '';

    // Format helpers
    const fmtVol = (v) => {
        if (v === null || v === undefined) return '-';
        const n = Number(v);
        if (!Number.isFinite(n)) return '-';
        if (n >= 1e8) return (n / 1e8).toFixed(2) + '億';
        if (n >= 1e4) return (n / 1e4).toFixed(1) + '萬';
        return String(n);
    };

    const kdText = (stock.kd_k != null && stock.kd_d != null) ? `K <span style="color:#238636">${stock.kd_k}</span> / D ${stock.kd_d}` : '-';
    const rsiText = (stock.rsi != null) ? `${stock.rsi}` : '-';
    const macdText = (stock.macd_dif != null && stock.macd_signal != null && stock.macd_hist != null)
        ? `DIF ${stock.macd_dif} / DEA ${stock.macd_signal} / H ${stock.macd_hist}`
        : '-';
    const biasText = (stock.bias20 != null) ? `${stock.bias20}%` : '-';
    const bbText = (stock.bb_upper != null && stock.bb_mid != null && stock.bb_lower != null && stock.bb_width != null)
        ? `Up ${stock.bb_upper} / Low ${stock.bb_lower} / W ${stock.bb_width}%`
        : '-';

    card.innerHTML = `
        <div class="card-header">
            <div class="stock-identity">
                <span class="stock-name">${stock.name}</span>
                <span class="stock-code-small">${stock.code}</span>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                <span class="badge ${stock.category === '其他' ? 'trad' : 'tech'}">${stock.category}</span>
                <span class="badge" style="background:#238636; color:white;">轉弱</span>
            </div>
        </div>
        <div class="card-body">
            <div class="price-info">
                <div class="stock-price">${stock.price}</div>
                <div class="stock-change ${changeClass}">
                    ${sign}${stock.change_percent}%
                </div>
            </div>
            
            <div class="breakout-stats" style="margin-top: 10px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 0.9em; color: #8b949e;">
                <div>成交量: <span style="color: #c9d1d9;">${fmtVol(stock.volume)}</span></div>
                <div>RSI: <span style="color: #c9d1d9;">${rsiText}</span></div>
                <div style="grid-column: 1/-1;">KD: <span style="color: #c9d1d9;">${kdText}</span></div>
                <div style="grid-column: 1/-1;">MACD: <span style="color: #c9d1d9;">${macdText}</span></div>
                <div>乖離(20): <span style="color: #c9d1d9;">${biasText}</span></div>
                <div style="grid-column: 1/-1;">布林(20,2): <span style="color: #c9d1d9;">${bbText}</span></div>
            </div>
        </div>
    `;

    return card;
}


// --- 多法人同買功能 (Multi-Investor Intersection) ---

async function openMultiInvestorModal(mode) {
    const modal = document.getElementById('multi-investor-modal');
    const title = document.getElementById('multi-investor-title');
    const loading = document.getElementById('multi-investor-loading');
    const container = document.getElementById('multi-investor-list');

    modal.classList.remove('hidden');
    loading.classList.remove('hidden');
    container.innerHTML = '';

    const label = mode === 'all-3' ? '🌟 3大法人同買' : '🤝 2法人同買';
    title.textContent = label;

    try {
        const response = await fetch(`/api/layout-stocks/intersection/${mode}?days=90&min_score=30&top_n=50`);
        const stocks = await response.json();

        loading.classList.add('hidden');

        if (stocks.error) {
            container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #f85149;">${stocks.error}</div>`;
            return;
        }

        if (!stocks || stocks.length === 0) {
            container.innerHTML = '<div style="grid-column: 1/-1; text-align: center;">目前無符合條件的股票</div>';
            return;
        }

        stocks.forEach(stock => {
            const card = createMultiLayoutCard(stock, mode);
            container.appendChild(card);
        });

    } catch (error) {
        console.error('Error fetching multi-investor stocks:', error);
        loading.classList.add('hidden');
        container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #f85149;">掃描失敗，請稍後重試</div>';
    }
}

function closeMultiInvestorModal() {
    const modal = document.getElementById('multi-investor-modal');
    modal.classList.add('hidden');
}

function createMultiLayoutCard(stock, mode) {
    const card = document.createElement('div');
    card.className = 'stock-card layout-stock-card';
    // Highlight border based on mode
    card.style.borderLeft = mode === 'all-3' ? '4px solid #d29922' : '4px solid #a371f7';

    card.onclick = () => {
        openChart(stock.stock_code, stock.stock_name, stock.category || '多法人佈局');
    };

    const netClass = stock.total_net >= 0 ? 'up' : 'down';
    const netSign = stock.total_net >= 0 ? '+' : '';

    // Create tags for active investors
    let tagsHtml = '';
    const tagColors = { '外資': '#238636', '投信': '#da3633', '自營商': '#1f6feb' };

    if (stock.active_investors) {
        stock.active_investors.forEach(inv => {
            const color = tagColors[inv] || '#8b949e';
            tagsHtml += `<span class="badge" style="background:${color}; color:white; margin-right:4px;">${inv}</span>`;
        });
    }

    // 評分顏色
    let scoreClass = 'score-low';
    if (stock.combined_score >= 100) scoreClass = 'score-high'; // Combined score will be higher
    else if (stock.combined_score >= 60) scoreClass = 'score-medium';

    card.innerHTML = `
        <div class="card-header">
            <div class="stock-identity">
                <span class="stock-name">${stock.stock_name}</span>
                <span class="stock-code-small">${stock.stock_code}</span>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                 <span class="badge ${stock.category === '其他' ? 'trad' : 'tech'}">${stock.category}</span>
                 <span class="layout-score ${scoreClass}">總分${stock.combined_score}</span>
            </div>
        </div>
        
        <div class="investor-tags" style="margin: 8px 16px;">
            ${tagsHtml}
        </div>

        <div class="card-body">
            <div class="layout-stats">
                <div class="layout-stat-item">
                    <span class="stat-label">參與法人數</span>
                    <span class="stat-value">${stock.investor_count}</span>
                </div>
                <div class="layout-stat-item">
                    <span class="stat-label">累積總淨買超</span>
                    <span class="stat-value ${netClass}">${netSign}${(stock.total_net / 1000).toFixed(1)}千股</span>
                </div>
            </div>
        </div>
    `;

    return card;
}


// --- 綜合分析功能 (Comprehensive Analysis) ---

function toggleAnalysisPanel() {
    const list = document.getElementById('analysis-options');
    const icon = document.getElementById('analysis-toggle-icon');
    if (list.classList.contains('hidden')) {
        list.classList.remove('hidden');
        icon.textContent = '▲';
    } else {
        list.classList.add('hidden');
        icon.textContent = '▼';
    }
}

let lastComprehensiveResults = null; // 綜合分析暫存

async function runComprehensiveAnalysis() {
    const checkboxes = document.querySelectorAll('input[name="strategy"]:checked');
    const selectedStrategies = Array.from(checkboxes).map(cb => cb.value);

    if (selectedStrategies.length === 0) {
        alert('請至少選擇一種篩選策略');
        return;
    }

    const btn = document.getElementById('analysis-btn');
    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.5';
        btn.textContent = '分析中...';
    }

    // Show loading
    const stockListEl = document.getElementById('stock-list');
    const loadingMsg = document.getElementById('loading-msg');
    stockListEl.innerHTML = '';
    loadingMsg.style.display = 'block';
    loadingMsg.textContent = '正在進行綜合分析...';

    // API Mapping
    const apiMap = {
        'ma': '/api/stocks',
        'momentum': '/api/momentum-stocks?min_days=2',
        'breakout': '/api/breakout-stocks',
        'rebound': '/api/rebound-stocks',
        'downtrend': '/api/downtrend-stocks',
        'investor3': '/api/layout-stocks/intersection/all-3?days=90&min_score=30&top_n=200',
        'major3': '/api/layout-stocks/major?days=3&top_n=200',
        'investor2': '/api/layout-stocks/intersection/any-2?days=90&min_score=30&top_n=200',
        'dividend': '/api/high-dividend-stocks?min_yield=3.0&top_n=200',
        'divergence': '/api/divergence-stocks?days=5&min_net_buy=100&max_price_change=1.0',
        'intraday': '/api/intraday-stocks',
        'macd_breakout': '/api/star-confirmed-stocks',
        'pressure': '/api/pressure-stocks?min_days=2',
        'trend_radar': '/api/trend-radar-stocks',
        'trust_ratio': '/api/scanner/chips/trust-ratio',
        'dealer_buy': '/api/scanner/chips/dealer-buy'
    };

    try {
        // 動態建立帶 tech_only 參數的 API Map
        const tp = getTechParam();
        const apiMapWithParams = Object.fromEntries(
            Object.entries(apiMap).map(([k, url]) => {
                // 只有掃描類 endpoint 需要 tech_only
                const scanApis = ['breakout', 'macd_breakout', 'trend_radar'];
                if (scanApis.includes(k)) {
                    const sep = url.includes('?') ? '&' : '?';
                    return [k, url + sep + tp];
                }
                return [k, url];
            })
        );
        // Fetch All
        const promises = selectedStrategies.map(key => fetch(apiMapWithParams[key]).then(res => res.json()));
        const results = await Promise.all(promises);

        // Normalize Data
        // Convert all lists to a map: Code -> Data
        // To intersect, we need to track counts

        const codeCounts = {};
        const stockDataMap = {}; // Keep the "best" version of data (prefer MA for price info)

        results.forEach((list, index) => {
            if (list.error) return; // Skip errors

            // Handle different list formats
            // Layout API returns list directly or sometimes inside object? Should be list.
            // Breakout API returns { stocks: [...] }, so check for .stocks property
            let items = [];
            if (Array.isArray(list)) {
                items = list;
            } else if (list.stocks && Array.isArray(list.stocks)) {
                items = list.stocks;
            } else if (list.data && Array.isArray(list.data)) {
                items = list.data;
            } else {
                items = [];
            }

            items.forEach(stock => {
                // Normalize Code
                const code = stock.code || stock.stock_code;
                if (!code) return;

                // Increment count
                codeCounts[code] = (codeCounts[code] || 0) + 1;

                // Store data if not exists or if current source is 'ma' (richer data)
                // Actually, just keep the first one encountered, or merge.
                // For simplicity, keep first.
                if (!stockDataMap[code]) {
                    stockDataMap[code] = normalizeStockData(stock);
                }
            });
        });

        // Find Intersection
        const requiredCount = selectedStrategies.length;
        const finalStocks = [];

        Object.keys(codeCounts).forEach(code => {
            if (codeCounts[code] === requiredCount) {
                finalStocks.push(stockDataMap[code]);
            }
        });

        // 存入快取
        lastComprehensiveResults = finalStocks;

        // Render
        renderStocks(finalStocks);

        if (finalStocks.length === 0) {
            stockListEl.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 20px;">無符合「所有條件」的股票。試著減少勾選的條件？</div>';
        }

        // 強制重設按鈕狀態
        const safeBtn = document.getElementById('analysis-btn');
        if (safeBtn) {
            safeBtn.removeAttribute('disabled');
            safeBtn.disabled = false;
            safeBtn.style.opacity = '1';
            safeBtn.textContent = '開始分析';
        }

    } catch (error) {
        console.error('Analysis error:', error);
        loadingMsg.style.display = 'block';
        loadingMsg.textContent = '分析失敗，請檢查網路連線或稍後重試。';
        const safeBtn = document.getElementById('analysis-btn');
        if (safeBtn) {
            safeBtn.removeAttribute('disabled');
            safeBtn.disabled = false;
            safeBtn.style.opacity = '1';
            safeBtn.textContent = '開始分析';
        }
    } finally {
        // Double check reset
        setTimeout(() => {
            const finalBtn = document.getElementById('analysis-btn');
            if (finalBtn) {
                finalBtn.removeAttribute('disabled');
                finalBtn.disabled = false;
                finalBtn.style.opacity = '1';
                if (finalBtn.textContent.includes('分析中')) {
                    finalBtn.textContent = '開始分析';
                }
            }
        }, 500);
    }
}

// 恢復全市場表
window.restoreAllStocks = function() {
    if (allStocksCache) {
        renderStocks(allStocksCache);
    } else {
        // 如果沒有快取重新 fetch
        const stockListEl = document.getElementById('stock-list');
        const loadingMsg = document.getElementById('loading-msg');
        stockListEl.innerHTML = '';
        loadingMsg.style.display = 'block';
        loadingMsg.textContent = '正在載入全市場資料...';
        fetchStocks();
    }
}

// 檢視上次分析結果
window.showLastAnalysis = function() {
    if (lastComprehensiveResults) {
        renderStocks(lastComprehensiveResults);
        if (lastComprehensiveResults.length === 0) {
            document.getElementById('stock-list').innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 20px;">上次分析結果為空。</div>';
        }
    } else {
        alert("尚無上次的分析結果，請先執行包含多策略交集的「綜合分析」。");
    }
}

function normalizeStockData(source) {
    // Convert various API formats to standard format for renderStocks
    return {
        code: source.code || source.stock_code,
        name: source.name || source.stock_name,
        category: source.category || '其他',
        price: source.price || 0,
        change: source.change || 0,
        change_percent: source.change_percent || 0,

        // MA specific
        ma20: source.ma20,
        diff_percent: source.diff_percent,

        // Breakout specific
        reason: source.reason,

        // Layout specific
        total_net: source.total_net,

        // BB+MACD (起漲訊號 / 星級雙重確認)
        signal_type: source.signal_type,
        signal_desc: source.signal_desc,
        macd: source.macd,
        bollinger: source.bollinger,
        vol_ratio: source.vol_ratio,
        institutional: source.institutional,
        position: source.position,

        // Sparkline
        sparkline: source.sparkline || []
    };
}

function renderStockDetailLine(stock) {
    // BB+MACD 起漲訊號優先顯示
    if (stock.signal_type) {
        const bb = stock.bollinger || {};
        const macd = stock.macd || {};
        const inst = stock.institutional || {};
        const instTotal = inst.total ? Math.round(inst.total / 1000) : 0;
        const instStr = instTotal !== 0
            ? `&nbsp;|&nbsp;法人 <span style="color:${instTotal>0?'#3fb950':'#f85149'}">${instTotal>0?'+':''}${instTotal}張</span>`
            : '';
        return `<span style="color:#f1c40f;font-weight:700">${stock.signal_type}</span>&nbsp;
                DIF:<span style="color:#8b949e">${macd.dif??'-'}</span>&nbsp;
                OSC:<span style="color:${(macd.hist??0)>0?'#f85149':'#2ea043'}">${macd.hist??'-'}</span>&nbsp;
                %B:<span style="color:#8b949e">${bb.percent_b??'-'}%</span>${instStr}`;
    }
    if (stock.ma20 !== undefined && stock.diff_percent !== undefined) {
        return `MA20: ${stock.ma20} (${stock.diff_percent}%)`;
    }
    if (stock.reason) {
        return `訊號: ${stock.reason}`;
    }
    if (stock.total_net !== undefined) {
        const netSign = stock.total_net >= 0 ? '+' : '';
        return `累積買超: ${netSign}${(stock.total_net / 1000).toFixed(1)}千股`;
    }
    if (stock.price === 0) {
        return `<span style="color:#8b949e">即時資料需點擊查看</span>`;
    }
    return '';
}


// --- 高股息功能 (High Dividend) ---

async function openHighDividendModal() {
    const modal = document.getElementById('high-dividend-modal');
    const loading = document.getElementById('high-dividend-loading');
    const container = document.getElementById('high-dividend-list');

    modal.classList.remove('hidden');
    loading.classList.remove('hidden');
    container.innerHTML = '';

    try {
        const response = await fetch('/api/high-dividend-stocks?min_yield=3.0&top_n=50');
        const stocks = await response.json();

        loading.classList.add('hidden');

        if (stocks.error) {
            container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #f85149;">${stocks.error}</div>`;
            return;
        }

        if (!stocks || stocks.length === 0) {
            container.innerHTML = '<div style="grid-column: 1/-1; text-align: center;">目前無符合條件的高股息股票</div>';
            return;
        }

        stocks.forEach(stock => {
            const card = createHighDividendCard(stock);
            container.appendChild(card);
        });

    } catch (error) {
        console.error('Error fetching high dividend stocks:', error);
        loading.classList.add('hidden');
        container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #f85149;">掃描失敗，請稍後重試</div>';
    }
}

function closeHighDividendModal() {
    const modal = document.getElementById('high-dividend-modal');
    modal.classList.add('hidden');
}

function createHighDividendCard(stock) {
    const card = document.createElement('div');
    card.className = 'stock-card';
    card.style.borderLeft = '4px solid #f85149';

    card.onclick = () => {
        openChart(stock.code, stock.name, stock.category || '高股息');
    };

    const priceClass = stock.change_percent >= 0 ? 'up' : 'down';
    const priceSign = stock.change_percent >= 0 ? '+' : '';

    card.innerHTML = `
        <div class="card-header">
            <div class="stock-identity">
                <span class="stock-name">${stock.name}</span>
                <span class="stock-code-small">${stock.code}</span>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                 <span class="badge ${stock.category === '其他' ? 'trad' : 'tech'}">${stock.category}</span>
                 <span class="layout-score score-high">殖利率 ${stock.dividend_yield}%</span>
            </div>
        </div>
        
        <div class="card-body">
            <div class="price-info">
                <div class="stock-price">${stock.price}</div>
                <div class="stock-change ${priceClass}">
                     ${priceSign}${stock.change_percent}%
                </div>
            </div>
        </div>

        <div class="layout-stats" style="margin-top: 12px;">
            <div class="layout-stat-item">
                <span class="stat-label">現金股利</span>
                <span class="stat-value">${stock.cash_dividend} 元</span>
            </div>
            <div class="layout-stat-item">
                <span class="stat-label">股票股利</span>
                <span class="stat-value">${stock.stock_dividend} 元</span>
            </div>
            <div class="layout-stat-item">
                <span class="stat-label">總股利</span>
                <span class="stat-value">${stock.total_dividend} 元</span>
            </div>
            <div class="layout-stat-item">
                <span class="stat-label">除息日</span>
                <span class="stat-value">${stock.ex_dividend_date || 'N/A'}</span>
            </div>
        </div>
    `;

    return card;
}

// === 主力買超 (Major Investors) ===
async function openMajorInvestorsModal() {
    const modal = document.getElementById('major-investors-modal');
    const loading = document.getElementById('major-investors-loading');
    const container = document.getElementById('major-investors-list');

    modal.classList.remove('hidden');
    container.innerHTML = ''; // Clear previous
    loading.classList.remove('hidden');

    try {
        const response = await fetch('/api/layout-stocks/major?days=3&top_n=50');

        // Debugging Helper: Check response status
        if (!response.ok) {
            const errorText = await response.text();
            alert(`主力分析載入失敗 (Status: ${response.status})\n錯誤訊息: ${errorText.substring(0, 300)}`);
            throw new Error(`API Error: ${response.status} ${errorText}`);
        }

        const stocks = await response.json();

        loading.classList.add('hidden');

        if (!stocks || !Array.isArray(stocks) || stocks.length === 0) {
            container.innerHTML = '<div style="grid-column: 1/-1; text-align: center;">目前無明顯主力買超訊號</div>';
            return;
        }

        stocks.forEach(stock => {
            const card = createMajorInvestorCard(stock);
            container.appendChild(card);
        });

    } catch (error) {
        console.error('Error fetching major investors:', error);
        loading.classList.add('hidden');
        container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #f85149;">載入失敗，請稍後重試</div>';
    }
}

function closeMajorInvestorsModal() {
    document.getElementById('major-investors-modal').classList.add('hidden');
}

function createMajorInvestorCard(stock) {
    const card = document.createElement('div');
    card.className = 'stock-card layout-stock-card';
    card.style.borderLeft = '4px solid #79c0ff'; // Light Blue for Major

    card.onclick = () => {
        openChart(stock.stock_code, stock.stock_name, stock.category || '主力買超');
    };

    // Format total net (sheets)
    const totalNetStr = (stock.total_net / 1000).toFixed(1) + '張';

    // Details for tooltip or small text
    const fNet = Math.round(stock.details.foreign / 1000);
    const tNet = Math.round(stock.details.trust / 1000);
    const dNet = Math.round(stock.details.dealer / 1000);

    card.innerHTML = `
        <div class="card-header">
            <div class="stock-identity">
                <span class="stock-name">${stock.stock_name}</span>
                <span class="stock-code-small">${stock.stock_code}</span>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                 <span class="badge" style="background: #1f6feb;">${stock.category || '其他'}</span>
            </div>
        </div>
        <div class="card-body">
            <div class="price-info">
                 <div class="stock-price" style="font-size: 1.1em; color: #79c0ff;">${totalNetStr}</div>
                 <div class="stock-change" style="font-size: 0.85em; color: #8b949e;">近3日合計買超</div>
            </div>
            <div class="layout-metrics" style="margin-top: 10px; display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 4px; font-size: 0.8em; text-align: center;">
                <div style="color: ${fNet > 0 ? '#ff7b72' : '#8b949e'}">外 ${fNet}</div>
                <div style="color: ${tNet > 0 ? '#ff7b72' : '#8b949e'}">投 ${tNet}</div>
                <div style="color: ${dNet > 0 ? '#ff7b72' : '#8b949e'}">自 ${dNet}</div>
            </div>
        </div>
    `;
    return card;
}

// --- 連漲強勢功能 (Momentum) ---

function openMomentumModal() {
    const modal = document.getElementById('momentum-modal');
    modal.classList.remove('hidden');
    // Fetch data immediately when opened
    fetchMomentumStocks();
}

function closeMomentumModal() {
    document.getElementById('momentum-modal').classList.add('hidden');
}

// ─── 盤整蓄勢 ──────────────────────────────────────────────────────────────

function openConsolidationModal() {
    document.getElementById('consolidation-modal').classList.remove('hidden');
    fetchConsolidationStocks();
}

function closeConsolidationModal() {
    document.getElementById('consolidation-modal').classList.add('hidden');
}

async function fetchConsolidationStocks() {
    const listEl    = document.getElementById('consolidation-list');
    const loadingEl = document.getElementById('consolidation-loading');

    listEl.innerHTML = '';
    loadingEl.classList.remove('hidden');
    loadingEl.style.display = 'block';

    try {
        const resp = await fetch(`/api/consolidation-stocks?${getTechParam()}`);
        const data = await resp.json();
        const stocks = data.stocks || [];

        loadingEl.classList.add('hidden');

        if (!stocks.length) {
            listEl.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px;color:#8b949e;">目前暫無符合條件的盤整股票</div>';
            return;
        }

        // 分組標題
        const brokeGroup     = stocks.filter(s => s.status === 'just_broke_out');
        const consolidGroup  = stocks.filter(s => s.status === 'consolidating');

        const appendGroup = (label, list) => {
            if (!list.length) return;
            const header = document.createElement('div');
            header.style = 'grid-column:1/-1; padding:6px 0 4px; font-size:0.9em; font-weight:700; color:#cdd9e5; border-bottom:1px solid #30363d; margin-bottom:4px;';
            header.textContent = label;
            listEl.appendChild(header);
            list.forEach(s => listEl.appendChild(createConsolidationCard(s)));
        };

        appendGroup(`🚀 剛起漲（共 ${brokeGroup.length} 支）`, brokeGroup);
        appendGroup(`📦 盤整蓄勢（共 ${consolidGroup.length} 支）`, consolidGroup);

    } catch (err) {
        loadingEl.classList.add('hidden');
        listEl.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:#f85149;">掃描失敗，請稍後重試</div>';
    }
}

function createConsolidationCard(stock) {
    const card = document.createElement('div');
    card.className = 'stock-card';
    const isBroke = stock.status === 'just_broke_out';
    card.style.borderLeft = isBroke ? '4px solid #3fb950' : '4px solid #e3b341';
    if (isBroke) {
        card.style.background = 'linear-gradient(90deg, rgba(63,185,80,0.07) 0%, rgba(13,17,23,1) 100%)';
    }
    card.onclick = () => {
        hideForChart('consolidation-modal');
        openChart(stock.code, stock.name, '盤整蓄勢');
    };

    const changeClass = stock.change_percent >= 0 ? 'up' : 'down';
    const sign = stock.change_percent >= 0 ? '+' : '';

    // 五日三大法人格式化（股 → 張）
    const inst5 = stock.inst_5d || {};
    const fmtLots = (v) => {
        if (v == null) return '-';
        const lots = Math.round(v / 1000);
        const s = lots >= 0 ? '+' : '';
        const col = lots >= 0 ? '#3fb950' : '#f85149';
        return `<span style="color:${col}">${s}${lots.toLocaleString()}張</span>`;
    };

    const hasInst5 = (inst5.foreign || inst5.trust || inst5.dealer || inst5.total);

    // MACD
    const macd = stock.macd || {};
    const macdText = macd.hist != null
        ? `DIF:${macd.dif} DEA:${macd.dea} OSC:${macd.hist}`
        : '-';

    // 盤整狀態標籤
    const statusBadge = isBroke
        ? `<span style="background:#3fb950;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.82em;font-weight:700;">🚀 剛起漲</span>`
        : `<span style="background:#b08000;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.82em;font-weight:700;">📦 盤整中</span>`;

    // 營收
    const rev = stock.revenue || {};
    const revText = (rev.mom != null || rev.yoy != null)
        ? `MOM: ${rev.mom != null ? rev.mom + '%' : 'N/A'}  |  YOY: ${rev.yoy != null ? rev.yoy + '%' : 'N/A'}`
        : null;

    card.innerHTML = `
        <div class="card-header">
            <div class="stock-identity">
                <div class="breakout-title">
                    <span class="stock-name">${stock.name}</span>
                    <span class="stock-code-small">${stock.code}</span>
                </div>
                <div style="margin-top:5px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
                    ${statusBadge}
                    <span style="font-size:0.82em;color:#8b949e;">盤整 <strong style="color:#cdd9e5;">${stock.consolidation_days}</strong> 天</span>
                </div>
                <!-- 箱型資訊 -->
                <div style="margin-top:5px;font-size:0.80em;color:#6e7681;">
                    箱型：${stock.box_low} ~ ${stock.box_high}
                    <span style="margin-left:6px;color:#8b949e;">波動 ${stock.box_range_pct}%</span>
                </div>
                <!-- MACD -->
                <div style="margin-top:4px;font-size:0.77em;color:#6e7681;">MACD: ${macdText}</div>
                <!-- 近5日三大法人 -->
                ${hasInst5 ? `
                <div style="margin-top:6px;font-size:0.80em;background:rgba(255,255,255,0.03);border-radius:4px;padding:5px 6px;">
                    <div style="color:#8b949e;margin-bottom:3px;">近5日三大法人</div>
                    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;">
                        <div>外資 ${fmtLots(inst5.foreign)}</div>
                        <div>投信 ${fmtLots(inst5.trust)}</div>
                        <div>自營 ${fmtLots(inst5.dealer)}</div>
                    </div>
                    <div style="margin-top:3px;border-top:1px solid #21262d;padding-top:3px;">
                        合計 ${fmtLots(inst5.total)}
                    </div>
                </div>` : ''}
                <!-- 營收 -->
                ${revText ? `<div style="margin-top:6px;padding:4px 8px;background:rgba(35,134,54,0.1);
                              border-left:3px solid #238636;border-radius:3px;
                              font-size:0.80em;color:#3fb950;">💰 ${revText}</div>` : ''}
            </div>
        </div>
        <div class="card-body">
            <div class="price-info">
                <div class="stock-price">${stock.price}</div>
                <div class="stock-change ${changeClass}">${sign}${stock.change_percent}%</div>
            </div>
        </div>`;

    return card;
}

// ─── /盤整蓄勢 ─────────────────────────────────────────────────────────────

async function fetchMomentumStocks() {
    const listEl = document.getElementById('momentum-list');
    const loadingEl = document.getElementById('momentum-loading');

    listEl.innerHTML = '';
    loadingEl.classList.remove('hidden');
    loadingEl.style.display = 'block';

    try {
        const response = await fetch('/api/momentum-stocks?min_days=2');
        const stocks = await response.json();

        loadingEl.classList.add('hidden');
        loadingEl.style.display = 'none';

        if (!stocks || stocks.length === 0) {
            listEl.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 20px; color: #8b949e;">目前沒有符合連續上漲條件的股票</div>';
            return;
        }

        stocks.forEach(stock => {
            const card = createMomentumCard(stock);
            listEl.appendChild(card);

            // Add click event for chart
            card.addEventListener('click', (e) => {
                if (e.target.closest('.layout-score') || e.target.closest('.badge')) return;
                openChart(stock.code);
            });
        });

    } catch (error) {
        console.error('Error fetching momentum stocks:', error);
        loadingEl.textContent = '載入失敗，請稍後重試';
    }
}

function createMomentumCard(stock) {
    const card = document.createElement('div');
    card.className = 'stock-card breakout-card'; // Reuse breakout styling

    // Price change styling
    const changeClass = stock.change > 0 ? 'up' : (stock.change < 0 ? 'down' : '');
    const changeSign = stock.change > 0 ? '+' : '';

    // Tags HTML
    const tagsHtml = (stock.tags || []).map(tag => {
        let color = '#388bfd';
        if (tag.includes('連漲')) color = '#ff7b72'; // Red-ish for strong trend
        if (tag.includes('累積')) color = '#e3b341'; // Yellow for accumulation
        if (tag.includes('法人')) color = '#a371f7'; // Purple for inst
        return `<span style="background: ${color}15; color: ${color}; border: 1px solid ${color}44; padding: 1px 6px; border-radius: 4px; font-size: 0.75em; margin-right: 4px; display: inline-block;">${tag}</span>`;
    }).join('');

    card.innerHTML = `
        <div class="card-header">
             <div class="stock-identity">
                <div class="breakout-title">
                    <span class="stock-name">${stock.name}</span>
                    <span class="stock-code-small">${stock.code}</span>
                </div>
                 <!-- Tags -->
                <div class="diagnostic-area" style="margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px;">
                    ${tagsHtml}
                </div>
            </div>
        </div>
        
        <div class="card-body">
            <span class="stock-price ${changeClass}">${stock.price}</span>
            <div class="stock-change ${changeClass}">
                ${changeSign}${stock.change} (${changeSign}${stock.change_percent}%)
            </div>
        </div>
        
        <div class="breakout-metrics" style="margin-top: 12px; border-top: 1px solid #30363d; padding-top: 8px;">
             <div class="breakout-metric">
                <span class="metric-label">連漲天數</span>
                <span class="metric-value" style="color: #ff7b72; font-weight: bold;">${stock.consecutive_days} 天</span>
            </div>
            <div class="breakout-metric">
                <span class="metric-label">波段漲幅</span>
                <span class="metric-value" style="color: #e3b341;">${stock.total_increase_pct}%</span>
            </div>
             <div class="breakout-metric">
                <span class="metric-label">成交量</span>
                <span class="metric-value">${Math.floor(stock.volume / 1000).toLocaleString()} 張</span>
            </div>
        </div>
    `;
    return card;
}

// --- 法人接刀 (Divergence Scanner) ---

async function openDivergenceModal() {
    const modal = document.getElementById('divergence-modal');
    const loading = document.getElementById('divergence-loading');
    const container = document.getElementById('divergence-list');
    const shadowCheckbox = document.getElementById('divergence-shadow-only');

    // Get checkbox state (default false if element missing)
    const requireShadow = shadowCheckbox ? shadowCheckbox.checked : false;

    modal.classList.remove('hidden');
    loading.classList.remove('hidden');
    container.innerHTML = '';

    try {
        // Default: 5 days, min 100 sheets (100000 shares), allow 1.0% change (default flat/small rise)
        // Pass shadow param
        const response = await fetch(`/api/divergence-stocks?days=5&min_net_buy=100&max_price_change=1.0&require_lower_shadow=${requireShadow}`);
        const result = await response.json();

        loading.classList.add('hidden');

        if (result.status === 'error') {
            container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #f85149;">掃描失敗: ${result.message}</div>`;
            return;
        }

        const stocks = result.data || [];

        if (stocks.length === 0) {
            container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #8b949e;">目前沒有發現法人接刀的股票 (淨買超 > 100張 且 股價下跌)</div>';
            return;
        }

        stocks.forEach(stock => {
            const card = createDivergenceCard(stock);
            container.appendChild(card);
        });

    } catch (error) {
        console.error('Error fetching divergence stocks:', error);
        loading.classList.add('hidden');
        container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #f85149;">掃描失敗，請稍後重試</div>`;
    }
}

function closeDivergenceModal() {
    document.getElementById('divergence-modal').classList.add('hidden');
}

function createDivergenceCard(stock) {
    const card = document.createElement('div');
    card.className = 'stock-card divergence-card'; // Reuse styles or add specific ones
    card.onclick = () => openChart(stock.code, stock.name, stock.category || '法人接刀');

    // Format numbers
    const netBuySheets = (stock.total_net / 1000).toFixed(0);
    const priceChange = stock.price_change_pct; // e.g. -2.5

    // Determine main investor (who bought the most)
    let mainInvestor = '';
    let maxBuy = -99999999;
    const details = stock.details;
    if (details.foreign > maxBuy) { maxBuy = details.foreign; mainInvestor = '外資'; }
    if (details.trust > maxBuy) { maxBuy = details.trust; mainInvestor = '投信'; }
    if (details.dealer > maxBuy) { maxBuy = details.dealer; mainInvestor = '自營'; }

    // Icon mapping
    const icons = { '外資': '🌍', '投信': '🏦', '自營': '🏢' };
    const icon = icons[mainInvestor] || '🦈';

    card.innerHTML = `
        <div class="card-header">
            <div class="stock-identity">
                <span class="stock-name">${stock.name}</span>
                <span class="stock-code-small">${stock.code}</span>
            </div>
            <span class="badge ${stock.category === '其他' ? 'trad' : 'tech'}">${stock.category}</span>
        </div>
        <div class="card-body">
            <div class="price-info">
                   <div class="stock-price">${stock.price}</div>
                   <div class="stock-change down" style="font-size: 0.9em;">
                        ${priceChange}% (5日)
                   </div>
            </div>
            
            <div style="margin-top: 10px; border-top: 1px solid #30363d; padding-top: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <span style="color: #8b949e; font-size: 0.9em;">主力淨買</span>
                    <span class="up" style="font-weight: bold;">+${netBuySheets}張</span>
                </div>
                 <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="color: #8b949e; font-size: 0.9em;">主要買盤</span>
                    <span style="color: #c9d1d9; font-size: 0.9em;">${icon} ${mainInvestor}</span>
                </div>
            </div>
        </div>
    `;
    return card;
}

// --- Pressure Scanner (Declining + Reduced Pressure) ---

function openPressureModal() {
    const modal = document.getElementById('pressure-modal');
    const loading = document.getElementById('pressure-loading');
    const resultsDiv = document.getElementById('pressure-results');

    if (modal) {
        modal.classList.remove('hidden');
        modal.style.display = 'block';

        // Reset and clear previous results
        resultsDiv.innerHTML = '';
        loading.classList.remove('hidden');
        loading.style.display = 'block';

        // Fetch data
        fetch('/api/pressure-stocks?min_days=2')
            .then(response => response.json())
            .then(data => {
                loading.classList.add('hidden');
                loading.style.display = 'none';

                if (data.length === 0) {
                    resultsDiv.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 20px;">目前沒有符合條件的股票</div>';
                    return;
                }

                data.forEach(stock => {
                    const card = createPressureStockCard(stock);
                    resultsDiv.appendChild(card);
                });
            })
            .catch(error => {
                console.error('Error fetching pressure stocks:', error);
                loading.style.display = 'none';
                resultsDiv.innerHTML = '<div style="color: red; text-align: center;">載入失敗，請稍後再試</div>';
            });
    }
}

function closePressureModal() {
    const modal = document.getElementById('pressure-modal');
    if (modal) {
        modal.classList.add('hidden');
        modal.style.display = 'none';
    }
}

function createPressureStockCard(stock) {
    const div = document.createElement('div');
    div.className = 'stock-card';
    div.onclick = () => openChart(stock.code, stock.name, stock.category);

    // Format tags
    const tagsHtml = (stock.tags || []).map(tag =>
        `<span class="stock-tag" style="background: #23863620; color: #238636; border: 1px solid #238636;">${tag}</span>`
    ).join('');

    div.innerHTML = `
        <div class="stock-header">
            <span class="stock-code">${stock.code}</span>
            <span class="stock-name">${stock.name || ''}</span>
        </div>
        <div class="stock-price-row">
            <span class="stock-price">$${stock.price}</span>
            <span class="stock-change price-down">
                ▼ ${Math.abs(stock.change)} (${stock.change_percent}%)
            </span>
        </div>
        <div class="stock-info-row" style="margin-top: 5px; font-size: 0.85em; color: #8b949e;">
            <span>連跌 ${stock.consecutive_drop_days} 天</span>
            <span>上影線佔比: ${stock.today_shadow_ratio}%</span>
        </div>
        <div class="stock-tags">
            ${tagsHtml}
        </div>
    `;
    return div;
}

// --- 分時強勢功能 (Intraday Strength) ---

async function openIntradayModal() {
    const modal = document.getElementById('intraday-modal');
    modal.classList.remove('hidden');
    fetchIntradayStocks();
}

function closeIntradayModal() {
    document.getElementById('intraday-modal').classList.add('hidden');
}

async function fetchIntradayStocks() {
    const listEl = document.getElementById('intraday-list');
    const loadingEl = document.getElementById('intraday-loading');

    listEl.innerHTML = '';
    loadingEl.classList.remove('hidden');

    try {
        const response = await fetch('/api/intraday-stocks');
        const data = await response.json();
        const stocks = data.stocks || [];

        loadingEl.classList.add('hidden');

        if (stocks.length === 0) {
            listEl.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 20px; color: #8b949e;">目前沒有發現符合分時強勢條件的股票。</div>';
            return;
        }

        stocks.forEach(stock => {
            const card = createIntradayCard(stock);
            listEl.appendChild(card);
        });

    } catch (error) {
        console.error('Error fetching intraday stocks:', error);
        loadingEl.classList.add('hidden');
        listEl.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #f85149;">載入失敗，請稍後重試</div>';
    }
}

function createIntradayCard(stock) {
    const card = document.createElement('div');
    card.className = 'stock-card breakout-card';

    // Tags HTML
    const tagsHtml = (stock.tags || []).map(tag => {
        let color = '#ff7b72'; // Default red for strength
        if (tag.includes('突破平盤')) color = '#388bfd';
        return '<span style="background: ' + color + '15; color: ' + color + '; border: 1px solid ' + color + '44; padding: 1px 6px; border-radius: 4px; font-size: 0.75em; margin-right: 4px; display: inline-block;">' + tag + '</span>';
    }).join('');

    card.onclick = () => openChart(stock.code, stock.name, stock.category);

    card.innerHTML = `
        <div class="card-header">
             <div class="stock-identity">
                <div class="breakout-title">
                    <span class="stock-name">${stock.name}</span>
                    <span class="stock-code-small">${stock.code}</span>
                </div>
                <div class="diagnostic-area" style="margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px;">
                    ${tagsHtml}
                </div>
            </div>
            <span class="badge ${stock.category === '其他' ? 'trad' : 'tech'}">${stock.category}</span>
        </div>
        
        <div class="card-body">
            <span class="stock-price up">${stock.price}</span>
            <div class="stock-change up">
                +${stock.change_percent}%
            </div>
        </div>
        
        <div class="breakout-metrics" style="margin-top: 12px; border-top: 1px solid #30363d; padding-top: 8px;">
            <div class="breakout-metric">
                <span class="metric-label">成交量</span>
                <span class="metric-value" style="color: #c9d1d9;">${stock.volume.toLocaleString()} 張</span>
            </div>
            <div class="breakout-metric">
                <span class="metric-label">當日高點</span>
                <span class="metric-value">${stock.high}</span>
            </div>
            <div class="breakout-metric">
                <span class="metric-label">回檔幅度</span>
                <span class="metric-value" style="color: ${stock.rebound_ratio < 0.1 ? '#ff7b72' : '#8b949e'};">${(stock.rebound_ratio * 100).toFixed(1)}%</span>
            </div>
        </div>
    `;
    return card;
}

async function openWantGooMajorModal() {
    const modal = document.getElementById('wantgoo-major-modal');
    const loading = document.getElementById('wantgoo-major-loading');
    const list = document.getElementById('wantgoo-major-list');

    modal.classList.remove('hidden');
    loading.classList.remove('hidden');
    list.innerHTML = '';

    try {
        const response = await fetch('/api/wantgoo/major-investors');
        const data = await response.json();

        loading.classList.add('hidden');
        if (data.length === 0) {
            list.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #8b949e;">目前無資料</div>';
            return;
        }

        data.forEach(stock => {
            list.appendChild(createWantGooMajorCard(stock));
        });
    } catch (error) {
        console.error('Error fetching WantGoo major investors:', error);
        loading.innerHTML = '載入失敗，請稍後重試';
    }
}

function closeWantGooMajorModal() {
    document.getElementById('wantgoo-major-modal').classList.add('hidden');
}

async function openWantGooEPSModal() {
    const modal = document.getElementById('wantgoo-eps-modal');
    const loading = document.getElementById('wantgoo-eps-loading');
    const list = document.getElementById('wantgoo-eps-list');

    modal.classList.remove('hidden');
    loading.classList.remove('hidden');
    list.innerHTML = '';

    try {
        const response = await fetch('/api/wantgoo/eps-rank');
        const data = await response.json();

        loading.classList.add('hidden');
        if (data.length === 0) {
            list.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #8b949e;">目前無資料</div>';
            return;
        }

        data.forEach(stock => {
            list.appendChild(createWantGooEPSCard(stock));
        });
    } catch (error) {
        console.error('Error fetching WantGoo EPS rank:', error);
        loading.innerHTML = '載入失敗，請稍後重試';
    }
}

function closeWantGooEPSModal() {
    document.getElementById('wantgoo-eps-modal').classList.add('hidden');
}

function createWantGooMajorCard(stock) {
    const div = document.createElement('div');
    div.className = 'stock-card';
    div.onclick = () => openChart(stock.code, stock.name, '主力');

    const isUp = stock.change_percent >= 0;
    const changeClass = isUp ? 'price-up' : 'price-down';
    const changePrefix = isUp ? '▲' : '▼';

    div.innerHTML = `
        <div class="stock-header">
            <span class="stock-code">${stock.code}</span>
            <span class="stock-name">${stock.name}</span>
        </div>
        <div class="stock-price-row">
            <span class="stock-price">$${stock.price}</span>
            <span class="stock-change ${changeClass}">
                ${changePrefix} ${Math.abs(stock.change_percent)}%
            </span>
        </div>
        <div class="stock-info-row" style="margin-top: 5px; font-size: 0.85em; color: #8b949e;">
            <span>淨買超: <span style="color: #ff7b72; font-weight: bold;">${stock.net_buy_sheets}</span> 張</span>
        </div>
    `;
    return div;
}

function createWantGooEPSCard(stock) {
    const div = document.createElement('div');
    div.className = 'stock-card';
    div.onclick = () => openChart(stock.code, stock.name, 'EPS');

    div.innerHTML = `
        <div class="stock-header">
            <span class="stock-code">${stock.code}</span>
            <span class="stock-name">${stock.name}</span>
        </div>
        <div class="stock-info-row" style="margin-top: 10px;">
            <span style="font-size: 1.1em; color: #e3b341;">單季 EPS: <strong>${stock.eps}</strong></span>
        </div>
    `;
    return div;
}

// Ensure click outside closes WantGoo modals
document.addEventListener('DOMContentLoaded', () => {
    window.addEventListener('click', (event) => {
        const majorModal = document.getElementById('wantgoo-major-modal');
        const epsModal = document.getElementById('wantgoo-eps-modal');
        if (event.target === majorModal) closeWantGooMajorModal();
        if (event.target === epsModal) closeWantGooEPSModal();

        const pressureModal = document.getElementById('pressure-modal');
        if (event.target === pressureModal) {
            closePressureModal();
        }

        const exDividendModal = document.getElementById('ex-dividend-modal');
        if (event.target === exDividendModal) {
            closeExDividendModal();
        }
    });
});

// --- TWSE Ex-Dividend Feature ---

async function openExDividendModal() {
    const modal = document.getElementById('ex-dividend-modal');
    const loading = document.getElementById('ex-dividend-loading');
    const container = document.getElementById('ex-dividend-list');

    modal.classList.remove('hidden');
    loading.classList.remove('hidden');
    container.innerHTML = '';

    try {
        const response = await fetch('/api/twse/ex-dividend?days=30');
        const stocks = await response.json();

        loading.classList.add('hidden');

        if (!stocks || stocks.length === 0) {
            container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #8b949e;">未來 30 天內無除權息預告</div>';
            return;
        }

        stocks.forEach(stock => {
            const card = createExDividendCard(stock);
            container.appendChild(card);
        });

    } catch (error) {
        console.error('Error fetching ex-dividend stocks:', error);
        loading.classList.add('hidden');
        container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #f85149;">載入失敗: ${error.message}</div>`;
    }
}

function closeExDividendModal() {
    document.getElementById('ex-dividend-modal').classList.add('hidden');
}

function createExDividendCard(stock) {
    const card = document.createElement('div');
    card.className = 'stock-card';
    card.style.cursor = 'pointer';
    card.onclick = () => {
        openChart(stock.code, stock.name, '除權息');
    };

    // Date formatting
    const dateObj = new Date(stock.date);
    const dateStr = `${dateObj.getMonth() + 1}/${dateObj.getDate()}`;
    const weekDay = ['日', '一', '二', '三', '四', '五', '六'][dateObj.getDay()];

    let badgeColor = '#1f6feb'; // Default Blue
    if (stock.type === '權') badgeColor = '#a371f7'; // Purple

    card.innerHTML = `
        <div class="card-header">
            <div class="stock-identity">
                <span class="stock-name">${stock.name}</span>
                <span class="stock-code-small">${stock.code}</span>
            </div>
            <span style="background: ${badgeColor}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.8em;">${stock.type}</span>
        </div>
        <div class="card-body">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="font-size: 1.2em; font-weight: bold; color: #e6edf3;">${dateStr} (${weekDay})</div>
                <div style="color: #8b949e; font-size: 0.9em;">除權息日</div>
            </div>
            
            <div class="layout-stats">
                 ${stock.cash_dividend > 0 ? `
                <div class="layout-stat-item">
                    <span class="stat-label">現金股利</span>
                    <span class="stat-value" style="color: #da3633;">${stock.cash_dividend.toFixed(2)}</span>
                </div>` : ''}
                
                ${stock.stock_dividend > 0 ? `
                <div class="layout-stat-item">
                    <span class="stat-label">股票股利</span>
                    <span class="stat-value" style="color: #da3633;">${stock.stock_dividend.toFixed(2)}</span>
                </div>` : ''}
            </div>
        </div>
    `;

    return card;
}

// --- MACD 起漲 (MACD Breakout) ---
function openMacdBreakoutModal() {
    document.getElementById('macd-breakout-modal').classList.remove('hidden');
    const listDiv = document.getElementById('macd-breakout-list');
    const loadingDiv = document.getElementById('macd-breakout-loading');

    // 如果已經有資料，就不重新抓取
    if (listDiv.children.length > 0) return;

    loadingDiv.classList.remove('hidden');
    listDiv.innerHTML = '';

    fetch(`/api/macd-breakout-stocks?${getTechParam()}`)
        .then(response => response.json())
        .then(data => {
            loadingDiv.classList.add('hidden');

            if (!data || data.length === 0) {
                listDiv.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #8b949e; padding: 20px;">目前沒有符合 MACD 起漲條件的股票。</div>';
                return;
            }

            data.forEach(stock => {
                const card = document.createElement('div');
                card.className = 'stock-card';
                card.onclick = () => {
                    hideForChart('macd-breakout-modal');
                    // 等 modal 完全隱藏後再開 chart，避免 chart container 尺寸計算錯誤
                    setTimeout(() => openChart(stock.code, stock.name, 'MACD起漲'), 150);
                };

                const changeClass = stock.change_percent >= 0 ? 'positive' : 'negative';
                const sign = stock.change_percent > 0 ? '+' : '';

                const priority = stock.signal_priority || 2;
                const borderColor = priority === 1 ? '#f1c40f' : '#da3633';
                const signalType = stock.signal_type || '-';
                const bb = stock.bollinger || {};
                const macd = stock.macd || {};
                const inst = stock.institutional || {};
                const fmtInst = (v) => {
                    if (!v) return null;
                    const lots = Math.round(v / 1000);
                    if (lots === 0) return null;
                    const sign = lots >= 0 ? '+' : '';
                    const color = lots >= 0 ? '#3fb950' : '#f85149';
                    return `<span style="color:${color}">${sign}${lots.toLocaleString()}張</span>`;
                };
                const instParts = [
                    inst.foreign ? `外資 ${fmtInst(inst.foreign)}` : null,
                    inst.trust   ? `投信 ${fmtInst(inst.trust)}`   : null,
                    inst.dealer  ? `自營 ${fmtInst(inst.dealer)}`  : null,
                ].filter(Boolean);

                card.innerHTML = `
                    <div class="stock-header">
                        <span class="stock-name" style="border-left: 4px solid ${borderColor}; padding-left: 8px;">
                            ${stock.name} (${stock.code})
                        </span>
                    </div>

                    <div class="stock-price-row" style="margin-top: 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: baseline;">
                        <span class="price" style="font-size: 1.4em; font-weight: bold;">${stock.price.toFixed(2)}</span>
                        <span class="change ${changeClass}" style="font-size: 1.1em; font-weight: bold;">
                            ${sign}${stock.change_percent.toFixed(2)}%
                        </span>
                    </div>

                    <div style="background: #0d1117; padding: 10px; border-radius: 6px; margin-bottom: 5px;">
                        <div style="color: ${borderColor}; font-weight: bold; margin-bottom: 5px;">${signalType}</div>
                        <div style="display: flex; flex-wrap: wrap; gap: 8px; font-size: 0.9em; color: #c9d1d9;">
                            <span>DIF: <span style="color:#8b949e">${macd.dif ?? '-'}</span></span>
                            <span>MACD(DEA): <span style="color:#8b949e">${macd.dea ?? '-'}</span></span>
                            <span>柱狀(Hist): <span style="color:${(macd.hist ?? 0) > 0 ? '#f85149' : '#2ea043'}">${macd.hist ?? '-'}</span></span>
                        </div>
                        <div style="font-size: 0.82em; color: #6e7681; margin-top: 4px;">
                            %B: ${bb.percent_b ?? '-'}%&nbsp; BBW: ${bb.bbw ?? '-'}%&nbsp; EMA: ${bb.bbw_ema ?? '-'}%
                        </div>
                        ${instParts.length ? `<div style="font-size:0.82em; margin-top:4px;">${instParts.join(' &nbsp;|&nbsp; ')}</div>` : ''}
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.85em; margin-top: 6px; padding-top: 6px; border-top: 1px solid #21262d;">
                        <span style="color: #8b949e;">
                            成交量 <span style="color: #c9d1d9;">${Math.round(stock.volume / 1000).toLocaleString()} 張</span>
                            &nbsp;|&nbsp; 量比
                            <span style="color: ${stock.vol_ratio >= 1.5 ? '#ff7b72' : stock.vol_ratio >= 1.0 ? '#e3b341' : '#8b949e'}; font-weight: bold;">
                                ${stock.vol_ratio ? stock.vol_ratio.toFixed(2) : '-'}x
                            </span>
                        </span>
                        <span style="color: #8b949e;">點擊查看走勢圖</span>
                    </div>
                `;
                listDiv.appendChild(card);
            });
        })
        .catch(error => {
            console.error('Error fetching MACD breakout stocks:', error);
            loadingDiv.classList.add('hidden');
            listDiv.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #ff7b72; padding: 20px;">載入失敗，請重試。</div>';
        });
}

function closeMacdBreakoutModal() {
    document.getElementById('macd-breakout-modal').classList.add('hidden');
}

// --- 動能趨勢雷達 (Trend & Momentum Radar) ---
let currentRadarTab = 'potential';

function openTrendRadarModal() {
    document.getElementById('trend-radar-modal').classList.remove('hidden');
    fetchTrendRadarStocks(false);
}

function closeTrendRadarModal() {
    document.getElementById('trend-radar-modal').classList.add('hidden');
}

function switchRadarTab(tabName) {
    currentRadarTab = tabName;
    document.querySelectorAll('.radar-tab').forEach(t => {
        t.style.color = '#8b949e';
        t.style.borderBottom = 'none';
        t.classList.remove('active');
    });
    
    const activeTab = document.getElementById('tab-' + tabName);
    activeTab.classList.add('active');
    activeTab.style.color = '#58a6ff';
    activeTab.style.borderBottom = '2px solid #58a6ff';
    
    if (tabName === 'potential') {
        document.getElementById('radar-potential-container').classList.remove('hidden');
        document.getElementById('radar-strong-container').classList.add('hidden');
    } else {
        document.getElementById('radar-potential-container').classList.add('hidden');
        document.getElementById('radar-strong-container').classList.remove('hidden');
    }
}

async function fetchTrendRadarStocks(forceRefresh = false) {
    const loading = document.getElementById('trend-radar-loading');
    const potentialList = document.getElementById('trend-radar-potential-list');
    const strongList = document.getElementById('trend-radar-strong-list');
    
    potentialList.innerHTML = '';
    strongList.innerHTML = '';
    loading.classList.remove('hidden');
    
    try {
        const response = await fetch(`/api/trend-radar-stocks?${forceRefresh ? 'force_refresh=true&' : ''}${getTechParam()}`);
        const result = await response.json();
        
        loading.classList.add('hidden');
        
        if (result.status === 'success') {
            const data = result.data;
            if (data.potential.length === 0) {
                potentialList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #8b949e; padding: 20px;">目前沒有符合潛龍伏淵條件的股票。</div>';
            } else {
                data.potential.forEach(stock => {
                    potentialList.appendChild(createTrendRadarCard(stock, 'potential'));
                });
            }
            
            if (data.strong.length === 0) {
                strongList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #8b949e; padding: 20px;">目前沒有符合乘風破浪條件的股票。</div>';
            } else {
                data.strong.forEach(stock => {
                    strongList.appendChild(createTrendRadarCard(stock, 'strong'));
                });
            }
        } else {
            throw new Error(result.error || '不明錯誤');
        }
    } catch (e) {
        console.error('Error fetching trend radar:', e);
        loading.classList.add('hidden');
        potentialList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #f85149; padding: 20px;">資料載入失敗，請重試。</div>';
        strongList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #f85149; padding: 20px;">資料載入失敗，請重試。</div>';
    }
}

function createTrendRadarCard(stock, type) {
    const card = document.createElement('div');
    card.className = 'stock-card';
    card.style.borderLeft = type === 'potential' ? '4px solid #58a6ff' : '4px solid #ff7b72';
    
    card.onclick = () => {
        // closeTrendRadarModal(); // 保持 modal 在背景
        openChart(stock.code, stock.name, '趨勢雷達');
    };

    const changeClass = stock.change_percent >= 0 ? 'up' : 'down';
    const sign = stock.change_percent > 0 ? '+' : '';
    
    const fmtVol = (v) => {
        if (!v) return '-';
        if (v >= 1e4) return (v/1e4).toFixed(1) + '萬';
        return Intl.NumberFormat().format(v);
    };

    card.innerHTML = `
        <div class="card-header">
            <div class="stock-identity">
                <span class="stock-name">${stock.name}</span>
                <span class="stock-code-small">${stock.code}</span>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                <span class="badge ${stock.category === '其他' ? 'trad' : 'tech'}">${stock.category}</span>
            </div>
        </div>
        <div class="card-body">
            <div class="price-info">
                 <div class="stock-price">${stock.price}</div>
                 <div class="stock-change ${changeClass}">
                      ${sign}${stock.change_percent}%
                 </div>
            </div>
            <div style="margin-top: 10px; color: #e6edf3; font-weight: bold; background: rgba(56, 139, 253, 0.1); padding: 4px 8px; border-radius: 4px; font-size: 0.85em; display: inline-block;">
                ${stock.reason || '動能點位'}
            </div>
            
            <div class="breakout-stats" style="margin-top: 8px; display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 0.85em; color: #8b949e;">
                <div>成交量: <span style="color: #c9d1d9;">${fmtVol(stock.volume)}</span></div>
                <div>三大法人: <span style="color: ${stock.inst_net > 0 ? '#da3633' : '#238636'};">${fmtVol(stock.inst_net)}</span></div>
                <div>位階: <span style="color: #c9d1d9;">${stock.position_pct}%</span></div>
                <div>RSI: <span style="color: #c9d1d9;">${stock.rsi || '-'}</span></div>
                <div>KD: <span style="color: #c9d1d9;">${stock.kd_k||'-'}/${stock.kd_d||'-'}</span></div>
                <div>MACD紅柱: <span style="color: ${(stock.macd_hist || 0) > 0 ? '#da3633' : '#238636'}">${stock.macd_hist||'-'}</span></div>
            </div>
        </div>
    `;
    return card;
}

/* --- Chips Scanner UI (Trust Ratio & Dealer Buy) --- */
async function openTrustRatioModal() {
    const modal = document.getElementById('trust-ratio-modal');
    const loading = document.getElementById('trust-ratio-loading');
    const container = document.getElementById('trust-ratio-list');
    
    modal.classList.remove('hidden');
    loading.classList.remove('hidden');
    container.innerHTML = '';
    
    try {
        const response = await fetch('/api/scanner/chips/trust-ratio');
        const stocks = await response.json();
        
        loading.classList.add('hidden');
        if (!stocks || stocks.length === 0) {
            container.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px;color:#8b949e;">今日無符合高投本比股票</div>';
            return;
        }
        
        stocks.forEach(stock => {
            const card = document.createElement('div');
            card.className = 'stock-card layout-stock-card';
            card.onclick = () => openChart(stock.code, stock.name, stock.category || '投本比高');
            
            card.innerHTML = `
                <div class="card-header">
                    <div class="stock-identity">
                        <span class="stock-name">${stock.name || stock.code}</span>
                        <span class="stock-code-small">${stock.code}</span>
                    </div>
                    <div style="display: flex; gap: 8px; align-items: center;">
                         <span class="badge" style="background:#d29922;color:black;font-weight:bold;">投本比 ${stock.trust_ratio}%</span>
                    </div>
                </div>
                <div class="card-body">
                    <div class="layout-stats" style="grid-template-columns: 1fr 1fr;">
                        <div class="layout-stat-item">
                            <span class="stat-label">今日價格</span>
                            <span class="stat-value" style="color:${stock.change >= 0 ? '#da3633' : '#238636'}">${stock.price || '--'}</span>
                        </div>
                        <div class="layout-stat-item">
                            <span class="stat-label">投信買超</span>
                            <span class="stat-value" style="color:#da3633;">+${stock.trust_net_buy} 張</span>
                        </div>
                    </div>
                </div>
            `;
            container.appendChild(card);
        });
    } catch(err) {
        console.error(err);
        loading.classList.add('hidden');
        container.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:#f85149;">載入失敗</div>';
    }
}

function closeTrustRatioModal() {
    const modal = document.getElementById('trust-ratio-modal');
    if (modal) modal.classList.add('hidden');
}

async function openDealerBuyModal() {
    const modal = document.getElementById('dealer-buy-modal');
    const loading = document.getElementById('dealer-buy-loading');
    const container = document.getElementById('dealer-buy-list');
    
    modal.classList.remove('hidden');
    loading.classList.remove('hidden');
    container.innerHTML = '';
    
    try {
        const response = await fetch('/api/scanner/chips/dealer-buy');
        const stocks = await response.json();
        
        loading.classList.add('hidden');
        if (!stocks || stocks.length === 0) {
            container.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px;color:#8b949e;">今日無自營商大買超股票</div>';
            return;
        }
        
        stocks.forEach(stock => {
            const card = document.createElement('div');
            card.className = 'stock-card layout-stock-card';
            card.onclick = () => openChart(stock.code, stock.name, stock.category || '自營商買超');
            
            card.innerHTML = `
                <div class="card-header">
                    <div class="stock-identity">
                        <span class="stock-name">${stock.name || stock.code}</span>
                        <span class="stock-code-small">${stock.code}</span>
                    </div>
                    <div style="display: flex; gap: 8px; align-items: center;">
                         <span class="badge" style="background:#ff7b72;color:black;font-weight:bold;">買超 ${stock.dealer_net_buy}張</span>
                    </div>
                </div>
                <div class="card-body">
                    <div class="layout-stats" style="grid-template-columns: 1fr 1fr;">
                        <div class="layout-stat-item">
                            <span class="stat-label">今日價格</span>
                            <span class="stat-value" style="color:${stock.change >= 0 ? '#da3633' : '#238636'}">${stock.price || '--'}</span>
                        </div>
                        <div class="layout-stat-item">
                            <span class="stat-label">成交量</span>
                            <span class="stat-value">${stock.volume} 張</span>
                        </div>
                    </div>
                </div>
            `;
            container.appendChild(card);
        });
    } catch(err) {
        console.error(err);
        loading.classList.add('hidden');
        container.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:#f85149;">載入失敗</div>';
    }
}

function closeDealerBuyModal() {
    const modal = document.getElementById('dealer-buy-modal');
    if (modal) modal.classList.add('hidden');
}

// Ensure modals close when clicked outside
window.addEventListener('click', (event) => {
    const trustRatioModal = document.getElementById('trust-ratio-modal');
    if (event.target === trustRatioModal) closeTrustRatioModal();
    
    const dealerBuyModal = document.getElementById('dealer-buy-modal');
    if (event.target === dealerBuyModal) closeDealerBuyModal();
});


window.openComboSuggestionModal = function() {
    const modal = document.getElementById('combo-suggestion-modal');
    if (modal) modal.classList.remove('hidden');
};

window.closeComboSuggestionModal = function() {
    const modal = document.getElementById('combo-suggestion-modal');
    if (modal) modal.classList.add('hidden');
};

window.addEventListener('click', (event) => {
    const comboModal = document.getElementById('combo-suggestion-modal');
    if (comboModal && event.target === comboModal) {
        window.closeComboSuggestionModal();
    }
});
