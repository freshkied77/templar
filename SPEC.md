# Templar — AI-Powered Digital Product System

## 1. Concept & Vision

Templar is a fully autonomous digital product generation and sales system. It generates Notion templates, creates listings, manages them across multiple marketplaces, and learns from market feedback — all without human intervention after initial configuration. The operator monitors from a single dashboard and intervenes only when the system surfaces an exception.

**Core philosophy:** Build once, sell forever, monitor always.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    CONTROL LAYER                        │
│              Dashboard + Kill Switch                    │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  AGENT CORE                             │
│         Goal-driven AI orchestrator                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Memory   │ │ Tool     │ │ Loop     │ │ Exception│  │
│  │ Store   │ │ Registry │ │ Manager  │ │ Handler  │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│               GENERATOR MODULES                          │
│  Notion Templates ← + Template Renderer (ZIP delivery)  │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│             MARKETPLACE LAYER                            │
│   Gumroad │ Payhip │ LemonSqueezy │ Etsy (OAuth 1.0a)  │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Components

### 3.1 Agent Core (`src/agent/`)

**Responsibilities:**
- Maintain long-term memory of all generated products, listings, sales, and failures
- Execute the main operational loop (generate → list → monitor → learn → self-correct)
- Surface exceptions that require human attention
- Make decisions based on revenue-weighted category performance

**Main Loop:**
```
every N minutes:
  1. Autodelist stale listings (zero sales after 30 days)
  2. Check marketplace APIs for new sales
  3. Update memory store with revenue data
  4. Decide: generate new product? or wait?
  5. Pick category using exploit/explore (70/30) weighted by revenue
  6. Generate AI-optimized description + Notion template
  7. Build deliverable ZIP package (template JSON + setup guide HTML)
  8. List on configured marketplaces
  9. Flag exceptions
  10. Sleep and repeat
```

**Stop Conditions:**
- Catalog below `MIN_CATALOG_SIZE` (5) → always generate
- Has stale listings → delist first, skip generation
- Top category saturated (>10% conversion) → explore new categories
- 70% exploit top categories / 30% explore uncovered categories

**Exception Types:**
- Listing rejected by marketplace
- Payment received (success, no action needed)
- Price change recommended by marketplace
- Listing suspended
- Anomaly detected (unusual sales spike or drop)
- API outage detected

### 3.2 Generator Modules (`src/generators/`)

**Interface:**
```python
class GeneratorModule(ABC):
    @property
    def name(self) -> str: pass
    @property
    def supported_types(self) -> list[str]: pass
    def generate(self, category: str, description: str) -> dict: pass
```

**Notion Template Generator:**
- Input: Category + description (AI-generated or structured fallback)
- Output: Complete Notion template dict (title, structure, sample_data, seo_description, tags, price_suggested)
- AI Providers: Anthropic Claude Sonnet 4, OpenAI GPT-4o
- Fallback: 6 hand-crafted rule-based templates for core categories

**Notion Delivery (`notion_delivery.py` + `notion_oauth.py`):**
- OAuth 2.0 buyer authorization flow (Notion's standard public integration flow)
- Template is created directly in the buyer's Notion workspace as a database
- Creates: parent page → inline database with all properties → sample data pages
- Handles token refresh automatically
- Delivery URL stored in `notion_buyers` table in memory

**Dashboard pages:**
- `/notion` — Notion buyer management: see connected workspaces, delivery status, re-deliver
- `/api/notion/auth-url` — Generate OAuth URL for a buyer
- `/api/notion/callback` — OAuth callback handler
- `/api/notion/deliver` — Deliver a template to a buyer's workspace
- `/api/notion/buyers` — List all buyers and delivery status


**Template Renderer (`template_renderer.py`):**
- Converts template JSON into a deliverable ZIP containing:
  - `template.json` — Full template schema + step-by-step instructions
  - `setup-guide.html` — Beautiful visual setup guide (open in browser)
  - `README.txt` — Plain text instructions
- This is the actual product file delivered to buyers

### 3.3 Marketplace Layer (`src/marketplaces/`)

**Implemented Adapters:**
- `GumroadMarketplace` — API v2, primary marketplace
- `PayhipMarketplace` — API v1
- `LemonsqueezyMarketplace` — API v1

**Etsy:** Integrated via OAuth 1.0a. Run `python -m src.marketplaces.etsy_auth` once to authorize. Listings are created as drafts and go through Etsy's content moderation before going live.

**Base Interface:**
```python
class BaseMarketplace(ABC):
    name: str
    def authenticate(credentials: dict) -> bool: ...
    def list_product(product_data: dict) -> str: ...  # returns listing_id
    def delist_product(listing_id: str) -> bool: ...
    def get_listing_status(listing_id: str) -> ListingStatus: ...
    def get_sales_data(timeframe: int) -> list[SaleRecord]: ...
```

### 3.4 Memory Store (`src/agent/memory.py`)

SQLite-based persistent memory. Tracks:
- All generated products (concept → output)
- All listings and their status, price, revenue per marketplace
- All sales events with revenue
- Agent decisions and reasoning
- Per-category performance: total_listings, total_sales, total_revenue, conversion_rate, avg_price
- Notion buyer connections: OAuth tokens, workspace info, delivery status
- Exception log

**Key methods:**
- `record_decision()` — log agent decisions with outcome
- `record_sales()` — update listing + category revenue aggregates
- `update_category_weight()` — upsert category performance data
- `get_category_weights()` — return all category performance
- `get_top_categories(limit)` — sorted by conversion_rate DESC
- `get_best_performing_listing(category)` — highest revenue listing
- `get_listings_with_no_sales(days)` — candidates for autodelisting
- `log_exception()` / `get_open_exceptions()` / `resolve_exception()`

### 3.5 Dashboard (`src/dashboard/`)

**Local web app (FastAPI + Jinja2)**

**Pages:**
- `/` — Overview: active listings, total revenue, open exceptions, sales by marketplace/category
- `/listings` — All listings with revenue, status, delist buttons
- `/sales` — Revenue breakdown by marketplace and category
- `/exceptions` — Open exceptions with resolve buttons
- `/generate` — Manual template generation with category + description input

**API Endpoints:**
- `GET /api/stats` — Full performance summary (revenue, listings, exceptions)
- `GET /api/listings` — All listings
- `GET /api/exceptions` — Open exceptions
- `POST /api/exceptions/{id}/resolve` — Mark exception resolved
- `POST /api/listings/{id}/{marketplace}/delist` — Delist a listing
- `POST /api/generate` — Trigger manual template generation
- `GET /api/marketplaces/status` — Test marketplace authentication

### 3.6 Kill Switch

Every listing has a `status` flag in the memory store. The dashboard provides:
- Individual delist button per listing
- Agent auto-delists listings with zero sales after 30 days

---

## 4. Product Data Model

```python
class SaleRecord:
    listing_id: str
    marketplace: str
    quantity: int
    revenue: float
    currency: str
    timestamp: str
    buyer_email: Optional[str]

class ListingRecord:
    id: str                    # local UUID
    marketplace: str
    category: str
    title: str
    status: str                # active, delisted
    price: float
    sales_count: int
    revenue: float
    listing_id: str            # marketplace's ID
    url: Optional[str]
    created_at: str
    last_updated: str
```

---

## 5. Configuration

```env
# AI
ANTHROPIC_API_KEY=sk-...       # Template + description generation
OPENAI_API_KEY=sk-...         # Alternative AI provider
AI_PROVIDER=anthropic          # anthropic or openai

# Marketplaces
GUMROAD_API_KEY=              # Gumroad access token
PAYHIP_API_KEY=               # Payhip Bearer token
LEMONSQUEEZY_API_KEY=         # LemonSqueezy Bearer token
LEMONSQUEEZY_STORE_ID=        # LemonSqueezy store ID

# Operation
LOOP_INTERVAL_SECONDS=300     # Agent loop interval (default 5 min)
DASHBOARD_PORT=5000           # Dashboard port

# Thresholds
MIN_CATALOG_SIZE=5            # Generate if below this
DELIST_AFTER_DAYS=30          # Autodelist if 0 sales after this
SATURATION_THRESHOLD=0.10     # Conv rate above this = explore new cats
```

---

## 6. Technology Stack

| Layer | Technology |
|---|---|
| Agent Core | Python 3 + sqlite3 |
| AI Generation | Anthropic API / OpenAI API |
| Memory | SQLite (synchronous) |
| Marketplace APIs | httpx (sync) |
| Dashboard | FastAPI + Jinja2 + Uvicorn |
| Template Delivery | zipfile (standard library) |

---

## 7. What's Implemented vs. Plan

**Implemented:**
- Autonomous agent loop with exploit/explore strategy
- AI template generation (Anthropic + OpenAI) with rule-based fallback
- AI description generation (wired into orchestrator)
- Template renderer → ZIP package with setup guide HTML
- Multi-marketplace listing (Gumroad, Payhip, LemonSqueezy)
- Revenue tracking per listing, category, marketplace
- Autonomous delisting of stale listings (30-day rule)
- Smart category selection using revenue-weighted conversion rates
- Stop conditions (catalog size, saturation, dead listing detection)
- Exception detection and surfacing
- Dashboard with revenue metrics

**Enabled:**
- Etsy integration via OAuth 1.0a. Authorize once with `python -m src.marketplaces.etsy_auth`. Listings created as draft, go through Etsy's moderation before going live.

**Not Yet Implemented (Future):**
- Spreadsheet Templates generator
- e-book Generator
- WebSocket/SSE for live dashboard updates
- Runtime config reload without restart
- Email capture and follow-up automation
- Price A/B testing (vary price on proven category)

- Etsy OAuth token refresh (tokens expire — check Etsy docs for refresh flow)
- Etsy moderation polling agent (check draft listings and alert when reviewed)
