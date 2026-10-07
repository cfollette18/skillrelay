"""Record the real demo workspace. Reviewer actions are scripted and labeled."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapter", choices=["review", "reuse", "versions"], default="review")
    args = parser.parse_args()
    output = ROOT / ".demo/video" / args.chapter
    output.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT / ".demo/workspace/config.json").read_text())
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            record_video_dir=str(output),
            record_video_size={"width": 1440, "height": 1000},
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto("http://127.0.0.1:8765")
        page.locator("#token").fill(config["reviewer_token"])
        page.get_by_role("button", name="Connect", exact=True).click()
        page.locator("#workspace").wait_for(state="visible")
        page.evaluate("""() => {
          const note=document.createElement('div');note.id='recording-note';
          note.style='background:#214136;padding:10px 6vw;color:#b1ffd8;font:14px system-ui';
          note.textContent='Recorded walkthrough · real Hermes evidence'
            +' · scripted reviewer actions';
          document.body.prepend(note);
        }""")
        if args.chapter == "review":
            page.wait_for_timeout(3000)
            page.get_by_role("button", name="Workflow traces", exact=True).click()
            page.wait_for_timeout(4000)
            page.evaluate("window.scrollTo(0, 520)")
            page.wait_for_timeout(4000)
            page.evaluate("window.scrollTo(0, 0)")
            page.get_by_role("button", name="Skills & review", exact=True).click()
            page.get_by_text("Checks, evaluation & exact content", exact=True).first.click()
            page.evaluate("window.scrollTo(0, 540)")
            page.wait_for_timeout(4000)
            page.get_by_role("button", name="approve", exact=True).first.click()
            page.wait_for_timeout(1500)
            assert "active" in page.locator("#content").inner_text()
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(3000)
        elif args.chapter == "reuse":
            page.get_by_role("button", name="Workflow traces", exact=True).click()
            page.wait_for_timeout(5000)
            page.evaluate("window.scrollTo(0, 420)")
            page.wait_for_timeout(4000)
            page.evaluate("window.scrollTo(0, 0)")
            page.get_by_role("button", name="Audit history", exact=True).click()
            page.wait_for_timeout(5000)
        else:
            page.get_by_role("button", name="Version diff", exact=True).first.click()
            page.wait_for_timeout(4000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.get_by_role("button", name="rollback", exact=True).last.click()
            page.wait_for_timeout(2500)
            page.evaluate("window.scrollTo(0, 0)")
            page.get_by_role("button", name="Audit history", exact=True).click()
            page.wait_for_timeout(4000)
        page.screenshot(path=str(output / "console.png"), full_page=True)
        assert not errors, errors
        video = page.video
        await_path = video.path()
        context.close()
        browser.close()
        print(await_path)


if __name__ == "__main__":
    main()
