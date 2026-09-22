const API = "";
const TOKEN_KEY = "srj_token";

function token() { return localStorage.getItem(TOKEN_KEY) || ""; }
function setToken(t) { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY); }
function authHeaders() {
  const h = { "Content-Type": "application/json" };
  if (token()) h.Authorization = "Bearer " + token();
  return h;
}
async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    ...opts,
    headers: { ...authHeaders(), ...(opts.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}
function money(n) {
  return "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
}
function toast(msg) {
  let t = document.getElementById("toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "toast";
    t.className = "toast";
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2400);
}
function currentUser() {
  try { return JSON.parse(localStorage.getItem("srj_user") || "null"); } catch { return null; }
}
function setUser(u) {
  if (u) localStorage.setItem("srj_user", JSON.stringify(u));
  else localStorage.removeItem("srj_user");
}
function logout() {
  setToken("");
  setUser(null);
  location.href = "/";
}
function cartGet() { try { return JSON.parse(localStorage.getItem("srj_cart") || "[]"); } catch { return []; } }
function cartSet(c) { localStorage.setItem("srj_cart", JSON.stringify(c)); updateCartCount(); }
function updateCartCount() {
  const n = cartGet().reduce((s, i) => s + i.qty, 0);
  document.querySelectorAll("#cart-count").forEach(el => el.textContent = n);
}
function addToCart(id, qty = 1) {
  const c = cartGet();
  const e = c.find(x => x.product_id === id);
  if (e) e.qty += qty; else c.push({ product_id: id, qty });
  cartSet(c);
  toast("Added to cart");
}

function productCard(p) {
  const img = (p.images && p.images[0]) || "";
  const badge = p.mrp && p.mrp > p.price ? "Sale" : (p.featured ? "Featured" : "");
  return `<article class="product-card">
    <div class="product-image">
      ${badge ? `<span class="product-badge">${badge}</span>` : ""}
      <img src="${img}" alt="${escapeHtml(p.name)}" loading="lazy"/>
      <div class="product-actions-overlay">
        <button class="btn btn-sm btn-primary" type="button" onclick="addToCart(${p.id})">Add to cart</button>
        <a class="btn btn-sm btn-outline-dark" href="/?product=${p.id}">View</a>
      </div>
    </div>
    <div class="product-info">
      <span class="product-category">${escapeHtml(p.store_name || "")}</span>
      <h3 class="product-name"><a href="/?product=${p.id}">${escapeHtml(p.name)}</a></h3>
      <div class="product-price">${money(p.price)}${p.mrp ? ` <span class="old">${money(p.mrp)}</span>` : ""}</div>
    </div>
  </article>`;
}
function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const ICO = {
  home: "M4 11.5 12 4l8 7.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z",
  shop: "M4 8h16v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V8zm1-4h14l1.5 4H3.5L5 4zM9 12v4m6-4v4",
  categories: "M4 4h7v7H4zm9 0h7v7h-7zM4 13h7v7H4zm9 0h7v7h-7z",
  food: "M5 21V10m0-6v3m0 0h3V7a3 3 0 0 0-3-3zm9-1v14m0-14c2.5 0 4 2 4 5s-1.5 5-4 5",
  seller: "M4 20V8l8-4 8 4v12M8 20v-6h8v6",
  search: "M11 18a7 7 0 1 1 0-14 7 7 0 0 1 0 14zm6.5-1.5 3 3",
  account: "M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4zm-7 9a7 7 0 0 1 14 0",
  cart: "M5 7h15l-1.4 8.2A2 2 0 0 1 16.6 17H9.2a2 2 0 0 1-2-1.6L5 4H3m5 16a1 1 0 1 0 0-2 1 1 0 0 0 0 2zm9 0a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  orders: "M7 4h10v16H7zM9 8h6M9 12h6M9 16h3",
  heart: "M12 20s-7-4.4-7-9a4 4 0 0 1 7-2 4 4 0 0 1 7 2c0 4.6-7 9-7 9z",
  menu: "M4 7h16M4 12h16M4 17h16",
  fashion: "M8 5l4 3 4-3 2 4-6 3-6-3 2-4zm0 7v8h8v-8",
  jewellery: "M12 8a3 3 0 1 0-3-3 3 3 0 0 0 3 3zm-6 12c0-4 2.7-7 6-7s6 3 6 7",
  living: "M4 11h16v9H4zm2-5h12v5H6z",
  kitchen: "M7 21V9m0 0a3 3 0 0 1 0-6v6zm10 12V8a4 4 0 0 0-4 4v9",
  electronics: "M9 3h6v2H9zm-2 4h10v12a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V7zm5 4v4",
  beauty: "M12 3v6m0 0c2.5 0 4 1.5 4 3.5S14.5 16 12 16s-4-1.5-4-3.5S9.5 9 12 9zm-2 11h4",
  shoes: "M4 16h13l3-3-4-2-3 1H8L4 14v2zm1 2h12",
  kids: "M12 10a3 3 0 1 0-3-3 3 3 0 0 0 3 3zM8 21v-6l4-2 4 2v6",
  sports: "M12 21a9 9 0 1 0-9-9 9 9 0 0 0 9 9zm-6.5-5.5 13-7m0 7-13-7",
  gifts: "M4 10h16v10H4zm8 0V20M4 10l8-6 8 6M8 6c0-2 2-3 4-1m4-1c2-2 4-1 4 1",
  trending: "M4 16l5-5 4 3 7-8M15 6h5v5",
  deals: "M12 3l2 4 4 .6-3 3 .8 4.4L12 13.5 8.2 15l.8-4.4-3-3 4-.6z",
  restaurant: "M4 21V4m4 0v10M4 8h4m8-5v18m0-18c3 0 4 3 4 6s-1 6-4 6",
  daily: "M7 4h10v16H7zM9 8h6",
  fastfood: "M5 12h14l-1 8H6zm2-4h10a3 3 0 0 0-10 0z",
  indian: "M4 20c2-8 14-8 16 0H4zm8-8a4 4 0 1 0-4-4 4 4 0 0 0 4 4z",
  bakery: "M5 14c0-5 14-5 14 0v5H5zm3-5a3 3 0 0 1 3-4 3 3 0 0 1 5 4",
  drinks: "M8 4h8l-1 10H9L8 4zm2 10v6h4v-6",
  grocery: "M6 7h12l1 13H5L6 7zm3-3h6l1 3H8z",
  produce: "M12 21c-5-3-7-7-7-11a7 7 0 0 1 14 0c0 4-2 8-7 11z",
  meat: "M5 12c0-5 4-8 8-8 5 0 6 5 4 8s-7 6-10 8C5 18 5 15 5 12z",
  dairy: "M8 8h8v13H8zm2-4h4l1 4H9z",
  snacks: "M7 8h10l2 12H5L7 8zm2-4h6",
  sweets: "M12 20s-7-4-7-9a4 4 0 0 1 7-2 4 4 0 0 1 7 2c0 5-7 9-7 9z",
  healthy: "M12 21s-8-5-8-11a5 5 0 0 1 8-4 5 5 0 0 1 8 4c0 6-8 11-8 11z",
  st_new: "M12 5v8m0 4h.01M12 3a9 9 0 1 0 9 9 9 9 0 0 0-9-9z",
  st_accepted: "M5 12l4 4 10-10",
  st_preparing: "M6 8h12M6 12h8M6 16h10M4 4h16v16H4z",
  st_ready: "M4 11h16v8H4zm2-5h12v5H6z",
  st_picked: "M4 12l5 5L20 7",
  st_shipped: "M3 16V8h11v8H3zm11 0h4l3-4v4h-3M7 18a1 1 0 1 0 0-2 1 1 0 0 0 0 2zm10 0a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  st_transit: "M3 12h18M14 6l7 6-7 6",
  st_out: "M12 3v10m0 0l4-4m-4 4L8 9M5 21h14",
  st_delivered: "M4 12l5 5L20 6",
  st_cancelled: "M6 6l12 12M18 6 6 18",
  st_returned: "M9 8H5v4m0-4 5-4m9 12h-4v-4m4 4-5 4",
  st_failed: "M12 8v5m0 3h.01M12 3a9 9 0 1 0 9 9 9 9 0 0 0-9-9z",
  dash: "M4 4h7v7H4zm9 0h7v4h-7zM4 13h7v7H4zm9 6h7v-9h-7z",
  products: "M4 8h16v12H4zm4-4h8l2 4H6z",
  add: "M12 5v14M5 12h14",
  inventory: "M4 7h16v4H4zm0 6h16v7H4z",
  sales: "M4 18V6m0 12h16M8 14v4m4-8v8m4-5v5",
  earnings: "M12 3a9 9 0 1 0 9 9 9 9 0 0 0-9-9zm-3 9h6m-3-3v6",
  commission: "M12 3v18M8 8h5a3 3 0 0 1 0 6H8h5a3 3 0 0 1 0 6H8",
  payouts: "M4 8h16v10H4zm4-4h8M8 13h8",
  profile: "M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4zM5 21a7 7 0 0 1 14 0",
  delivery: "M3 16V8h11v8zm11 0h4l3-4v4M7 18a1.2 1.2 0 1 0 0-2.4A1.2 1.2 0 0 0 7 18zm10 0a1.2 1.2 0 1 0 0-2.4A1.2 1.2 0 0 0 17 18z",
  settings: "M12 15a3 3 0 1 0-3-3 3 3 0 0 0 3 3zm7-3a7.5 7.5 0 0 0-.1-1.2l2-1.5-2-3.5-2.4 1a7.6 7.6 0 0 0-2.1-1.2L14 3h-4l-.4 2.6a7.6 7.6 0 0 0-2.1 1.2l-2.4-1-2 3.5 2 1.5A7.5 7.5 0 0 0 5 12a7.5 7.5 0 0 0 .1 1.2l-2 1.5 2 3.5 2.4-1a7.6 7.6 0 0 0 2.1 1.2L10 21h4l.4-2.6a7.6 7.6 0 0 0 2.1-1.2l2.4 1 2-3.5-2-1.5A7.5 7.5 0 0 0 19 12z",
  customers: "M8 11a3 3 0 1 0-3-3 3 3 0 0 0 3 3zm8 1a3 3 0 1 0-3-3 3 3 0 0 0 3 3zM3 20a5 5 0 0 1 10 0M13 20a5 5 0 0 1 8 0",
  analytics: "M5 19V9m7 10V5m7 14v-7",
  partners: "M8 11a3 3 0 1 0-3-3 3 3 0 0 0 3 3zm10-1a2.5 2.5 0 1 0-2.5-2.5A2.5 2.5 0 0 0 18 10zM4 20a4 4 0 0 1 8 0m6-2a3.5 3.5 0 0 1 6 0",
  instagram: "M8 3h8a5 5 0 0 1 5 5v8a5 5 0 0 1-5 5H8a5 5 0 0 1-5-5V8a5 5 0 0 1 5-5zm4 5.2A3.8 3.8 0 1 0 15.8 12 3.8 3.8 0 0 0 12 8.2zM17.2 6.6h.01",
  globe: "M12 21a9 9 0 1 0-9-9 9 9 0 0 0 9 9zM3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18",
  help: "M9.5 9a2.5 2.5 0 1 1 3.4 2.3c-.9.4-1.4 1-1.4 2.2V14m0 3.5h.01M12 3a9 9 0 1 0 9 9 9 9 0 0 0-9-9z",
  mail: "M4 6h16v12H4zm0 0 8 7 8-7",
  logout: "M10 6H6v12h4M14 16l5-4-5-4M9 12h10"
};

function icon(name, cls = "") {
  const d = ICO[name] || ICO.shop;
  return `<svg class="srj-ic ${cls}" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"/></svg>`;
}

function iconLabel(name, text, cls = "") {
  return `<span class="ic-label ${cls}">${icon(name)}${text}</span>`;
}

function categoryIconName(name) {
  const n = String(name || "").toLowerCase();
  const map = [
    ["fashion", "fashion"], ["jewellery", "jewellery"], ["accessor", "jewellery"],
    ["home", "living"], ["living", "living"], ["kitchen", "kitchen"],
    ["electronic", "electronics"], ["beauty", "beauty"], ["shoe", "shoes"], ["bag", "shoes"],
    ["kid", "kids"], ["sport", "sports"], ["fitness", "sports"], ["gift", "gifts"],
    ["trending", "trending"], ["deal", "deals"], ["offer", "deals"],
    ["restaurant", "restaurant"], ["daily", "daily"], ["fast food", "fastfood"], ["fast", "fastfood"],
    ["indian", "indian"], ["international", "restaurant"], ["bakery", "bakery"], ["dessert", "bakery"], ["cake", "bakery"],
    ["beverage", "drinks"], ["grocery", "grocery"], ["fruit", "produce"], ["vegetable", "produce"],
    ["meat", "meat"], ["seafood", "meat"], ["dairy", "dairy"], ["egg", "dairy"],
    ["snack", "snacks"], ["sweet", "sweets"], ["healthy", "healthy"], ["ready", "daily"], ["packaged", "grocery"],
    ["other food", "food"]
  ];
  for (const [k, v] of map) if (n.includes(k)) return v;
  return "categories";
}

function statusIconName(st) {
  const s = String(st || "").toLowerCase();
  if (["new", "placed", "new order"].includes(s)) return "st_new";
  if (s === "accepted") return "st_accepted";
  if (["preparing", "packed", "processing"].includes(s)) return "st_preparing";
  if (s.includes("ready")) return "st_ready";
  if (s.includes("picked")) return "st_picked";
  if (s === "shipped") return "st_shipped";
  if (s.includes("transit")) return "st_transit";
  if (s.includes("out_for") || s.includes("out for")) return "st_out";
  if (s === "delivered") return "st_delivered";
  if (s === "cancelled") return "st_cancelled";
  if (s === "returned") return "st_returned";
  if (s === "failed") return "st_failed";
  return "orders";
}

function statusBadge(st) {
  const label = String(st || "").replace(/_/g, " ");
  return `<span class="status-badge" title="${escapeHtml(label)}">${icon(statusIconName(st))} ${escapeHtml(label)}</span>`;
}

function headerHTML(active) {
  const u = currentUser();
  return `<header class="header"><div class="container header-inner">
    <a href="/" class="logo" aria-label="SRJ Choice Home">
      <img class="logo-img" src="/logo.jpg" alt="SRJ Choice"/>
    </a>
    <nav class="nav">
      <a class="nav-link ${active==="home"?"active":""}" href="/" title="Home">${icon("home")} Home</a>
      <a class="nav-link ${active==="shop"?"active":""}" href="/?page=shop" title="Shop">${icon("shop")} Shop</a>
      <a class="nav-link ${active==="food"?"active":""}" href="/?page=food" title="Food and Grocery">${icon("food")} Food & Grocery</a>
      <a class="nav-link ${active==="categories"?"active":""}" href="/?page=categories" title="Categories">${icon("categories")} Categories</a>
      <a class="nav-link" href="/seller" title="Become a Seller">${icon("seller")} Become a Seller</a>
    </nav>
    <div class="header-actions">
      <a class="icon-btn" href="/?page=shop" title="Search" aria-label="Search">${icon("search")}</a>
      <a class="icon-btn" href="/account" title="${u ? "Account" : "Log in"}" aria-label="${u ? "Account" : "Log in"}">${icon("account")}</a>
      <a class="icon-btn" href="/?page=cart" title="Cart" aria-label="Cart">${icon("cart")}<span class="cart-count" id="cart-count">0</span></a>
      <button class="icon-btn mobile-menu-btn" id="mobile-menu-btn" title="Menu" aria-label="Open menu">${icon("menu")}</button>
    </div>
  </div>
  <div class="mobile-nav" id="mobile-nav">
    <a class="nav-link" href="/">${icon("home")} Home</a>
    <a class="nav-link" href="/?page=shop">${icon("shop")} Shop</a>
    <a class="nav-link" href="/?page=food">${icon("food")} Food & Grocery</a>
    <a class="nav-link" href="/?page=categories">${icon("categories")} Categories</a>
    <a class="nav-link" href="/seller">${icon("seller")} Become a Seller</a>
    <a class="nav-link" href="/account">${icon("account")} Account</a>
    <a class="nav-link" href="/?page=cart">${icon("cart")} Cart</a>
    <a class="nav-link" href="/contact">${icon("help")} Help & Support</a>
  </div></header>`;
}

function footerHTML() {
  return `<footer class="footer"><div class="container footer-grid footer-grid-wide">
    <div class="footer-brand">
      <div class="logo"><img class="logo-img footer-logo" src="/logo.jpg" alt="SRJ Choice"/></div>
      <p>Your marketplace for products, food and grocery.</p>
      <div class="footer-social">
        <a class="social-chip" href="https://www.instagram.com/srjchoice/" target="_blank" rel="noopener" title="Instagram @srjchoice">${icon("instagram")} <span>Instagram<br><strong>@srjchoice</strong></span></a>
        <a class="social-chip" href="https://www.srjchoice.shop/" target="_blank" rel="noopener" title="Website">${icon("globe")} <span>Website<br><strong>www.srjchoice.shop</strong></span></a>
        <a class="social-chip" href="mailto:thesrjchoice@gmail.com" title="Email thesrjchoice@gmail.com">${icon("mail")} <span>Email<br><strong>thesrjchoice@gmail.com</strong></span></a>
      </div>
    </div>
    <div class="footer-col"><h4>Marketplace</h4>
      <a href="/?page=shop">${icon("shop")} Shop</a>
      <a href="/?page=categories">${icon("categories")} Categories</a>
      <a href="/?page=food">${icon("food")} Food & Grocery</a>
      <a href="/seller">${icon("seller")} Become a Seller</a>
    </div>
    <div class="footer-col"><h4>Customer</h4>
      <a href="/account">${icon("account")} My Account</a>
      <a href="/account">${icon("orders")} My Orders</a>
      <a href="/?page=cart">${icon("cart")} Cart</a>
      <a href="/contact">${icon("help")} Help & Support</a>
    </div>
    <div class="footer-col"><h4>Business</h4>
      <a href="/seller">${icon("seller")} Seller Center</a>
      <a href="/contact">${icon("mail")} Business Inquiry</a>
      <a href="/contact">${icon("partners")} Partner With Us</a>
      <a href="/contact">${icon("delivery")} Delivery Partners</a>
    </div>
    <div class="footer-col"><h4>Information</h4>
      <a href="/legal#about">About Us</a>
      <a href="/contact">Contact Us</a>
      <a href="/legal">Privacy Policy</a>
      <a href="/legal">Terms &amp; Conditions</a>
      <a href="/legal">Seller Agreement</a>
      <a href="/legal#shipping">Shipping &amp; Delivery Policy</a>
      <a href="/legal">Return &amp; Refund Policy</a>
    </div>
    </div>
    <div class="footer-bottom"><div class="container">
      <p>&copy; 2026 SRJ Choice. All rights reserved.</p>
      <p class="powered-by">Powered by HAS Productions</p>
    </div></div></footer><div class="toast" id="toast"></div>`;
}

document.addEventListener("click", e => {
  if (e.target.closest && e.target.closest("#mobile-menu-btn")) {
    document.getElementById("mobile-nav")?.classList.toggle("open");
  }
});
document.addEventListener("DOMContentLoaded", updateCartCount);
