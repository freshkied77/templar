"""
Template file renderer.
Converts a generated template JSON into deliverable files the buyer actually receives.
Produces: (1) JSON template structure file, (2) setup guide PDF-ready HTML,
(3) ZIP package containing both.
"""

import json
import zipfile
import os
from pathlib import Path
from datetime import datetime


OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "templates"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def render_template_json(template: dict) -> dict:
    """
    Render a complete template JSON file that documents the full Notion structure.
    This is the file the buyer receives — it documents exactly how to build the template.
    """
    return {
        "version": "1.0",
        "generated_at": datetime.utcnow().isoformat(),
        "template": {
            "category": template.get("category", ""),
            "title": template.get("title", ""),
            "tagline": template.get("tagline", ""),
            "price_paid": template.get("price_suggested", 19),
            "cover_concept": template.get("cover_concept", ""),
            "structure": template.get("structure", {}),
            "sample_data": template.get("sample_data", []),
            "seo_description": template.get("seo_description", ""),
            "tags": template.get("tags", []),
        },
        "instructions": _build_instructions(template),
        "database_schema": _build_schema(template),
    }


def _build_instructions(template: dict) -> list[dict]:
    """Build step-by-step instructions for recreating the template in Notion."""
    instructions = [
        {
            "step": 1,
            "title": "Create a new Notion page",
            "description": "Open Notion and click 'New page'. Choose 'Database' as the page type.",
        },
        {
            "step": 2,
            "title": "Set up the database properties",
            "description": "Add the following properties to your database, matching the types below.",
            "properties": template.get("structure", {}).get("properties", []),
        },
        {
            "step": 3,
            "title": "Configure database views",
            "description": f"Create these views: {', '.join(template.get('structure', {}).get('views', []))}. Click '+' at the top right of your database to add views.",
        },
        {
            "step": 4,
            "title": "Add sample data",
            "description": "Add the sample entries below to see how the template is meant to be used.",
            "sample_data": template.get("sample_data", []),
        },
        {
            "step": 5,
            "title": "Apply the cover concept",
            "description": template.get("cover_concept", "Add a cover image that represents your template."),
        },
    ]
    return instructions


def _build_schema(template: dict) -> dict:
    """Build a clear schema reference for each property."""
    schema = {}
    for prop in template.get("structure", {}).get("properties", []):
        schema[prop["name"]] = {
            "type": prop["type"],
            "options": prop.get("options", []),
            "description": _property_description(prop),
        }
    return schema


def _property_description(prop: dict) -> str:
    type_descriptions = {
        "title": "The main title field for each item in the database",
        "text": "Plain text for descriptions or notes",
        "number": "Numeric values (can be formatted as currency, percent, etc.)",
        "select": "Single choice from a predefined list of options",
        "multi_select": "Multiple tags from a predefined list",
        "date": "A specific date with optional time",
        "person": "Notion user (for assignments, ownership)",
        "checkbox": "True/false toggle",
        "url": "Link to an external URL",
        "email": "Email address",
        "phone": "Phone number",
        "formula": "Computed value based on other properties",
        "relation": "Linked entry from another database",
        "rollup": "Summary of related entries",
    }
    base = type_descriptions.get(prop["type"], f"A {prop['type']} property")
    if prop.get("options"):
        base += f". Options: {', '.join(prop['options'])}"
    return base


def render_setup_guide_html(template: dict) -> str:
    """Render a beautiful HTML setup guide the buyer receives."""
    structure = template.get("structure", {})
    views = structure.get("views", [])
    properties = structure.get("properties", [])
    sample_data = template.get("sample_data", [])
    instructions = _build_instructions(template)

    props_html = ""
    for prop in properties:
        opts = f" <em>Options: {', '.join(prop.get('options', []))}</em>" if prop.get("options") else ""
        props_html += f"      <li><strong>{prop['name']}</strong> ({prop['type']}){opts}\n"

    sample_html = ""
    for entry in sample_data:
        items = ", ".join(f"<strong>{k}</strong>: {v}" for k, v in entry.items())
        sample_html += f"      <li>{items}\n"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{template.get('title', 'Your Notion Template')}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #1a1a1a; color: #e0e0e0; line-height: 1.6; padding: 40px 20px; }}
  .container {{ max-width: 720px; margin: 0 auto; }}
  .header {{ text-align: center; margin-bottom: 48px; }}
  .header h1 {{ font-size: 2em; color: #ffffff; margin-bottom: 12px; }}
  .header .tagline {{ color: #a0a0a0; font-size: 1.1em; }}
  .category {{ display: inline-block; background: #7c6af7; color: white;
              padding: 4px 16px; border-radius: 20px; font-size: 0.85em;
              text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 16px; }}
  .cover {{ background: linear-gradient(135deg, #1e1e3f, #2a1a4a);
            border-radius: 12px; padding: 40px; text-align: center;
            margin-bottom: 40px; border: 1px solid #333; }}
  .cover h2 {{ color: #ffffff; font-size: 1.4em; margin-bottom: 8px; }}
  .cover p {{ color: #c0c0c0; }}
  .section {{ background: #222; border-radius: 12px; padding: 28px;
              margin-bottom: 24px; border: 1px solid #333; }}
  .section h3 {{ color: #7c6af7; margin-bottom: 16px; font-size: 1.1em;
                 text-transform: uppercase; letter-spacing: 0.05em; }}
  .step {{ margin-bottom: 20px; }}
  .step-num {{ display: inline-block; background: #7c6af7; color: white;
               width: 28px; height: 28px; border-radius: 50%;
               text-align: center; line-height: 28px; font-size: 0.85em;
               margin-right: 12px; vertical-align: middle; }}
  .step h4 {{ display: inline; color: #ffffff; font-size: 1em; }}
  .step p {{ margin-top: 6px; margin-left: 40px; color: #b0b0b0; }}
  .props-list, .sample-list {{ margin-left: 40px; margin-top: 8px; }}
  .props-list li, .sample-list li {{ margin-bottom: 6px; color: #b0b0b0; }}
  .props-list strong, .sample-list strong {{ color: #e0e0e0; }}
  .views-label {{ color: #7c6af7; font-weight: bold; }}
  .cta {{ text-align: center; background: linear-gradient(135deg, #7c6af7, #5a4ad1);
          border-radius: 12px; padding: 32px; margin-top: 32px; }}
  .cta h3 {{ color: white; margin-bottom: 12px; }}
  .cta p {{ color: rgba(255,255,255,0.8); }}
  .footer {{ text-align: center; margin-top: 40px; color: #666; font-size: 0.85em; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <span class="category">{template.get('category', '')}</span>
    <h1>{template.get('title', '')}</h1>
    <p class="tagline">{template.get('tagline', '')}</p>
  </div>

  <div class="cover">
    <h2>{template.get('cover_concept', 'Premium Notion Template')}</h2>
    <p>Your template is ready. Follow the steps below to set it up in minutes.</p>
  </div>

  <div class="section">
    <h3>What You're Getting</h3>
    <p>{template.get('seo_description', '')}</p>
    <p style="margin-top:12px;">
      Tags: <strong>{', '.join(template.get('tags', []))}</strong>
    </p>
  </div>

  <div class="section">
    <h3>Database Structure</h3>
    <p><span class="views-label">Views included:</span> {', '.join(views)}</p>
    <p style="margin-top: 12px; color: #b0b0b0;">Properties to create:</p>
    <ul class="props-list">
{props_html}
    </ul>
  </div>

  <div class="section">
    <h3>Setup Instructions</h3>
    <div class="step">
      <span class="step-num">1</span>
      <h4>Create a new Notion page</h4>
      <p>Open Notion and click <strong>+ New page</strong>. Choose <strong>Database</strong> as the page type.</p>
    </div>
    <div class="step">
      <span class="step-num">2</span>
      <h4>Name your database</h4>
      <p>Give it a name at the top (e.g., "{template.get('title', 'My Template')}").</p>
    </div>
    <div class="step">
      <span class="step-num">3</span>
      <h4>Add all properties</h4>
      <p>Click <strong>Properties</strong> at the top right. Add each property from the list above.
         Set the type for each one (Title, Select, Number, Date, etc.).</p>
    </div>
    <div class="step">
      <span class="step-num">4</span>
      <h4>Create views</h4>
      <p>At the top right of the database, click <strong>+ Add a view</strong>.
         Create each view: {', '.join(f'<strong>{v}</strong>' for v in views)}.</p>
    </div>
    <div class="step">
      <span class="step-num">5</span>
      <h4>Add sample data</h4>
      <p>Add the sample entries below to see how the template is organized.</p>
      <ul class="sample-list">
{sample_html}
      </ul>
    </div>
    <div class="step">
      <span class="step-num">6</span>
      <h4>Apply your cover</h4>
      <p>{template.get('cover_concept', 'Add a cover image at the top of your page.')}</p>
    </div>
  </div>

  <div class="section">
    <h3>Sample Entries</h3>
    <ul class="sample-list">
{sample_html}
    </ul>
  </div>

  <div class="cta">
    <h3>Need Help?</h3>
    <p>If you have questions about setting up this template, reply to your purchase confirmation email.<br>
    This template was generated by Templar — an autonomous digital product system.</p>
  </div>

  <div class="footer">
    <p>Generated {datetime.utcnow().strftime('%B %d, %Y')} &middot; {template.get('category', '')}</p>
  </div>
</div>
</body>
</html>"""


def build_template_package(template: dict) -> str:
    """
    Build a complete deliverable package as a ZIP file.
    Returns the path to the created ZIP.
    """
    title_slug = (template.get("title", "template")
                  .replace(" — ", "-")
                  .replace(" ", "-")
                  .replace("'", "")
                  .lower()[:50])
    timestamp = datetime.utcnow().strftime("%Y%m%d")
    zip_name = f"{title_slug}-{timestamp}.zip"
    zip_path = OUTPUT_DIR / zip_name

    # Render components
    template_json = render_template_json(template)
    setup_html = render_setup_guide_html(template)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add template JSON
        zf.writestr(
            "template.json",
            json.dumps(template_json, indent=2, ensure_ascii=False),
        )
        # Add setup guide
        zf.writestr(
            "setup-guide.html",
            setup_html,
        )
        # Add README
        readme = f"""{template.get('title', 'Notion Template')}

{template.get('tagline', '')}

CATEGORY: {template.get('category', '')}
PRICE PAID: ${template.get('price_suggested', '?')}

---
WHAT'S INCLUDED:
- template.json: The full template structure and schema
- setup-guide.html: Step-by-step visual setup guide (open in browser)
- README.txt: This file

---
SETUP INSTRUCTIONS:
1. Open setup-guide.html in your browser
2. Follow the 6 steps to recreate the template in Notion
3. The template.json file contains the complete schema for reference

Questions? Reply to your purchase confirmation email.

---
Generated by Templar — Autonomous Digital Product System
"""
        zf.writestr("README.txt", readme)

    return str(zip_path)


def get_template_file_url(template: dict) -> str:
    """
    Get the URL/path for the template package.
    The file is stored locally; in production this would be a CDN URL.
    Returns the local path for now.
    """
    title_slug = (template.get("title", "template")
                  .replace(" — ", "-")
                  .replace(" ", "-")
                  .replace("'", "")
                  .lower()[:50])
    timestamp = datetime.utcnow().strftime("%Y%m%d")
    return str(OUTPUT_DIR / f"{title_slug}-{timestamp}.zip")
