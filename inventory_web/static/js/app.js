const $ = (selector) => document.querySelector(selector);
const barcodeInput = $("#barcode");
const branchInput = $("#branch");

function number(value) { return Number(value || 0).toLocaleString("zh-CN", {maximumFractionDigits: 4}); }
function escapeHtml(value) { const node = document.createElement("div"); node.textContent = value ?? ""; return node.innerHTML; }
function showError(target, message) { target.hidden = false; target.innerHTML = `<div class="error-box">${escapeHtml(message)}</div>`; window.alert(message); }

async function api(path) { const response = await fetch(path); const data = await response.json(); if (!response.ok || !data.ok) throw new Error(data.message || "请求失败"); return data; }

function renderLookup(data) {
  const container = $("#lookup-result"); const empty = $("#lookup-empty"); empty.hidden = true; container.hidden = false;
  if (!data.found) { container.innerHTML = `<div class="empty-state">${escapeHtml(data.message)}</div>`; return; }
  const item = data.items[0];
  const chips = [
    `商品编码：${item.item_no}`, `主条码：${item.master_barcode || "未维护"}`, `覆盖门店：${item.branch_count}`,
    item.valid_day != null ? `保质期规则：${item.valid_day}` : "未维护保质期规则",
    item.tip_day1 != null ? `提示阈值 1：${item.tip_day1} 天` : ""
  ].filter(Boolean).map(text => `<span class="chip">${escapeHtml(text)}</span>`).join("");
  const stockRows = data.stock_by_branch.map(row => `<tr><td>${escapeHtml(row.branch_no)}</td><td>${escapeHtml(row.item_no)}</td><td>${number(row.stock_qty)}</td></tr>`).join("");
  container.innerHTML = `<article class="item-card"><div class="item-head"><div><p class="code">${escapeHtml(item.item_no)}</p><h3>${escapeHtml(item.item_name)}</h3><p class="subname">${escapeHtml(item.item_subname || "")}</p></div><div class="quantity"><small>${data.branch ? "本门店库存" : "全部门店库存"}</small><strong>${number(item.stock_qty)}</strong><span>件</span></div></div><div class="item-meta">${chips}</div>${stockRows ? `<table class="stock-table"><thead><tr><th>门店</th><th>商品编码</th><th>库存数量</th></tr></thead><tbody>${stockRows}</tbody></table>` : "<p class='subname'>未查询到库存明细。</p>"}</article>`;
}

async function lookup(event) { event?.preventDefault(); const barcode = barcodeInput.value.trim(); if (!barcode) { barcodeInput.focus(); return; } const params = new URLSearchParams({barcode}); if (branchInput.value.trim()) params.set("branch", branchInput.value.trim()); const target = $("#lookup-result"); target.hidden = false; target.innerHTML = "<div class='empty-state'>正在查询商品与库存…</div>"; try { renderLookup(await api(`/api/lookup?${params}`)); } catch (error) { showError(target, error.message); } finally { barcodeInput.select(); barcodeInput.focus(); } }

async function loadExpiry() { const days = $("#expiry-days").value || "30"; const params = new URLSearchParams({days}); if (branchInput.value.trim()) params.set("branch", branchInput.value.trim()); const target = $("#expiry-result"); target.className = "empty-state"; target.innerHTML = "正在读取临期批次…"; try { const data = await api(`/api/near-expiry?${params}`); if (!data.rows.length) { target.textContent = `未来 ${data.days} 天内没有临期批次。`; return; } const rows = data.rows.map(row => { const cls = row.days_to_expiry <= 7 ? "badge-warn" : "badge-ok"; const label = row.days_to_expiry === 0 ? "今天到期" : `${row.days_to_expiry} 天后到期`; return `<tr><td>${escapeHtml(row.branch_no)}</td><td>${escapeHtml(row.item_name)}</td><td>${escapeHtml(row.batch_no)}</td><td>${String(row.valid_date).slice(0,10)}</td><td>${number(row.stock_qty)}</td><td><span class="chip ${cls}">${label}</span></td></tr>`; }).join(""); target.innerHTML = `<p class="result-summary">未来 ${data.days} 天内到期：${data.rows.length} 个批次</p><table class="stock-table"><thead><tr><th>门店</th><th>商品</th><th>批号</th><th>有效期</th><th>库存</th><th>状态</th></tr></thead><tbody>${rows}</tbody></table>`; } catch (error) { showError(target, error.message); } }

async function health() { const status = $("#db-status"); try { const data = await api("/api/health"); status.className = "status ok"; status.textContent = `数据库已连接 · ${data.database.name}`; } catch (error) { status.className = "status error"; status.textContent = "数据库未连接"; window.alert(error.message); } }

$("#lookup-form").addEventListener("submit", lookup); barcodeInput.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); lookup(event); } }); $("#expiry-button").addEventListener("click", loadExpiry); document.querySelectorAll(".tab").forEach(tab => tab.addEventListener("click", () => { document.querySelectorAll(".tab,.panel").forEach(node => node.classList.remove("active")); tab.classList.add("active"); $("#" + tab.dataset.panel).classList.add("active"); })); barcodeInput.focus(); health();
