const COUNTRIES = [
  ["US", "美国"], ["CA", "加拿大"], ["UK", "英国"], ["DE", "德国"],
  ["FR", "法国"], ["IT", "意大利"], ["ES", "西班牙"],
];
const $ = (id) => document.getElementById(id);
let activeCountry = "";
let activeCategory = "";
let latestProducts = [];

function countryControls(target, checked = true) {
  $(target).innerHTML = COUNTRIES.map(([code]) => `<label class="country-pill"><input type="checkbox" value="${code}" ${checked ? "checked" : ""}><span>${code}</span></label>`).join("");
}

function selectedCountries(target) {
  return [...$(target).querySelectorAll("input:checked")].map((input) => input.value);
}

function categoryPath(prefix = "cat") {
  return [$(prefix + "1")?.value, $(prefix + "2")?.value, $(prefix + "3")?.value].filter(Boolean).join(" > ");
}

function esc(value = "") {
  return String(value).replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
}

function safeUrl(value) {
  try {
    const url = new URL(value, window.location.href);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
  } catch {
    return "#";
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `请求失败 (${response.status})`);
    return payload;
  }
  if (!response.ok) throw new Error(`请求失败 (${response.status})`);
  return response;
}

function formatPrice(row) {
  if (row.price == null) return "--";
  try { return new Intl.NumberFormat("en", {style:"currency", currency:row.currency || "USD", maximumFractionDigits:2}).format(row.price); }
  catch { return `${row.currency || ""} ${row.price}`; }
}

function tagsMarkup(tags = []) {
  if (!tags.length) return '<span class="tag gray">数据不足</span>';
  return `<div class="tags">${tags.map((tag) => `<span class="tag ${tag === "利润款候选" ? "orange" : ""}">${esc(tag)}</span>`).join("")}</div>`;
}

function productCell(row) {
  const fallback = "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><rect width="100%" height="100%" fill="#f0f3f1"/><path d="M18 58h44M25 52V27h30v25M30 33h20" stroke="#94a69c" fill="none" stroke-width="2"/></svg>');
  const image = row.image_url ? esc(safeUrl(row.image_url)) : fallback;
  const link = row.product_url ? esc(safeUrl(row.product_url)) : "#";
  return `<div class="product-cell"><img loading="lazy" src="${image}" alt="" onerror="this.src='${fallback}'"><div><a href="${link}" target="_blank" rel="noopener">${esc(row.title || "未命名商品")}</a><small>${esc(row.brand || "品牌未标注")} ${row.asin ? "· " + esc(row.asin) : ""}</small></div></div>`;
}

function renderRows(items, target, mode = "research") {
  if (!items.length) {
    $(target).innerHTML = `<tr><td colspan="${mode === "data" ? 8 : 9}" class="empty-cell">暂无符合条件的记录。公开商品页不含可验证的销量和销售额。</td></tr>`;
    return;
  }
  if (mode === "data") {
    $(target).innerHTML = items.map((r) => `<tr><td>${productCell(r)}</td><td>${esc(r.country)}</td><td>${esc(r.category_path || "--")}</td><td>${formatPrice(r)}</td><td>${r.units ?? "--"}</td><td>${r.revenue ?? "--"}</td><td>${r.rating ?? "--"}</td><td>${esc(r.source)}</td></tr>`).join("");
    return;
  }
  $(target).innerHTML = items.map((r) => `<tr><td>${productCell(r)}</td><td>${esc(r.country)}</td><td>${formatPrice(r)}</td><td>${r.units ?? "--"}</td><td>${r.revenue ?? "--"}</td><td>${r.growth == null ? "--" : `${r.growth}%`}</td><td>${r.rating == null ? "--" : `${r.rating} / ${r.reviews ?? "--"}`}</td><td>${tagsMarkup(r.opportunity_tags)}</td><td>${esc(r.source)}</td></tr>`).join("");
}

function filterProducts() {
  const country = $("countryFilter").value;
  const tag = $("tagFilter").value;
  const rows = latestProducts.filter((r) => (!country || r.country === country) && (!tag || (r.opportunity_tags || []).includes(tag)));
  renderRows(rows, "productRows");
  $("metricCount").textContent = rows.length.toLocaleString();
  const revs = rows.map((r) => r.revenue).filter((x) => x != null);
  $("metricRevenue").textContent = revs.length ? revs.reduce((a,b)=>a+b,0).toLocaleString() : "缺少销量源";
  $("metricGrowth").textContent = rows.some((r) => r.growth != null) ? rows.filter((r)=>r.growth>=20).length.toString() : "待导入";
  const prices = rows.map((r)=>r.price).filter((x)=>x!=null).sort((a,b)=>a-b);
  $("metricPrice").textContent = prices.length ? formatPrice({price:prices[Math.floor((prices.length-1)*0.75)],currency:rows.find((r)=>r.price!=null)?.currency}) : "--";
}

async function refresh() {
  const status = await api("/api/status");
  $("dataPath").textContent = status.data_dir;
  $("dataProducts").textContent = status.products.toLocaleString();
  $("dataCountries").textContent = `${status.countries_with_data} / 7`;
  $("dataLatest").textContent = status.latest_update ? new Date(status.latest_update).toLocaleString() : "--";
  $("dbCount").textContent = `${status.products.toLocaleString()} 条本地记录`;
  $("storageLabel").textContent = `本机数据目录 · ${status.countries_with_data}/7 国`;
  const payload = await api("/api/products");
  latestProducts = payload.items || [];
  const countryFilter = $("countryFilter");
  const selected = countryFilter.value;
  countryFilter.innerHTML = '<option value="">所有国家</option>' + COUNTRIES.map(([code,label])=>`<option value="${code}">${label}</option>`).join("");
  countryFilter.value = selected;
  filterProducts();
  renderRows(latestProducts, "dataRows", "data");
}

function showNotice(message, error = false) {
  const node = $("runNotice"); node.classList.remove("hidden", "error");
  if (error) node.classList.add("error"); node.textContent = message;
}

function marketStatus(item, running = false) {
  const label = item.label || item.country;
  if (item.status === "ok") return `${label}: 完成 ${item.count} 条`;
  if (item.status === "partial") return `${label}: 部分完成 ${item.count} 条（${item.warning || "后续页面未取到"}）`;
  if (item.status === "failed") return `${label}: 0 条（${item.error || "未返回商品"}）`;
  return `${label}: 第 ${item.page || 1} 页，已去重 ${item.count || 0}/${item.target || 100} 条${item.warning ? `（${item.warning}）` : ""}`;
}

async function searchMarkets() {
  const button = $("searchBtn");
  const keyword = $("keyword").value.trim();
  if (!keyword) return showNotice("先填写产品名称或搜索词。", true);
  button.disabled = true; showNotice("正在逐站尝试公开搜索页。受访问限制的站点会记录失败，不会绕过验证。", false);
  try {
    const result = await api("/api/search", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({keyword,category_path:categoryPath(),countries:selectedCountries("countryChecks")})});
    let task;
    do {
      task = await api(`/api/search-run?id=${encodeURIComponent(result.run_id)}`);
      const progress = task.progress?.countries || task.progress || [];
      const statusText = progress.map((x)=>marketStatus(x, true)).join(" | ");
      const completeCount = progress.filter((x)=>["ok", "partial", "failed"].includes(x.status)).length;
      showNotice(`采集进度 ${completeCount}/${task.countries ? JSON.parse(task.countries).length : 7} 个站点${statusText ? `：${statusText}` : "：准备启动"}`);
      if (task.status === "RUNNING") await new Promise((resolve)=>setTimeout(resolve,800));
    } while (task.status === "RUNNING");
    const finalProgress = task.progress?.countries || [];
    const statuses = finalProgress.map((x)=>marketStatus(x)).join(" | ");
    showNotice(`采集结束，共缓存 ${task.progress?.saved || 0} 条。${statuses}`, task.status === "FAILED");
    activeCategory = categoryPath(); await refresh();
  } catch (err) { showNotice(err.message, true); }
  finally { button.disabled = false; }
}

function renderAnalysis(result) {
  const featureItems = Object.entries(result.features).filter(([,v])=>v.present).map(([name,v])=>`<div class="feature-item"><strong>${esc(name)}</strong><small>识别证据：${esc(v.evidence.join(" / "))}</small></div>`).join("") || '<div class="feature-item"><strong>未识别到标准功能关键词</strong><small>建议在资料中提供明确的功能描述或规格字段。</small></div>';
  const competitors = result.competitors.map((item)=>{
    const comparisons = item.feature_comparison.map((diff)=>`<div class="diff-row"><b>${esc(diff.feature)}</b><br>${esc(diff.verdict)}${diff.our_evidence.length ? `<br>我方：${esc(diff.our_evidence.join("、"))}` : ""}${diff.competitor_evidence.length ? `<br>页面：${esc(diff.competitor_evidence.join("、"))}` : ""}</div>`).join("");
    return `<article class="competitor-card">${item.image_url ? `<img src="${esc(safeUrl(item.image_url))}" alt="商品图" loading="lazy">` : '<div class="competitor-placeholder">无图</div>'}<div><h3><a href="${esc(safeUrl(item.product_url || "#"))}" target="_blank" rel="noopener">${esc(item.title)}</a></h3><div class="competitor-meta">${esc(item.country)} · ${formatPrice(item)} · ${item.rating ?? "--"} 星 · ${item.reviews ?? "--"} 评 · ${esc(item.asin)}</div><div class="diff-list">${comparisons}</div></div></article>`;
  }).join("");
  $("analysisResults").innerHTML = `<section class="analysis-card"><h3>产品资料识别</h3><p><b>${esc(result.product_name)}</b> · ${esc(result.category_path || "三级类目未填写")}</p><div class="feature-grid">${featureItems}</div></section><section class="analysis-card"><h3>结论与证据边界</h3><p>检索到 <b>${result.competitors.length}</b> 个本地竞品记录。暂可提出的差异线索：${result.supported_differentiators.length ? esc(result.supported_differentiators.join("、")) : "目前没有足够证据证明我方具备竞品稀缺优势；不强行包装优势。"}</p>${result.limitations.map((x)=>`<p>• ${esc(x)}</p>`).join("")}</section><section><div class="section-heading"><div><h2>逐项竞品对照</h2><p>标题未提及只表示缺少页面证据，不代表商品没有该功能。</p></div></div>${competitors || '<div class="analysis-card"><p>当前本机没有所选国家和类目的竞品数据。先到“市场研究”搜索，或导入 SellerSprite 明细，再运行对照。</p></div>'}</section>`;
}

async function analyze() {
  const button = $("analyzeBtn"); button.disabled = true; button.textContent = "分析中";
  try {
    const result = await api("/api/analyze", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({product_name:$("productName").value,category_path:$("analysisCategory").value,product_text:$("productText").value,countries:selectedCountries("analysisCountryChecks")})});
    renderAnalysis(result);
  } catch (err) { $("analysisResults").innerHTML = `<div class="analysis-card"><p>${esc(err.message)}</p></div>`; }
  finally { button.disabled = false; button.textContent = "生成证据对照"; }
}

async function importFile(file) {
  if (!file) return;
  $("importNotice").textContent = "正在导入并识别字段…";
  try {
    const result = await api("/api/import", {method:"POST",headers:{"Content-Type":"application/octet-stream","X-File-Name":encodeURIComponent(file.name)},body:file});
    $("importNotice").textContent = `导入完成：${result.imported} 条有效记录。`;
    await refresh();
  } catch (err) { $("importNotice").textContent = `导入失败：${err.message}`; }
}

document.querySelectorAll(".nav-item").forEach((button)=>button.addEventListener("click",()=>{
  document.querySelectorAll(".nav-item").forEach((x)=>x.classList.toggle("active",x===button));
  document.querySelectorAll(".view").forEach((x)=>x.classList.toggle("active",x.id===`view-${button.dataset.view}`));
}));
countryControls("countryChecks"); countryControls("analysisCountryChecks");
$("searchBtn").addEventListener("click",searchMarkets); $("keyword").addEventListener("keydown",(e)=>{if(e.key==="Enter")searchMarkets();});
$("analyzeBtn").addEventListener("click",analyze); $("countryFilter").addEventListener("change",filterProducts); $("tagFilter").addEventListener("change",filterProducts);
$("refreshBtn").addEventListener("click",()=>refresh().catch((e)=>showNotice(e.message,true)));
for (const id of ["exportBtn","exportBtn2"]) $(id).addEventListener("click",()=>{window.location.href=`/api/export.xlsx${activeCategory?`?category=${encodeURIComponent(activeCategory)}`:""}`;});
$("fileInput").addEventListener("change",(e)=>importFile(e.target.files[0]));
$("dropZone").addEventListener("dragover",(e)=>{e.preventDefault();});
$("dropZone").addEventListener("drop",(e)=>{e.preventDefault();importFile(e.dataTransfer.files[0]);});
refresh().catch((err)=>{ $("dbCount").textContent="服務未連線"; showNotice(err.message,true); });
