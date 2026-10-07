from sections import (BALANCE_SHEET, CASH_FLOW, INCOME, html_to_lines, split_sections,
                      statement_parts, strip_page_footers)

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
    assert sections_by_item()["8"]["text"] == "Total net sales | $391,035"


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
                               "Foreign currency rates | $97")


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
    html = '<table><tr><td><span style="font-weight:700">Total</span></td><td>assets</td></tr></table>'
    assert html_to_lines(html.encode()) == ["Total assets"]


def test_no_body_found_returns_nothing():
    toc_only = "<table><tr><td>Item 1.</td><td>Business</td></tr>" \
               "<tr><td>Item 1A.</td><td>Risk Factors</td></tr></table>"
    assert split_sections(toc_only.encode()) == []


def var_block(year, fx, rates):
    """One year of PM's value-at-risk table, laid out as in its 10-K: 3-column
    cells, labels wrapped in <div>, empty spacer cells and rows."""
    cell = '<td colspan="3"><div>{}</div></td>'
    row  = "<tr>" + cell * 8 + "</tr>"
    return (
        '<tr><td colspan="3"></td><td colspan="21"><div>Fair Value Impact</div></td></tr>'
        + row.format("(in millions)", f"At December 31, {year}", "", "Average", "", "High", "", "Low")
        + row.format("Instruments sensitive to:", *[""] * 7)
        + row.format("Foreign currency rates", fx[0], "", fx[1], "", fx[2], "", fx[3])
        + row.format(*[""] * 8)
        + row.format("Interest rates", rates[0], "", rates[1], "", rates[2], "", rates[3]))


def test_value_at_risk_rows_keep_their_column_headers():
    html = ("<table>" + "<tr>" + "<td></td>" * 24 + "</tr>"
            + var_block(2025, ["$97", "$152", "$197", "$97"], ["$135", "$191", "$239", "$135"])
            + var_block(2024, ["$130", "$92", "$130", "$69"], ["$221", "$233", "$272", "$200"])
            + "</table>")
    lines = html_to_lines(html.encode())
    assert "Foreign currency rates | At December 31, 2025: $97 | Average: $152 | High: $197 | Low: $97" in lines
    assert "Interest rates | At December 31, 2025: $135 | Average: $191 | High: $239 | Low: $135" in lines
    # The second block's headers replace the first block's.
    assert "Foreign currency rates | At December 31, 2024: $130 | Average: $92 | High: $130 | Low: $69" in lines


def test_statement_rows_merge_currency_and_negative_cells_under_year_headers():
    html = """<table>
      <tr><td></td><td colspan="6">Year Ended December 31,</td></tr>
      <tr><td></td><td colspan="2">2025</td><td colspan="2">2024</td><td colspan="2">2023</td></tr>
      <tr><td>Revenues</td></tr>
      <tr><td>Total revenues</td><td>$</td><td>94,827</td><td>$</td><td>97,690</td><td>$</td><td>96,773</td></tr>
      <tr><td>Interest expense</td><td>(</td><td>338 )</td><td>(</td><td>350)</td><td>(</td><td>156 )</td></tr>
    </table>"""
    lines = html_to_lines(html.encode())
    assert lines[:3] == ["Year Ended December 31,", "2025 | 2024 | 2023", "Revenues"]
    assert lines[3] == "Total revenues | 2025: $94,827 | 2024: $97,690 | 2023: $96,773"
    assert lines[4] == "Interest expense | 2025: (338) | 2024: (350) | 2023: (156)"


def test_header_dollar_and_percent_columns_stay_separate():
    html = """<table>
      <tr><td>(Dollars in millions)</td><td colspan="2">2025</td><td>$</td><td>%</td></tr>
      <tr><td>Total revenues</td><td>$</td><td>94,827</td><td>$(2,863)</td><td>(3)%</td></tr>
    </table>"""
    assert html_to_lines(html.encode())[1] == \
        "Total revenues | 2025: $94,827 | $: $(2,863) | %: (3)%"


def test_table_without_figures_is_left_as_text():
    html = "<table><tr><td>Name</td><td>Title</td></tr><tr><td>Jane Doe</td><td>Director</td></tr></table>"
    assert html_to_lines(html.encode()) == ["Name Title", "Jane Doe Director"]


ITEM_8 = "\n".join([
    "Index to Consolidated Financial Statements",
    "Consolidated Statements of Operations | Page: 50",
    "Report of Independent Registered Public Accounting Firm",
    "We have audited the accompanying consolidated balance sheets.",
    "CONSOLIDATED STATEMENTS OF OPERATIONS",
    "Total revenues | 2025: 94,827 | 2024: 97,690",
    "See accompanying Notes to Consolidated Financial Statements.",
    "Consolidated Statements of Comprehensive Income",
    "Comprehensive income | 2025: 4,825",
    "Consolidated Balance Sheets",
    "Total assets | 2025: 137,806",
    "Consolidated Statements of Cash Flows",
    "Net cash provided by operating activities | 2025: 14,747",
    "CONSOLIDATED STATEMENTS OF SHAREOWNERS’ EQUITY",
    "Balance at end of year | 2025: 1,000",
    "Notes to Consolidated Financial Statements",
    "Note 1. The consolidated statements of operations include all subsidiaries.",
])


def test_item_8_primary_statements_are_separate_parts():
    parts = statement_parts({"section": "8", "text": ITEM_8})
    assert [kind for kind, _ in parts] == ["", INCOME, "", BALANCE_SHEET, CASH_FLOW, ""]
    assert parts[1][1] == "\n".join(ITEM_8.split("\n")[4:7])
    assert "\n".join(text for _, text in parts) == ITEM_8


def test_index_entries_and_sentences_naming_a_statement_are_not_headings():
    parts = statement_parts({"section": "8", "text": ITEM_8})
    assert parts[0][1].startswith("Index to Consolidated Financial Statements")
    assert parts[0][1].endswith("consolidated balance sheets.")
    assert parts[-1][1].startswith("CONSOLIDATED STATEMENTS OF SHAREOWNERS’ EQUITY")
    assert parts[-1][1].endswith("include all subsidiaries.")


def test_statement_names_used_by_other_filers_are_recognised():
    for heading, kind in [("Consolidated Statements of Earnings", INCOME),
                          ("CONSOLIDATED STATEMENTS OF INCOME", INCOME),
                          ("Consolidated Statements of Financial Position", BALANCE_SHEET),
                          ("Consolidated Statements of Comprehensive Earnings", "")]:
        parts = statement_parts({"section": "8", "text": f"Intro\n{heading}\nRow | 2025: 1"})
        assert [k for k, _ in parts] == (["", kind] if kind else [""])


def test_statement_headings_outside_item_8_are_ignored():
    text = "Consolidated Statements of Operations\nRevenue grew."
    assert statement_parts({"section": "7", "text": text}) == [("", text)]
