"""Autofill application forms with Playwright.

Usage:
    python autofill.py            # takes URL from the clipboard
    python autofill.py <url>

The script fills standard fields, attaches the CV, takes a screenshot and
stops. It never clicks Submit, so you always review the form first.
"""

import hashlib
import json
import re
import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
LETTERS_DIR = os.path.join(HERE, "letters")
APPLIED_PATH = os.path.join(HERE, "applied.json")

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
    "bio": ["about you", "tell your story", "about me", "short bio", "your bio",
            "introduce yourself", "professional summary"],
    "skills": ["skills you want", "your skills", "key skills", "skills", "expertise",
               "technologies"],
}

TAG_KEYS = ("skills",)
SUBMIT_WORDS = ("submit", "send application", "apply now")

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


def url_key(url):
    return hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:16]


def load_applied():
    if not os.path.exists(APPLIED_PATH):
        return {}
    try:
        with open(APPLIED_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def is_applied(url):
    return url_key(url) in load_applied()


def mark_applied(url, title="", note=""):
    data = load_applied()
    data[url_key(url)] = {
        "url": url,
        "title": title,
        "at": time.strftime("%Y-%m-%d %H:%M"),
        "note": note,
    }
    with open(APPLIED_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return len(data)


def cached_letter(url):
    path = os.path.join(LETTERS_DIR, url_key(url) + ".txt")
    if os.path.exists(path):
        text = open(path, encoding="utf-8").read().strip()
        return text or ""
    return ""


def save_letter(url, text):
    if not text:
        return ""
    os.makedirs(LETTERS_DIR, exist_ok=True)
    path = os.path.join(LETTERS_DIR, url_key(url) + ".txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text.strip() + "\n")
    return path


def letter_for(url, profile):
    """Letter for this job: local cache first, VPS over SSH only on a miss."""
    text = cached_letter(url)
    if text:
        return text, "cache"
    text = fetch_letter_ssh(profile, url)
    if text:
        save_letter(url, text)
        return text, "vps"
    text = read_letter(profile)
    return text, "file" if text else "none"


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


def match_field(strong, weak):
    """Match a form field to a profile key.

    The visible label wins over name/placeholder, otherwise a placeholder like
    "skills you want employers to see" matches "company" through "employers".
    """
    for hay in (strong, weak):
        if not hay:
            continue
        for key, words in FIELD_MAP.items():
            if any(re.search(r"\b" + re.escape(w), hay) for w in words):
                return key
    return None


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
            matched = match_field(label_hint, hint)
            # profile fields win over the cover letter: bio often reads "tell us about yourself"
            if matched in ("bio", "skills") and str(profile.get(matched, "") or ""):
                if type_into(page, el, str(profile[matched]), tag_input=matched in TAG_KEYS):
                    filled.append(matched)
                else:
                    skipped.append(matched + " (type failed)")
                continue
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


def open_apply_form(page, url):
    """Open the real application form for the common ATS hosts."""
    note = "as is"
    if "jobs.lever.co" in url and "/apply" not in url:
        try:
            page.goto(url.rstrip("/") + "/apply", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            return "lever /apply"
        except Exception:
            return "lever: apply page failed"
    if not any(h in url for h in ("greenhouse.io", "ashbyhq.com", "workable.com")):
        return note
    if "job-boards.greenhouse.io" in url and "/jobs/" in url and "/apply" not in url:
        page.wait_for_timeout(1200)
    for label in ("Apply for this job", "Apply Now", "Apply now", "Apply"):
        try:
            btn = page.query_selector("a:has-text('%s'), button:has-text('%s')" % (label, label))
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(2500)
                return "clicked: " + label
        except Exception:
            continue
    return note


def type_into(page, el, value, tag_input=False):
    """Fill a field. Tag inputs need one value per Enter, plain fields one shot."""
    if not tag_input:
        el.fill(value)
        return True
    parts = [x.strip() for x in value.split(",") if x.strip()]
    if len(parts) <= 1:
        el.fill(value)
        return True
    try:
        el.click()
        for part in parts:
            el.type(part, delay=12)
            page.wait_for_timeout(70)
            page.keyboard.press("Enter")
            page.wait_for_timeout(70)
        return True
    except Exception:
        try:
            el.fill(value)
        except Exception:
            return False
        return True


def advance_steps(page, limit):
    """Click Continue/Next up to `limit` times. Submit is never clicked."""
    done = []
    for _ in range(max(0, limit)):
        moved = False
        for sel in ("button:has-text('Continue')", "button:has-text('Next')",
                    "a:has-text('Continue')", "button:has-text('Save and continue')"):
            try:
                btns = page.query_selector_all(sel)
            except Exception:
                continue
            for btn in btns:
                try:
                    text = (btn.inner_text() or "").strip().lower()
                    if not btn.is_visible() or any(w in text for w in SUBMIT_WORDS):
                        continue
                    btn.click()
                    page.wait_for_timeout(2200)
                    done.append(text[:24])
                    moved = True
                    break
                except Exception:
                    continue
            if moved:
                break
        if not moved:
            break
    return done


def parse_args(argv):
    url, steps, flags = "", 0, set()
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--steps" and i + 1 < len(argv):
            try:
                steps = int(argv[i + 1])
            except ValueError:
                steps = 0
            i += 2
            continue
        if arg.startswith("--"):
            flags.add(arg[2:])
            i += 1
            continue
        if not url and "://" in arg:
            url = arg.strip()
        i += 1
    return url, steps, flags


def run(url, profile, letter="", headless=None, steps=0, keep_open=None):
    """Fill the form for one job URL. Never clicks Submit."""
    if headless is None:
        headless = os.getenv("AUTOFILL_HEADLESS", "0") == "1"
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=headless,
            args=[] if headless else ["--start-maximized"],
        )
        context = browser.new_context(no_viewport=True)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        form_note = open_apply_form(page, url)

        filled, skipped = fill_inputs(page, profile, letter)
        selects = fill_selects(page, profile)
        added = fill_add_answer(page, profile)
        combos = fill_combos(page, profile)
        # some questions appear only after the previous one is answered
        page.wait_for_timeout(900)
        combos += fill_combos(page, profile)
        radios = fill_radios(page, profile)
        steps_done = advance_steps(page, steps)
        cv = attach_cv(page, profile)

        shot = os.path.join(HERE, "last_fill.png")
        try:
            page.screenshot(path=shot, full_page=True)
        except Exception:
            pass

        print("Form:", form_note)
        print("Filled:", ", ".join(sorted(set(filled))) or "nothing")
        print("Selects:", "; ".join(selects) or "nothing")
        print("Combos:", "; ".join(combos) or "nothing")
        print("Radios:", "; ".join(radios) or "nothing")
        print("Add-answer:", "; ".join(added) or "nothing")
        print("Steps:", "; ".join(steps_done) or "none")
        print("CV:", cv)
        print("Skipped:", "; ".join(skipped[:12]) or "nothing")
        print("Screenshot:", shot)
        print()
        print("Review the form in the browser and submit it yourself.")
        if keep_open is None:
            keep_open = not headless
        if keep_open:
            try:
                page.wait_for_event("close", timeout=1800000)
            except Exception:
                pass
        browser.close()
    return {"filled": filled, "skipped": skipped, "cv": cv, "steps": steps_done,
            "form": form_note, "screenshot": shot}


def main():
    url, steps, flags = parse_args(sys.argv[1:])
    if not url:
        url = get_url()
    if "://" not in url:
        print("No URL found. Copy a job link, then run again.")
        if sys.stdin and sys.stdin.isatty():
            try:
                input("Press Enter to close...")
            except (EOFError, KeyboardInterrupt):
                pass
        return
    profile = load_profile()
    applied = is_applied(url)
    print("URL:", url)
    if applied and "force" not in flags:
        print("Already in applied.json:", load_applied()[url_key(url)])
        print("Run with --force to fill it again.")
        return
    letter, source = letter_for(url, profile)
    print("Letter:", source)
    run(url, profile, letter=letter, steps=steps)
    if "mark" in flags:
        count = mark_applied(url)
        print("Marked applied (%d total)." % count)


if __name__ == "__main__":
    main()
