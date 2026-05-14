/**
 * 华为运动健康 - 睡眠数据无障碍直读脚本 (Hamibot / AutoX.js)
 * ===========================================================
 * 
 * 功能：通过安卓无障碍服务读取华为运动健康 App 睡眠详情页的 UI 文本，
 *       组装为 JSON 后 HTTP POST 到 PC 端 MyTimeLogger 的接收服务。
 * 
 * 使用前提：
 *   1. 手机安装 Hamibot 或 AutoX.js 并开启无障碍服务
 *   2. PC 和手机在同一局域网
 *   3. MyTimeLogger 已启动（HTTP 服务端口 5055）
 * 
 * ⚠️ 重要：华为运动健康 App 不同版本/手机分辨率，UI 节点可能有差异。
 *   首次使用请用 Hamibot 的「布局分析」工具确认节点结构，按需调整下方选择器。
 * 
 * 使用方法：
 *   1. 修改下方 PC_IP 为你的电脑局域网 IP
 *   2. 在 Hamibot 控制台上传此脚本并运行
 *   3. 脚本会自动：打开华为运动健康 → 进入睡眠详情 → 读取数据 → POST 到 PC
 */

// ==================== 配置区 ====================
const PC_IP = "192.168.1.100";    // ← 改为你的 PC 局域网 IP
const PC_PORT = 5055;
const POST_URL = `http://${PC_IP}:${PC_PORT}/sleep`;

// 等待时间（毫秒），根据手机性能调整
const WAIT_APP_LAUNCH = 4000;     // 等待 App 启动
const WAIT_PAGE_LOAD = 2000;      // 等待页面切换
const WAIT_SCROLL = 1000;         // 等待滚动

// ==================== 主流程 ====================
function main() {
    console.log("🌙 开始获取华为运动健康睡眠数据...");
    
    // 1. 请求截图权限（虽然不截图，但某些版本 AutoX 需要）
    // requestScreenCapture();
    
    // 2. 启动华为运动健康
    launchApp("华为运动健康");
    console.log("等待 App 启动...");
    sleep(WAIT_APP_LAUNCH);
    
    // 3. 导航到睡眠详情页
    if (!navigateToSleepPage()) {
        console.error("❌ 无法导航到睡眠页面");
        return;
    }
    
    sleep(WAIT_PAGE_LOAD);
    
    // 4. 读取睡眠数据
    var data = readSleepData();
    if (!data) {
        console.error("❌ 读取睡眠数据失败");
        return;
    }
    
    console.log("📊 读取到的数据: " + JSON.stringify(data, null, 2));
    
    // 5. 发送到 PC
    sendToPC(data);
    
    console.log("✅ 完成！");
}

// ==================== 导航逻辑 ====================
function navigateToSleepPage() {
    /**
     * 策略：
     * 1. 先尝试在主页找「睡眠」卡片并点击
     * 2. 如果找不到，尝试点击底部「健康」Tab，再找睡眠入口
     * 
     * ⚠️ 你需要根据自己手机上华为运动健康的实际 UI 调整这里的选择器。
     *    用 Hamibot 的「布局分析」悬浮窗查看具体的 text / id / className。
     */
    
    // 尝试直接在主页找到睡眠入口
    var sleepEntry = text("睡眠").findOne(3000);
    if (sleepEntry) {
        console.log("找到「睡眠」入口，点击...");
        sleepEntry.click();
        sleep(WAIT_PAGE_LOAD);
        return true;
    }
    
    // 备选：尝试找「夜间睡眠」
    var nightSleep = text("夜间睡眠").findOne(3000);
    if (nightSleep) {
        console.log("找到「夜间睡眠」入口，点击...");
        nightSleep.click();
        sleep(WAIT_PAGE_LOAD);
        return true;
    }
    
    // 备选：描述中含有睡眠
    var descSleep = desc("睡眠").findOne(2000);
    if (descSleep) {
        console.log("通过 contentDescription 找到睡眠入口");
        descSleep.click();
        sleep(WAIT_PAGE_LOAD);
        return true;
    }
    
    console.warn("⚠️ 未找到睡眠入口，请用布局分析工具确认 UI 结构");
    return false;
}

// ==================== 数据读取 ====================
function readSleepData() {
    /**
     * 通过无障碍服务遍历当前界面的 UI 节点，
     * 查找包含睡眠指标的 TextView 文本。
     * 
     * 华为运动健康睡眠详情页通常展示：
     * - 睡眠评分（大数字）
     * - 入睡时间 / 醒来时间
     * - 深睡 / 浅睡 / REM / 清醒 时长
     * - 深睡比例 / 浅睡比例等
     * 
     * ⚠️ 以下选择器需要根据你手机上的实际 UI 调整！
     */
    
    var result = {
        date: getTodayDate(),
        sleep_score: 0,
        sleep_start: "",
        sleep_end: "",
        deep_sleep_text: "",
        light_sleep_text: "",
        rem_sleep_text: "",
        awake_text: "",
        deep_sleep_ratio: 0,
        light_sleep_ratio: 0,
        rem_sleep_ratio: 0,
        raw_texts: []
    };
    
    // === 方法1: 按关键词精确查找 ===
    
    // 睡眠评分 — 通常是页面上较大的数字
    var scoreNode = findTextNear("分", 3000);
    if (scoreNode) {
        var scoreText = scoreNode.text();
        var scoreMatch = scoreText.match(/(\d+)\s*分/);
        if (scoreMatch) {
            result.sleep_score = parseInt(scoreMatch[1]);
        }
    }
    
    // 入睡时间
    var bedNode = findTextNear("入睡", 2000);
    if (bedNode) {
        result.sleep_start = extractTime(bedNode);
    }
    
    // 醒来时间
    var wakeNode = findTextNear("醒来", 2000);
    if (wakeNode) {
        result.sleep_end = extractTime(wakeNode);
    }
    
    // 深睡
    var deepNode = findTextNear("深睡", 2000);
    if (deepNode) {
        result.deep_sleep_text = extractDuration(deepNode);
    }
    
    // 浅睡
    var lightNode = findTextNear("浅睡", 2000);
    if (lightNode) {
        result.light_sleep_text = extractDuration(lightNode);
    }
    
    // 快速眼动
    var remNode = findTextNear("快速眼动", 2000) || findTextNear("REM", 2000);
    if (remNode) {
        result.rem_sleep_text = extractDuration(remNode);
    }
    
    // === 方法2: 全量扫描所有文本（兜底） ===
    var allTexts = getAllTexts();
    result.raw_texts = allTexts;
    
    // 从原始文本中尝试解析比例
    allTexts.forEach(function(t) {
        var ratioMatch;
        if ((ratioMatch = t.match(/深睡比例\s*(\d+)%/))) {
            result.deep_sleep_ratio = parseInt(ratioMatch[1]);
        }
        if ((ratioMatch = t.match(/浅睡比例\s*(\d+)%/))) {
            result.light_sleep_ratio = parseInt(ratioMatch[1]);
        }
        if ((ratioMatch = t.match(/快速眼动比例\s*(\d+)%/))) {
            result.rem_sleep_ratio = parseInt(ratioMatch[1]);
        }
    });
    
    // 转换时长文本为分钟数
    result.deep_sleep_min = parseDurationToMin(result.deep_sleep_text);
    result.light_sleep_min = parseDurationToMin(result.light_sleep_text);
    result.rem_sleep_min = parseDurationToMin(result.rem_sleep_text);
    
    // 需要滚动页面获取更多数据（心率、血氧等在下方）
    scrollDown();
    sleep(WAIT_SCROLL);
    
    var moreTexts = getAllTexts();
    result.raw_texts = result.raw_texts.concat(moreTexts);
    
    // 去重
    result.raw_texts = [...new Set(result.raw_texts)];
    
    // 拼接完整原始文本
    result.raw_text = result.raw_texts.join(" ");
    
    return result;
}

// ==================== 辅助函数 ====================

/** 查找包含关键词的节点 */
function findTextNear(keyword, timeout) {
    var node = textContains(keyword).findOne(timeout || 2000);
    return node || null;
}

/** 从节点及其相邻节点提取时间（如 "23:30"） */
function extractTime(node) {
    var t = node.text() || "";
    var match = t.match(/(\d{1,2}:\d{2})/);
    if (match) return match[1];
    
    // 查找父节点下的相邻文本
    var parent = node.parent();
    if (parent) {
        for (var i = 0; i < parent.childCount(); i++) {
            var child = parent.child(i);
            if (child) {
                var ct = child.text() || "";
                var m = ct.match(/(\d{1,2}:\d{2})/);
                if (m) return m[1];
            }
        }
    }
    return t;
}

/** 从节点及其相邻节点提取时长文本（如 "2小时3分钟"） */
function extractDuration(node) {
    var t = node.text() || "";
    // 如果文本本身就包含时长
    if (t.match(/\d+.*[小时分钟秒]/)) return t;
    
    // 查找兄弟节点
    var parent = node.parent();
    if (parent) {
        for (var i = 0; i < parent.childCount(); i++) {
            var child = parent.child(i);
            if (child) {
                var ct = child.text() || "";
                if (ct.match(/\d+.*[小时分钟秒]/) && ct !== t) return ct;
            }
        }
    }
    return t;
}

/** 将 "X小时Y分钟" 格式转为分钟数 */
function parseDurationToMin(text) {
    if (!text) return 0;
    var hours = 0, mins = 0;
    var hMatch = text.match(/(\d+)\s*小时/);
    var mMatch = text.match(/(\d+)\s*分/);
    if (hMatch) hours = parseInt(hMatch[1]);
    if (mMatch) mins = parseInt(mMatch[1]);
    return hours * 60 + mins;
}

/** 获取当前界面所有可见文本 */
function getAllTexts() {
    var texts = [];
    var root = auto.rootInActiveWindow;
    if (!root) return texts;
    
    function traverse(node) {
        if (!node) return;
        var t = node.text();
        if (t && t.trim().length > 0) {
            texts.push(t.trim());
        }
        var desc = node.contentDescription;
        if (desc && desc.trim().length > 0 && desc !== t) {
            texts.push(desc.trim());
        }
        for (var i = 0; i < node.childCount(); i++) {
            traverse(node.child(i));
        }
    }
    
    traverse(root);
    return texts;
}

/** 向下滚动页面 */
function scrollDown() {
    var h = device.height;
    var w = device.width;
    swipe(w / 2, h * 0.7, w / 2, h * 0.3, 500);
}

/** 获取今天日期（YYYY-MM-DD） */
function getTodayDate() {
    var now = new Date();
    var y = now.getFullYear();
    var m = String(now.getMonth() + 1).padStart(2, '0');
    var d = String(now.getDate()).padStart(2, '0');
    return y + "-" + m + "-" + d;
}

/** POST 数据到 PC */
function sendToPC(data) {
    console.log("📤 正在发送数据到 " + POST_URL + " ...");
    try {
        var res = http.postJSON(POST_URL, data);
        if (res && res.statusCode === 200) {
            var body = res.body.string();
            console.log("✅ 发送成功: " + body);
            toast("睡眠数据已同步到 PC！");
        } else {
            var code = res ? res.statusCode : "N/A";
            console.error("❌ 发送失败，状态码: " + code);
            toast("发送失败: HTTP " + code);
        }
    } catch (e) {
        console.error("❌ 网络错误: " + e);
        toast("网络错误，请确认 PC 和手机在同一局域网，且 MyTimeLogger 已启动");
    }
}

// ==================== 执行入口 ====================
main();
