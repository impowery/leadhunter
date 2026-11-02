import sys

sys.path.insert(0, "/root/LeadHunter")
import lead_hunter_pro as h

for name, fn in [
    ("Remotive", h.parse_remotive),
    ("WorkingNomads", h.parse_workingnomads),
    ("NoDesk", h.parse_nodesk),
]:
    try:
        leads = fn()
        print("==", name, "->", len(leads))
        for lead in leads[:3]:
            print("   ", lead["title"][:60], "|", lead["url"][:60])
    except Exception as e:
        print("==", name, "ERR", str(e)[:100])
