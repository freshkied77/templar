"""
Notion Delivery Engine.

Converts a generated template JSON into a real Notion database
inside the buyer's workspace.

Flow:
1. Buyer clicks "Deliver to Notion" (they authorize via OAuth once)
2. We create a new page in their workspace
3. We create an inline database with the template structure
4. We add sample data pages to the database
5. We return the page URL to the buyer
"""

import json
import logging
import time
import urllib.error
from typing import Optional

from .notion_oauth import NotionOAuth

log = logging.getLogger("templar.notion_delivery")

# Map our template property types → Notion API property types
PROPERTY_TYPE_MAP = {
    "title": "title",
    "text": "rich_text",
    "rich_text": "rich_text",
    "select": "select",
    "multi_select": "multi_select",
    "number": "number",
    "date": "date",
    "checkbox": "checkbox",
    "person": "people",
    "url": "url",
    "email": "email",
    "phone": "phone_number",
    "formula": "formula",
    "relation": "relation",
    "rollup": "rollup",
}


def _build_notion_property(name: str, prop_def: dict) -> dict:
    """Convert a template property definition into a Notion API property object."""
    notion_type = PROPERTY_TYPE_MAP.get(prop_def.get("type", ""), "rich_text")

    if notion_type == "title":
        return {"title": {"title": []}}

    if notion_type == "rich_text":
        return {"rich_text": {"rich_text": []}}

    if notion_type == "select":
        options = [
            {"name": opt, "color": "default"}
            for opt in prop_def.get("options", [])
        ]
        return {"select": {"select": {"options": options}} if options else {"select": {}}}

    if notion_type == "multi_select":
        options = [
            {"name": opt, "color": "default"}
            for opt in prop_def.get("options", [])
        ]
        return {"multi_select": {"multi_select": {"options": options}} if options else {"multi_select": {}}}

    if notion_type == "number":
        return {
            "number": {
                "number": {
                    "format": _infer_number_format(name)
                }
            }
        }

    if notion_type == "date":
        return {"date": {"date": {}}}

    if notion_type == "checkbox":
        return {"checkbox": {"checkbox": {}}}

    if notion_type == "people":
        return {"people": {"people": []}}

    if notion_type == "url":
        return {"url": {"url": {}}}

    if notion_type == "email":
        return {"email": {"email": {}}}

    if notion_type == "phone_number":
        return {"phone_number": {"phone_number": {}}}

    if notion_type == "formula":
        return {"formula": {"formula": {"expression": ""}}}

    # Fallback for unknown types
    return {"rich_text": {"rich_text": []}}


def _infer_number_format(property_name: str) -> str:
    """Infer the Notion number format from the property name."""
    name_lower = property_name.lower()
    if "price" in name_lower or "cost" in name_lower or "amount" in name_lower:
        return "dollar"
    if "percent" in name_lower or "rate" in name_lower or "conversion" in name_lower:
        return "percent"
    if "hours" in name_lower or "estimate" in name_lower:
        return "number"
    return "number"


def _build_block_content(template: dict) -> list:
    """
    Build Notion block content for the template page.
    These blocks go inside the parent page (before the database).
    """
    blocks = []

    # Header callout
    blocks.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": template.get("tagline", "")}}],
            "icon": {"emoji": "🎯"},
            "color": "blue_background",
        },
    })

    # Description section
    blocks.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "How to Use This Template"}}],
        },
    })

    blocks.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": template.get("seo_description", ""), "link": None}}],
        },
    })

    # Structure overview
    structure = template.get("structure", {})
    views = structure.get("views", [])
    if views:
        blocks.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": "Views: " + ", ".join(views)}}],
            },
        })

    # Properties reference
    properties = structure.get("properties", [])
    if properties:
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Database Properties"}}],
            },
        })
        for prop in properties:
            opts = f" ({', '.join(prop.get('options', []))})" if prop.get("options") else ""
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": f"{prop['name']} ({prop['type']}){opts}"}}],
                },
            })

    return blocks


def _build_sample_page_properties(template: dict, sample_entry: dict) -> dict:
    """Build the properties dict for a sample data page."""
    structure = template.get("structure", {})
    properties = structure.get("properties", [])
    props = {}

    for prop_def in properties:
        name = prop_def["name"]
        value = sample_entry.get(name, "")

        if not value and value != 0:
            continue  # Skip empty values

        prop_type = prop_def.get("type", "")
        notion_type = PROPERTY_TYPE_MAP.get(prop_type, "rich_text")

        if notion_type == "title":
            props[name] = {"title": [{"text": {"content": str(value)}}]}

        elif notion_type == "rich_text":
            props[name] = {"rich_text": [{"text": {"content": str(value)}}]}

        elif notion_type == "select":
            props[name] = {"select": {"name": str(value)}}

        elif notion_type == "multi_select":
            vals = [v.strip() for v in str(value).split(",")]
            props[name] = {"multi_select": [{"name": v} for v in vals if v]}

        elif notion_type == "number":
            try:
                num_val = float(str(value).replace("$", "").replace(",", "").strip())
                props[name] = {"number": num_val}
            except (ValueError, AttributeError):
                props[name] = {"rich_text": [{"text": {"content": str(value)}}]}

        elif notion_type == "date":
            props[name] = {"date": {"start": str(value)}}

        elif notion_type == "checkbox":
            props[name] = {"checkbox": bool(value)}

        elif notion_type == "url":
            props[name] = {"url": str(value)}

        elif notion_type == "email":
            props[name] = {"email": str(value)}

        else:
            props[name] = {"rich_text": [{"text": {"content": str(value)}}]}

    return props


class NotionDelivery:
    """
    Handles delivering a template to the buyer's Notion workspace.

    Usage:
        delivery = NotionDelivery(access_token)
        result = delivery.create_template_database(template)
        print(result["url"])  # The buyer's Notion page URL
    """

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.oauth = NotionOAuth()

    def _notion_post(self, path: str, data: dict, retries: int = 2) -> dict:
        """Make a POST request to the Notion API with retry logic."""
        for attempt in range(retries + 1):
            try:
                return self.oauth.make_notion_request(
                    method="POST",
                    path=path,
                    access_token=self.access_token,
                    json_data=data,
                )
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries:
                    # Rate limited — wait and retry
                    wait = int(e.headers.get("Retry-After", 5))
                    log.warning(f"Notion rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                raise
        raise Exception("Max retries exceeded for Notion API")

    def _notion_get(self, path: str, params: dict = None) -> dict:
        """Make a GET request to the Notion API."""
        return self.oauth.make_notion_request(
            method="GET",
            path=path,
            access_token=self.access_token,
        )

    def create_template_database(self, template: dict, parent_page_id: str = None) -> dict:
        """
        Create a complete Notion template in the buyer's workspace.

        Creates:
        1. A new page (parent) in their workspace
        2. An inline database inside that page with the template structure
        3. Sample data pages inside the database

        Returns: {"page_id", "database_id", "url", "blocks_created"}

        Raises: Exception if Notion API call fails.
        """
        structure = template.get("structure", {})
        properties = structure.get("properties", [])
        sample_data = template.get("sample_data", [])
        cover_concept = template.get("cover_concept", "")
        template_title = template.get("title", "Notion Template")

        # ── Step 1: Create parent page ──────────────────────────────────────
        parent_page_payload = {
            "parent": {"page_id": parent_page_id} if parent_page_id else {"workspace": True},
            "properties": {
                "title": {
                    "title": [{"text": {"content": template_title}}]
                }
            },
            "children": [],
            "icon": {"emoji": "📋"},
        }

        parent_page = self._notion_post("/v1/pages", parent_page_payload)
        parent_id = parent_page["id"]
        log.info(f"Created parent page: {parent_id}")

        # ── Step 2: Create the inline database ─────────────────────────────
        database_properties = {}
        for prop in properties:
            database_properties[prop["name"]] = _build_notion_property(prop["name"], prop)

        # Title property (always needed for database)
        database_properties["Name"] = {"title": {"title": []}}

        database_payload = {
            "parent": {"page_id": parent_id},
            "is_inline": True,
            "title": [{"text": {"content": template_title}}],
            "properties": database_properties,
        }

        # Add cover image concept as description
        if cover_concept:
            database_payload["description"] = [
                {"text": {"content": cover_concept}}
            ]

        database = self._notion_post("/v1/databases", database_payload)
        database_id = database["id"]
        log.info(f"Created database: {database_id}")

        # ── Step 3: Add header blocks to parent page ───────────────────────
        blocks = _build_block_content(template)
        if blocks:
            block_payload = {"children": blocks}
            self._notion_post(f"/v1/blocks/{parent_id}/children", block_payload)
            log.info(f"Added {len(blocks)} blocks to parent page")

        # ── Step 4: Create sample data pages ───────────────────────────────
        pages_created = 0
        for entry in sample_data[:10]:  # Limit to 10 sample entries
            page_props = _build_sample_page_properties(template, entry)
            # Ensure there's always a title
            if "Name" not in page_props and "title" not in page_props:
                page_props["Name"] = {
                    "title": [{"text": {"content": entry.get("Habit") or entry.get("Task") or entry.get("Goal") or "Entry"}}]
                }

            page_payload = {
                "parent": {"database_id": database_id},
                "properties": page_props,
            }

            try:
                self._notion_post("/v1/pages", page_payload)
                pages_created += 1
            except Exception as e:
                log.warning(f"Failed to create sample page: {e}")
                continue

        log.info(f"Created {pages_created} sample data pages")

        # ── Step 5: Return the result ───────────────────────────────────────
        # The database URL is the parent page URL (inline database is inside it)
        page_url = parent_page.get("url", "")

        return {
            "page_id": parent_id,
            "database_id": database_id,
            "url": page_url,
            "blocks_created": len(blocks),
            "sample_pages_created": pages_created,
            "template_title": template_title,
        }

    def get_workspace_pages(self, num_pages: int = 5) -> list:
        """Get the buyer's recent workspace pages to use as parent."""
        try:
            result = self._notion_get("/v1/search", {"filter": {"value": "page", "property": "object"}, "page_size": num_pages})
            return result.get("results", [])
        except Exception:
            return []


def deliver_template(
    access_token: str,
    template: dict,
    buyer_id: str,
    parent_page_id: str = None,
) -> dict:
    """
    Top-level function: deliver a template to a buyer's Notion workspace.

    Args:
        access_token: The buyer's Notion OAuth access token
        template: The generated template JSON
        buyer_id: Local buyer ID (for logging/audit)
        parent_page_id: Optional specific page to create under

    Returns:
        Delivery result dict with page URL, IDs, etc.
    """
    delivery = NotionDelivery(access_token)
    result = delivery.create_template_database(template, parent_page_id)
    result["buyer_id"] = buyer_id
    return result
