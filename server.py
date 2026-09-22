#!/usr/bin/env python3
"""SRJ Choice multi-vendor marketplace backend (stdlib + sqlite3)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import urllib.parse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT
DATA = ROOT / "data"
UPLOADS = PUBLIC / "uploads"
DB_PATH = Path("/tmp/srj-choice.db")
SECRET_PATH = DATA / "secret.key"

DATA.mkdir(exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)

TOKEN_TTL = 60 * 60 * 24 * 14
MAX_UPLOAD = 4 * 1024 * 1024
ALLOWED_IMG = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

DEFAULT_CATEGORIES = [
    ("Fashion", ["Men", "Women", "Ethnic", "Western"]),
    ("Jewellery & Accessories", ["Jewellery", "Watches", "Sunglasses", "Other Accessories"]),
    ("Home & Living", ["Decor", "Furniture", "Bedding", "Lighting"]),
    ("Kitchen", ["Cookware", "Serveware", "Storage", "Appliances"]),
    ("Electronics", ["Audio", "Mobile Accessories", "Wearables", "Gadgets"]),
    ("Beauty & Personal Care", ["Skincare", "Haircare", "Makeup", "Fragrance"]),
    ("Shoes & Bags", ["Footwear", "Handbags", "Backpacks", "Wallets"]),
    ("Kids", ["Toys", "Kids Fashion", "Baby Care", "School"]),
    ("Sports & Fitness", ["Sportswear", "Equipment", "Yoga", "Outdoor"]),
    ("Gifts", ["Personalized", "Festive", "Corporate", "Hampers"]),
    ("Trending", ["New Arrivals", "Popular"]),
    ("Deals & Offers", ["Flash Sale", "Clearance", "Bundle Offers"]),
]

FOOD_CATEGORIES = [
    ("Restaurants", ["North Indian", "South Indian", "Chinese", "Multi-cuisine"]),
    ("Fast Food", ["Burgers", "Pizza", "Wraps", "Street Food"]),
    ("Indian Food", ["Thali", "Biryani", "Curry", "Tandoor"]),
    ("International Food", ["Italian", "Asian", "Continental", "Mexican"]),
    ("Bakery & Desserts", ["Pastries", "Cookies", "Ice Cream"]),
    ("Cakes", ["Designer Cakes", "Cupcakes"]),
    ("Sweets", ["Mithai", "Chocolate"]),
    ("Snacks", ["Namkeen", "Chips", "Evening Snacks"]),
    ("Beverages", ["Tea & Coffee", "Juices", "Shakes"]),
    ("Grocery", ["Staples", "Oil & Spices", "Household"]),
    ("Fruits & Vegetables", ["Fruits", "Vegetables", "Herbs"]),
    ("Meat & Seafood", ["Chicken", "Mutton", "Fish"]),
    ("Dairy & Eggs", ["Milk", "Cheese", "Eggs"]),
    ("Packaged Foods", ["Ready Packs", "Canned"]),
    ("Healthy Food", ["Salads", "Bowls"]),
    ("Ready-to-Eat", ["Meals", "Combos"]),
    ("Other Food", ["Misc"]),
]

PRODUCT_FLOW = [
    "placed", "accepted", "packed", "ready_pickup", "shipped",
    "in_transit", "out_for_delivery", "delivered", "cancelled", "failed", "returned",
]
FOOD_FLOW = [
    "new", "accepted", "preparing", "ready_pickup", "picked_up",
    "out_for_delivery", "delivered", "cancelled",
]
VERTICALS = ("product", "food", "grocery", "service")


def secret() -> bytes:
    if SECRET_PATH.exists():
        return SECRET_PATH.read_bytes()
    s = secrets.token_bytes(32)
    SECRET_PATH.write_bytes(s)
    return s


def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120_000)
    return f"pbkdf2$120000${salt}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, rounds, salt, hx = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), int(rounds))
        return hmac.compare_digest(dk.hex(), hx)
    except Exception:
        return False


def sign_token(payload: dict) -> str:
    body = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(secret(), body, hashlib.sha256).hexdigest()
    return body.hex() + "." + sig


def parse_token(token: str) -> dict | None:
    try:
        hx, sig = token.split(".", 1)
        body = bytes.fromhex(hx)
        expect = hmac.new(secret(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expect, sig):
            return None
        data = json.loads(body.decode())
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=DELETE")
    return con


def seed():
    con = db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sellers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            store_name TEXT NOT NULL,
            address TEXT,
            city TEXT,
            pincode TEXT,
            gstin TEXT,
            pan_last4 TEXT,
            kyc_note TEXT,
            bank_name TEXT,
            ifsc TEXT,
            account_last4 TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            bio TEXT,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER,
            active INTEGER NOT NULL DEFAULT 1,
            commission_pct REAL,
            sort_order INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            category_id INTEGER,
            subcategory_id INTEGER,
            description TEXT,
            price REAL NOT NULL,
            mrp REAL,
            stock INTEGER NOT NULL DEFAULT 0,
            sku TEXT,
            size TEXT,
            color TEXT,
            shipping TEXT,
            images TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            featured INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(seller_id) REFERENCES sellers(id)
        );
        CREATE TABLE IF NOT EXISTS addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            label TEXT,
            line1 TEXT,
            city TEXT,
            state TEXT,
            pincode TEXT,
            phone TEXT
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT UNIQUE,
            customer_id INTEGER NOT NULL,
            address_json TEXT,
            payment_method TEXT,
            payment_status TEXT,
            status TEXT NOT NULL,
            subtotal REAL NOT NULL,
            shipping REAL NOT NULL,
            total REAL NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            name TEXT,
            qty INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            commission_pct REAL NOT NULL,
            commission_amt REAL NOT NULL,
            seller_amt REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'placed'
        );
        CREATE TABLE IF NOT EXISTS payouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            note TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS rate_limits (
            key TEXT PRIMARY KEY,
            count INTEGER,
            window_start INTEGER
        );
        """
    )
    if not con.execute("SELECT 1 FROM settings WHERE key='commission_default'").fetchone():
        con.execute("INSERT INTO settings(key,value) VALUES('commission_default','10')")
    if not con.execute("SELECT 1 FROM categories").fetchone():
        sort = 0
        for main, subs in DEFAULT_CATEGORIES:
            sort += 1
            cur = con.execute(
                "INSERT INTO categories(name,parent_id,active,commission_pct,sort_order) VALUES(?,?,1,NULL,?)",
                (main, None, sort),
            )
            pid = cur.lastrowid
            for i, sub in enumerate(subs):
                con.execute(
                    "INSERT INTO categories(name,parent_id,active,commission_pct,sort_order) VALUES(?,?,1,NULL,?)",
                    (sub, pid, i + 1),
                )
    if not con.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        admin_pw = os.environ.get("SRJ_ADMIN_PASSWORD", "SRJ-Admin-2408")
        con.execute(
            "INSERT INTO users(role,name,email,phone,password_hash,created_at) VALUES(?,?,?,?,?,?)",
            (
                "admin",
                "SRJ Admin",
                "admin@srjchoice.in",
                "9999999999",
                hash_password(admin_pw),
                int(time.time()),
            ),
        )
        print("Admin created: admin@srjchoice.in / (see SRJ_ADMIN_PASSWORD or default SRJ-Admin-2408)")
    # demo seller + products if empty
    if not con.execute("SELECT 1 FROM products").fetchone():
        pw = hash_password("Seller@123")
        con.execute(
            "INSERT INTO users(role,name,email,phone,password_hash,created_at) VALUES(?,?,?,?,?,?)",
            ("seller", "Aarav Stores", "seller@srjchoice.in", "9888888888", pw, int(time.time())),
        )
        uid = con.execute("SELECT id FROM users WHERE email='seller@srjchoice.in'").fetchone()["id"]
        con.execute(
            """INSERT INTO sellers(user_id,store_name,address,city,pincode,status,bio,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (uid, "Aarav Atelier", "MG Road", "Mumbai", "400001", "approved", "Independent premium seller", int(time.time())),
        )
        sid = con.execute("SELECT id FROM sellers WHERE user_id=?", (uid,)).fetchone()["id"]
        fashion = con.execute("SELECT id FROM categories WHERE name='Fashion' AND parent_id IS NULL").fetchone()["id"]
        acc = con.execute("SELECT id FROM categories WHERE name='Jewellery & Accessories' AND parent_id IS NULL").fetchone()["id"]
        home = con.execute("SELECT id FROM categories WHERE name='Home & Living' AND parent_id IS NULL").fetchone()["id"]
        elec = con.execute("SELECT id FROM categories WHERE name='Electronics' AND parent_id IS NULL").fetchone()["id"]
        samples = [
            ("Minimal Leather Watch", acc, 15690, 19010, "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600", "Refined leather strap watch."),
            ("Wireless Headphones", elec, 20670, None, "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600", "ANC headphones, 30-hour battery."),
            ("Organic Cotton Crew Tee", fashion, 3980, 5150, "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=600", "Soft organic cotton tee."),
            ("Ceramic Pour-Over Set", home, 6470, None, "https://images.unsplash.com/photo-1514228742587-6b1558fcca3d?w=600", "Handcrafted ceramic brew set."),
            ("Leather Crossbody Bag", acc, 13700, None, "https://images.unsplash.com/photo-1548036328-c9fa89d128fa?w=600", "Full-grain leather bag."),
            ("Linen Throw Blanket", home, 7390, None, "https://images.unsplash.com/photo-1584100936595-c0654b55a2e2?w=600", "Washed linen throw."),
        ]
        for name, cid, price, mrp, img, desc in samples:
            con.execute(
                """INSERT INTO products(seller_id,name,category_id,description,price,mrp,stock,images,status,created_at)
                   VALUES(?,?,?,?,?,?,?,?, 'published', ?)""",
                (sid, name, cid, desc, price, mrp, 25, json.dumps([img]), int(time.time())),
            )
    migrate_ext(con)
    con.commit()
    con.close()


def add_col(con, table, col, spec):
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    if col not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {spec}")


def migrate_ext(con):
    add_col(con, "categories", "vertical", "TEXT DEFAULT 'product'")
    add_col(con, "sellers", "vertical", "TEXT DEFAULT 'product'")
    add_col(con, "sellers", "open_status", "TEXT DEFAULT 'open'")
    add_col(con, "sellers", "hours_open", "TEXT")
    add_col(con, "sellers", "hours_close", "TEXT")
    add_col(con, "sellers", "delivery_enabled", "INTEGER DEFAULT 1")
    add_col(con, "sellers", "pickup_enabled", "INTEGER DEFAULT 1")
    add_col(con, "sellers", "shipping_method", "TEXT DEFAULT 'courier'")
    add_col(con, "sellers", "delivery_areas", "TEXT")
    add_col(con, "sellers", "seller_code", "TEXT")
    for row in con.execute("SELECT id FROM sellers WHERE seller_code IS NULL OR seller_code=''").fetchall():
        con.execute("UPDATE sellers SET seller_code=? WHERE id=?", ("SRJ-S" + secrets.token_hex(3).upper(), row["id"]))
    add_col(con, "sellers", "prep_time_min", "INTEGER DEFAULT 30")
    add_col(con, "sellers", "process_time_hours", "INTEGER DEFAULT 24")
    add_col(con, "products", "vertical", "TEXT DEFAULT 'product'")
    add_col(con, "products", "ingredients", "TEXT")
    add_col(con, "products", "prep_time_min", "INTEGER")
    add_col(con, "products", "available", "INTEGER DEFAULT 1")
    add_col(con, "orders", "vertical", "TEXT DEFAULT 'product'")
    add_col(con, "orders", "fulfillment", "TEXT DEFAULT 'courier'")
    add_col(con, "orders", "delivery_fee", "REAL DEFAULT 0")
    add_col(con, "orders", "discount", "REAL DEFAULT 0")
    add_col(con, "orders", "tax", "REAL DEFAULT 0")
    add_col(con, "orders", "eta_minutes", "INTEGER")
    add_col(con, "orders", "eta_date", "TEXT")
    add_col(con, "order_items", "vertical", "TEXT DEFAULT 'product'")
    add_col(con, "order_items", "delivery_fee_share", "REAL DEFAULT 0")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS delivery_partners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            contact TEXT,
            api_ready INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            partner_id INTEGER,
            status TEXT NOT NULL,
            pickup_address TEXT,
            drop_address TEXT,
            fee REAL DEFAULT 0,
            tracking_code TEXT,
            eta_minutes INTEGER,
            proof TEXT,
            notes TEXT,
            assigned_at INTEGER,
            updated_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS delivery_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS inquiries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            inquiry_type TEXT NOT NULL,
            subject TEXT,
            order_number TEXT,
            message TEXT NOT NULL,
            attachment TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            admin_note TEXT,
            reply TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER
        );
        """
    )
    defaults = {
        "product_delivery_fee": "49",
        "product_free_above": "999",
        "food_delivery_fee": "39",
        "food_free_above": "499",
        "grocery_delivery_fee": "29",
        "grocery_free_above": "399",
        "contact_business_email": "",
        "contact_support_email": "",
        "contact_seller_email": "",
        "contact_address": "",
        "contact_hours": "",
        "instagram_url": "https://www.instagram.com/srjchoice/",
        "instagram_handle": "@srjchoice",
        "website_url": "https://www.srjchoice.shop/",
        "website_label": "www.srjchoice.shop",
    }
    for k, v in defaults.items():
        if not con.execute("SELECT 1 FROM settings WHERE key=?", (k,)).fetchone():
            con.execute("INSERT INTO settings(key,value) VALUES(?,?)", (k, v))
    if not con.execute("SELECT 1 FROM categories WHERE vertical='food'").fetchone():
        sort = 100
        for main, subs in FOOD_CATEGORIES:
            sort += 1
            cur = con.execute(
                "INSERT INTO categories(name,parent_id,active,commission_pct,sort_order,vertical) VALUES(?,?,1,NULL,?, 'food')",
                (main, None, sort),
            )
            pid = cur.lastrowid
            for i, sub in enumerate(subs):
                con.execute(
                    "INSERT INTO categories(name,parent_id,active,commission_pct,sort_order,vertical) VALUES(?,?,1,NULL,?, 'food')",
                    (sub, pid, i + 1),
                )
    if not con.execute("SELECT 1 FROM delivery_partners").fetchone():
        now = int(time.time())
        for name, kind in (
            ("SRJ Courier Connect", "shipping"),
            ("Local Rider Network", "food"),
            ("Seller Self-Ship", "seller"),
        ):
            con.execute(
                "INSERT INTO delivery_partners(name,kind,api_ready,active,created_at) VALUES(?,?,0,1,?)",
                (name, kind, now),
            )
    if not con.execute("SELECT 1 FROM sellers WHERE vertical='food'").fetchone():
        if not con.execute("SELECT 1 FROM users WHERE email='food@srjchoice.in'").fetchone():
            con.execute(
                "INSERT INTO users(role,name,email,phone,password_hash,created_at) VALUES(?,?,?,?,?,?)",
                ("seller", "Spice Kitchen", "food@srjchoice.in", "9777777777", hash_password("Food@123"), int(time.time())),
            )
        uid = con.execute("SELECT id FROM users WHERE email='food@srjchoice.in'").fetchone()["id"]
        con.execute(
            """INSERT INTO sellers(user_id,store_name,address,city,pincode,status,bio,created_at,vertical,open_status,hours_open,hours_close,delivery_enabled,pickup_enabled,shipping_method,prep_time_min)
               VALUES(?,?,?,?,?,'approved',?,?, 'food','open','10:00','23:00',1,1,'platform',25)""",
            (uid, "Spice Kitchen", "Bandra West", "Mumbai", "400050", "Home-style Indian meals", int(time.time())),
        )
        fsid = con.execute("SELECT id FROM sellers WHERE user_id=?", (uid,)).fetchone()["id"]
        indian = con.execute("SELECT id FROM categories WHERE name='Indian Food' AND parent_id IS NULL").fetchone()
        bakery = con.execute("SELECT id FROM categories WHERE name='Bakery & Desserts' AND parent_id IS NULL").fetchone()
        foods = [
            ("Butter Chicken Bowl", indian["id"] if indian else None, 349, "Creamy tomato gravy with rice.", 20),
            ("Veg Thali", indian["id"] if indian else None, 249, "Dal, sabzi, roti, rice, salad.", 25),
            ("Gulab Jamun (2 pc)", bakery["id"] if bakery else None, 89, "Warm milk dumplings.", 10),
        ]
        for name, cid, price, desc, prep in foods:
            con.execute(
                """INSERT INTO products(seller_id,name,category_id,description,price,stock,images,status,created_at,vertical,prep_time_min,available)
                   VALUES(?,?,?,?,?,99,?,'published',?, 'food', ?, 1)""",
                (fsid, name, cid, desc, price, json.dumps([]), int(time.time()), prep),
            )


def rowd(r) -> dict:
    return dict(r) if r is not None else None


def rows(rs) -> list:
    return [dict(x) for x in rs]


def commission_pct(con, category_id) -> float:
    default = float(con.execute("SELECT value FROM settings WHERE key='commission_default'").fetchone()["value"])
    if not category_id:
        return default
    cat = con.execute("SELECT commission_pct, parent_id FROM categories WHERE id=?", (category_id,)).fetchone()
    if cat and cat["commission_pct"] is not None:
        return float(cat["commission_pct"])
    if cat and cat["parent_id"]:
        parent = con.execute("SELECT commission_pct FROM categories WHERE id=?", (cat["parent_id"],)).fetchone()
        if parent and parent["commission_pct"] is not None:
            return float(parent["commission_pct"])
    return default


def rate_ok(con, key: str, limit=8, window=60) -> bool:
    now = int(time.time())
    rec = con.execute("SELECT count, window_start FROM rate_limits WHERE key=?", (key,)).fetchone()
    if not rec or now - rec["window_start"] > window:
        con.execute("INSERT OR REPLACE INTO rate_limits(key,count,window_start) VALUES(?,?,?)", (key, 1, now))
        con.commit()
        return True
    if rec["count"] >= limit:
        return False
    con.execute("UPDATE rate_limits SET count=count+1 WHERE key=?", (key,))
    con.commit()
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = "SRJChoice/1.0"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def _json(self, code, obj):
        raw = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _text(self, code, body, ctype="text/plain"):
        raw = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _file(self, path: Path):
        if not path.exists() or not path.is_file():
            self._text(404, "Not found")
            return
        data = path.read_bytes()
        ext = path.suffix.lower()
        types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }
        self.send_response(200)
        self.send_header("Content-Type", types.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        if ext in {".css", ".js", ".png", ".jpg", ".webp"}:
            self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def json_body(self) -> dict:
        raw = self.body()
        if not raw:
            return {}
        return json.loads(raw.decode())

    def token(self) -> dict | None:
        auth = self.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            return parse_token(auth.split(" ", 1)[1].strip())
        cookie = SimpleCookie()
        if "Cookie" in self.headers:
            cookie.load(self.headers["Cookie"])
        if "srj_token" in cookie:
            return parse_token(cookie["srj_token"].value)
        return None

    def require(self, *roles):
        t = self.token()
        if not t:
            self._json(401, {"error": "Login required"})
            return None
        if roles and t.get("role") not in roles:
            self._json(403, {"error": "Not allowed"})
            return None
        return t

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        q = dict(urllib.parse.parse_qsl(parsed.query))
        if path.startswith("/api/"):
            return self.api_get(path, q)
        if path == "/":
            return self._file(PUBLIC / "index.html")
        if path in ("/seller", "/seller/"):
            return self._file(PUBLIC / "seller.html")
        if path in ("/admin", "/admin/"):
            return self._file(PUBLIC / "admin.html")
        if path in ("/account", "/account/"):
            return self._file(PUBLIC / "account.html")
        if path in ("/legal", "/legal/"):
            return self._file(PUBLIC / "legal.html")
        if path in ("/contact", "/contact/", "/help", "/help/"):
            return self._file(PUBLIC / "contact.html")
        rel = path.lstrip("/")
        candidate = (PUBLIC / rel).resolve()
        if str(candidate).startswith(str(PUBLIC.resolve())) and candidate.exists():
            return self._file(candidate)
        return self._file(PUBLIC / "index.html")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        self.api_post(parsed.path)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        self.api_put(parsed.path)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        self.api_delete(parsed.path)

    def api_get(self, path, q):
        con = db()
        try:
            if path == "/api/health":
                return self._json(200, {"ok": True, "brand": "SRJ Choice"})
            if path == "/api/settings/public":
                comm = con.execute("SELECT value FROM settings WHERE key='commission_default'").fetchone()
                return self._json(200, {"commission_default": float(comm["value"]), "brand": "SRJ Choice"})
            if path == "/api/contact":
                keys = (
                    "contact_business_email", "contact_support_email", "contact_seller_email",
                    "contact_address", "contact_hours", "instagram_url", "instagram_handle",
                    "website_url", "website_label",
                )
                out = {
                    "instagram_url": "https://www.instagram.com/srjchoice/",
                    "instagram_handle": "@srjchoice",
                    "website_url": "https://www.srjchoice.shop/",
                    "website_label": "www.srjchoice.shop",
                }
                for k in keys:
                    r = con.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
                    if r and r["value"]:
                        out[k.replace("contact_", "")] = r["value"]
                        out[k] = r["value"]
                return self._json(200, {"contact": out})
            if path == "/api/admin/inquiries":
                auth = self.require("admin")
                if not auth:
                    return
                typ = q.get("type")
                st = q.get("status")
                qtext = (q.get("q") or "").strip()
                sql = "SELECT * FROM inquiries WHERE 1=1"
                args = []
                if typ:
                    sql += " AND inquiry_type=?"
                    args.append(typ)
                if st:
                    sql += " AND status=?"
                    args.append(st)
                if qtext:
                    sql += " AND (name LIKE ? OR email LIKE ? OR phone LIKE ? OR subject LIKE ? OR order_number LIKE ?)"
                    like = f"%{qtext}%"
                    args += [like, like, like, like, like]
                sql += " ORDER BY id DESC LIMIT 300"
                return self._json(200, {"inquiries": rows(con.execute(sql, args))})
            if path == "/api/categories":
                vert = q.get("vertical")
                if vert:
                    cats = rows(con.execute("SELECT * FROM categories WHERE active=1 AND COALESCE(vertical,'product')=? ORDER BY parent_id IS NOT NULL, sort_order, name", (vert,)))
                else:
                    cats = rows(con.execute("SELECT * FROM categories WHERE active=1 ORDER BY parent_id IS NOT NULL, sort_order, name"))
                return self._json(200, {"categories": cats})
            if path == "/api/food/restaurants":
                sl = rows(con.execute(
                    """SELECT id, store_name, city, bio, open_status, hours_open, hours_close,
                              delivery_enabled, pickup_enabled, prep_time_min, address
                       FROM sellers WHERE status='approved' AND COALESCE(vertical,'product') IN ('food','grocery')
                       ORDER BY store_name"""
                ))
                return self._json(200, {"restaurants": sl})
            if path == "/api/delivery/partners":
                auth = self.token()
                if auth and auth.get("role") == "admin":
                    return self._json(200, {"partners": rows(con.execute("SELECT * FROM delivery_partners ORDER BY id"))})
                return self._json(200, {"partners": rows(con.execute("SELECT id,name,kind,active FROM delivery_partners WHERE active=1"))})
            if path == "/api/delivery/orders":
                auth = self.require("admin")
                if not auth:
                    return
                vert = q.get("vertical")
                sql = "SELECT * FROM orders"
                args = []
                if vert:
                    sql += " WHERE COALESCE(vertical,'product')=?"
                    args.append(vert)
                sql += " ORDER BY id DESC LIMIT 300"
                ords = rows(con.execute(sql, args))
                for o in ords:
                    o["items"] = rows(con.execute("SELECT * FROM order_items WHERE order_id=?", (o["id"],)))
                    o["delivery"] = rowd(con.execute("SELECT * FROM deliveries WHERE order_id=? ORDER BY id DESC LIMIT 1", (o["id"],)).fetchone())
                return self._json(200, {"orders": ords})
            if path == "/api/categories/all":
                auth = self.token()
                if not auth or auth.get("role") != "admin":
                    cats = rows(con.execute("SELECT * FROM categories WHERE active=1 ORDER BY sort_order, name"))
                else:
                    cats = rows(con.execute("SELECT * FROM categories ORDER BY sort_order, name"))
                return self._json(200, {"categories": cats})
            if path == "/api/sellers/public":
                qtext = (q.get("q") or "").strip()
                sql = """SELECT s.id, s.store_name, s.city, s.bio, s.vertical, s.open_status, s.prep_time_min
                         FROM sellers s WHERE s.status='approved'"""
                args = []
                if q.get("vertical"):
                    sql += " AND COALESCE(s.vertical,'product')=?"
                    args.append(q["vertical"])
                if qtext:
                    sql += " AND (s.store_name LIKE ? OR s.city LIKE ?)"
                    args += [f"%{qtext}%", f"%{qtext}%"]
                return self._json(200, {"sellers": rows(con.execute(sql, args))})
            if path.startswith("/api/sellers/public/"):
                sid = int(path.rsplit("/", 1)[-1])
                s = con.execute(
                    """SELECT id, store_name, city, bio, vertical, open_status, hours_open, hours_close,
                              delivery_enabled, pickup_enabled, prep_time_min, process_time_hours, address
                       FROM sellers WHERE id=? AND status='approved'""",
                    (sid,),
                ).fetchone()
                if not s:
                    return self._json(404, {"error": "Store not found"})
                prods = rows(
                    con.execute(
                        "SELECT id,name,price,mrp,images,status FROM products WHERE seller_id=? AND status='published'",
                        (sid,),
                    )
                )
                return self._json(200, {"seller": dict(s), "products": prods})
            if path == "/api/products":
                return self._json(200, {"products": self.list_products(con, q, public=True)})
            if path.startswith("/api/products/") and path.count("/") == 3:
                pid = int(path.rsplit("/", 1)[-1])
                p = con.execute(
                    """SELECT p.*, s.store_name, s.id as store_id, s.city as store_city
                       FROM products p JOIN sellers s ON s.id=p.seller_id WHERE p.id=?""",
                    (pid,),
                ).fetchone()
                if not p or p["status"] != "published":
                    auth = self.token()
                    if not p:
                        return self._json(404, {"error": "Not found"})
                    if not auth or (auth.get("role") == "seller" and self.seller_id(con, auth) != p["seller_id"] and auth.get("role") != "admin"):
                        if not auth or auth.get("role") not in ("admin", "seller"):
                            return self._json(404, {"error": "Not found"})
                d = dict(p)
                d["images"] = json.loads(d.get("images") or "[]")
                return self._json(200, {"product": d})
            if path == "/api/me":
                auth = self.require()
                if not auth:
                    return
                u = con.execute("SELECT id,role,name,email,phone,created_at FROM users WHERE id=?", (auth["uid"],)).fetchone()
                extra = {}
                if u["role"] == "seller":
                    extra["seller"] = rowd(con.execute("SELECT * FROM sellers WHERE user_id=?", (u["id"],)).fetchone())
                    if extra["seller"]:
                        extra["seller"].pop("account_last4", None)  # still return last4 ok
                extra["addresses"] = rows(con.execute("SELECT * FROM addresses WHERE user_id=?", (u["id"],)))
                return self._json(200, {"user": dict(u), **extra})
            if path == "/api/orders/mine":
                auth = self.require("customer", "admin")
                if not auth:
                    return
                if auth["role"] == "admin":
                    ords = rows(con.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 200"))
                else:
                    ords = rows(con.execute("SELECT * FROM orders WHERE customer_id=? ORDER BY id DESC", (auth["uid"],)))
                for o in ords:
                    o["items"] = rows(con.execute("SELECT * FROM order_items WHERE order_id=?", (o["id"],)))
                    o["delivery"] = rowd(con.execute("SELECT * FROM deliveries WHERE order_id=? ORDER BY id DESC LIMIT 1", (o["id"],)).fetchone())
                return self._json(200, {"orders": ords})
            if path == "/api/seller/dashboard":
                auth = self.require("seller", "admin")
                if not auth:
                    return
                sid = int(q["seller_id"]) if auth["role"] == "admin" and q.get("seller_id") else self.seller_id(con, auth)
                if not sid:
                    return self._json(400, {"error": "Seller profile missing"})
                return self._json(200, self.seller_dash(con, sid))
            if path == "/api/seller/products":
                auth = self.require("seller", "admin")
                if not auth:
                    return
                sid = self.seller_id(con, auth) if auth["role"] == "seller" else int(q.get("seller_id") or 0)
                if auth["role"] == "seller":
                    prods = rows(con.execute("SELECT * FROM products WHERE seller_id=? ORDER BY id DESC", (sid,)))
                else:
                    prods = rows(con.execute("SELECT * FROM products ORDER BY id DESC"))
                for p in prods:
                    p["images"] = json.loads(p.get("images") or "[]")
                return self._json(200, {"products": prods})
            if path == "/api/seller/orders":
                auth = self.require("seller")
                if not auth:
                    return
                sid = self.seller_id(con, auth)
                items = rows(
                    con.execute(
                        """SELECT oi.*, o.public_id, o.created_at as order_created, o.status as order_status
                           FROM order_items oi JOIN orders o ON o.id=oi.order_id
                           WHERE oi.seller_id=? ORDER BY oi.id DESC""",
                        (sid,),
                    )
                )
                return self._json(200, {"orders": items})
            if path == "/api/admin/stats":
                auth = self.require("admin")
                if not auth:
                    return
                return self._json(200, self.admin_stats(con))
            if path == "/api/admin/sellers":
                auth = self.require("admin")
                if not auth:
                    return
                sl = rows(
                    con.execute(
                        """SELECT s.*, u.name, u.email, u.phone FROM sellers s JOIN users u ON u.id=s.user_id ORDER BY s.id DESC"""
                    )
                )
                return self._json(200, {"sellers": sl})
            if path == "/api/admin/customers":
                auth = self.require("admin")
                if not auth:
                    return
                cs = rows(con.execute("SELECT id,name,email,phone,created_at FROM users WHERE role='customer' ORDER BY id DESC"))
                return self._json(200, {"customers": cs})
            if path == "/api/admin/orders":
                auth = self.require("admin")
                if not auth:
                    return
                ords = rows(con.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 300"))
                for o in ords:
                    o["items"] = rows(con.execute("SELECT * FROM order_items WHERE order_id=?", (o["id"],)))
                return self._json(200, {"orders": ords})
            if path == "/api/admin/payouts":
                auth = self.require("admin")
                if not auth:
                    return
                return self._json(200, {"payouts": rows(con.execute("SELECT * FROM payouts ORDER BY id DESC"))})
            return self._json(404, {"error": "Unknown API"})
        except Exception as e:
            return self._json(500, {"error": str(e)})
        finally:
            con.close()

    def seller_id(self, con, auth):
        r = con.execute("SELECT id FROM sellers WHERE user_id=?", (auth["uid"],)).fetchone()
        return r["id"] if r else None

    def list_products(self, con, q, public=True):
        sql = """SELECT p.id,p.name,p.price,p.mrp,p.stock,p.images,p.status,p.featured,
                        p.category_id,p.subcategory_id,p.description,p.vertical,p.available,p.prep_time_min,p.ingredients,
                        s.store_name,s.id as store_id,s.vertical as store_vertical,s.open_status
                 FROM products p JOIN sellers s ON s.id=p.seller_id WHERE 1=1"""
        args = []
        if public:
            sql += " AND p.status='published' AND s.status='approved' AND COALESCE(p.available,1)=1"
        if q.get("vertical"):
            sql += " AND COALESCE(p.vertical,'product')=?"
            args.append(q["vertical"])
        if q.get("category"):
            sql += " AND (p.category_id=? OR p.subcategory_id=?)"
            args += [q["category"], q["category"]]
        if q.get("seller"):
            sql += " AND p.seller_id=?"
            args.append(q["seller"])
        if q.get("q"):
            sql += " AND (p.name LIKE ? OR p.description LIKE ? OR s.store_name LIKE ?)"
            like = f"%{q['q']}%"
            args += [like, like, like]
        if q.get("deals") == "1":
            sql += " AND p.mrp IS NOT NULL AND p.mrp > p.price"
        if q.get("featured") == "1":
            sql += " AND p.featured=1"
        sort = q.get("sort") or "featured"
        if sort == "price-asc":
            sql += " ORDER BY p.price ASC"
        elif sort == "price-desc":
            sql += " ORDER BY p.price DESC"
        elif sort == "name-asc":
            sql += " ORDER BY p.name ASC"
        else:
            sql += " ORDER BY p.featured DESC, p.id DESC"
        out = rows(con.execute(sql, args))
        for p in out:
            p["images"] = json.loads(p.get("images") or "[]")
        return out

    def seller_dash(self, con, sid):
        seller = rowd(con.execute("SELECT * FROM sellers WHERE id=?", (sid,)).fetchone())
        items = rows(con.execute("SELECT * FROM order_items WHERE seller_id=?", (sid,)))
        gross = sum(i["unit_price"] * i["qty"] for i in items)
        commission = sum(i["commission_amt"] for i in items)
        net = sum(i["seller_amt"] for i in items)
        paid = con.execute(
            "SELECT COALESCE(SUM(amount),0) s FROM payouts WHERE seller_id=? AND status='paid'",
            (sid,),
        ).fetchone()["s"]
        available = max(0, net - float(paid or 0))
        products = rows(con.execute("SELECT id,name,stock,status,price FROM products WHERE seller_id=?", (sid,)))
        payouts = rows(con.execute("SELECT * FROM payouts WHERE seller_id=? ORDER BY id DESC", (sid,)))
        return {
            "seller": seller,
            "stats": {
                "gross_sales": gross,
                "commission": commission,
                "net_earnings": net,
                "paid": float(paid or 0),
                "available_payout": available,
                "orders": len(items),
                "products": len(products),
            },
            "products": products,
            "payouts": payouts,
        }

    def admin_stats(self, con):
        return {
            "customers": con.execute("SELECT COUNT(*) c FROM users WHERE role='customer'").fetchone()["c"],
            "sellers": con.execute("SELECT COUNT(*) c FROM sellers").fetchone()["c"],
            "pending_sellers": con.execute("SELECT COUNT(*) c FROM sellers WHERE status='pending'").fetchone()["c"],
            "products": con.execute("SELECT COUNT(*) c FROM products").fetchone()["c"],
            "pending_products": con.execute("SELECT COUNT(*) c FROM products WHERE status='pending'").fetchone()["c"],
            "orders": con.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"],
            "gmv": con.execute("SELECT COALESCE(SUM(total),0) s FROM orders").fetchone()["s"],
            "commission": con.execute("SELECT COALESCE(SUM(commission_amt),0) s FROM order_items").fetchone()["s"],
            "commission_default": float(con.execute("SELECT value FROM settings WHERE key='commission_default'").fetchone()["value"]),
        }

    def issue(self, user):
        tok = sign_token({"uid": user["id"], "role": user["role"], "exp": time.time() + TOKEN_TTL})
        return {"token": tok, "user": {"id": user["id"], "role": user["role"], "name": user["name"], "email": user["email"]}}

    def api_post(self, path):
        con = db()
        try:
            if path == "/api/auth/register":
                return self.reg(con, "customer")
            if path == "/api/auth/register-seller":
                return self.reg(con, "seller")
            if path == "/api/auth/login":
                data = self.json_body()
                ident = (data.get("email") or data.get("phone") or "").strip().lower()
                pw = data.get("password") or ""
                ip = self.client_address[0]
                if not rate_ok(con, "login:" + ip, 12, 60):
                    return self._json(429, {"error": "Too many attempts"})
                u = con.execute(
                    "SELECT * FROM users WHERE lower(email)=? OR phone=?",
                    (ident, re.sub(r"\D", "", ident)),
                ).fetchone()
                if not u or not verify_password(pw, u["password_hash"]):
                    return self._json(401, {"error": "Invalid credentials"})
                if u["role"] == "seller":
                    s = con.execute("SELECT status FROM sellers WHERE user_id=?", (u["id"],)).fetchone()
                    if s and s["status"] == "suspended":
                        return self._json(403, {"error": "Seller account suspended"})
                return self._json(200, self.issue(u))
            if path == "/api/products" or path == "/api/seller/products":
                return self.create_product(con)
            if path == "/api/orders":
                return self.create_order(con)
            if path == "/api/inquiries":
                return self.create_inquiry(con)
            if path == "/api/upload":
                return self.upload(con)
            if path == "/api/addresses":
                auth = self.require("customer", "seller", "admin")
                if not auth:
                    return
                d = self.json_body()
                con.execute(
                    "INSERT INTO addresses(user_id,label,line1,city,state,pincode,phone) VALUES(?,?,?,?,?,?,?)",
                    (auth["uid"], d.get("label", "Home"), d.get("line1"), d.get("city"), d.get("state"), d.get("pincode"), d.get("phone")),
                )
                con.commit()
                return self._json(200, {"ok": True})
            if path == "/api/admin/categories":
                auth = self.require("admin")
                if not auth:
                    return
                d = self.json_body()
                con.execute(
                    "INSERT INTO categories(name,parent_id,active,commission_pct,sort_order) VALUES(?,?,?,?,?)",
                    (d["name"], d.get("parent_id"), 1 if d.get("active", True) else 0, d.get("commission_pct"), d.get("sort_order", 0)),
                )
                con.commit()
                return self._json(200, {"ok": True, "id": con.execute("SELECT last_insert_rowid() i").fetchone()["i"]})
            if path == "/api/admin/payouts":
                auth = self.require("admin")
                if not auth:
                    return
                d = self.json_body()
                sid = int(d["seller_id"])
                amt = float(d["amount"])
                if amt <= 0:
                    return self._json(400, {"error": "Invalid amount"})
                dash = self.seller_dash(con, sid)
                if amt > dash["stats"]["available_payout"] + 0.01:
                    return self._json(400, {"error": "Amount exceeds available payout"})
                con.execute(
                    "INSERT INTO payouts(seller_id,amount,status,note,created_at) VALUES(?,?,?,?,?)",
                    (sid, amt, "paid", d.get("note", ""), int(time.time())),
                )
                con.commit()
                return self._json(200, {"ok": True})
            if path == "/api/account/delete":
                auth = self.require()
                if not auth:
                    return
                if auth["role"] == "admin":
                    return self._json(400, {"error": "Admin accounts cannot self-delete here"})
                con.execute("UPDATE users SET email=NULL, phone=NULL, name='Deleted User', password_hash=? WHERE id=?",
                            (hash_password(secrets.token_hex(16)), auth["uid"]))
                con.commit()
                return self._json(200, {"ok": True})
            return self._json(404, {"error": "Unknown API"})
        except Exception as e:
            return self._json(500, {"error": str(e)})
        finally:
            con.close()

    def reg(self, con, role):
        data = self.json_body()
        ip = self.client_address[0]
        if not rate_ok(con, "reg:" + ip, 6, 120):
            return self._json(429, {"error": "Too many registrations"})
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        phone = re.sub(r"\D", "", data.get("phone") or "")
        pw = data.get("password") or ""
        if len(name) < 2 or len(pw) < 8 or len(phone) < 10:
            return self._json(400, {"error": "Name, 10-digit mobile and password (8+) required"})
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return self._json(400, {"error": "Valid email required"})
        if con.execute("SELECT 1 FROM users WHERE email=? OR phone=?", (email, phone)).fetchone():
            return self._json(409, {"error": "Account already exists"})
        con.execute(
            "INSERT INTO users(role,name,email,phone,password_hash,created_at) VALUES(?,?,?,?,?,?)",
            (role, name, email, phone, hash_password(pw), int(time.time())),
        )
        uid = con.execute("SELECT last_insert_rowid() i").fetchone()["i"]
        if role == "seller":
            store = (data.get("store_name") or name + " Store").strip()
            vert = data.get("vertical") if data.get("vertical") in VERTICALS else "product"
            seller_code = "SRJ-S" + secrets.token_hex(3).upper()
            con.execute(
                """INSERT INTO sellers(user_id,store_name,seller_code,address,city,pincode,gstin,pan_last4,kyc_note,
                   bank_name,ifsc,account_last4,status,bio,created_at,vertical,prep_time_min,process_time_hours)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?,?,?,?)""",
                (
                    uid,
                    store,
                    seller_code,
                    data.get("address"),
                    data.get("city"),
                    data.get("pincode"),
                    data.get("gstin"),
                    (data.get("pan") or "")[-4:],
                    data.get("kyc_note"),
                    data.get("bank_name"),
                    data.get("ifsc"),
                    (data.get("account_number") or "")[-4:],
                    data.get("bio"),
                    int(time.time()),
                    vert,
                    int(data.get("prep_time_min") or 30),
                    int(data.get("process_time_hours") or 24),
                ),
            )
        con.commit()
        u = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return self._json(200, self.issue(u))

    def create_product(self, con):
        auth = self.require("seller", "admin")
        if not auth:
            return
        d = self.json_body()
        if auth["role"] == "seller":
            sid = self.seller_id(con, auth)
            st = con.execute("SELECT status FROM sellers WHERE id=?", (sid,)).fetchone()
            if not st or st["status"] != "approved":
                return self._json(403, {"error": "Seller not approved yet"})
        else:
            sid = int(d.get("seller_id") or 0)
        name = (d.get("name") or "").strip()
        try:
            price = float(d.get("price"))
        except Exception:
            return self._json(400, {"error": "Valid price required"})
        if not name or price <= 0:
            return self._json(400, {"error": "Name and price required"})
        mrp = d.get("mrp")
        mrp = float(mrp) if mrp not in (None, "") else None
        stock = int(d.get("stock") or 0)
        images = d.get("images") or []
        if isinstance(images, str):
            images = [images]
        status = "pending"
        if auth["role"] == "admin":
            status = d.get("status") or "published"
        srow = con.execute("SELECT vertical FROM sellers WHERE id=?", (sid,)).fetchone()
        vertical = d.get("vertical") or (srow["vertical"] if srow and srow["vertical"] else "product")
        con.execute(
            """INSERT INTO products(seller_id,name,category_id,subcategory_id,description,price,mrp,stock,sku,size,color,shipping,images,status,created_at,vertical,ingredients,prep_time_min,available)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                sid,
                name,
                d.get("category_id"),
                d.get("subcategory_id"),
                d.get("description"),
                price,
                mrp,
                stock,
                d.get("sku"),
                d.get("size"),
                d.get("color"),
                d.get("shipping"),
                json.dumps(images),
                status,
                int(time.time()),
                vertical,
                d.get("ingredients"),
                d.get("prep_time_min"),
                0 if d.get("available") in (0, False, "0") else 1,
            ),
        )
        con.commit()
        return self._json(200, {"ok": True, "id": con.execute("SELECT last_insert_rowid() i").fetchone()["i"], "status": status})

    INQUIRY_TYPES = {
        "general", "seller", "food_partner", "grocery_partner", "delivery_partner",
        "partnership", "order_support", "payment_support", "refund", "technical", "other",
    }

    def create_inquiry(self, con):
        ip = self.client_address[0]
        if not rate_ok(con, "inq:" + ip, 5, 300):
            return self._json(429, {"error": "Please wait before sending another inquiry"})
        d = self.json_body()
        name = (d.get("name") or "").strip()
        phone = re.sub(r"\D", "", d.get("phone") or "")
        email = (d.get("email") or "").strip().lower()
        msg = (d.get("message") or "").strip()
        typ = d.get("inquiry_type") or "general"
        if typ not in self.INQUIRY_TYPES:
            typ = "other"
        if len(name) < 2 or len(msg) < 10:
            return self._json(400, {"error": "Name and a detailed message are required"})
        if len(phone) < 10 and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return self._json(400, {"error": "Valid mobile or email required"})
        subject = (d.get("subject") or typ.replace("_", " ").title())[:160]
        con.execute(
            """INSERT INTO inquiries(name,phone,email,inquiry_type,subject,order_number,message,attachment,status,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?, 'new', ?, ?)""",
            (
                name, phone or None, email or None, typ, subject,
                (d.get("order_number") or "").strip() or None,
                msg[:4000], d.get("attachment"), int(time.time()), int(time.time()),
            ),
        )
        con.commit()
        return self._json(200, {"ok": True, "message": "Inquiry received. SRJ Choice will review it privately."})

    def create_order(self, con):
        auth = self.require("customer", "admin")
        if not auth:
            return
        d = self.json_body()
        items = d.get("items") or []
        if not items:
            return self._json(400, {"error": "Cart is empty"})
        pay = d.get("payment_method") or "upi"
        if pay not in ("upi", "netbanking", "cod", "wallet"):
            pay = "upi"
        # never accept card PAN/CVV or client-sent prices
        line_rows = []
        subtotal = 0.0
        verts = set()
        max_prep = 0
        process_hours = 24
        for it in items:
            pid = int(it["product_id"])
            qty = int(it.get("qty") or 1)
            if qty < 1 or qty > 99:
                return self._json(400, {"error": "Invalid quantity"})
            p = con.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            if not p or p["status"] != "published":
                return self._json(400, {"error": "Product unavailable"})
            if p["stock"] < qty:
                return self._json(400, {"error": f"Insufficient stock for {p['name']}"})
            if "available" in p.keys() and p["available"] == 0:
                return self._json(400, {"error": f"{p['name']} is unavailable"})
            seller = con.execute("SELECT * FROM sellers WHERE id=?", (p["seller_id"],)).fetchone()
            if not seller or seller["status"] != "approved":
                return self._json(400, {"error": "Seller unavailable"})
            vert = (p["vertical"] if "vertical" in p.keys() and p["vertical"] else None) or seller["vertical"] if "vertical" in seller.keys() else "product"
            vert = vert or "product"
            if vert in ("food", "grocery") and seller["open_status"] not in (None, "open"):
                return self._json(400, {"error": "Restaurant is closed"})
            verts.add(vert)
            price = float(p["price"])
            pct = commission_pct(con, p["category_id"])
            comm = round(price * qty * pct / 100.0, 2)
            seller_amt = round(price * qty - comm, 2)
            subtotal += price * qty
            prep = p["prep_time_min"] if "prep_time_min" in p.keys() and p["prep_time_min"] else (seller["prep_time_min"] if "prep_time_min" in seller.keys() else 30)
            max_prep = max(max_prep, int(prep or 0))
            process_hours = int(seller["process_time_hours"] or 24) if "process_time_hours" in seller.keys() else 24
            line_rows.append((p, qty, price, pct, comm, seller_amt, vert, seller))
        if len(verts) > 1 and ("food" in verts or "grocery" in verts) and "product" in verts:
            return self._json(400, {"error": "Food and physical products must be ordered separately"})
        vertical = next(iter(verts)) if verts else "product"
        fulfillment = d.get("fulfillment") or ("platform" if vertical in ("food", "grocery") else "courier")
        if fulfillment not in ("seller_ship", "platform", "courier", "pickup"):
            fulfillment = "courier"
        def sval(key, default):
            r = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return float(r["value"]) if r else default
        if fulfillment == "pickup":
            delivery_fee = 0.0
        elif vertical == "food":
            delivery_fee = 0.0 if subtotal >= sval("food_free_above", 499) else sval("food_delivery_fee", 39)
        elif vertical == "grocery":
            delivery_fee = 0.0 if subtotal >= sval("grocery_free_above", 399) else sval("grocery_delivery_fee", 29)
        else:
            delivery_fee = 0.0 if subtotal >= sval("product_free_above", 999) else sval("product_delivery_fee", 49)
        discount = 0.0
        tax = 0.0
        total = subtotal + delivery_fee + tax - discount
        eta_min = (max_prep + 25) if vertical in ("food", "grocery") else None
        eta_date = None if eta_min else f"{process_hours}-{process_hours + 48}h"
        public_id = "SRJ-" + secrets.token_hex(4).upper()
        init_status = "new" if vertical in ("food", "grocery") else "placed"
        con.execute(
            """INSERT INTO orders(public_id,customer_id,address_json,payment_method,payment_status,status,subtotal,shipping,total,created_at,vertical,fulfillment,delivery_fee,discount,tax,eta_minutes,eta_date)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                public_id, auth["uid"], json.dumps(d.get("address") or {}), pay,
                "pending" if pay != "cod" else "cod", init_status, subtotal, delivery_fee, total,
                int(time.time()), vertical, fulfillment, delivery_fee, discount, tax, eta_min, eta_date,
            ),
        )
        oid = con.execute("SELECT last_insert_rowid() i").fetchone()["i"]
        for p, qty, price, pct, comm, seller_amt, vert, seller in line_rows:
            con.execute(
                """INSERT INTO order_items(order_id,product_id,seller_id,name,qty,unit_price,commission_pct,commission_amt,seller_amt,status,vertical)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (oid, p["id"], p["seller_id"], p["name"], qty, price, pct, comm, seller_amt, init_status, vert),
            )
            con.execute("UPDATE products SET stock=stock-? WHERE id=?", (qty, p["id"]))
        pickup_addr = line_rows[0][7]["address"] if line_rows else ""
        drop = json.dumps(d.get("address") or {})
        partner = con.execute(
            "SELECT id FROM delivery_partners WHERE active=1 AND kind=? LIMIT 1",
            ("food" if vertical in ("food", "grocery") else "shipping",),
        ).fetchone()
        con.execute(
            """INSERT INTO deliveries(order_id,partner_id,status,pickup_address,drop_address,fee,tracking_code,eta_minutes,assigned_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                oid, partner["id"] if partner else None, "requested", pickup_addr, drop,
                delivery_fee, "TRK-" + secrets.token_hex(4).upper(), eta_min or process_hours * 60,
                int(time.time()), int(time.time()),
            ),
        )
        con.commit()
        return self._json(200, {
            "ok": True, "order_id": public_id, "total": total, "payment_method": pay,
            "delivery_fee": delivery_fee, "commission_note": "calculated on server",
            "vertical": vertical, "eta_minutes": eta_min, "eta_date": eta_date,
        })

    def upload(self, con):
        auth = self.require("seller", "admin")
        if not auth:
            return
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype:
            return self._json(400, {"error": "multipart required"})
        raw = self.body()
        if len(raw) > MAX_UPLOAD + 2048:
            return self._json(400, {"error": "File too large"})
        m = re.search(rb'filename="([^"]+)"', raw)
        name = (m.group(1).decode("utf-8", "ignore") if m else "img.jpg")
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_IMG:
            return self._json(400, {"error": "Images only"})
        idx = raw.find(b"\r\n\r\n")
        if idx < 0:
            return self._json(400, {"error": "Bad upload"})
        data = raw[idx + 4 :]
        end = data.rfind(b"\r\n--")
        if end > 0:
            data = data[:end]
        if len(data) > MAX_UPLOAD:
            return self._json(400, {"error": "File too large"})
        fname = secrets.token_hex(12) + ext
        (UPLOADS / fname).write_bytes(data)
        return self._json(200, {"url": "/uploads/" + fname})

    def api_put(self, path):
        con = db()
        try:
            if path.startswith("/api/seller/products/"):
                return self.update_product(con, int(path.rsplit("/", 1)[-1]))
            if path.startswith("/api/seller/orders/"):
                return self.update_seller_order(con, int(path.rsplit("/", 1)[-1]))
            if path.startswith("/api/admin/sellers/"):
                return self.admin_seller(con, int(path.rsplit("/", 1)[-1]))
            if path.startswith("/api/admin/products/"):
                return self.admin_product(con, int(path.rsplit("/", 1)[-1]))
            if path.startswith("/api/admin/categories/"):
                return self.admin_cat(con, int(path.rsplit("/", 1)[-1]))
            if path.startswith("/api/admin/deliveries/"):
                auth = self.require("admin")
                if not auth:
                    return
                did = int(path.rsplit("/", 1)[-1])
                d = self.json_body()
                fields, args = [], []
                for k in ("status", "partner_id", "tracking_code", "eta_minutes", "proof", "notes"):
                    if k in d:
                        fields.append(f"{k}=?")
                        args.append(d[k])
                if fields:
                    fields.append("updated_at=?")
                    args += [int(time.time()), did]
                    con.execute(f"UPDATE deliveries SET {', '.join(fields)} WHERE id=?", args)
                    con.commit()
                return self._json(200, {"ok": True})
            if path.startswith("/api/admin/inquiries/"):
                auth = self.require("admin")
                if not auth:
                    return
                iid = int(path.rsplit("/", 1)[-1])
                d = self.json_body()
                rec = con.execute("SELECT * FROM inquiries WHERE id=?", (iid,)).fetchone()
                if not rec:
                    return self._json(404, {"error": "Not found"})
                if d.get("delete") or d.get("archive"):
                    con.execute("DELETE FROM inquiries WHERE id=?", (iid,))
                    con.commit()
                    return self._json(200, {"ok": True})
                fields, args = [], []
                if d.get("status") in ("new", "open", "in_progress", "resolved", "closed"):
                    fields.append("status=?")
                    args.append(d["status"])
                if "admin_note" in d:
                    fields.append("admin_note=?")
                    args.append(d["admin_note"])
                if "reply" in d:
                    fields.append("reply=?")
                    args.append(d["reply"])
                if fields:
                    fields.append("updated_at=?")
                    args += [int(time.time()), iid]
                    con.execute(f"UPDATE inquiries SET {', '.join(fields)} WHERE id=?", args)
                    con.commit()
                return self._json(200, {"ok": True})
            if path.startswith("/api/admin/orders/"):
                auth = self.require("admin")
                if not auth:
                    return
                oid = int(path.rsplit("/", 1)[-1])
                d = self.json_body()
                if d.get("status"):
                    con.execute("UPDATE orders SET status=? WHERE id=?", (d["status"], oid))
                con.commit()
                return self._json(200, {"ok": True})
            if path == "/api/admin/settings":
                auth = self.require("admin")
                if not auth:
                    return
                d = self.json_body()
                for key in (
                    "commission_default", "product_delivery_fee", "product_free_above",
                    "food_delivery_fee", "food_free_above", "grocery_delivery_fee", "grocery_free_above",
                    "contact_business_email", "contact_support_email", "contact_seller_email",
                    "contact_address", "contact_hours",
                ):
                    if key in d:
                        con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(d[key])))
                con.commit()
                return self._json(200, {"ok": True})
            if path == "/api/seller/profile":
                auth = self.require("seller")
                if not auth:
                    return
                d = self.json_body()
                con.execute(
                    """UPDATE sellers SET store_name=COALESCE(?,store_name), bio=COALESCE(?,bio),
                       address=COALESCE(?,address), city=COALESCE(?,city),
                       open_status=COALESCE(?,open_status), hours_open=COALESCE(?,hours_open),
                       hours_close=COALESCE(?,hours_close), delivery_enabled=COALESCE(?,delivery_enabled),
                       pickup_enabled=COALESCE(?,pickup_enabled), shipping_method=COALESCE(?,shipping_method),
                       delivery_areas=COALESCE(?,delivery_areas), prep_time_min=COALESCE(?,prep_time_min),
                       process_time_hours=COALESCE(?,process_time_hours)
                       WHERE user_id=?""",
                    (
                        d.get("store_name"), d.get("bio"), d.get("address"), d.get("city"),
                        d.get("open_status"), d.get("hours_open"), d.get("hours_close"),
                        d.get("delivery_enabled"), d.get("pickup_enabled"), d.get("shipping_method"),
                        d.get("delivery_areas"), d.get("prep_time_min"), d.get("process_time_hours"),
                        auth["uid"],
                    ),
                )
                con.commit()
                return self._json(200, {"ok": True})
            if path == "/api/me":
                auth = self.require()
                if not auth:
                    return
                d = self.json_body()
                con.execute(
                    "UPDATE users SET name=COALESCE(?,name) WHERE id=?",
                    (d.get("name"), auth["uid"]),
                )
                con.commit()
                return self._json(200, {"ok": True})
            return self._json(404, {"error": "Unknown"})
        except Exception as e:
            return self._json(500, {"error": str(e)})
        finally:
            con.close()

    def update_product(self, con, pid):
        auth = self.require("seller", "admin")
        if not auth:
            return
        p = con.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if not p:
            return self._json(404, {"error": "Not found"})
        if auth["role"] == "seller" and p["seller_id"] != self.seller_id(con, auth):
            return self._json(403, {"error": "Not your product"})
        d = self.json_body()
        fields = []
        args = []
        for k in ("name", "description", "sku", "size", "color", "shipping"):
            if k in d:
                fields.append(f"{k}=?")
                args.append(d[k])
        for k in ("price", "mrp"):
            if k in d and d[k] not in (None, ""):
                fields.append(f"{k}=?")
                args.append(float(d[k]))
        if "stock" in d:
            fields.append("stock=?")
            args.append(int(d["stock"]))
        if "category_id" in d:
            fields.append("category_id=?")
            args.append(d["category_id"])
        if "subcategory_id" in d:
            fields.append("subcategory_id=?")
            args.append(d["subcategory_id"])
        if "images" in d:
            fields.append("images=?")
            args.append(json.dumps(d["images"]))
        if "available" in d:
            fields.append("available=?")
            args.append(1 if d["available"] in (1, True, "1", "available") else 0)
        if "ingredients" in d:
            fields.append("ingredients=?")
            args.append(d["ingredients"])
        if "prep_time_min" in d:
            fields.append("prep_time_min=?")
            args.append(d["prep_time_min"])
        if auth["role"] == "seller" and any(k in d for k in ("name", "price", "description", "images")):
            fields.append("status=?")
            args.append("pending")
        if not fields:
            return self._json(400, {"error": "No changes"})
        args.append(pid)
        con.execute(f"UPDATE products SET {', '.join(fields)} WHERE id=?", args)
        con.commit()
        return self._json(200, {"ok": True})

    def update_seller_order(self, con, item_id):
        auth = self.require("seller")
        if not auth:
            return
        sid = self.seller_id(con, auth)
        it = con.execute("SELECT * FROM order_items WHERE id=?", (item_id,)).fetchone()
        if not it or it["seller_id"] != sid:
            return self._json(403, {"error": "Not your order"})
        d = self.json_body()
        st = d.get("status")
        vert = it["vertical"] if "vertical" in it.keys() and it["vertical"] else "product"
        allowed = set(FOOD_FLOW if vert in ("food", "grocery") else PRODUCT_FLOW)
        if st not in allowed:
            return self._json(400, {"error": "Invalid status for this order type"})
        con.execute("UPDATE order_items SET status=? WHERE id=?", (st, item_id))
        con.execute("UPDATE orders SET status=? WHERE id=?", (st, it["order_id"]))
        deliv_map = {
            "ready_pickup": "assigned",
            "picked_up": "picked_up",
            "shipped": "in_transit",
            "in_transit": "in_transit",
            "out_for_delivery": "out_for_delivery",
            "delivered": "delivered",
            "cancelled": "cancelled",
            "failed": "failed",
            "returned": "returned",
        }
        if st in deliv_map:
            con.execute(
                "UPDATE deliveries SET status=?, updated_at=? WHERE order_id=?",
                (deliv_map[st], int(time.time()), it["order_id"]),
            )
        con.commit()
        return self._json(200, {"ok": True})

    def admin_seller(self, con, sid):
        auth = self.require("admin")
        if not auth:
            return
        d = self.json_body()
        if d.get("status") in ("pending", "approved", "rejected", "suspended"):
            con.execute("UPDATE sellers SET status=? WHERE id=?", (d["status"], sid))
        con.commit()
        return self._json(200, {"ok": True})

    def admin_product(self, con, pid):
        auth = self.require("admin")
        if not auth:
            return
        d = self.json_body()
        if d.get("status"):
            con.execute("UPDATE products SET status=? WHERE id=?", (d["status"], pid))
        if "featured" in d:
            con.execute("UPDATE products SET featured=? WHERE id=?", (1 if d["featured"] else 0, pid))
        con.commit()
        return self._json(200, {"ok": True})

    def admin_cat(self, con, cid):
        auth = self.require("admin")
        if not auth:
            return
        d = self.json_body()
        if d.get("delete"):
            con.execute("UPDATE categories SET active=0 WHERE id=?", (cid,))
        else:
            if "name" in d:
                con.execute("UPDATE categories SET name=? WHERE id=?", (d["name"], cid))
            if "active" in d:
                con.execute("UPDATE categories SET active=? WHERE id=?", (1 if d["active"] else 0, cid))
            if "commission_pct" in d:
                con.execute("UPDATE categories SET commission_pct=? WHERE id=?", (d["commission_pct"], cid))
        con.commit()
        return self._json(200, {"ok": True})

    def api_delete(self, path):
        con = db()
        try:
            if path.startswith("/api/seller/products/"):
                auth = self.require("seller", "admin")
                if not auth:
                    return
                pid = int(path.rsplit("/", 1)[-1])
                p = con.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
                if not p:
                    return self._json(404, {"error": "Not found"})
                if auth["role"] == "seller" and p["seller_id"] != self.seller_id(con, auth):
                    return self._json(403, {"error": "Not your product"})
                con.execute("UPDATE products SET status='rejected' WHERE id=?", (pid,))
                con.commit()
                return self._json(200, {"ok": True})
            return self._json(404, {"error": "Unknown"})
        finally:
            con.close()


def main():
    seed()
    host = os.environ.get("SRJ_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT") or os.environ.get("SRJ_PORT", "8080"))
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"SRJ Choice marketplace running at http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
