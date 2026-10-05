const SUPABASE_URL = 'https://zyetspnudlkojcqiwtao.supabase.co';
const SUPABASE_KEY = 'sb_publishable_e9BdBnsaKzy-aX3iXggpug_LJM18QPc';

// 支出與收入/轉帳分類資料
const categoryData = {
    "income": {
        name: "💰 收入",
        type: "income",
        subcategories: {
            "salary": "薪水收入",
            "parttime": "兼職收入",
            "bonus": "獎金/其他收入"
        }
    },
    "transfer": {
        name: "🔄 提領/儲值 (轉帳)",
        type: "transfer",
        subcategories: {
            "cash_withdraw": "現金提領 (銀行提款)",
            "easycard_topup": "悠遊卡加值 (銀行扣款)"
        }
    },
    "food": {
        name: "飲食",
        type: "expense",
        subcategories: {
            "restaurant": "餐廳/外食",
            "fastfood": "速食/速食店",
            "breakfast": "早午晚餐",
            "cafe": "咖啡/飲料",
            "delivery": "外送平台"
        }
    },
    "clothing": {
        name: "服飾與美容",
        type: "expense",
        subcategories: {
            "clothes": "衣物/鞋包",
            "beauty": "美容/理髮/保養",
            "accessories": "飾品/配件"
        }
    },
    "transport": {
        name: "交通",
        type: "expense",
        subcategories: {
            "fuel": "加油",
            "public": "大眾運輸",
            "parking": "停車費",
            "toll": "過路費/儲值"
        }
    },
    "living": {
        name: "居家與生活",
        type: "expense",
        subcategories: {
            "rent": "房租",
            "utilities": "水電瓦斯",
            "telecom": "電信/通訊",
            "grocery": "生鮮/超市",
            "daily": "藥妝/日用品",
            "hardware": "居家/五金/修繕"
        }
    },
    "entertainment": {
        name: "休閒與旅遊",
        type: "expense",
        subcategories: {
            "accommodation": "住宿/飯店",
            "activity": "休閒娛樂/景點"
        }
    },
    "shopping": {
        name: "購物",
        type: "expense",
        subcategories: {
            "online": "網購/綜合購物",
            "pet": "寵物用品"
        }
    },
    "digital": {
        name: "數位與軟體",
        type: "expense",
        subcategories: {
            "software": "軟體訂閱/服務",
            "wallet": "電子票證加值"
        }
    },
    "misc": {
        name: "其他/手續費",
        type: "expense",
        subcategories: {
            "fee": "銀行/手續費",
            "refund": "折抵/退款",
            "tithe": "什一奉獻"
        }
    }
};

// DOM 元素
const form = document.getElementById('expense-form');
const amountInput = document.getElementById('amount');
const dateInput = document.getElementById('date');
const paymentMethodSelect = document.getElementById('payment-method');
const mainCategorySelect = document.getElementById('main-category');
const subCategorySelect = document.getElementById('sub-category');
const noteInput = document.getElementById('note');
const expenseList = document.getElementById('expense-list');
const totalAmountDisplay = document.getElementById('total-amount');
const totalIncomeDisplay = document.getElementById('total-income');
const totalBalanceDisplay = document.getElementById('total-balance');
const cashBalanceDisplay = document.getElementById('cash-balance');
const cashHintDisplay = document.getElementById('cash-hint');
const easycardBalanceDisplay = document.getElementById('easycard-balance');
const easycardHintDisplay = document.getElementById('easycard-hint');
const monthSelector = document.getElementById('month-selector');
const categoryBreakdown = document.getElementById('category-breakdown');
const clearDataBtn = document.getElementById('clear-data-btn');
const exportCsvBtn = document.getElementById('export-csv-btn');

// 初始化資料
let expenses = [];

// 初始化畫面
async function init() {
    // 設定預設日期為今天
    const today = new Date().toISOString().split('T')[0];
    dateInput.value = today;

    // 設定月份選擇器為當月
    monthSelector.value = today.slice(0, 7);

    // 載入主分類選項
    for (const [key, value] of Object.entries(categoryData)) {
        const option = document.createElement('option');
        option.value = key;
        option.textContent = value.name;
        mainCategorySelect.appendChild(option);
    }

    await loadDataFromCloud();
}

// 主分類變更事件：連動次分類與預設支付方式
mainCategorySelect.addEventListener('change', (e) => {
    const mainKey = e.target.value;

    // 清空並啟用次分類
    subCategorySelect.innerHTML = '<option value="" disabled selected>請選擇次分類</option>';
    subCategorySelect.disabled = false;

    if (mainKey && categoryData[mainKey]) {
        const subs = categoryData[mainKey].subcategories;
        for (const [subKey, subName] of Object.entries(subs)) {
            const option = document.createElement('option');
            option.value = subKey;
            option.textContent = subName;
            subCategorySelect.appendChild(option);
        }

        // 智慧帶入建議的支付/入帳方式
        if (mainKey === 'income') {
            paymentMethodSelect.value = '銀行轉帳';
        } else if (mainKey === 'transfer') {
            paymentMethodSelect.value = '銀行轉帳';
        }
    }
});

// 監聽月份選擇器變更
monthSelector.addEventListener('change', renderExpenses);

// 表單送出事件
form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const amount = parseFloat(amountInput.value);
    const date = dateInput.value;
    const paymentMethod = paymentMethodSelect.value;
    const mainCat = mainCategorySelect.value;
    const subCat = subCategorySelect.value;
    const note = noteInput.value.trim();

    if (!amount || !date || !mainCat || !subCat || !paymentMethod) {
        alert('請填寫完整資訊！');
        return;
    }

    // 將按鈕設為讀取中，避免重複點擊
    const submitBtn = form.querySelector('button[type="submit"]');
    const originalBtnText = submitBtn.textContent;
    submitBtn.textContent = '雲端儲存中...';
    submitBtn.disabled = true;

    const newExpense = {
        amount: amount,
        date: date,
        payment_method: paymentMethod,
        main_cat: mainCat,
        sub_cat: subCat,
        note: note
    };

    try {
        const response = await fetch(`${SUPABASE_URL}/rest/v1/expenses`, {
            method: 'POST',
            headers: {
                'apikey': SUPABASE_KEY,
                'Authorization': `Bearer ${SUPABASE_KEY}`,
                'Content-Type': 'application/json',
                'Prefer': 'return=representation'
            },
            body: JSON.stringify(newExpense)
        });

        if (!response.ok) throw new Error('新增失敗');
        const data = await response.json();
        
        // 將雲端回傳的完整資料 (包含 UUID) 加到最前面
        const inserted = data[0];
        expenses.unshift({
            id: inserted.id,
            amount: inserted.amount,
            date: inserted.date,
            paymentMethod: inserted.payment_method,
            mainCat: inserted.main_cat,
            subCat: inserted.sub_cat,
            note: inserted.note
        });

        // 若新增的日期不在目前選擇的月份，可自動切換至該月
        const expMonth = date.slice(0, 7);
        if (monthSelector.value !== expMonth) {
            monthSelector.value = expMonth;
        }

        renderExpenses();

        // 重設表單部分欄位，保留日期
        amountInput.value = '';
        noteInput.value = '';
        amountInput.focus();

    } catch (error) {
        console.error("Error saving data:", error);
        alert('儲存失敗，請檢查網路連線。');
    } finally {
        submitBtn.textContent = originalBtnText;
        submitBtn.disabled = false;
    }
});

// 清除資料
clearDataBtn.addEventListener('click', async () => {
    if (confirm('確定要清除所有記帳紀錄嗎？此動作無法復原且會刪除雲端資料庫的所有資料！')) {
        clearDataBtn.textContent = '清除中...';
        clearDataBtn.disabled = true;
        try {
            // 刪除所有不為空的 ID，等於清空整個 Table (請小心使用)
            const response = await fetch(`${SUPABASE_URL}/rest/v1/expenses?id=not.is.null`, {
                method: 'DELETE',
                headers: {
                    'apikey': SUPABASE_KEY,
                    'Authorization': `Bearer ${SUPABASE_KEY}`
                }
            });
            if (!response.ok) throw new Error('清除失敗');
            expenses = [];
            renderExpenses();
        } catch (error) {
            console.error(error);
            alert('清除失敗，請檢查連線');
        } finally {
            clearDataBtn.textContent = '清除全部紀錄';
            clearDataBtn.disabled = false;
        }
    }
});

// 匯出 CSV
exportCsvBtn.addEventListener('click', () => {
    if (expenses.length === 0) {
        alert('目前沒有資料可以匯出喔！');
        return;
    }

    const headers = ['日期', '類型', '主分類', '次分類', '支付/入帳方式', '金額', '備註'];
    const csvRows = [headers.join(',')];

    // 依日期排序 (最新在最上)
    const sortedExpenses = [...expenses].sort((a, b) => new Date(b.date) - new Date(a.date));

    sortedExpenses.forEach(exp => {
        const itemType = categoryData[exp.mainCat]?.type || 'expense';
        let typeLabel = '支出';
        if (itemType === 'income') typeLabel = '收入';
        if (itemType === 'transfer') typeLabel = '提領/儲值';

        const mainName = categoryData[exp.mainCat]?.name || exp.mainCat;
        const subName = categoryData[exp.mainCat]?.subcategories?.[exp.subCat] || exp.subCat;
        const note = exp.note ? `"${exp.note.replace(/"/g, '""')}"` : '';

        const row = [
            exp.date,
            typeLabel,
            mainName.replace(/^[^\s]+\s/, ''), // 去除 Emoji 保持 CSV 清爽
            subName,
            exp.paymentMethod || '信用卡',
            exp.amount,
            note
        ];
        csvRows.push(row.join(','));
    });

    const csvString = "\uFEFF" + csvRows.join('\n'); // 加上 BOM 讓 Excel 正確顯示中文
    const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", `記帳紀錄_${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
});

// 刪除單筆資料 (供 HTML 呼叫)
window.deleteExpense = async function (id) {
    if (confirm('確定要刪除這筆紀錄嗎？')) {
        try {
            const response = await fetch(`${SUPABASE_URL}/rest/v1/expenses?id=eq.${id}`, {
                method: 'DELETE',
                headers: {
                    'apikey': SUPABASE_KEY,
                    'Authorization': `Bearer ${SUPABASE_KEY}`
                }
            });
            if (!response.ok) throw new Error('刪除失敗');
            
            expenses = expenses.filter(exp => exp.id !== id);
            renderExpenses();
        } catch (error) {
            console.error("Error deleting:", error);
            alert('刪除失敗，請檢查連線');
        }
    }
};

// 從 Supabase 載入資料
async function loadDataFromCloud() {
    try {
        const response = await fetch(`${SUPABASE_URL}/rest/v1/expenses?order=date.desc`, {
            headers: {
                'apikey': SUPABASE_KEY,
                'Authorization': `Bearer ${SUPABASE_KEY}`
            }
        });
        
        if (!response.ok) throw new Error('無法讀取雲端資料');
        
        const data = await response.json();
        expenses = data.map(exp => ({
            id: exp.id,
            amount: exp.amount,
            date: exp.date,
            paymentMethod: exp.payment_method,
            mainCat: exp.main_cat,
            subCat: exp.sub_cat,
            note: exp.note
        }));
        
        renderExpenses();
    } catch (error) {
        console.error("Error loading data:", error);
        expenseList.innerHTML = '<div class="empty-state">雲端資料載入失敗，請檢查連線</div>';
    }
}

// 格式化貨幣
function formatCurrency(num) {
    return num.toLocaleString('zh-TW');
}

// 渲染歷史紀錄與統計
function renderExpenses() {
    expenseList.innerHTML = '';
    categoryBreakdown.innerHTML = '';

    const currentMonth = monthSelector.value; // e.g. "2026-09"

    // 過濾出當月紀錄
    const filteredExpenses = expenses.filter(exp => exp.date.startsWith(currentMonth));

    // 計算當月現金與悠遊卡餘額 (依據當前選擇月份統計)
    let totalCashWithdrawn = 0;
    let totalCashSpent = 0;
    let totalEasycardLoaded = 0;
    let totalEasycardSpent = 0;

    filteredExpenses.forEach(exp => {
        // 現金提領累加 (當月)
        if (exp.mainCat === 'transfer' && exp.subCat === 'cash_withdraw') {
            totalCashWithdrawn += exp.amount;
        }
        // 現金支出扣除 (當月只要是現金支付的支出項目)
        if (exp.mainCat !== 'income' && exp.mainCat !== 'transfer' && exp.paymentMethod === '現金') {
            totalCashSpent += exp.amount;
        }

        // 悠遊卡加值累加 (當月)
        if ((exp.mainCat === 'transfer' && exp.subCat === 'easycard_topup') ||
            (exp.mainCat === 'digital' && exp.subCat === 'wallet')) {
            totalEasycardLoaded += exp.amount;
        }
        // 悠遊卡支出扣除 (當月只要是悠遊卡/電子票證支付的支出項目)
        if (exp.mainCat !== 'income' && exp.mainCat !== 'transfer' && 
            (exp.paymentMethod === '悠遊卡/電子票證' || exp.paymentMethod === '悠遊付')) {
            totalEasycardSpent += exp.amount;
        }
    });

    const currentCashBalance = totalCashWithdrawn - totalCashSpent;
    const currentEasycardBalance = totalEasycardLoaded - totalEasycardSpent;

    if (cashBalanceDisplay) {
        cashBalanceDisplay.textContent = `NT$ ${formatCurrency(currentCashBalance)}`;
        cashBalanceDisplay.className = `wallet-amount ${currentCashBalance < 0 ? 'negative' : ''}`;
    }
    if (cashHintDisplay) {
        cashHintDisplay.textContent = `提領 ${formatCurrency(totalCashWithdrawn)} - 支出 ${formatCurrency(totalCashSpent)}`;
    }

    if (easycardBalanceDisplay) {
        easycardBalanceDisplay.textContent = `NT$ ${formatCurrency(currentEasycardBalance)}`;
        easycardBalanceDisplay.className = `wallet-amount ${currentEasycardBalance < 0 ? 'negative' : ''}`;
    }
    if (easycardHintDisplay) {
        easycardHintDisplay.textContent = `加值 ${formatCurrency(totalEasycardLoaded)} - 支出 ${formatCurrency(totalEasycardSpent)}`;
    }

    if (filteredExpenses.length === 0) {
        expenseList.innerHTML = '<div class="empty-state">本月尚無紀錄</div>';
        if (totalAmountDisplay) totalAmountDisplay.textContent = 'NT$ 0';
        if (totalIncomeDisplay) totalIncomeDisplay.textContent = 'NT$ 0';
        if (totalBalanceDisplay) totalBalanceDisplay.textContent = 'NT$ 0';
        return;
    }

    let totalExpense = 0;
    let totalIncome = 0;
    const categoryTotals = {}; // 記錄各支出主分類總和
    const paymentTotals = {}; // 記錄各支出支付方式總和

    filteredExpenses.forEach(exp => {
        const itemType = categoryData[exp.mainCat]?.type || 'expense';

        if (itemType === 'income') {
            totalIncome += exp.amount;
        } else if (itemType === 'expense') {
            totalExpense += exp.amount;

            // 累加分類金額
            if (!categoryTotals[exp.mainCat]) {
                categoryTotals[exp.mainCat] = 0;
            }
            categoryTotals[exp.mainCat] += exp.amount;

            // 累加支付方式金額
            const pMethod = exp.paymentMethod || '其他';
            if (!paymentTotals[pMethod]) {
                paymentTotals[pMethod] = 0;
            }
            paymentTotals[pMethod] += exp.amount;
        }

        const mainName = categoryData[exp.mainCat]?.name || exp.mainCat;
        const subName = categoryData[exp.mainCat]?.subcategories?.[exp.subCat] || exp.subCat;

        const item = document.createElement('div');
        item.className = `expense-item item-type-${itemType}`;

        // 組合顯示文字
        let titleText = `${mainName} - ${subName}`;
        if (exp.note) {
            titleText += ` (${exp.note})`;
        }

        let typeBadge = '';
        let amountPrefix = '-$';
        let amountClass = 'item-amount expense';

        if (itemType === 'income') {
            typeBadge = '<span class="badge badge-income">收入</span>';
            amountPrefix = '+$';
            amountClass = 'item-amount income';
        } else if (itemType === 'transfer') {
            typeBadge = '<span class="badge badge-transfer">提領/儲值</span>';
            amountPrefix = '$';
            amountClass = 'item-amount transfer';
        }

        item.innerHTML = `
            <div class="item-info">
                <div class="item-category">${typeBadge}${titleText}</div>
                <div class="item-sub-info">
                    <span class="item-date">${exp.date}</span>
                    <span class="item-date">${exp.paymentMethod || '信用卡'}</span>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 10px;">
                <div class="${amountClass}">
                    ${amountPrefix}${formatCurrency(exp.amount)}
                </div>
                <button class="delete-btn" onclick="deleteExpense('${exp.id}')" title="刪除此筆">×</button>
            </div>
        `;

        expenseList.appendChild(item);
    });

    const netBalance = totalIncome - totalExpense;

    if (totalAmountDisplay) totalAmountDisplay.textContent = `NT$ ${formatCurrency(totalExpense)}`;
    if (totalIncomeDisplay) totalIncomeDisplay.textContent = `NT$ ${formatCurrency(totalIncome)}`;
    if (totalBalanceDisplay) {
        totalBalanceDisplay.textContent = `NT$ ${formatCurrency(netBalance)}`;
        totalBalanceDisplay.className = `stat-value ${netBalance >= 0 ? 'positive' : 'negative'}`;
    }

    // 渲染支出分類報表區塊
    Object.entries(categoryTotals)
        .sort((a, b) => b[1] - a[1]) // 金額由大到小排序
        .forEach(([catKey, catAmount]) => {
            const catName = categoryData[catKey]?.name || catKey;
            const percentage = totalExpense > 0 ? (catAmount / totalExpense * 100).toFixed(1) : 0;

            const bdItem = document.createElement('div');
            bdItem.className = 'breakdown-item';
            bdItem.innerHTML = `
                <div class="breakdown-item-name">${catName}</div>
                <div class="breakdown-bar-container">
                    <div class="breakdown-bar" style="width: ${percentage}%"></div>
                </div>
                <div>$${formatCurrency(catAmount)} (${percentage}%)</div>
            `;
            categoryBreakdown.appendChild(bdItem);
        });
        
    // 渲染支付方式統計區塊
    const paymentBreakdown = document.getElementById('payment-breakdown');
    if (paymentBreakdown) {
        paymentBreakdown.innerHTML = '';
        Object.entries(paymentTotals)
            .sort((a, b) => b[1] - a[1]) // 金額由大到小排序
            .forEach(([payKey, payAmount]) => {
                const percentage = totalExpense > 0 ? (payAmount / totalExpense * 100).toFixed(1) : 0;
    
                const bdItem = document.createElement('div');
                bdItem.className = 'breakdown-item';
                bdItem.innerHTML = `
                    <div class="breakdown-item-name" style="width: 100px;">${payKey}</div>
                    <div class="breakdown-bar-container">
                        <div class="breakdown-bar" style="width: ${percentage}%; background: linear-gradient(90deg, #10b981, #34d399);"></div>
                    </div>
                    <div>$${formatCurrency(payAmount)} (${percentage}%)</div>
                `;
                paymentBreakdown.appendChild(bdItem);
            });
    }
}

// 啟動應用程式
init();
