from sections import html_to_lines, split_sections, strip_page_footers

BODY = "Body text. " * 60  # long enough to read as a section, not a TOC entry

# A minimal 10-K covering the cases seen in real filings: a table of
# contents, headings with and without a space after the period, Item 6
# directly followed by Item 7, a line-start cross-reference, a table,
# a page number, and the hidden inline-XBRL header.
FILING = f"""
<html><body>
<div style="display:none"><ix:header><ix:hidden>HIDDEN XBRL FACT</ix:hidden></ix:header></div>
<table>
  <tr><td>Item 1.</td><td>Business</td><td>1</td></tr>
  <tr><td>Item 1A.</td><td>Risk Factors</td><td>5</td></tr>
  <tr><td>Item 3.</td><td>Legal Proceedings</td><td>9</td></tr>
  <tr><td>Item 6.</td><td>[Reserved]</td><td>10</td></tr>
  <tr><td>Item 7.</td><td>MD&amp;A</td><td>11</td></tr>
  <tr><td>Item 7A.</td><td>Market Risk</td><td>20</td></tr>
  <tr><td>Item 8.</td><td>Financial Statements</td><td>21</td></tr>
  <tr><td>Item 9.</td><td>Changes in Accountants</td><td>40</td></tr>
</table>
<p>Item 1. Business</p><p>{BODY}</p>
<p>Item 1A. Risk Factors</p><p>Risk text.</p>
<p>Item 3.Legal Proceedings</p><p>See Note 12.</p>
<p>Item 6. [Reserved]</p>
<p>Item 7. Management's Discussion and Analysis</p>
<p>Revenue grew.</p>
<p>Item 8, Note 2. Summary of Significant Accounting Policies describes estimates.</p>
<p>42</p>
<p>Item 7A. Quantitative and Qualitative Disclosures About Market Risk</p>
<p>The information called for by this Item is included in Item 7, Market Risk.</p>
<p>Item 8. Financial Statements and Supplementary Data</p>
<table><tr><td>Total net sales</td><td>$</td><td>391,035</td></tr></table>
<p>Item 9. Changes in and Disagreements with Accountants</p><p>None.</p>
</body></html>
"""


def sections_by_item():
    return {s["section"]: s for s in split_sections(FILING.encode())}


def test_finds_kept_items_once():
    assert list(sections_by_item()) == ["1", "1A", "3", "7", "7A", "8"]


def test_table_of_contents_is_skipped():
    business = sections_by_item()["1"]
    assert business["title"] == "Business"
    assert business["text"].startswith("Body text.")


def test_heading_without_space_after_period():
    legal = sections_by_item()["3"]
    assert legal["title"] == "Legal Proceedings"
    assert legal["text"] == "See Note 12."


def test_line_start_cross_reference_stays_in_section():
    mdna = sections_by_item()["7"]
    assert "Item 8, Note 2." in mdna["text"]


def test_section_ends_at_next_heading_including_unkept_items():
    assert sections_by_item()["8"]["text"] == "Total net sales $ 391,035"


def test_pointer_section_is_kept_as_is():
    assert "included in Item 7, Market Risk" in sections_by_item()["7A"]["text"]


def test_hidden_xbrl_and_page_numbers_are_dropped():
    lines = html_to_lines(FILING.encode())
    assert "HIDDEN XBRL FACT" not in " ".join(lines)
    assert "42" not in lines


def test_repeated_page_footers_are_stripped():
    lines = []
    for page in range(1, 7):
        lines += [f"Paragraph on page {page}.", f"Apple Inc. | 2025 Form 10-K | {page}"]
    assert strip_page_footers(lines) == [f"Paragraph on page {p}." for p in range(1, 7)]


def test_repeated_lines_without_footer_shape_are_kept():
    # Table headers repeat across pages but have no "label | page" shape.
    lines = ["2025 2024 2023", "Net sales 100 90 80"] * 6
    assert strip_page_footers(lines) == lines


def test_rare_pipe_lines_are_kept():
    lines = ["Segment | 12", "Other text"]
    assert strip_page_footers(lines) == lines


def pointer_filing(pointer_target, item_7a=None):
    """A filing whose Item 7 has 12pt bold subsections and a 10pt bold table caption."""
    h12 = '<div><span style="font-size:12pt;font-weight:700">{}</span></div>'
    h10 = '<div><span style="font-size:10pt;font-weight:700">{}</span></div>'
    item_7a = item_7a or ("The information called for by this Item is included in "
                          f"Item 7, {pointer_target}.")
    return f"""<html><body>
<p>Item 1. Business</p><p>{BODY}</p>
<p>Item 7. Management's Discussion and Analysis</p>
{h12.format("Liquidity")}<p>Cash is ample.</p>
{h12.format("Market Risk")}
<p>Value at Risk - We use a value at risk computation.</p>
{h10.format("Fair Value Impact")}
<table><tr><td>Foreign currency rates</td><td>$97</td></tr></table>
{h12.format("Cautionary Factors")}<p>Forward-looking statements.</p>
<p>Item 7A. Quantitative and Qualitative Disclosures About Market Risk</p>
<p>{item_7a}</p>
<p>Item 8. Financial Statements</p><p>Statements.</p>
</body></html>""".encode()


def test_7a_pointer_resolves_to_named_item_7_subsection():
    item_7a = {s["section"]: s for s in split_sections(pointer_filing("Market Risk"))}["7A"]
    assert item_7a["content_source"] == "pointer_resolved"
    assert item_7a["resolved_from"] == "Item 7, Market Risk"
    # Runs past the smaller 10pt caption, stops at the next 12pt heading.
    assert item_7a["text"] == ("Value at Risk - We use a value at risk computation.\n"
                               "Fair Value Impact\n"
                               "Foreign currency rates $97")


def test_unresolvable_7a_pointer_is_flagged_and_kept():
    item_7a = {s["section"]: s for s in split_sections(pointer_filing("Interest Rate Risk"))}["7A"]
    assert item_7a["content_source"] == "short_unresolved"
    assert item_7a["resolved_from"] == ""
    assert "included in Item 7, Interest Rate Risk" in item_7a["text"]


def test_7a_with_own_content_is_not_treated_as_pointer():
    own = "We hedge forecasted foreign currency cash flows. " * 20
    item_7a = {s["section"]: s for s in split_sections(pointer_filing("", item_7a=own))}["7A"]
    assert item_7a["content_source"] == "own"
    assert item_7a["text"] == own.strip()


def test_bold_markers_leave_no_extra_whitespace():
    html = '<table><tr><td><span style="font-weight:700">Total</span></td><td>15,777</td></tr></table>'
    assert html_to_lines(html.encode()) == ["Total 15,777"]


def test_no_body_found_returns_nothing():
    toc_only = "<table><tr><td>Item 1.</td><td>Business</td></tr>" \
               "<tr><td>Item 1A.</td><td>Risk Factors</td></tr></table>"
    assert split_sections(toc_only.encode()) == []
