from company_intel.cleaner import CleanPage, build_context, clean_html, detect_block


def test_clean_dom_removes_boilerplate_but_preserves_contact_signals():
    page = clean_html("""<html><head><title>Acme</title><style>badcss</style></head><body>
        <nav>Bad navigation</nav><main><h1>Our team</h1><p>Ada Lovelace</p><p>CEO</p>
        <p>We build developer tools for engineering teams working on complex APIs.</p></main>
        <script>const secret = 'not-evidence@tracking.example';</script><svg>Bad SVG</svg>
        <footer>Bad footer<a href="mailto:sales+hello@acme.com">Email</a>
        <a href="https://linkedin.com/in/ada-lovelace">Profile</a></footer></body></html>""", "https://acme.com/about")
    for bad in ("Bad navigation", "badcss", "Bad SVG", "Bad footer", "<script>", "const secret"):
        assert bad not in page.text
    assert "Ada Lovelace" in page.text
    assert page.emails == ["sales+hello@acme.com"]
    assert page.linkedin_urls == ["https://www.linkedin.com/in/ada-lovelace"]
    assert "mailto:" not in build_context([page], 2000)


def test_context_budget_prioritizes_team_over_marketing():
    pages = [CleanPage("https://acme.com/", "Home", "MARKETING " * 10000),
             CleanPage("https://acme.com/team", "Team", "Ada Lovelace\nCEO\n" + "Research " * 500)]
    context = build_context(pages, 1000)
    assert len(context) <= 3000
    assert context.startswith("PAGE: https://acme.com/team")
    assert "Ada Lovelace" in context


def test_does_not_treat_captcha_script_or_product_copy_as_challenge():
    assert detect_block("<html><title>Product</title><script>captcha()</script><p>Build captcha tools</p></html>", 200) is None
    assert detect_block("<html><title>Just a moment...</title></html>", 200)
    assert detect_block("<p>Hello</p>", 403)


def test_context_deduplicates_repeated_long_boilerplate():
    shared = "This is a long boilerplate paragraph repeated across all of the company's pages."
    pages = [CleanPage(f"https://acme.com/{path}", path, f"{path}\n{shared}") for path in ("team", "about")]
    assert build_context(pages, 4000).count(shared) == 1
