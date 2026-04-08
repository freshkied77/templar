"""
SQLite-backed persistent memory for the Templar agent.
Tracks all decisions, listings, sales, category weights, exceptions, and Notion buyer connections.
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent.parent / "data" / "memory.db"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentMemory:
    """
    Persistent SQLite memory store for the autonomous agent.

    Schema:
      decisions        — every agent decision with outcome and revenue
      category_weights— per-category performance (listings, sales, revenue, conversion)
      listings        — all created listings with status and revenue
      exceptions_log  — unresolved exceptions flagged by the system
      notion_buyers   — buyer Notion OAuth connections and delivery status
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS decisions (
                id              TEXT PRIMARY KEY,
                category        TEXT NOT NULL,
                action          TEXT NOT NULL,
                outcome         TEXT NOT NULL,
                revenue         REAL DEFAULT 0.0,
                sales_count     INTEGER DEFAULT 0,
                conversion_rate REAL DEFAULT 0.0,
                created_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS category_weights (
                category        TEXT PRIMARY KEY,
                total_listings  INTEGER DEFAULT 0,
                total_sales     INTEGER DEFAULT 0,
                total_revenue   REAL DEFAULT 0.0,
                conversion_rate REAL DEFAULT 0.0,
                avg_price       REAL DEFAULT 0.0,
                last_updated    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS listings (
                id           TEXT PRIMARY KEY,
                marketplace  TEXT NOT NULL,
                category     TEXT NOT NULL,
                title        TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'active',
                price        REAL DEFAULT 0.0,
                sales_count  INTEGER DEFAULT 0,
                revenue      REAL DEFAULT 0.0,
                listing_id   TEXT,
                url          TEXT,
                created_at   TEXT NOT NULL,
                last_updated TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS exceptions_log (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                description TEXT NOT NULL,
                severity    TEXT NOT NULL DEFAULT 'medium',
                resolved    INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notion_buyers (
                id                      TEXT PRIMARY KEY,
                delivery_token          TEXT UNIQUE NOT NULL,
                marketplace            TEXT NOT NULL,
                listing_id             TEXT,
                template_category      TEXT,
                notion_workspace_id    TEXT,
                notion_workspace_name  TEXT,
                access_token          TEXT NOT NULL,
                refresh_token         TEXT,
                token_expires_at      TEXT,
                delivered_page_url    TEXT,
                delivered_at          TEXT,
                status                TEXT NOT NULL DEFAULT 'authorized',
                connected_at          TEXT NOT NULL
            );
        """)
        conn.commit()

    # ── Decisions ──────────────────────────────────────────────────────────────

    def record_decision(
        self,
        category: str,
        action: str,
        outcome: str,
        revenue: float = 0.0,
        sales_count: int = 0,
        conversion_rate: float = 0.0,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO decisions
               (id, category, action, outcome, revenue, sales_count, conversion_rate, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), category, action, outcome, revenue, sales_count, conversion_rate, _utcnow()),
        )
        conn.commit()

    # ── Sales ─────────────────────────────────────────────────────────────────

    def record_sales(
        self,
        listing_id: str,
        marketplace: str,
        quantity: int,
        revenue: float,
        timestamp: str,
    ) -> None:
        """Record a sale against a listing, updating both listing and category aggregates."""
        conn = self._get_conn()
        now = _utcnow()

        result = conn.execute(
            """UPDATE listings
               SET sales_count = sales_count + ?, revenue = revenue + ?, last_updated = ?
               WHERE listing_id = ? AND marketplace = ?""",
            (quantity, revenue, now, listing_id, marketplace),
        )

        if result.rowcount == 0:
            result = conn.execute(
                """UPDATE listings
                   SET sales_count = sales_count + ?, revenue = revenue + ?, last_updated = ?
                   WHERE marketplace = ? AND listing_id = ?""",
                (quantity, revenue, now, marketplace, listing_id),
            )

        row = conn.execute(
            "SELECT category FROM listings WHERE listing_id = ? AND marketplace = ?",
            (listing_id, marketplace),
        ).fetchone()
        if row:
            category = row["category"]
            conn.execute(
                """UPDATE category_weights
                   SET total_sales = total_sales + ?,
                       total_revenue = total_revenue + ?,
                       last_updated = ?
                   WHERE category = ?""",
                (quantity, revenue, now, category),
            )
        conn.commit()

    # ── Category weights ──────────────────────────────────────────────────────

    def update_category_weight(
        self,
        category: str,
        total_listings: int,
        total_sales: int,
        total_revenue: float,
        conversion_rate: float,
        avg_price: float,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO category_weights
               (category, total_listings, total_sales, total_revenue, conversion_rate, avg_price, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(category) DO UPDATE SET
                   total_listings  = excluded.total_listings,
                   total_sales    = excluded.total_sales,
                   total_revenue  = excluded.total_revenue,
                   conversion_rate= excluded.conversion_rate,
                   avg_price      = excluded.avg_price,
                   last_updated   = excluded.last_updated""",
            (category, total_listings, total_sales, total_revenue, conversion_rate, avg_price, _utcnow()),
        )
        conn.commit()

    def get_category_weights(self) -> dict[str, dict]:
        """Return {category: {total_listings, total_sales, total_revenue, conversion_rate, avg_price}}."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM category_weights").fetchall()
        return {r["category"]: dict(r) for r in rows}

    def get_top_categories(self, limit: int = 3) -> list[str]:
        """Return top categories sorted by conversion_rate desc."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT category FROM category_weights ORDER BY conversion_rate DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [r["category"] for r in rows]

    def get_best_performing_listing(self, category: Optional[str] = None) -> Optional[dict]:
        """Return the listing with the highest revenue."""
        conn = self._get_conn()
        if category:
            row = conn.execute(
                """SELECT * FROM listings
                   WHERE category = ? AND sales_count > 0
                   ORDER BY revenue DESC LIMIT 1""",
                (category,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM listings WHERE sales_count > 0 ORDER BY revenue DESC LIMIT 1",
            ).fetchone()
        return dict(row) if row else None

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_listing_category(self, listing_id: str, marketplace: str) -> Optional[str]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT category FROM listings WHERE listing_id = ? AND marketplace = ?",
            (listing_id, marketplace),
        ).fetchone()
        return row["category"] if row else None

    # ── Listings ─────────────────────────────────────────────────────────────

    def add_listing(
        self,
        marketplace: str,
        category: str,
        title: str,
        listing_id: str,
        status: str = "active",
        price: float = 0.0,
        url: Optional[str] = None,
    ) -> str:
        conn = self._get_conn()
        local_id = str(uuid.uuid4())
        now = _utcnow()
        conn.execute(
            """INSERT INTO listings
               (id, marketplace, category, title, status, price, listing_id, url, created_at, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (local_id, marketplace, category, title, status, price, listing_id, url, now, now),
        )
        conn.execute(
            """INSERT INTO category_weights (category, total_listings, last_updated)
               VALUES (?, 1, ?)
               ON CONFLICT(category) DO UPDATE SET
                   total_listings = total_listings + 1""",
            (category, now),
        )
        conn.commit()
        return local_id

    def remove_listing(self, listing_id: str, marketplace: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE listings SET status = 'delisted', last_updated = ? WHERE listing_id = ? AND marketplace = ?",
            (_utcnow(), listing_id, marketplace),
        )
        conn.commit()

    def get_all_listings(self, status: Optional[str] = None) -> list[dict]:
        conn = self._get_conn()
        if status:
            rows = conn.execute(
                "SELECT * FROM listings WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM listings ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_listings_with_no_sales(self, days_old: int = 30) -> list[dict]:
        """Return listings older than `days_old` with zero sales — candidates for delisting."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM listings
               WHERE sales_count = 0
                 AND status = 'active'
                 AND date(last_updated, '+' || ? || ' days') < date('now')
               ORDER BY last_updated ASC""",
            (days_old,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Exceptions ─────────────────────────────────────────────────────────

    def log_exception(self, title: str, description: str, severity: str = "medium") -> str:
        conn = self._get_conn()
        exc_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO exceptions_log (id, title, description, severity, created_at) VALUES (?, ?, ?, ?, ?)",
            (exc_id, title, description, severity, _utcnow()),
        )
        conn.commit()
        return exc_id

    def get_open_exceptions(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM exceptions_log WHERE resolved = 0 ORDER BY created_at DESC",
        ).fetchall()
        return [dict(r) for r in rows]

    def resolve_exception(self, exc_id: str) -> None:
        conn = self._get_conn()
        conn.execute("UPDATE exceptions_log SET resolved = 1 WHERE id = ?", (exc_id,))
        conn.commit()

    # ── Notion Buyers ────────────────────────────────────────────────────────

    def add_notion_buyer(
        self,
        delivery_token: str,
        marketplace: str,
        access_token: str,
        refresh_token: str = None,
        listing_id: str = None,
        template_category: str = None,
        notion_workspace_id: str = None,
        notion_workspace_name: str = None,
        token_expires_at: str = None,
    ) -> str:
        """
        Record a buyer who has authorized Notion access for template delivery.
        delivery_token is a unique token tied to a specific purchase/delivery event.
        """
        conn = self._get_conn()
        buyer_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO notion_buyers
               (id, delivery_token, marketplace, listing_id, template_category,
                notion_workspace_id, notion_workspace_name, access_token, refresh_token,
                token_expires_at, status, connected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'authorized', ?)""",
            (buyer_id, delivery_token, marketplace, listing_id, template_category,
             notion_workspace_id, notion_workspace_name, access_token, refresh_token,
             token_expires_at, _utcnow()),
        )
        conn.commit()
        return buyer_id

    def get_notion_buyer(self, delivery_token: str) -> Optional[dict]:
        """Look up a buyer by their delivery token."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM notion_buyers WHERE delivery_token = ?",
            (delivery_token,),
        ).fetchone()
        return dict(row) if row else None

    def get_notion_buyer_by_workspace(self, workspace_id: str) -> Optional[dict]:
        """Get buyer's tokens by workspace ID (for re-delivery)."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM notion_buyers WHERE notion_workspace_id = ? AND status = 'authorized'",
            (workspace_id,),
        ).fetchone()
        return dict(row) if row else None

    def mark_notion_delivery_complete(
        self,
        delivery_token: str,
        page_url: str,
        workspace_id: str = None,
        workspace_name: str = None,
    ) -> None:
        """Mark a buyer's template as delivered."""
        conn = self._get_conn()
        conn.execute(
            """UPDATE notion_buyers
               SET delivered_page_url = ?,
                   notion_workspace_id = ?,
                   notion_workspace_name = ?,
                   status = 'delivered',
                   delivered_at = ?
               WHERE delivery_token = ?""",
            (page_url, workspace_id, workspace_name, _utcnow(), delivery_token),
        )
        conn.commit()

    def refresh_notion_token(self, delivery_token: str, new_access_token: str, new_refresh_token: str = None) -> None:
        """Update tokens after a refresh."""
        conn = self._get_conn()
        if new_refresh_token:
            conn.execute(
                """UPDATE notion_buyers
                   SET access_token = ?, refresh_token = ?, token_expires_at = ?
                   WHERE delivery_token = ?""",
                (new_access_token, new_refresh_token, _utcnow(), delivery_token),
            )
        else:
            conn.execute(
                """UPDATE notion_buyers
                   SET access_token = ?, token_expires_at = ?
                   WHERE delivery_token = ?""",
                (new_access_token, _utcnow(), delivery_token),
            )
        conn.commit()

    def get_undelivered_notion_buyers(self) -> list[dict]:
        """Return all authorized-but-not-yet-delivered buyers."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM notion_buyers
               WHERE status = 'authorized' AND delivered_page_url IS NULL
               ORDER BY connected_at DESC""",
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_notion_buyers(self, limit: int = 50) -> list[dict]:
        """Return recent Notion buyers."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM notion_buyers ORDER BY connected_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_notion_delivery_stats(self) -> dict:
        """Return Notion delivery stats."""
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as c FROM notion_buyers").fetchone()["c"]
        delivered = conn.execute(
            "SELECT COUNT(*) as c FROM notion_buyers WHERE status = 'delivered'"
        ).fetchone()["c"]
        pending = conn.execute(
            "SELECT COUNT(*) as c FROM notion_buyers WHERE status = 'authorized' AND delivered_page_url IS NULL"
        ).fetchone()["c"]
        return {"total": total, "delivered": delivered, "pending": pending}

    # ── Stats ───────────────────────────────────────────────────────────────

    def get_total_stats(self) -> dict:
        conn = self._get_conn()
        listings = conn.execute(
            "SELECT COUNT(*) as c, SUM(revenue) as r FROM listings WHERE status = 'active'"
        ).fetchone()
        total_revenue = conn.execute(
            "SELECT SUM(total_revenue) as r FROM category_weights"
        ).fetchone()["r"] or 0.0
        return {
            "active_listings": listings["c"] or 0,
            "total_sales_revenue": total_revenue,
            "open_exceptions": conn.execute(
                "SELECT COUNT(*) as c FROM exceptions_log WHERE resolved = 0"
            ).fetchone()["c"],
        }
