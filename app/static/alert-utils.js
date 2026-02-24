/**
 * 警示輔助工具
 * 處理頂層橫幅提示與音效播放
 */

let alertAudio = null;

// 顯示頂層警示橫幅
function showTopLevelAlert(title, body, stockCode) {
    const banner = document.getElementById('top-alert-banner');
    const messageEl = document.getElementById('alert-message');

    if (!banner || !messageEl) return;

    // 設定訊息內容
    messageEl.innerHTML = `<strong>${title}</strong>: ${body}`;

    // 點擊橫幅開啟圖表
    banner.onclick = (e) => {
        if (e.target.classList.contains('alert-close')) return;
        if (typeof openChart === 'function') {
            openChart(stockCode);
        }
    };

    // 顯示橫幅
    banner.classList.remove('hidden');

    // 播放音效
    playAlertSound();

    // 10秒後自動關閉
    setTimeout(() => {
        closeTopAlert();
    }, 15000);
}

// 關閉頂層警示橫幅
function closeTopAlert() {
    const banner = document.getElementById('top-alert-banner');
    if (banner) {
        banner.classList.add('hidden');
    }
}

// 播放警示音
function playAlertSound() {
    try {
        if (!alertAudio) {
            // 使用 Base64 內嵌簡短的通知音效，確保在沒有外部檔案的情況下也能運作
            // 這是一個簡單的 "Ping" 聲
            const base64Audio = "data:audio/wav;base64,UklGRl9vT19XQVZFRm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YV9vT18A";
            // 由於 Base64 太長會影響處理，這裡先嘗試讀取外部檔案，若失敗則不播放或使用更簡短的資源
            alertAudio = new Audio('https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3');
        }
        alertAudio.play().catch(e => console.log('Audio play blocked by browser policy:', e));
    } catch (e) {
        console.error('Failed to play alert sound:', e);
    }
}
