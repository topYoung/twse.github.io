/**
 * 監控清單功能 UI 控制函數
 * 與 watchlist.js 模組整合
 */

// 全域變數：目前選中的股票
let selectedStock = null;

// 開啟監控清單 Modal
function openWatchlistModal() {
    const modal = document.getElementById('watchlist-modal');
    modal.classList.remove('hidden');

    // 渲染監控清單
    renderWatchlistItems();
}

// 關閉監控清單 Modal
function closeWatchlistModal() {
    const modal = document.getElementById('watchlist-modal');
    modal.classList.add('hidden');

    // 清空搜尋
    document.getElementById('watchlist-search').value = '';
    selectedStock = null;
    document.getElementById('watchlist-selected-stock').classList.add('hidden');
    document.getElementById('watchlist-alert-config').classList.add('hidden');
}

// 渲染監控項目清單
function renderWatchlistItems() {
    const container = document.getElementById('watchlist-items');
    const items = watchlistManager.getAll();

    if (items.length === 0) {
        container.innerHTML = '<div style="text-align: center; color: #8b949e; padding: 40px;">尚未新增任何監控項目</div>';
        return;
    }

    container.innerHTML = '';

    items.forEach(item => {
        const card = createWatchlistCard(item);
        container.appendChild(card);
    });
}

// 建立監控項目卡片
function createWatchlistCard(item) {
    const card = document.createElement('div');
    card.className = 'watchlist-card';
    card.style.cssText = 'background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 16px; margin-bottom: 12px;';

    // 建立警示列表 HTML
    let alertsHtml = '';
    item.alerts.forEach((alert, index) => {
        if (!alert.enabled) return;

        const icon = alert.type.includes('above') ? '📈' : '📉';
        const typeName = ALERT_TYPES[alert.type] || alert.type;
        const triggered = item.triggered.includes(`${alert.type}_${index}`);

        alertsHtml += `
            <div class="alert-item" style="display: flex; align-items: center; gap: 8px; padding: 6px 10px; background: ${triggered ? '#1a2c1a' : '#0d1117'}; border-radius: 4px; margin-bottom: 4px; ${triggered ? 'border: 1px solid #238636' : ''}">
                <span style="font-size: 1.2em;">${icon}</span>
                <span style="flex: 1; color: ${triggered ? '#3fb950' : '#e6edf3'};">${typeName}: ${alert.value}</span>
                ${triggered ? '<span style="color: #3fb950; font-size: 0.9em;">✓ 已觸發</span>' : ''}
            </div>
        `;
    });

    if (!alertsHtml) {
        alertsHtml = '<div style="color: #8b949e; font-size: 0.9em;">無啟用的警示條件</div>';
    }

    card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div>
                <span style="color: #58a6ff; font-size: 1.1em; font-weight: bold;">${item.stock_name}</span>
                <span style="color: #8b949e; margin-left: 8px;">(${item.stock_code})</span>
            </div>
            <button onclick="removeWatchlistItem('${item.id}')" class="investor-btn" 
                style="padding: 4px 8px; background: #da3633; border: none; color: white; font-size: 0.9em;">
                刪除
            </button>
        </div>
        <div class="alert-list">
            ${alertsHtml}
        </div>
    `;

    return card;
}

// 股票搜尋 - 即時搜尋建議
let searchTimeout = null;
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('watchlist-search');
    if (!searchInput) return;

    searchInput.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        const query = e.target.value.trim();

        if (query.length < 1) {
            document.getElementById('watchlist-search-results').classList.add('hidden');
            return;
        }

        searchTimeout = setTimeout(async () => {
            try {
                const response = await fetch(`/api/search?query=${encodeURIComponent(query)}&limit=8`);
                const results = await response.json();

                displaySearchResults(results);
            } catch (error) {
                console.error('Search failed:', error);
            }
        }, 300);
    });
});

// 顯示搜尋結果
function displaySearchResults(results) {
    const container = document.getElementById('watchlist-search-results');

    if (results.length === 0) {
        container.classList.add('hidden');
        return;
    }

    container.innerHTML = '';
    container.classList.remove('hidden');

    results.forEach(stock => {
        const item = document.createElement('div');
        item.className = 'search-result-item';
        item.style.cssText = 'padding: 10px; cursor: pointer; border-bottom: 1px solid #30363d;';
        item.innerHTML = `
            <span style="color: #58a6ff;">${stock.name}</span>
            <span style="color: #8b949e; margin-left: 8px;">(${stock.code})</span>
        `;

        item.addEventListener('click', () => selectStock(stock));
        item.addEventListener('mouseenter', () => item.style.background = '#161b22');
        item.addEventListener('mouseleave', () => item.style.background = 'transparent');

        container.appendChild(item);
    });
}

// 選擇股票
function selectStock(stock) {
    selectedStock = stock;

    // 隱藏搜尋結果
    document.getElementById('watchlist-search-results').classList.add('hidden');
    document.getElementById('watchlist-search').value = '';

    // 顯示選中的股票
    document.getElementById('selected-stock-name').textContent = `${stock.name} (${stock.code})`;
    document.getElementById('watchlist-selected-stock').classList.remove('hidden');

    // 顯示警示設定區
    document.getElementById('watchlist-alert-config').classList.remove('hidden');
}

// 新增監控項目
function addWatchlistItem() {
    if (!selectedStock) {
        alert('請先選擇股票');
        return;
    }

    // 收集警示條件
    const alerts = [];
    const alertItems = document.querySelectorAll('.alert-config-item');

    alertItems.forEach(item => {
        const checkbox = item.querySelector('.alert-enabled');
        const valueInput = item.querySelector('.alert-value');

        if (checkbox.checked && valueInput.value) {
            alerts.push({
                type: checkbox.dataset.type,
                value: parseFloat(valueInput.value),
                enabled: true
            });
        }
    });

    if (alerts.length === 0) {
        alert('請至少設定一個警示條件');
        return;
    }

    // 新增到管理器
    watchlistManager.add(selectedStock, alerts);

    // 重置表單
    selectedStock = null;
    document.getElementById('watchlist-selected-stock').classList.add('hidden');
    document.getElementById('watchlist-alert-config').classList.add('hidden');

    // 清空警示設定
    alertItems.forEach(item => {
        item.querySelector('.alert-enabled').checked = false;
        item.querySelector('.alert-value').value = '';
    });

    // 重新渲染列表
    renderWatchlistItems();

    // 顯示成功訊息
    alert(`✓ 已新增 ${selectedStock.name} 至監控清單`);
    selectedStock = null;
}

// 移除監控項目
function removeWatchlistItem(id) {
    if (confirm('確定要移除這個監控項目嗎？')) {
        watchlistManager.remove(id);
        renderWatchlistItems();
    }
}

// 啟動/停止監控輪詢
function toggleWatchlistPolling() {
    const button = document.getElementById('watchlist-toggle');

    if (watchlistPolling.isRunning) {
        watchlistPolling.stop();
        button.textContent = '啟動監控';
        button.style.background = '';
    } else {
        const items = watchlistManager.getAll();

        if (items.length === 0) {
            alert('請先新增監控項目');
            return;
        }

        // 請求通知權限
        if (Notification.permission === 'default') {
            Notification.requestPermission().then(permission => {
                if (permission === 'granted') {
                    watchlistPolling.start();
                    button.textContent = '停止監控';
                    button.style.background = '#da3633';
                } else {
                    alert('需要通知權限才能使用監控功能');
                }
            });
        } else if (Notification.permission === 'granted') {
            watchlistPolling.start();
            button.textContent = '停止監控';
            button.style.background = '#da3633';
        } else {
            alert('需要通知權限才能使用監控功能\n請在瀏覽器設定中允許通知');
        }
    }
}
