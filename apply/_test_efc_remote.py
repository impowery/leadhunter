import re

import lead_hunter_pro as h

urls = [
    "https://www.efinancialcareers.com/jobs?remote=true",
    "https://www.efinancialcareers.com/jobs-remote",
    "https://www.efinancialcareers.com/jobs?location=remote",
    "https://www.efinancialcareers.com/jobs-remote-united-states",
]
for url in urls:
    try:
        md, status = h._crawl_spa(url)
        md = md or ""
        links = re.findall(r"\[([^\]]{5,90})\]\((https://www\.efinancialcareers\.com/jobs-[^)]+)\)", md)
        remote_links = [t for t, u in links if "remote" in (t + " " + u).lower()]
        print(url, "| status:", status, "| links:", len(links), "| remote:", len(remote_links))
        for t, u in links[:3]:
            print("   ", t[:60], "|", u.split("/")[-1][:60])
    except Exception as e:
        print(url, "ERR", str(e)[:80])
