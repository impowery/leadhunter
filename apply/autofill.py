"""Autofill application forms with Playwright.

Usage:
    python autofill.py            # takes URL from the clipboard
    python autofill.py <url>

The script fills standard fields, attaches the CV, takes a screenshot and
stops. It never clicks Submit, so you always review the form first.
"""

import json
import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))

FIELD_MAP = {
    "first_name": ["first name", "firstname", "given name", "first_name"],
    "last_name": ["last name", "lastname", "family name", "surname", "last_name"],
    "full_name": ["full name", "your name", "name"],
    "email": ["email", "e-mail", "mail"],
    "phone": ["phone", "mobile", "telephone", "contact number"],
    "location": ["location", "city", "where are you based", "current location"],
    "country": ["country"],
    "linkedin": ["linkedin"],
    "github": ["github"],
    "website": ["website", "portfolio", "personal site", "url"],
    "company": ["current company", "company", "employer", "organisation", "organization", "org"],
    "salary": ["salary", "compensation", "rate", "expected pay", "desired"],
    "notice": ["notice", "start date", "availability", "when can you start"],
}

COVER_WORDS = ["cover letter", "why do you", "why are you", "message", "additional information",
               "tell us about yourself", "motivation", "comment"]


def get_url():
    if len(sys.argv) > 1:
        return sys.argv[1].strip()
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            capture_output=True, text=True, timeout=10,
        )
        val = (out.stdout or "").strip()
        for token in val.split():
            if token.startswith("http"):
                return token.strip()
    except Exception:
        pass
    return ""


def load_profile():
    with open(os.path.join(HERE, "profile.json"), encoding="utf-8") as f:
        return json.load(f)


def read_letter(profile):
    path = os.path.join(HERE, profile.get("letter_path", "last_letter.txt"))
    if os.path.exists(path):
        text = open(path, encoding="utf-8").read().strip()
        if text:
            return text
    return ""


def fetch_letter_ssh(profile, url):
    """Ask the bot's database for the letter generated for this job URL."""
    import shlex
    import shutil

    key = profile.get("ssh_key") or os.path.expanduser("~/.ssh/vps_opencode")
    host = profile.get("vps") or "root@193.233.19.171"
    ssh_bin = shutil.which("ssh") or r"C:\Windows\System32\OpenSSH\ssh.exe"
    try:
        out = subprocess.run(
            [
                ssh_bin, "-i", key,
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=10",
                host,
                "cd /root/LeadHunter && ./venv/bin/python get_letter.py " + shlex.quote(url),
            ],
            capture_output=True, text=True, timeout=40,
        )
        if out.returncode != 0:
            print("Letter fetch rc=%s: %s" % (out.returncode, (out.stderr or "").strip()[:160]))
            return ""
        return (out.stdout or "").strip()
    except Exception as e:
        print("Letter fetch failed:", str(e)[:200])
        return ""


def describe(el):
    try:
        return " ".join(
            str(x or "") for x in [
                el.get_attribute("name"),
                el.get_attribute("id"),
                el.get_attribute("placeholder"),
                el.get_attribute("aria-label"),
            ]
        ).lower()
    except Exception:
        return ""


def fill_inputs(page, profile, letter):
    filled, skipped = [], []
    fields = page.query_selector_all(
        "input:not([type=hidden]):not([type=file]):not([type=submit]):not([type=checkbox]):not([type=radio]), textarea"
    )
    for el in fields:
        try:
            if not el.is_visible() or not el.is_editable():
                continue
            hint = describe(el)
            label_hint = ""
            try:
                el_id = el.get_attribute("id")
                if el_id:
                    lab = page.query_selector("label[for='" + el_id + "']")
                    if lab:
                        label_hint = (lab.inner_text() or "").lower()
            except Exception:
                pass
            haystack = hint + " " + label_hint
            if not haystack.strip():
                skipped.append("(no label)")
                continue
            kind = el.get_attribute("type") or el.evaluate("e => e.tagName.toLowerCase()")
            if kind == "textarea" or any(w in haystack for w in COVER_WORDS):
                if letter:
                    el.fill(letter[:1800])
                    filled.append("cover letter")
                else:
                    skipped.append("cover letter (no text file)")
                continue
            done = False
            for key, words in FIELD_MAP.items():
                if any(w in haystack for w in words):
                    if key == "country" and "code" in haystack:
                        continue
                    value = str(profile.get(key, "") or "")
                    if not value:
                        skipped.append(key + " (empty in profile)")
                        done = True
                        break
                    el.fill(value)
                    page.wait_for_timeout(120)
                    if "phone" in haystack or "tel" in haystack:
                        filled.append(key)
                        done = True
                        break
                    if (el.input_value() or "").strip() != value.strip():
                        try:
                            el.click()
                            el.press_sequentially(value, delay=25)
                            page.wait_for_timeout(200)
                        except Exception:
                            pass
                    if (el.input_value() or "").strip() == value.strip():
                        filled.append(key)
                    else:
                        skipped.append(key + " (field cleared)")
                    done = True
                    break
            if not done:
                skipped.append(haystack[:40] or "(unknown)")
        except Exception as e:
            skipped.append("error: " + str(e)[:40])
    return filled, skipped


def fill_selects(page, profile):
    done = []
    selects = page.query_selector_all("select")
    for sel in selects:
        try:
            if not sel.is_visible():
                continue
            hint = describe(sel)
            try:
                sel_id = sel.get_attribute("id")
                if sel_id:
                    lab = page.query_selector("label[for='" + sel_id + "']")
                    if lab:
                        hint += " " + (lab.inner_text() or "").lower()
                else:
                    box = sel.evaluate_handle(
                        "e => { const p = e.closest('li, .field, .application-question, div'); "
                        "return p ? p.innerText : '' }"
                    )
                    hint += " " + str(box.json_value() if box else "").lower()[:200]
            except Exception:
                pass
            options = sel.eval_on_selector_all("o => Array.from(o.options).map(o => o.text)")
            options = [o for o in options if o and o.strip()]
            if not options:
                continue

            def pick(want):
                w = str(want or "").strip().lower()
                if not w:
                    return None
                for o in options:
                    if o.strip().lower() == w:
                        return o
                for o in options:
                    if w in o.lower():
                        return o
                return None

            target = None
            if "hub" in hint and "willing" in hint:
                target = pick(profile.get("hub_willing", ""))
            elif "country" in hint:
                target = pick("thailand")
            elif "gender" in hint:
                target = pick(profile.get("gender", ""))
            elif "veteran" in hint:
                target = pick(profile.get("veteran_status", ""))
            elif "race" in hint or "ethnic" in hint:
                target = pick(profile.get("race", ""))
            elif "english" in hint or "language" in hint:
                target = pick(profile.get("english", "fluent"))
            elif "notice" in hint or "start" in hint or "availability" in hint:
                target = pick(profile.get("notice", "immediately")) or pick("immediately")
            elif "time zone" in hint or "timezone" in hint or "eastern time" in hint:
                target = pick(profile.get("timezone_ok", "yes"))
            elif "sponsor" in hint:
                target = pick(profile.get("require_sponsorship", ""))
            elif "authoriz" in hint or "eligible" in hint or "visa" in hint or "right to work" in hint:
                target = pick(profile.get("work_authorization", ""))
            elif "remote" in hint:
                target = pick("yes") or pick("remote")
            if target:
                sel.select_option(label=target)
                done.append(hint[:30] + " -> " + target[:30])
        except Exception:
            pass
    return done


def fill_combos(page, profile):
    """Handle react-select style dropdowns (role=combobox)."""
    done = []
    rules = [
        (("authoriz", "eligible to work", "right to work"), profile.get("work_authorization")),
        (("sponsor",), profile.get("require_sponsorship")),
        (("gender",), profile.get("gender")),
        (("veteran",), profile.get("veteran_status")),
        (("race", "ethnic"), profile.get("race")),
        (("country",), profile.get("country")),
    ]
    for cb in page.query_selector_all("[role=combobox], input[aria-haspopup='listbox']"):
        try:
            if not cb.is_visible():
                continue
            hint = describe(cb)
            try:
                info = cb.evaluate(
                    """e => {
                        const out = [];
                        if (e.id) {
                            const l = document.querySelector('label[for="' + e.id + '"]');
                            if (l) out.push(l.innerText);
                        }
                        const lb = e.getAttribute('aria-labelledby');
                        if (lb) {
                            const n = document.getElementById(lb);
                            if (n) out.push(n.innerText);
                        }
                        if (e.getAttribute('aria-label')) out.push(e.getAttribute('aria-label'));
                        return out.join(' ').toLowerCase();
                    }"""
                )
                hint += " " + str(info or "")
            except Exception:
                pass
            want = None
            for keys, value in rules:
                if any(k in hint for k in keys) and value:
                    want = str(value)
                    break
            if not want:
                continue
            cb.click()
            page.wait_for_timeout(300)
            try:
                cb.press_sequentially(want, delay=40)
            except Exception:
                try:
                    page.keyboard.type(want, delay=40)
                except Exception:
                    pass
            page.wait_for_timeout(500)
            options = page.query_selector_all("[role=option], .select__option")
            target = None
            for opt in options:
                try:
                    if (opt.inner_text() or "").strip().lower() == want.lower():
                        target = opt
                        break
                except Exception:
                    pass
            if not target:
                for opt in options:
                    try:
                        if want.lower() in (opt.inner_text() or "").lower():
                            target = opt
                            break
                    except Exception:
                        pass
            if target:
                target.click()
                page.wait_for_timeout(250)
                done.append(want)
            else:
                try:
                    cb.press("Enter")
                    page.wait_for_timeout(200)
                    done.append(want + " (enter)")
                except Exception:
                    page.keyboard.press("Escape")
        except Exception:
            pass
    return done


def fill_radios(page, profile):
    """Answer yes/no radio groups for authorization and sponsorship."""
    done = []
    rules = [
        (("authoriz", "legally authorized", "eligible to work", "right to work"),
         profile.get("work_authorization")),
        (("sponsor",), profile.get("require_sponsorship")),
    ]
    groups = {}
    for radio in page.query_selector_all("input[type=radio]"):
        try:
            name = radio.get_attribute("name") or ""
            if name:
                groups.setdefault(name, []).append(radio)
        except Exception:
            pass
    for name, radios in groups.items():
        hint = name.lower()
        try:
            rid = radios[0].get_attribute("id")
            if rid:
                lab = page.query_selector("label[for='%s']" % rid)
                if lab:
                    hint += " " + (lab.inner_text() or "").lower()
        except Exception:
            pass
        want = None
        for keys, value in rules:
            if value and any(k in hint for k in keys):
                want = str(value).strip().lower()
                break
        if not want:
            continue
        for radio in radios:
            try:
                text = ""
                rid = radio.get_attribute("id")
                if rid:
                    lab = page.query_selector("label[for='%s']" % rid)
                    if lab:
                        text = (lab.inner_text() or "").strip().lower()
                if not text:
                    text = (radio.get_attribute("value") or "").strip().lower()
                if text == want or text.startswith(want[:3]):
                    radio.check()
                    done.append(hint[:28] + " -> " + text[:8])
                    break
            except Exception:
                pass
    return done


def fill_add_answer(page, profile):
    """Handle Greenhouse questions hidden behind a "+ Add answer" button."""
    done = []
    rules = [
        (("legally authorized", "authorized to work", "eligible to work"),
         profile.get("work_authorization")),
        (("require sponsorship", "require employer sponsorship", "require visa"),
         profile.get("require_sponsorship")),
    ]
    buttons = page.query_selector_all("button:has-text('Add answer'), a:has-text('Add answer')")
    for btn in buttons:
        try:
            if not btn.is_visible():
                continue
            box = btn.evaluate_handle(
                "e => { const p = e.closest('li, .field, .application-question, div'); "
                "return p ? p.innerText : '' }"
            )
            hint = str(box.json_value() or "").lower()
            want = None
            for keys, value in rules:
                if value and any(k in hint for k in keys):
                    want = str(value).strip()
                    break
            if not want:
                continue
            btn.click()
            page.wait_for_timeout(600)
            options = page.query_selector_all("[role=option], .select__option")
            target = None
            for opt in options:
                try:
                    if (opt.inner_text() or "").strip().lower() == want.lower():
                        target = opt
                        break
                except Exception:
                    pass
            if target is None:
                for opt in page.query_selector_all("label, button"):
                    try:
                        if not opt.is_visible():
                            continue
                        if (opt.inner_text() or "").strip().lower() == want.lower():
                            target = opt
                            break
                    except Exception:
                        pass
            if target:
                target.click()
                page.wait_for_timeout(300)
                done.append(hint[:34] + " -> " + want)
        except Exception:
            pass
    return done


def attach_cv(page, profile):
    path = os.path.abspath(os.path.join(HERE, profile.get("cv_path", "")))
    if not os.path.exists(path):
        return "CV file not found: " + path
    inputs = page.query_selector_all("input[type=file]")
    if not inputs:
        return "no file input found"
    try:
        inputs[0].set_input_files(path)
        return "attached " + os.path.basename(path)
    except Exception as e:
        return "attach failed: " + str(e)[:80]


def main():
    url = get_url()
    if not url.startswith("http"):
        print("No URL found. Copy a job link, then run again.")
        input("Press Enter to close...")
        return
    profile = load_profile()
    letter = read_letter(profile)
    if not letter:
        print("Asking the bot for the tailored letter...")
        letter = fetch_letter_ssh(profile, url)
    print("URL:", url)
    print("Letter:", "loaded" if letter else "not found")

    with sync_playwright() as p:
        headless = os.getenv("AUTOFILL_HEADLESS", "0") == "1"
        browser = p.chromium.launch(
            channel="chrome",
            headless=headless,
            args=[] if headless else ["--start-maximized"],
        )
        context = browser.new_context(no_viewport=True)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        if "jobs.lever.co" in url and "/apply" not in url:
            try:
                page.goto(url.rstrip("/") + "/apply", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2500)
            except Exception:
                pass

        filled, skipped = fill_inputs(page, profile, letter)
        selects = fill_selects(page, profile)
        added = fill_add_answer(page, profile)
        combos = fill_combos(page, profile)
        # some questions appear only after the previous one is answered
        page.wait_for_timeout(900)
        combos += fill_combos(page, profile)
        radios = fill_radios(page, profile)
        cv = attach_cv(page, profile)

        shot = os.path.join(HERE, "last_fill.png")
        try:
            page.screenshot(path=shot, full_page=True)
        except Exception:
            pass

        print()
        print("Filled:", ", ".join(sorted(set(filled))) or "nothing")
        print("Selects:", "; ".join(selects) or "nothing")
        print("Combos:", "; ".join(combos) or "nothing")
        print("Radios:", "; ".join(radios) or "nothing")
        print("Add-answer:", "; ".join(added) or "nothing")
        print("CV:", cv)
        print("Skipped:", "; ".join(skipped[:12]) or "nothing")
        print("Screenshot:", shot)
        print()
        print("Review the form in the browser and submit it yourself.")
        print("Close the browser window when you are done.")
        if not headless:
            try:
                page.wait_for_event("close", timeout=1800000)
            except Exception:
                pass
        browser.close()


if __name__ == "__main__":
    main()
