// DOM Elements
const indexPriceEl = document.getElementById('index-price');
const indexChangeEl = document.getElementById('index-change');
const stockListEl = document.getElementById('stock-list');
const loadingMsg = document.getElementById('loading-msg');
const chartSection = document.getElementById('chart-container-wrapper');
const chartContainer = document.getElementById('chart-container');
const chartTitle = document.getElementById('chart-title');
const closeChartBtn = document.getElementById('close-chart');

// State
let chart = null;
let currentStock = null;
let candlestickSeries = null;

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    fetchMarketIndex();
    fetchStocks();
    setInterval(fetchMarketIndex, 5000); // Update index every 5 seconds

    closeChartBtn.addEventListener('click', closeChart);
});

// --- Market Index ---
async function fetchMarketIndex() {
    try {
        const response = await fetch('/api/market-index');
        const data = await response.json();
        renderIndex(data);
    } catch (error) {
        console.error('Error fetching index:', error);
    }
}

function renderIndex(data) {
    indexPriceEl.textContent = data.price.toLocaleString();
    const sign = data.change >= 0 ? '+' : '';
    const colorClass = data.change >= 0 ? 'up' : 'down';

    indexChangeEl.textContent = `${sign}${data.change} (${data.percent_change}%)`;
    indexChangeEl.className = `index-change ${colorClass}`;
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

function renderStocks(stocks) {
    loadingMsg.style.display = 'none';
    stockListEl.innerHTML = '';
    categoryFilterEl.innerHTML = '';

    if (stocks.length === 0) {
        stockListEl.innerHTML = '<div style="grid-column: 1/-1; text-align: center;">目前沒有符合條件的股票。</div>';
        return;
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
                         MA20: ${stock.ma20} (${stock.diff_percent}%)
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

    if (!chart) {
        initChart();
    }

    // Force resize calculation after modal is shown to ensure chart renders
    const resizeChart = () => {
        if (chart && chartContainer) {
            chart.resize(chartContainer.clientWidth, chartContainer.clientHeight);
            chart.timeScale().fitContent();
        }
    };

    // Try multiple resize attempts to ensure it catches the layout
    setTimeout(resizeChart, 50);
    setTimeout(resizeChart, 200);
    setTimeout(resizeChart, 500);

    // Reset to "Day" view by default
    currentInterval = '1d';
    await loadChartData(stockCode, '1d');

    // One more resize after data load
    setTimeout(resizeChart, 100);

    // Start polling for real-time updates
    if (chartIntervalId) clearInterval(chartIntervalId);
    chartIntervalId = setInterval(() => {
        // Default to '1d' or current selected interval if we tracked it
        // For simplicity, let's just re-fetch the current view
        // But we need to know the current interval. 
        // Let's store it.
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
}

function initChart() {
    chart = LightweightCharts.createChart(chartContainer, {
        width: chartContainer.clientWidth,
        height: chartContainer.clientHeight,
        layout: {
            background: { type: 'solid', color: '#161b22' },
            textColor: '#c9d1d9',
        },
        grid: {
            vertLines: { color: '#30363d' },
            horzLines: { color: '#30363d' },
        },
        rightPriceScale: {
            borderColor: '#30363d',
        },
        timeScale: {
            borderColor: '#30363d',
        },
    });

    candlestickSeries = chart.addCandlestickSeries({
        upColor: '#da3633',        // Red for up
        downColor: '#238636',      // Green for down
        borderVisible: false,
        wickUpColor: '#da3633',    // Red for up
        wickDownColor: '#238636',  // Green for down
    });

    new ResizeObserver(entries => {
        if (entries.length === 0 || entries[0].target !== chartContainer) { return; }
        const newRect = entries[0].contentRect;
        chart.applyOptions({ width: newRect.width, height: newRect.height });
    }).observe(chartContainer);
}

let currentInterval = '1d';

async function setChartInterval(interval) {
    if (!currentStock) return;
    // Map Chinese UI to backend interval
    const map = { 'D': '1d', 'W': '1wk', 'M': '1mo' };
    currentInterval = map[interval] || '1d';
    await loadChartData(currentStock, currentInterval);
}

async function loadChartData(stockCode, interval) {
    try {
        const response = await fetch(`/api/history/${stockCode}?interval=${interval}`);
        const data = await response.json();
        console.log(`[Chart Data] ${stockCode} (${interval}):`, data); // Debug Log
        if (!data || data.length === 0) {
            console.warn(`[Chart Data] No data received for ${stockCode}`);
            return;
        }
        candlestickSeries.setData(data);
        chart.timeScale().fitContent();

        // Update Header Info based on latest data
        updateChartHeader(data);
    } catch (error) {
        console.error('Error loading chart:', error);
    }
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
