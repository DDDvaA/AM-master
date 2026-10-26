import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const sourcePath = "C:/Users/DELL-PC/Documents/New project/outputs/智能猫砂盆七国产品开发分析/litter_analysis_data.json";
const outputDir = "C:/Users/DELL-PC/Documents/New project/outputs/智能猫砂盆七国产品开发分析";
const outputPath = `${outputDir}/智能猫砂盆七国市场与产品开发方向_2026-10-26.xlsx`;
const data = JSON.parse(await fs.readFile(sourcePath, "utf8"));

const workbook = Workbook.create();
const fontName = "Arial";
const colors = {
  navy: "#17324D",
  blue: "#2F5D7C",
  paleBlue: "#EAF2F8",
  paleGreen: "#EAF4EA",
  paleAmber: "#FFF3D6",
  paleRed: "#FCE8E6",
  border: "#CBD5E1",
  text: "#1F2937",
  muted: "#64748B",
  white: "#FFFFFF",
};

function safe(value) {
  return value === undefined ? null : value;
}

function setColumns(sheet, widths) {
  widths.forEach((width, index) => {
    sheet.getRangeByIndexes(0, index, 1, 1).format.columnWidth = width;
  });
}

function styleTitle(sheet, title, context = "") {
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[title]];
  sheet.getRange("A2").format.font = { name: fontName, size: 15, bold: true, color: colors.navy };
  sheet.getRange("A3").values = [[context]];
  sheet.getRange("A3").format.font = { name: fontName, size: 10, italic: true, color: colors.muted };
}

function writeTable(sheet, startRow, headers, rows, options = {}) {
  const startCol = options.startCol ?? 0;
  const headerRange = sheet.getRangeByIndexes(startRow, startCol, 1, headers.length);
  headerRange.values = [headers];
  headerRange.format = {
    fill: colors.navy,
    font: { name: fontName, size: 10, bold: true, color: colors.white },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: colors.white },
  };
  if (rows.length) {
    const body = sheet.getRangeByIndexes(startRow + 1, startCol, rows.length, headers.length);
    body.values = rows.map((row) => row.map(safe));
    body.format.font = { name: fontName, size: 10, color: colors.text };
    body.format.verticalAlignment = "center";
    body.format.borders = { preset: "inside", style: "thin", color: colors.border };
    if (options.wrap !== false) body.format.wrapText = true;
    if (options.rowHeight) body.format.rowHeight = options.rowHeight;
  }
  return { firstDataRow: startRow + 1, lastRow: startRow + rows.length };
}

const summary = workbook.worksheets.add("管理结论");
summary.tabColor = colors.navy;
styleTitle(summary, "智能猫砂盆七国市场与产品开发方向", "分析时间：2026-10-26；范围：美国、加拿大、英国、德国、法国、意大利、西班牙");
setColumns(summary, [28, 14, 22, 28, 14, 14, 14, 14, 14, 14, 14]);
summary.getRange("A5:B5").values = [["核心指标", "结果"]];
summary.getRange("A5:B5").format = { fill: colors.navy, font: { name: fontName, size: 10, bold: true, color: colors.white }, horizontalAlignment: "center" };
summary.getRange("A6:B10").values = [
  ["七国搜索样本", data.meta.raw_products],
  ["严格合格整机", data.meta.qualified_products],
  ["整机占搜索样本", data.meta.qualified_products / data.meta.raw_products],
  ["真实评论", data.meta.real_reviews],
  ["评论覆盖整机", data.meta.review_products],
];
summary.getRange("B6:B7").format.numberFormat = "#,##0";
summary.getRange("B8").format.numberFormat = "0.0%";
summary.getRange("B9:B10").format.numberFormat = "#,##0";
summary.getRange("A6:B10").format.borders = { preset: "inside", style: "thin", color: colors.border };
summary.getRange("D5:K5").values = [["产品经理核心结论", null, null, null, null, null, null, null]];
summary.getRange("D5:K5").format = { fill: colors.navy, font: { name: fontName, size: 10, bold: true, color: colors.white } };
data.meta.management_conclusions.forEach((text, index) => {
  const row = 6 + index;
  summary.mergeCells(`D${row}:K${row}`);
  summary.getRange(`D${row}`).values = [[`${index + 1}. ${text}`]];
  summary.getRange(`D${row}:K${row}`).format.fill = index < 3 ? colors.paleGreen : colors.paleBlue;
  summary.getRange(`D${row}:K${row}`).format.borders = { preset: "outside", style: "thin", color: colors.border };
  summary.getRange(`D${row}`).format = { font: { name: fontName, size: 10, bold: index < 3, color: colors.text }, wrapText: true, verticalAlignment: "center" };
  summary.getRange(`D${row}:K${row}`).format.rowHeight = 32;
});
summary.getRange("A13:K13").values = [["上市门槛", "级别", "决策", "说明", null, null, null, null, null, null, null]];
summary.getRange("A13:K13").format = { fill: colors.navy, font: { name: fontName, size: 10, bold: true, color: colors.white } };
const gates = [
  ["生命安全、防夹、防困、断网断电安全", "P0", "未通过不上市", "基础安全优先于摄像头、AI和自动打包"],
  ["清洁循环、卡机恢复、漏砂和满仓预警", "P0", "未通过不上市", "连续可靠性决定退货率和口碑"],
  ["可拆洗、尿液隔离、集便仓密封", "P0/P1", "量产前完成污染测试", "避免尿液侵入电机与传感器"],
  ["APP、家庭共享、离线功能、通知配置", "P1", "基础款必须", "七国评论均显示连接和通知痛点"],
  ["摄像头、AI健康、自动打包", "P2", "只做高配", "必须建立在基础可靠性达标之后"],
];
summary.getRange("A14:D18").values = gates;
summary.getRange("A14:D18").format = { font: { name: fontName, size: 10, color: colors.text }, wrapText: true, verticalAlignment: "center", borders: { preset: "inside", style: "thin", color: colors.border } };
summary.getRange("B14:B15").format.fill = colors.paleRed;
summary.getRange("C14:C15").format.font = { name: fontName, size: 10, bold: true, color: "#A61B1B" };
summary.getRange("A21:K21").values = [["数据边界", null, null, null, null, null, null, null, null, null, null]];
summary.getRange("A21:K21").format = { fill: colors.paleAmber, font: { name: fontName, size: 10, bold: true, color: colors.text } };
data.meta.limitations.forEach((text, index) => {
  const row = 22 + index;
  summary.mergeCells(`A${row}:K${row}`);
  summary.getRange(`A${row}`).values = [[`${index + 1}. ${text}`]];
  summary.getRange(`A${row}:K${row}`).format.rowHeight = 28;
  summary.getRange(`A${row}`).format = { font: { name: fontName, size: 10, color: colors.text }, wrapText: true };
});

const market = workbook.worksheets.add("七国市场结构");
market.tabColor = colors.blue;
styleTitle(market, "七国市场结构", "严格整机以标题明确显示自动清洁证据为准；配件、手动滚筒和无法确认商品不计入整机市场结构");
setColumns(market, [10, 12, 12, 11, 11, 11, 11, 11, 11, 11, 11, 11, 38]);
const marketHeaders = ["国家", "搜索样本", "严格整机", "配件", "手动款", "待确认", "有效价格数", "币种", "P25价格", "中位价格", "P75价格", "平均评分", "国家结论"];
const marketRows = data.countries.map((c) => [c.label, c.raw_products, c.qualified_products, c.accessories, c.manual, c.unconfirmed, c.priced_products, c.currency, c.price_p25, c.price_median, c.price_p75, c.average_rating, c.strategy]);
writeTable(market, 4, marketHeaders, marketRows, { rowHeight: 42 });
market.getRange("B6:G12").format.numberFormat = "#,##0";
market.getRange("I6:K12").format.numberFormat = "#,##0.00";
market.getRange("L6:L12").format.numberFormat = "0.00";
market.getRange("A15:M15").values = [["标题功能宣称频次", null, null, null, null, null, null, null, null, null, null, null, null]];
market.getRange("A15:M15").format = { fill: colors.paleBlue, font: { name: fontName, size: 10, bold: true, color: colors.navy } };
const featureNames = [...new Set(data.features.map((row) => row.feature))];
const featureRows = data.countries.map((country) => [country.label, ...featureNames.map((name) => {
  const match = data.features.find((row) => row.country === country.country && row.feature === name);
  return match ? match.share : 0;
})]);
writeTable(market, 16, ["国家", ...featureNames], featureRows, { rowHeight: 24 });
market.getRangeByIndexes(17, 1, featureRows.length, featureNames.length).format.numberFormat = "0%";
market.freezePanes.freezeRows(5);

const roadmap = workbook.worksheets.add("产品开发方向");
roadmap.tabColor = colors.navy;
styleTitle(roadmap, "产品开发方向", "P0为上市阻断项；P1为七国共用基础能力；P2为高配差异化");
setColumns(roadmap, [9, 24, 54, 50, 46]);
writeTable(roadmap, 4, ["优先级", "模块", "开发定义", "数据理由", "建议验收指标"], data.roadmap, { rowHeight: 68 });
for (let row = 6; row <= 5 + data.roadmap.length; row++) {
  const priority = roadmap.getRange(`A${row}`).values?.[0]?.[0];
  roadmap.getRange(`A${row}`).format.fill = priority === "P0" ? colors.paleRed : priority === "P1" ? colors.paleGreen : colors.paleBlue;
  roadmap.getRange(`A${row}`).format.font = { name: fontName, size: 10, bold: true, color: colors.text };
}
roadmap.freezePanes.freezeRows(5);

const strategies = workbook.worksheets.add("国家策略");
styleTitle(strategies, "国家策略", "价格建议只在页面返回当地币种且样本充分时给出；US、UK、DE不使用CNY页面价格");
setColumns(strategies, [10, 12, 12, 12, 12, 12, 12, 58]);
const strategyRows = data.countries.map((c) => [c.label, c.qualified_products, c.review_count, c.negative_reviews, c.negative_rate, c.price_median, c.currency, c.strategy]);
writeTable(strategies, 4, ["国家", "整机样本", "评论数", "负面评论", "负面率", "中位价格", "币种", "产品与上市策略"], strategyRows, { rowHeight: 54 });
strategies.getRange("B6:D12").format.numberFormat = "#,##0";
strategies.getRange("E6:E12").format.numberFormat = "0.0%";
strategies.getRange("F6:F12").format.numberFormat = "#,##0.00";
strategies.freezePanes.freezeRows(5);

const competitors = workbook.worksheets.add("竞品样本");
styleTitle(competitors, "严格合格整机竞品样本", `${data.meta.qualified_products}条；按国家和评论量排序。销量、销售额和增长率没有授权数据，因此保持为空`);
setColumns(competitors, [9, 13, 42, 13, 12, 10, 10, 12, 14, 34, 54]);
const competitorRows = data.qualified_products.map((p) => [
  p.country, p.asin, p.title, p.brand, p.price, p.currency, p.rating, p.reviews,
  (p.feature_hits || []).join("、"), p.image_url, p.product_url,
]);
writeTable(competitors, 4, ["国家", "ASIN", "商品标题", "品牌", "价格", "币种", "评分", "评论数", "标题功能", "图片URL", "商品URL"], competitorRows, { rowHeight: 48 });
competitors.getRange(`E6:E${5 + competitorRows.length}`).format.numberFormat = "#,##0.00";
competitors.getRange(`G6:G${5 + competitorRows.length}`).format.numberFormat = "0.0";
competitors.getRange(`H6:H${5 + competitorRows.length}`).format.numberFormat = "#,##0";
competitors.freezePanes.freezeRows(5);
competitors.freezePanes.freezeColumns(2);

const themeSheet = workbook.worksheets.add("七国评论分析");
styleTitle(themeSheet, "七国真实评论主题", `仅统计严格整机ASIN；${data.meta.real_reviews}条真实评论，覆盖${data.meta.review_products}个商品。主题按评论原文关键词归类`);
setColumns(themeSheet, [10, 24, 12, 14, 14, 52]);
const themeRows = data.themes.map((row) => {
  const action = row.theme === "APP与连接" ? "提高配网与重连成功率，保留离线核心功能" :
    row.theme === "安全与防夹" ? "设置冗余传感器和机械释放，作为P0" :
    row.theme === "清洁循环与卡机" ? "提高循环成功率并提供故障恢复" :
    row.theme === "除臭与集便仓" ? "优化密封、换袋路径和满仓前预警" :
    row.theme === "清洁与材质" ? "快拆水洗并隔离尿液与电气舱" :
    row.theme === "漏砂与带砂" ? "优化入口、踏板和筛网几何" :
    row.theme === "耗材与维护成本" ? "兼容通用垃圾袋，公开耗材寿命与成本" :
    row.theme === "多猫与体重识别" ? "允许用户校正猫档案并显示识别置信度" :
    "纳入对应模块验证，不把营销宣称视为完成";
  return [row.label, row.theme, row.mentions, row.negative_mentions, row.negative_share, action];
});
writeTable(themeSheet, 4, ["国家", "评论主题", "提及数", "负面提及", "负面占比", "产品动作"], themeRows, { rowHeight: 32 });
themeSheet.getRange(`C6:D${5 + themeRows.length}`).format.numberFormat = "#,##0";
themeSheet.getRange(`E6:E${5 + themeRows.length}`).format.numberFormat = "0.0%";
themeSheet.freezePanes.freezeRows(5);

const reviewSheet = workbook.worksheets.add("评论原文");
styleTitle(reviewSheet, "真实评论原文", "评论原文保留来源、评分、日期和主题；不含早期误抓的喂食器与配件评论");
setColumns(reviewSheet, [9, 13, 34, 10, 30, 70, 22, 12, 16, 36]);
const reviewRows = data.reviews.map((r) => [r.country, r.asin, r.product_title, r.rating, r.review_title, r.review_body, r.review_date_text, r.verified ? "是" : "否", (r.themes || []).join("、"), r.review_url]);
writeTable(reviewSheet, 4, ["国家", "ASIN", "商品", "评分", "评论标题", "评论正文", "评论日期", "已验证购买", "主题", "评论URL"], reviewRows, { rowHeight: 72 });
reviewSheet.getRange(`D6:D${5 + reviewRows.length}`).format.numberFormat = "0.0";
reviewSheet.freezePanes.freezeRows(5);
reviewSheet.freezePanes.freezeColumns(2);

const rawSheet = workbook.worksheets.add("商品原始数据");
styleTitle(rawSheet, "Amazon公开搜索原始数据", "七国各100条去重商品，共700条；保留严格分类结果和排除原因");
setColumns(rawSheet, [9, 13, 46, 13, 12, 10, 10, 12, 19, 20, 34, 54]);
const rawRows = data.products.map((p) => [p.country, p.asin, p.title, p.brand, p.price, p.currency, p.rating, p.reviews, p.classification, p.classification_reason, p.image_url, p.product_url]);
writeTable(rawSheet, 4, ["国家", "ASIN", "商品标题", "品牌", "价格", "币种", "评分", "评论数", "分类", "分类理由", "图片URL", "商品URL"], rawRows, { rowHeight: 48 });
rawSheet.getRange(`E6:E${5 + rawRows.length}`).format.numberFormat = "#,##0.00";
rawSheet.getRange(`G6:G${5 + rawRows.length}`).format.numberFormat = "0.0";
rawSheet.getRange(`H6:H${5 + rawRows.length}`).format.numberFormat = "#,##0";
rawSheet.freezePanes.freezeRows(5);
rawSheet.freezePanes.freezeColumns(2);

const sourceSheet = workbook.worksheets.add("数据源与边界");
sourceSheet.tabColor = "#94A3B8";
styleTitle(sourceSheet, "数据源与边界", "本页定义数据可支持和不可支持的结论");
setColumns(sourceSheet, [24, 34, 68]);
const sourceRows = [
  ["Amazon公开搜索页", "2026-10-26；US/CA/UK/DE/FR/IT/ES", "每国100条去重搜索样本。用于商品供给、标题功能、评分和评论量结构，不代表完整市场销量。"],
  ["Amazon商品评论", "2026-10-26本地采集", `${data.meta.real_reviews}条与严格整机ASIN关联的真实评论，覆盖${data.meta.review_products}个商品。用于痛点和功能优先级，不外推为全市场投诉率。`],
  ["SellerSprite/BSR", "本类目未取得授权数据", "销量、销售额、增长率和真实BSR保持为空。不能把评论数或搜索位置当作销量。"],
  ["价格", "仅保留页面币种与站点币种一致的数据", "美国、英国、德国页面返回CNY，价格已清空；加拿大、法国、意大利、西班牙可用于样本价格带。"],
  ["严格整机定义", "标题明确自动/电动/机器人/自清洁证据", "排除垃圾袋、垫子、滤芯、替换件、家具、监测器、Omega Paw/Catit Smartsift等手动或非整机产品。"],
  ["功能频次", "商品标题关键词", "代表卖家在标题中的功能宣称，不等同于测试验证，也不能证明实际性能。"],
  ["本地数据位置", "D:/AM-master-data/am_master.sqlite3", "原始页面保存在D:/AM-master-data/raw；分析结论已写入AM master的analysis_runs。"],
];
writeTable(sourceSheet, 4, ["数据项", "时间与范围", "使用边界"], sourceRows, { rowHeight: 62 });

workbook.recalculate();

const checks = [];
for (const spec of [
  ["管理结论", "A2:K26"],
  ["七国市场结构", "A2:M24"],
  ["产品开发方向", "A2:E15"],
  ["国家策略", "A2:H12"],
  ["竞品样本", "A2:K18"],
  ["七国评论分析", "A2:F22"],
  ["评论原文", "A2:J14"],
  ["商品原始数据", "A2:L14"],
  ["数据源与边界", "A2:C12"],
]) {
  const inspection = await workbook.inspect({ kind: "table", sheetId: spec[0], range: spec[1], include: "values,formulas", tableMaxRows: 24, tableMaxCols: 14, maxChars: 8000 });
  checks.push({ sheet: spec[0], ok: !inspection.ndjson.includes("#REF!") && !inspection.ndjson.includes("#VALUE!") });
  const preview = await workbook.render({ sheetName: spec[0], range: spec[1], scale: 0.8, format: "png" });
  const previewPath = path.join(os.tmpdir(), `am-master-${spec[0]}.png`);
  await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
}
const formulas = await workbook.inspect({ kind: "formula", maxChars: 5000, options: { maxResults: 300 } });
if (formulas.ndjson && /#REF!|#DIV\/0!|#VALUE!|#NAME\?|#NUM!|#NULL!|#SPILL!|#CALC!/.test(formulas.ndjson)) {
  throw new Error(`Formula error scan failed: ${formulas.ndjson}`);
}

await fs.mkdir(outputDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, checks, sheets: 9 }, null, 2));
