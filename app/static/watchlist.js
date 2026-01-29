/**
 * 股票監控警示系統 - 前端模組
 * 功能：監控清單管理、警示條件檢查、瀏覽器通知
 */

// ===== 警示類型定義 =====
const ALERT_TYPES = {
    'price_above': '價格突破',
    'price_below': '價格跌破',
    'change_percent_above': '漲幅超過',
    'change_percent_below': '跌幅超過',
    'bid_ask_ratio_above': '買賣比超過'
};

// ===== 監控清單管理器 =====
class WatchlistManager {
    constructor() {
        this.watchlist = this.load();
    }

    save() {
        try {
            localStorage.setItem('stock_watchlist', JSON.stringify(this.watchlist));
        } catch (e) {
            console.error('Failed to save watchlist:', e);
        }
    }

    load() {
        try {
            const data = localStorage.getItem('stock_watchlist');
            return data ? JSON.parse(data) : [];
        } catch (e) {
            console.error('Failed to load watchlist:', e);
            return [];
        }
    }

    add(stock, alerts) {
        const item = {
            id: `watch_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            stock_code: stock.code,
            stock_name: stock.name,
            alerts: alerts || [],
            triggered: [],
            created_at: new Date().toISOString()
        };
        this.watchlist.push(item);
        this.save();
        return item;
    }

    remove(id) {
        this.watchlist = this.watchlist.filter(item => item.id !== id);
        this.save();
    }

    update(id, alerts) {
        const item = this.watchlist.find(w => w.id === id);
        if (item) {
            item.alerts = alerts;
            this.save();
        }
    }

    get(id) {
        return this.watchlist.find(w => w.id === id);
    }

    getAll() {
        return this.watchlist;
    }

    resetTriggered() {
        // 收盤後重設觸發記錄（每天14:00後執行）
        this.watchlist.forEach(item => {
            item.triggered = [];
        });
        this.save();
    }
}

// ===== 監控輪詢管理器 =====
class WatchlistPolling {
    constructor(manager) {
        this.manager = manager;
        this.interval = null;
        this.isRunning = false;
        this.lastCheckTime = null;
        this.checkFrequency = 30000; // 30 seconds
    }

    isMarketHours() {
        const now = new Date();
        const hour = now.getHours();
        const minute = now.getMinutes();
        const day = now.getDay();

        // Monday to Friday, 09:00-13:30
        if (day >= 1 && day <= 5) {
            if ((hour === 9 && minute >= 0) || (hour >= 10 && hour < 13) || (hour === 13 && minute <= 30)) {
                return true;
            }
        }
        return false;
    }

    start() {
        if (this.isRunning) {
            console.log('[Watchlist] Polling already running');
            return;
        }

        console.log('[Watchlist] Starting polling...');
        this.isRunning = true;

        // Immediate first check
        this.check();

        // Set interval
        this.interval = setInterval(() => {
            if (this.isMarketHours()) {
                this.check();
            } else {
                console.log('[Watchlist] Outside market hours, skipping check');
                this.updateStatusDisplay('非盤中時間');
            }
        }, this.checkFrequency);
    }

    async check() {
        const watchlist = this.manager.getAll();

        if (watchlist.length === 0) {
            console.log('[Watchlist] No items to monitor');
            this.updateStatusDisplay('無監控項目');
            return;
        }

        const codes = watchlist.map(item => item.stock_code);
        console.log(`[Watchlist] Checking ${codes.length} stocks...`);

        try {
            const response = await fetch(`/api/watchlist/check?codes=${codes.join(',')}`);
            const stocks = await response.json();

            this.lastCheckTime = new Date();
            this.updateStatusDisplay(`運作中 - ${this.formatTime(this.lastCheckTime)}`);

            stocks.forEach(stock => {
                const watchItems = watchlist.filter(w => w.stock_code === stock.code);
                watchItems.forEach(item => {
                    this.checkAlerts(item, stock);
                });
            });

        } catch (error) {
            console.error('[Watchlist] Check failed:', error);
            this.updateStatusDisplay('檢查失敗');
        }
    }

    checkAlerts(item, stock) {
        item.alerts.forEach((alert, index) => {
            if (!alert.enabled) return;

            const alertKey = `${alert.type}_${index}`;
            if (item.triggered.includes(alertKey)) return; // Already triggered today

            let triggered = false;
            let actualValue = null;

            switch (alert.type) {
                case 'price_above':
                    triggered = stock.price >= alert.value;
                    actualValue = stock.price;
                    break;
                case 'price_below':
                    triggered = stock.price <= alert.value;
                    actualValue = stock.price;
                    break;
                case 'change_percent_above':
                    triggered = stock.change_percent >= alert.value;
                    actualValue = stock.change_percent;
                    break;
                case 'change_percent_below':
                    triggered = stock.change_percent <= alert.value;
                    actualValue = stock.change_percent;
                    break;
                case 'bid_ask_ratio_above':
                    triggered = stock.bid_ask_ratio >= alert.value;
                    actualValue = stock.bid_ask_ratio;
                    break;
            }

            if (triggered) {
                this.notify(item.stock_name, alert, actualValue, stock);
                item.triggered.push(alertKey);
                this.manager.save();
            }
        });
    }

    notify(stockName, alert, actualValue, stock) {
        const title = `⚠️ ${stockName} 警示`;
        const body = `${ALERT_TYPES[alert.type]}: ${alert.value}\n實際: ${actualValue}\n目前股價: ${stock.price} (${stock.change_percent >= 0 ? '+' : ''}${stock.change_percent}%)`;

        console.log(`[Watchlist] Alert triggered: ${title} - ${body}`);

        // Browser notification
        if (Notification.permission === 'granted') {
            const notification = new Notification(title, {
                body: body,
                icon: '/static/icon.png',
                badge: '/static/icon.png',
                requireInteraction: false
            });

            notification.onclick = function () {
                window.focus();
                openChart(stock.code, stockName, '監控警示');
                notification.close();
            };
        }

        // Also play sound (optional)
        try {
            const audio = new Audio('/static/alert.mp3'); //如果有音效檔案
            audio.play().catch(e => console.log('Audio play failed:', e));
        } catch (e) {
            // Ignore if no audio file
        }
    }

    updateStatusDisplay(status) {
        const statusEl = document.getElementById('watchlist-status');
        if (statusEl) {
            statusEl.textContent = status;
        }
    }

    formatTime(date) {
        return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
    }

    stop() {
        if (this.interval) {
            clearInterval(this.interval);
            this.interval = null;
        }
        this.isRunning = false;
        this.updateStatusDisplay('已停止');
        console.log('[Watchlist] Polling stopped');
    }
}

// ===== Global Instances =====
let watchlistManager = null;
let watchlistPolling = null;

// ===== Initialization =====
function initWatchlist() {
    watchlistManager = new WatchlistManager();
    watchlistPolling = new WatchlistPolling(watchlistManager);

    // Request notification permission
    if (Notification.permission === 'default') {
        Notification.requestPermission().then(permission => {
            console.log(`[Watchlist] Notification permission: ${permission}`);
        });
    }

    // Auto-start polling if market hours
    if (watchlistPolling.isMarketHours() && watchlistManager.getAll().length > 0) {
        watchlistPolling.start();
    }

    // Reset triggered alerts daily at 14:30
    const now = new Date();
    const resetTime = new Date();
    resetTime.setHours(14, 30, 0, 0);

    if (now > resetTime) {
        resetTime.setDate(resetTime.getDate() + 1);
    }

    const msToReset = resetTime - now;
    setTimeout(() => {
        watchlistManager.resetTriggered();
        console.log('[Watchlist] Daily reset completed');
        // Schedule next reset
        setInterval(() => {
            watchlistManager.resetTriggered();
        }, 24 * 60 * 60 * 1000);
    }, msToReset);
}

// Initialize when DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initWatchlist);
} else {
    initWatchlist();
}
