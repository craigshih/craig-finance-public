// 模擬交易的「四指標體檢」：依站長提供的圖卡「炒股越久越簡單，真正有用的往往只有 4 個指標」。
// 先看趨勢（均線）→ 再看量能（成交量）→ 最後看日內強弱，再套兩條組合規則。
// 只是教學用的規則判斷，不是買賣建議；門檻寫在這裡，頁面上也會顯示。

export const RULES = {
  volumeBurst: 2.5,   // 今日量 ≥ 20 日均量 2.5 倍：爆量
  volumeUp: 1.2,      // 1.2～2.5 倍：放大（溫和放大）
  volumeDown: 0.8,    // < 0.8 倍：縮小
  volumeDry: 0.5,     // < 0.5 倍且接近 60 日最低量：地量
};

const avg = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
const sma = (xs, n, end = xs.length) => (end >= n ? avg(xs.slice(end - n, end)) : null);

// rows：[{date, open, high, low, close, volume}]，舊 → 新
export function maSeries(rows, n) {
  const closes = rows.map((r) => r.close);
  return rows.map((_, i) => (i + 1 >= n ? +sma(closes, n, i + 1).toFixed(2) : null));
}

export function computeSignals(rows) {
  if (!rows || rows.length < 61) return null;
  const closes = rows.map((r) => r.close);
  const vols = rows.map((r) => r.volume || 0);
  const last = rows[rows.length - 1];
  const ma5 = sma(closes, 5), ma20 = sma(closes, 20), ma60 = sma(closes, 60);
  const ma20Prev = sma(closes, 20, closes.length - 5);

  // 趨勢
  let trend, trendNote;
  if (ma5 > ma20 && ma20 > ma60 && last.close > ma20) {
    trend = "多頭排列"; trendNote = "5 日 > 20 日 > 60 日線，股價站在 20 日線上，上升趨勢較穩";
  } else if (ma5 < ma20 && ma20 < ma60 && last.close < ma20) {
    trend = "空頭排列"; trendNote = "5 日 < 20 日 < 60 日線，股價在 20 日線下，趨勢偏弱";
  } else if (last.close < ma20 && ma5 < ma20) {
    trend = "均線破位"; trendNote = "跌破 20 日線（波段生命線），短線轉弱";
  } else if (last.close > ma20 && ma5 > ma20) {
    trend = "均線走強"; trendNote = "站上 20 日線，5 日線在 20 日線之上";
  } else {
    trend = "均線糾結"; trendNote = "均線交錯，方向還不明確";
  }
  const strong = trend === "多頭排列" || trend === "均線走強";
  const broken = trend === "均線破位" || trend === "空頭排列";

  // 量能：今日量對前 20 日均量
  const vAvg20 = avg(vols.slice(-21, -1));
  const ratio = vAvg20 ? last.volume / vAvg20 : null;
  const min60 = Math.min(...vols.slice(-61, -1).filter((v) => v > 0));
  const vAvg5 = avg(vols.slice(-5));
  let volume, volumeNote;
  if (ratio == null) {
    volume = "無資料"; volumeNote = "";
  } else if (ratio >= RULES.volumeBurst) {
    volume = "爆量"; volumeNote = "要注意，可能有籌碼鬆動";
  } else if (ratio >= RULES.volumeUp) {
    volume = "放大"; volumeNote = "有增量資金，趨勢更可信";
  } else if (ratio < RULES.volumeDry && last.volume <= min60 * 1.1) {
    volume = "地量"; volumeNote = "多為空頭衰竭，等待變盤訊號";
  } else if (ratio < RULES.volumeDown) {
    volume = "縮小"; volumeNote = "地壓不大，常是強勢整理";
  } else {
    volume = "持平"; volumeNote = "量能沒有明顯變化";
  }
  const volRising = ratio != null && ratio >= RULES.volumeUp && ratio < RULES.volumeBurst;
  const volFalling = (ratio != null && ratio < RULES.volumeDown) || (vAvg5 != null && vAvg20 && vAvg5 < vAvg20 * RULES.volumeDown);

  // 日內強弱：收盤在當日高低區間的位置
  const range = last.high - last.low;
  const pos = range > 0 ? (last.close - last.low) / range : 0.5;
  const intraday = pos >= 0.7 ? "收在高檔" : pos <= 0.3 ? "收在低檔" : "收在中間";

  // 兩條組合規則
  let verdict, verdictNote;
  if (strong && volRising) {
    verdict = "watch"; verdictNote = "均線走強＋量能溫和放大＝可以加入觀察名單";
  } else if (broken && volFalling) {
    verdict = "retreat"; verdictNote = "均線破位＋量能下滑＝先撤退再說";
  } else {
    verdict = "neutral"; verdictNote = "兩條組合規則都沒有成立，先觀察";
  }

  const r2 = (x) => (x == null ? null : +x.toFixed(2));
  return {
    date: last.date, close: last.close,
    ma5: r2(ma5), ma20: r2(ma20), ma60: r2(ma60), ma20_rising: ma20Prev ? ma20 > ma20Prev : null,
    trend, trend_note: trendNote,
    volume, volume_note: volumeNote, vol_ratio: r2(ratio),
    intraday, intraday_pos: r2(pos),
    verdict, verdict_note: verdictNote,
  };
}

export function parseYahooChart(json) {
  const r = json?.chart?.result?.[0];
  if (!r) return [];
  const q = r.indicators?.quote?.[0] || {};
  const tz = (r.meta?.gmtoffset || 28800) * 1000;
  const rows = [];
  (r.timestamp || []).forEach((t, i) => {
    const [o, h, l, c, v] = [q.open?.[i], q.high?.[i], q.low?.[i], q.close?.[i], q.volume?.[i]];
    if ([o, h, l, c].some((x) => x == null)) return;
    rows.push({ date: new Date(t * 1000 + tz).toISOString().slice(0, 10), open: +o.toFixed(2), high: +h.toFixed(2), low: +l.toFixed(2), close: +c.toFixed(2), volume: v || 0 });
  });
  return rows;
}
