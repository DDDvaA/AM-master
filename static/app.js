const COUNTRIES = [
  ["US", "美国"], ["CA", "加拿大"], ["UK", "英国"], ["DE", "德国"],
  ["FR", "法国"], ["IT", "意大利"], ["ES", "西班牙"],
];
const $ = (id) => document.getElementById(id);
let activeCountry = "";
let activeCategory = "";
let latestProducts = [];
let latestReviewCountries = [];

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
    $(target).innerHTML = `<tr><td colspan="${mode === "data" ? 9 : 10}" class="empty-cell">暂无符合条件的记录。公开商品页不含可验证的销量和销售额。</td></tr>`;
    return;
  }
  if (mode === "data") {
    $(target).innerHTML = items.map((r) => `<tr><td>${productCell(r)}</td><td>${esc(r.country)}</td><td>${esc(r.category_path || "--")}</td><td>${r.bsr_rank ?? "--"}</td><td>${formatPrice(r)}</td><td>${r.units ?? "--"}</td><td>${r.revenue ?? "--"}</td><td>${r.rating ?? "--"}</td><td>${esc(r.source)}</td></tr>`).join("");
    return;
  }
  $(target).innerHTML = items.map((r) => `<tr><td>${productCell(r)}</td><td>${esc(r.country)}</td><td>${r.bsr_rank ?? "--"}</td><td>${formatPrice(r)}</td><td>${r.units ?? "--"}</td><td>${r.revenue ?? "--"}</td><td>${r.growth == null ? "--" : `${r.growth}%`}</td><td>${r.rating == null ? "--" : `${r.rating} / ${r.reviews ?? "--"}`}</td><td>${tagsMarkup(r.opportunity_tags)}</td><td>${esc(r.source)}</td></tr>`).join("");
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

function renderReviews() {
  const countryFilter = $("reviewCountryFilter").value;
  const countries = latestReviewCountries.filter((item)=>!countryFilter || item.country === countryFilter);
  $("reviewSummary").innerHTML = countries.map((item)=>{
    const themes = item.themes.slice(0,5).map((theme)=>`<span class="review-theme">${esc(theme.theme)} <b>${theme.count}</b><small>低星 ${theme.negative}</small></span>`).join("") || '<span class="tag gray">暂无主题样本</span>';
    return `<article class="review-country-card"><div class="review-country-head"><div><small>${esc(item.country)}</small><h3>${esc(item.label)}</h3></div><strong>${item.sample_count}</strong></div><dl><div><dt>商品数</dt><dd>${item.product_count}</dd></div><div><dt>平均星级</dt><dd>${item.average_rating ?? "--"}</dd></div><div><dt>低星评论</dt><dd>${item.negative_count}</dd></div><div><dt>最近采集</dt><dd>${item.latest_collection ? new Date(item.latest_collection).toLocaleString() : "--"}</dd></div></dl><div class="review-themes">${themes}</div></article>`;
  }).join("");
  const rows = countries.flatMap((item)=>item.reviews.map((review)=>({...review,country_label:item.label})));
  $("reviewRows").innerHTML = rows.length ? rows.map((r)=>{
    let themes=[]; try { themes=JSON.parse(r.themes_json || "[]"); } catch {}
    return `<tr><td><b>${esc(r.country_label)}</b><small class="table-sub">${esc(r.asin)} · ${esc(r.product_title)}</small></td><td>${r.rating ?? "--"}</td><td><b>${esc(r.review_title || "无标题")}</b><div class="review-body">${esc(r.review_body)}</div></td><td>${esc(r.review_date_text || "--")}</td><td>${r.verified ? "已验证购买" : "未标注"}<small class="table-sub">有用 ${r.helpful_count || 0}</small></td><td>${themes.map((x)=>`<span class="tag">${esc(x)}</span>`).join(" ") || "--"}</td><td><a href="${esc(safeUrl(r.review_url))}" target="_blank" rel="noopener">Amazon 原评论</a><small class="table-sub">${new Date(r.collected_at).toLocaleString()}</small></td></tr>`;
  }).join("") : '<tr><td colspan="7" class="empty-cell">尚未采集到评论原文。</td></tr>';
}

async function refreshReviews() {
  const category = $("reviewCategory").value.trim();
  const payload = await api(`/api/reviews${category ? `?category=${encodeURIComponent(category)}` : ""}`);
  latestReviewCountries = payload.items || [];
  const filter = $("reviewCountryFilter"); const selected = filter.value;
  filter.innerHTML = '<option value="">所有国家</option>' + COUNTRIES.map(([code,label])=>`<option value="${code}">${label}</option>`).join(""); filter.value=selected;
  renderReviews();
}

function reviewProgressText(run) {
  const countries = run.result?.countries || [];
  const details = countries.map((item)=>`${item.label}: ${item.reviews || 0} 条${item.status === "failed" ? `（${item.error || item.warning || "失败"}）` : ""}`).join(" | ");
  return `${run.message}${details ? ` · ${details}` : ""}`;
}

async function syncReviews() {
  const button=$("reviewSyncBtn"); button.disabled=true;
  const notice=$("reviewNotice"); notice.classList.remove("hidden","error"); notice.textContent="正在选择 BSR 优先商品并启动评论采集…";
  try {
    const run=await api("/api/reviews/sync",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({countries:selectedCountries("reviewCountryChecks"),category_path:$("reviewCategory").value.trim(),products_per_country:Number($("reviewProductLimit").value),reviews_per_product:Number($("reviewLimit").value)})});
    let state;
    do { state=await api(`/api/sellersprite-run?id=${encodeURIComponent(run.id)}`); notice.textContent=reviewProgressText(state); notice.classList.toggle("error",state.status==="FAILED"); if(state.status==="RUNNING") await new Promise((resolve)=>setTimeout(resolve,1000)); } while(state.status==="RUNNING");
    await refreshReviews(); await refresh();
  } catch(err) { notice.classList.add("error"); notice.textContent=err.message; }
  finally { button.disabled=false; }
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
  button.disabled = true; showNotice("正在逐站采集：自动重试临时错误；必要时弹出 Edge 等待人工验证；仍失败则用本机成功快照补齐。", false);
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

function showSellerNotice(message, error = false) {
  const node = $("sellerNotice");
  node.classList.remove("hidden", "error");
  if (error) node.classList.add("error");
  node.textContent = message;
}

async function waitForConnector(runId) {
  let run;
  do {
    run = await api(`/api/sellersprite-run?id=${encodeURIComponent(runId)}`);
    showSellerNotice(`${run.message}${run.page ? ` · 第 ${run.page} 页` : ""}${run.count ? ` · ${run.count} 条` : ""}`, run.status === "FAILED");
    if (run.status === "RUNNING") await new Promise((resolve)=>setTimeout(resolve,1000));
  } while (run.status === "RUNNING");
  if (run.status === "FAILED") throw new Error(run.message);
  await refresh();
  return run;
}

async function sellerLogin() {
  const button = $("sellerLoginBtn"); button.disabled = true;
  try {
    const run = await api("/api/sellersprite/login", {method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
    showSellerNotice("正在打开专用 Edge。请只在卖家精灵页面中输入账号、密码和验证码。", false);
    await waitForConnector(run.id);
    $("sellerProfileState").textContent = "登录会话已保存在本机";
  } catch (err) { showSellerNotice(err.message, true); }
  finally { button.disabled = false; }
}

async function sellerSync() {
  const button = $("sellerSyncBtn"); button.disabled = true;
  try {
    const run = await api("/api/sellersprite/sync", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:$("sellerUrl").value.trim(),category_path:$("sellerCategory").value.trim(),max_products:100})});
    await waitForConnector(run.id);
  } catch (err) { showSellerNotice(err.message, true); }
  finally { button.disabled = false; }
}

async function refreshSellerState() {
  const state = await api("/api/sellersprite/status");
  $("sellerProfileState").textContent = state.profile_ready ? "本机会话目录已建立" : "首次使用请打开登录窗口";
  if (state.active_run) showSellerNotice(state.active_run.message, false);
}

document.querySelectorAll(".nav-item").forEach((button)=>button.addEventListener("click",()=>{
  document.querySelectorAll(".nav-item").forEach((x)=>x.classList.toggle("active",x===button));
  document.querySelectorAll(".view").forEach((x)=>x.classList.toggle("active",x.id===`view-${button.dataset.view}`));
}));
countryControls("countryChecks"); countryControls("analysisCountryChecks"); countryControls("reviewCountryChecks");
$("searchBtn").addEventListener("click",searchMarkets); $("keyword").addEventListener("keydown",(e)=>{if(e.key==="Enter")searchMarkets();});
$("analyzeBtn").addEventListener("click",analyze); $("countryFilter").addEventListener("change",filterProducts); $("tagFilter").addEventListener("change",filterProducts);
$("refreshBtn").addEventListener("click",()=>refresh().catch((e)=>showNotice(e.message,true)));
for (const id of ["exportBtn","exportBtn2"]) $(id).addEventListener("click",()=>{window.location.href=`/api/export.xlsx${activeCategory?`?category=${encodeURIComponent(activeCategory)}`:""}`;});
$("fileInput").addEventListener("change",(e)=>importFile(e.target.files[0]));
$("sellerLoginBtn").addEventListener("click",sellerLogin); $("sellerSyncBtn").addEventListener("click",sellerSync);
$("reviewSyncBtn").addEventListener("click",syncReviews); $("refreshReviewsBtn").addEventListener("click",()=>refreshReviews().catch((e)=>{$("reviewNotice").textContent=e.message;})); $("reviewCountryFilter").addEventListener("change",renderReviews);
$("dropZone").addEventListener("dragover",(e)=>{e.preventDefault();});
$("dropZone").addEventListener("drop",(e)=>{e.preventDefault();importFile(e.dataTransfer.files[0]);});
Promise.all([refresh(),refreshSellerState(),refreshReviews()]).catch((err)=>{ $("dbCount").textContent="服務未連線"; showNotice(err.message,true); });
