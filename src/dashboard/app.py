"""
Templar monitoring dashboard.
Run with: python -m src.dashboard.app
"""

import os
import sys
import logging
import secrets
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import uvicorn
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("templar.dashboard")

# ── Marketplace registry ──────────────────────────────────────────────────────
from src.marketplaces.gumroad import GumroadMarketplace
from src.marketplaces.payhip import PayhipMarketplace
from src.marketplaces.lemonsqueezy import LemonSqueezyMarketplace
from src.marketplaces.etsy import EtsyMarketplace
from src.generators.notion_template import NotionTemplateGenerator
from src.generators.notion_oauth import NotionOAuth
from src.generators.notion_delivery import NotionDelivery

etsy = EtsyMarketplace()
MARKETPLACES = {
    "gumroad": GumroadMarketplace(),
    "payhip": PayhipMarketplace(),
    "lemonsqueezy": LemonSqueezyMarketplace(),
    "etsy": etsy,
}

GENERATORS = {
    "notion_template": NotionTemplateGenerator(),
}

# ── Shared state ─────────────────────────────────────────────────────────────
memory = AgentMemory()
tracker = SalesTracker(memory)
exception_detector = ExceptionDetector(memory)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Templar Dashboard")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


# ── Pages ─────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def overview(request: Request):
    summary = tracker.get_performance_summary()
    summary["notion_stats"] = memory.get_notion_delivery_stats()
    return templates.TemplateResponse("overview.html", {
        "request": request,
        "summary": summary,
        "page": "overview",
    })


@app.get("/listings", response_class=HTMLResponse)
async def listings_page(request: Request):
    summary = tracker.get_performance_summary()
    return templates.TemplateResponse("listings.html", {
        "request": request,
        "summary": summary,
        "page": "listings",
    })


@app.get("/sales", response_class=HTMLResponse)
async def sales_page(request: Request):
    summary = tracker.get_performance_summary()
    return templates.TemplateResponse("sales.html", {
        "request": request,
        "summary": summary,
        "page": "sales",
    })


@app.get("/exceptions", response_class=HTMLResponse)
async def exceptions_page(request: Request):
    open_exceptions = exception_detector.get_open_exceptions()
    return templates.TemplateResponse("exceptions.html", {
        "request": request,
        "exceptions": open_exceptions,
        "page": "exceptions",
    })


@app.get("/notion", response_class=HTMLResponse)
async def notion_page(request: Request):
    buyers = memory.get_all_notion_buyers()
    stats = memory.get_notion_delivery_stats()
    return templates.TemplateResponse("notion.html", {
        "request": request,
        "buyers": buyers,
        "stats": stats,
        "page": "notion",
    })


@app.get("/generate", response_class=HTMLResponse)
async def generate_page(request: Request):
    return templates.TemplateResponse("generate.html", {
        "request": request,
        "page": "generate",
    })


# ── API endpoints ──────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def api_stats():
    summary = tracker.get_performance_summary()
    summary["notion_stats"] = memory.get_notion_delivery_stats()
    return summary


@app.get("/api/listings")
async def api_listings():
    return memory.get_all_listings()


@app.get("/api/exceptions")
async def api_exceptions():
    return exception_detector.get_open_exceptions()


@app.post("/api/exceptions/{exception_id}/resolve")
async def resolve_exception(exception_id: str):
    exception_detector.resolve(exception_id)
    return {"status": "resolved"}


@app.post("/api/listings/{listing_id}/{marketplace}/delist")
async def delist_listing(listing_id: str, marketplace: str):
    mp = MARKETPLACES.get(marketplace)
    if not mp:
        raise HTTPException(status_code=404, detail="Marketplace not found")
    try:
        success = mp.delist_product(listing_id)
        if success:
            memory.remove_listing(listing_id, marketplace)
            return {"status": "delisted"}
        raise HTTPException(status_code=500, detail="Delist failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate")
async def trigger_generation(category: str, description: str = ""):
    from src.agent.orchestrator import Orchestrator
    orch = Orchestrator(memory=memory, loop_interval=999999)
    orch._init_tools(GENERATORS, MARKETPLACES)

    gen_result = orch.tools.call("generate_template", category=category, description=description)
    if not gen_result.success:
        raise HTTPException(status_code=500, detail=gen_result.error)

    template = gen_result.data
    list_result = orch.tools.call(
        "list_product",
        template=template,
        marketplaces_to_use=["gumroad", "payhip", "lemonsqueezy"],
    )
    return {"template": template, "listings": list_result.data}


@app.get("/api/marketplaces/status")
async def marketplace_status():
    status = {}
    for name, mp in MARKETPLACES.items():
        try:
            authed = mp.authenticate({})
            status[name] = "connected" if authed else "auth_failed"
        except Exception:
            status[name] = "error"
    return status


# ── Notion OAuth endpoints ─────────────────────────────────────────────────────

@app.get("/api/notion/auth-url")
async def get_notion_auth_url(delivery_token: str, return_to: str = ""):
    """
    Generate the Notion OAuth authorization URL for a buyer.
    delivery_token: unique token for this purchase/delivery
    return_to: URL to redirect after successful authorization
    """
    oauth = NotionOAuth()
    if not oauth.client_id:
        raise HTTPException(status_code=500, detail="NOTION_CLIENT_ID not configured")

    state = f"{delivery_token}:{return_to}" if return_to else delivery_token
    auth_url = oauth.get_authorization_url(state)
    return {"auth_url": auth_url, "delivery_token": delivery_token}


@app.get("/api/notion/callback")
async def notion_oauth_callback(code: str = None, error: str = None, state: str = None):
    """
    OAuth callback from Notion.
    Exchanges code for tokens and stores buyer record.
    Then redirects to a success/error page.
    """
    if error:
        return RedirectResponse(url=f"/?notion_auth=error&reason={error}", status_code=302)

    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    # Parse state: delivery_token[:return_to_url]
    delivery_token = state or ""
    return_to = ""
    if ":" in state:
        parts = state.split(":", 1)
        delivery_token = parts[0]
        return_to = parts[1] if len(parts) > 1 else ""

    oauth = NotionOAuth()
    try:
        token_data = oauth.exchange_code(code)
    except Exception as e:
        log.error(f"Notion token exchange failed: {e}")
        return RedirectResponse(url=f"/?notion_auth=error&reason=token_exchange_failed", status_code=302)

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    bot_info = token_data.get("bot_id", "")

    # Get workspace info
    workspace_id = token_data.get("workspace_id", "")
    workspace_name = token_data.get("workspace_name", "")

    # Store buyer record
    memory.add_notion_buyer(
        delivery_token=delivery_token,
        marketplace="notion",
        access_token=access_token,
        refresh_token=refresh_token,
        notion_workspace_id=workspace_id,
        notion_workspace_name=workspace_name,
    )

    log.info(f"Notion buyer authorized: workspace={workspace_name} ({workspace_id})")

    # Redirect back to the return_to URL or dashboard
    if return_to:
        import urllib.parse
        safe_return = urllib.parse.quote(return_to)
        return RedirectResponse(url=f"/?notion_auth=success&workspace={workspace_name}", status_code=302)

    return RedirectResponse(url=f"/?notion_auth=success&workspace={workspace_name}", status_code=302)


@app.post("/api/notion/deliver")
async def deliver_template(delivery_token: str, template_json: dict = None):
    """
    Deliver a template to the buyer's Notion workspace.
    Called after purchase confirmation or from the delivery queue.
    """
    buyer = memory.get_notion_buyer(delivery_token)
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found or Notion not connected")

    if not template_json:
        raise HTTPException(status_code=400, detail="template_json required")

    access_token = buyer["access_token"]

    # Check if token needs refresh
    oauth = NotionOAuth()
    try:
        delivery = NotionDelivery(access_token)
        result = delivery.create_template_database(template_json)
    except Exception as e:
        err_msg = str(e)
        # Check if it's a token expiration error
        if "invalid_token" in err_msg or buyer.get("refresh_token"):
            # Try refreshing
            try:
                new_tokens = oauth.refresh_token(buyer["refresh_token"])
                memory.refresh_notion_token(delivery_token, new_tokens["access_token"], new_tokens.get("refresh_token"))
                delivery = NotionDelivery(new_tokens["access_token"])
                result = delivery.create_template_database(template_json)
            except Exception as refresh_err:
                raise HTTPException(status_code=500, detail=f"Delivery failed: {refresh_err}")
        else:
            raise HTTPException(status_code=500, detail=f"Delivery failed: {err_msg}")

    # Mark as delivered
    memory.mark_notion_delivery_complete(
        delivery_token=delivery_token,
        page_url=result["url"],
        workspace_id=buyer.get("notion_workspace_id"),
        workspace_name=buyer.get("notion_workspace_name"),
    )

    log.info(f"Template delivered to {buyer.get('notion_workspace_name')}: {result['url']}")
    return result


@app.get("/api/notion/buyers")
async def list_notion_buyers():
    """List all Notion buyers and their delivery status."""
    buyers = memory.get_all_notion_buyers()
    stats = memory.get_notion_delivery_stats()
    return {"buyers": buyers, "stats": stats}


@app.get("/api/notion/undelivered")
async def get_undelivered():
    """Get buyers who connected Notion but haven't received their template yet."""
    return memory.get_undelivered_notion_buyers()


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
