"""Read-only MCP server for LeadHunter Pro.

This process is intentionally separate from the Telegram loop. It exposes the
existing lead data and draft generation without allowing database writes,
Telegram sends, shell commands, or arbitrary URL access.
"""

import re
from typing import Any

from mcp.server.fastmcp import FastMCP

from lead_hunter_pro import (
    OWNER_EMAIL,
    PROFILE_TEXT,
    _agent_get_lead_details,
    _agent_get_profile,
    _agent_scan_summary,
    _agent_search_leads,
    generate_application,
)


mcp = FastMCP("leadhunter-readonly")


@mcp.tool()
def search_leads(
    keywords: list[str] | None = None,
    days: int = 30,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Find fresh LeadHunter records matching profile-related keywords."""
    return _agent_search_leads(keywords=keywords, days=days, limit=limit)


@mcp.tool()
def get_lead_details(lead_id: int) -> dict[str, Any] | None:
    """Read one lead by its database ID."""
    return _agent_get_lead_details(lead_id)


@mcp.tool()
def get_scan_summary() -> dict[str, int]:
    """Return current database counts without changing anything."""
    return _agent_scan_summary()


@mcp.tool()
def get_profile() -> dict[str, str]:
    """Return the active profile with the contact line removed."""
    profile = _agent_get_profile().get("profile", PROFILE_TEXT)
    profile = re.sub(r"\n?- Contact:.*$", "", profile, flags=re.I | re.S).strip()
    return {"profile": profile}


@mcp.tool()
def draft_application(lead_id: int) -> dict[str, Any]:
    """Generate a draft for a lead; never sends or stores the draft."""
    lead = _agent_get_lead_details(lead_id)
    if not lead:
        return {"found": False, "message": "Lead not found"}
    draft = generate_application(lead, email=OWNER_EMAIL or None)
    return {
        "found": True,
        "lead_id": lead_id,
        "title": lead.get("title", ""),
        "draft": draft or "Draft was not generated",
        "sent": False,
        "stored": False,
    }


if __name__ == "__main__":
    # Standard MCP stdio transport. The parent client owns this process.
    mcp.run(transport="stdio")
