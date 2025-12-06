import json
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def find_samples():
    for sample_dir in sorted(EXAMPLES_DIR.iterdir()):
        if sample_dir.is_dir():
            before = sample_dir / "before.html"
            after = sample_dir / "after.html"
            if before.exists() and after.exists():
                yield sample_dir, before, after


def ensure_metadata(sample_dir: Path):
    metadata_path = sample_dir / "metadata.json"
    if metadata_path.exists():
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    else:
        metadata = {}

    metadata.setdefault("sample_id", sample_dir.name)
    metadata.setdefault("source", "custom_demo_app")
    metadata.setdefault(
        "created_at_utc",
        datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def generate_screenshots():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})

        for sample_dir, before, after in find_samples():
            print(f"Processing {sample_dir.name}...")
            before_png = sample_dir / "before.png"
            after_png = sample_dir / "after.png"

            # BEFORE
            page = context.new_page()
            page.goto(before.resolve().as_uri())
            page.wait_for_timeout(1000)
            page.screenshot(path=str(before_png), full_page=True)
            page.close()

            # AFTER
            page = context.new_page()
            page.goto(after.resolve().as_uri())
            page.wait_for_timeout(1000)
            page.screenshot(path=str(after_png), full_page=True)
            page.close()

            ensure_metadata(sample_dir)

        browser.close()


if __name__ == "__main__":
    generate_screenshots()
    print("Done generating screenshots and metadata.")


#this is from the feature branch
