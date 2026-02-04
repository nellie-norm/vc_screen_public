#!/usr/bin/env python3
"""Bramble Partners - Company Screening Tool with Research"""

import argparse
import sys
import json
import os
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("\n  ERROR: Missing 'anthropic' package")
    print("  Run: pip3 install anthropic\n")
    sys.exit(1)

try:
    import pdfplumber
except ImportError:
    print("\n  ERROR: Missing 'pdfplumber' package")
    print("  Run: pip3 install pdfplumber\n")
    sys.exit(1)

try:
    from openai import OpenAI
except ImportError:
    print("\n  ERROR: Missing 'openai' package (needed for Perplexity)")
    print("  Run: pip3 install openai\n")
    sys.exit(1)

import requests
import base64


# Investment thesis loaded from environment variable (set in Streamlit secrets)
BRAMBLE_THESIS = os.environ.get("BRAMBLE_THESIS", "Investment thesis not configured.")


def extract_pdf_text(pdf_path: str) -> str:
    """Extract text content from a PDF file."""
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(f"[Page {i}]\n{page_text}")
    return "\n\n".join(text_parts)


def extract_company_info(client: anthropic.Anthropic, deck_content: str) -> dict:
    """Use Claude to extract company name and key details from deck."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""Extract the following from this pitch deck. Return JSON only, no other text.

PITCH DECK:
{deck_content[:8000]}

Return this exact JSON format:
{{"company_name": "Name of the company", "industry": "Their industry/sector", "founders": ["Founder 1 name", "Founder 2 name"], "product": "What they sell/do in 5 words"}}"""
        }]
    )

    try:
        # Extract JSON from response
        text = response.content[0].text
        # Handle if Claude wraps it in markdown code blocks
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except:
        return {"company_name": "Unknown Company", "industry": "food tech", "founders": [], "product": "unknown"}


def research_companies_house(company_name: str) -> str:
    """Fetch company data from Companies House API."""

    api_key = os.environ.get("COMPANIES_HOUSE_API_KEY")
    if not api_key:
        key_file = Path(__file__).parent / ".companies_house_key"
        if key_file.exists():
            api_key = key_file.read_text().strip()
            os.environ["COMPANIES_HOUSE_API_KEY"] = api_key

    if not api_key:
        return "Companies House API key not configured - skipping UK registry lookup."

    # Basic auth with API key as username, blank password
    auth = base64.b64encode(f"{api_key}:".encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}

    results = []

    try:
        # Search for company - try with common suffixes for better matching
        search_queries = [
            f"{company_name} Technologies Limited",
            f"{company_name} Technologies Ltd",
            f"{company_name} Technologies",
            f"{company_name} Limited",
            f"{company_name} Ltd",
            company_name
        ]

        search_data = None
        for query in search_queries:
            search_url = f"https://api.company-information.service.gov.uk/search/companies?q={requests.utils.quote(query)}"
            resp = requests.get(search_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Check if first result is a good match (contains the company name)
                if data.get("items") and company_name.lower() in data["items"][0].get("title", "").lower():
                    search_data = data
                    break

        if not search_data:
            # Fallback to original search
            search_url = f"https://api.company-information.service.gov.uk/search/companies?q={requests.utils.quote(company_name)}"
            resp = requests.get(search_url, headers=headers, timeout=10)

            if resp.status_code != 200:
                return f"Companies House search failed (status {resp.status_code})"

            search_data = resp.json()

        if not search_data.get("items"):
            return f"No Companies House record found for '{company_name}'"

        # Take first match
        company = search_data["items"][0]
        company_number = company.get("company_number")
        company_title = company.get("title")

        results.append(f"## COMPANIES HOUSE DATA: {company_title}")
        results.append(f"Company Number: {company_number}")
        results.append(f"Status: {company.get('company_status', 'Unknown')}")
        results.append(f"Incorporated: {company.get('date_of_creation', 'Unknown')}")
        results.append(f"Address: {company.get('address_snippet', 'Unknown')}")
        results.append("")

        # Get officers (directors)
        officers_url = f"https://api.company-information.service.gov.uk/company/{company_number}/officers"
        officers_resp = requests.get(officers_url, headers=headers, timeout=10)

        if officers_resp.status_code == 200:
            officers_data = officers_resp.json()
            results.append("### DIRECTORS & OFFICERS:")
            for officer in officers_data.get("items", [])[:10]:
                name = officer.get("name", "Unknown")
                role = officer.get("officer_role", "")
                appointed = officer.get("appointed_on", "")
                resigned = officer.get("resigned_on", "")
                status = f"(resigned {resigned})" if resigned else "(current)"
                results.append(f"- {name} - {role} - appointed {appointed} {status}")
            results.append("")

        # Get persons with significant control (major shareholders)
        psc_url = f"https://api.company-information.service.gov.uk/company/{company_number}/persons-with-significant-control"
        psc_resp = requests.get(psc_url, headers=headers, timeout=10)

        if psc_resp.status_code == 200:
            psc_data = psc_resp.json()
            results.append("### PERSONS WITH SIGNIFICANT CONTROL (>25% ownership):")
            for psc in psc_data.get("items", [])[:10]:
                name = psc.get("name", psc.get("name_elements", {}).get("surname", "Unknown"))
                nature = ", ".join(psc.get("natures_of_control", []))
                notified = psc.get("notified_on", "")
                results.append(f"- {name}: {nature} (notified {notified})")
            results.append("")

        # Get filing history (look for share allotments = funding rounds)
        filings_url = f"https://api.company-information.service.gov.uk/company/{company_number}/filing-history?items_per_page=50"
        filings_resp = requests.get(filings_url, headers=headers, timeout=10)

        if filings_resp.status_code == 200:
            filings_data = filings_resp.json()
            results.append("### RECENT SHARE ALLOTMENTS (potential funding rounds):")
            allotments = [f for f in filings_data.get("items", [])
                         if "allotment" in f.get("description", "").lower() or
                            "SH01" in f.get("type", "")]

            if allotments:
                for filing in allotments[:10]:
                    date = filing.get("date", "")
                    desc = filing.get("description", "")
                    results.append(f"- {date}: {desc}")
            else:
                results.append("- No share allotments found in recent filings")
            results.append("")

        results.append(f"Source: https://find-and-update.company-information.service.gov.uk/company/{company_number}")

        return "\n".join(results)

    except Exception as e:
        return f"Companies House lookup failed: {e}"


def research_investors(company_name: str, industry: str) -> str:
    """Dedicated Perplexity query for investor/funding information."""

    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        key_file = Path(__file__).parent / ".perplexity_key"
        if key_file.exists():
            api_key = key_file.read_text().strip()

    if not api_key:
        return "Perplexity API key not configured - skipping investor research."

    client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

    investor_prompt = f"""List ALL funding rounds and investors for "{company_name}" (UK {industry} company).

For EACH funding round, provide:
- Round name (Seed, Series A, Series B, etc.)
- Date (month and year)
- Amount raised
- Lead investor(s)
- All participating investors
- Valuation (if known)

Also list:
- Any angel investors by name
- Government grants (Innovate UK, UKRI, etc.)
- Total funding raised to date

Be specific - name every investor mentioned in any source. Cite the source URL for each fact."""

    try:
        response = client.chat.completions.create(
            model="sonar-pro",
            messages=[{"role": "user", "content": investor_prompt}]
        )
        content = response.choices[0].message.content

        # Extract citations
        try:
            raw = response.model_dump()
            if 'citations' in raw and raw['citations']:
                content += "\n\nSOURCES:\n"
                for i, url in enumerate(raw['citations'], 1):
                    content += f"[{i}] {url}\n"
        except:
            pass

        return content
    except Exception as e:
        return f"Investor research failed: {e}"


def research_with_perplexity(company_info: dict) -> str:
    """Conduct deep research using Perplexity API."""

    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        # Try to read from file
        key_file = Path(__file__).parent / ".perplexity_key"
        if key_file.exists():
            api_key = key_file.read_text().strip()
            os.environ["PERPLEXITY_API_KEY"] = api_key

    if not api_key:
        print("\n  WARNING: No Perplexity API key found.")
        print("  Set PERPLEXITY_API_KEY environment variable or create .perplexity_key file")
        print("  Continuing without research...\n")
        return "No research available - Perplexity API key not configured."

    company = company_info.get("company_name", "Unknown")
    industry = company_info.get("industry", "food tech")
    founders = company_info.get("founders", [])
    product = company_info.get("product", "")

    founder_str = ", ".join(founders[:3]) if founders else "the founders"

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.perplexity.ai"
    )

    research_prompt = f"""Research the company "{company}" in the {industry} sector for a venture capital investment screening.

Provide comprehensive, factual information on:

1. **Company Overview**: What does {company} do? When founded? HQ location? Business model (B2B/B2C/marketplace)?

2. **Funding History & Investors** (search Crunchbase, PitchBook, tech news):
   - Search "site:crunchbase.com {company}" for funding data
   - All known funding rounds - dates, amounts, valuations
   - WHO invested in each round (lead investors and participants)
   - Name specific investors (VCs, angels, strategic investors)
   - Any Innovate UK grants, SEIS/EIS raises, or government funding
   - If funding details aren't found, explicitly state "No funding round details found on Crunchbase or similar sources"

3. **Traction & Metrics**: Revenue, growth rate, customers, partnerships, or any public performance data.

4. **Founders & Team - SEARCH THOROUGHLY**:
   - Search LinkedIn, Crunchbase, and news for each founder: {founder_str}
   - For each person find: previous companies, exits, education, notable achievements
   - Search "[founder name] LinkedIn" and "[founder name] Crunchbase" specifically
   - Any red flags (lawsuits, failed ventures, controversies)?
   - If you cannot find information on a founder, explicitly state "No independent information found for [name]"

5. **Competitive Landscape**: Who are the 3-5 closest competitors? How do they compare on funding, scale, approach? What's {company}'s differentiation?

6. **Market Size**: TAM/SAM/SOM for {industry}. Growth projections. Key market drivers and headwinds.

7. **Red Flags & Concerns**: Any negative press, regulatory issues, customer complaints, Glassdoor reviews, or reasons for concern?

8. **Recent News**: Latest developments in the past 6-12 months.

Be specific with numbers, dates, and sources where possible. If information is not available, say so explicitly rather than guessing.

IMPORTANT: For each fact you provide, cite the specific source URL where you found it. Use inline citations like [1], [2] etc. and list all URLs at the end. Only cite URLs that actually contain the specific information - don't cite a company homepage for market data."""

    try:
        response = client.chat.completions.create(
            model="sonar-pro",
            messages=[{"role": "user", "content": research_prompt}]
        )
        content = response.choices[0].message.content

        # Extract citations from Perplexity response
        citations = []

        # Perplexity returns citations at top level of response
        try:
            raw = response.model_dump()
            if 'citations' in raw and raw['citations']:
                citations = raw['citations']
        except:
            pass

        # Fallback checks
        if not citations:
            if hasattr(response, 'citations') and response.citations:
                citations = list(response.citations)

        # Append citations prominently so Claude uses them
        if citations:
            content += "\n\n" + "="*60 + "\n"
            content += "IMPORTANT: USE THESE VERIFIED SOURCE URLs FOR CITATIONS\n"
            content += "="*60 + "\n"
            for i, cite in enumerate(citations, 1):
                if isinstance(cite, str):
                    content += f"[{i}] {cite}\n"
                elif isinstance(cite, dict):
                    url = cite.get('url', cite.get('link', str(cite)))
                    content += f"[{i}] {url}\n"
            content += "="*60 + "\n"
            content += "When citing facts, use format: [claim](URL from list above)\n"
            content += "DO NOT use dogtooth.tech for third-party claims like funding.\n"
            content += "="*60 + "\n"
        else:
            content += "\n\n## SOURCES\nNo structured citations returned - verify claims independently.\n"

        return content
    except Exception as e:
        print(f"\n  WARNING: Perplexity research failed: {e}")
        return f"Research failed: {e}"


def analyze_company(deck_content: str, research_text: str, additional_notes: str = "") -> str:
    """Multi-agent debate: Bull analyst, Bear analyst, then IC Chair synthesizes."""

    client = anthropic.Anthropic()

    notes_section = ""
    if additional_notes:
        notes_section = f"\n\nADDITIONAL NOTES FROM MEETING:\n{additional_notes}"

    # Shared context for all analysts
    shared_context = f"""{BRAMBLE_THESIS}

===== SOURCE 1: PITCH DECK (cite as "per deck") =====
{deck_content}

===== SOURCE 2: EXTERNAL RESEARCH (cite with URLs) =====
{research_text}
{notes_section}

CITATION RULES:
- Deck content → cite as "(per deck)"
- External research → cite as [text](url) using ONLY URLs from the SOURCES list
- No URL available → mark as "(unverified)"
- NEVER invent URLs"""

    # ========== BULL ANALYST ==========
    bull_prompt = f"""You are a BULL ANALYST at Bramble Partners. Your job is to make the STRONGEST POSSIBLE CASE for investing in this company.

You are an advocate, not a judge. Find every reason to say yes. Be persuasive but grounded in facts.

{shared_context}

Write a compelling investment case covering:

1. **THE OPPORTUNITY** - Why this company matters for the food system. What's the big insight?

2. **MARKET POTENTIAL** - Why the market is attractive. Size, growth, tailwinds.

3. **COMPETITIVE ADVANTAGE** - Why this team wins. What's their moat?

4. **THE BULL CASE** - 4-5 specific reasons this could be a fund-returner. Be specific and bold.

5. **TEAM STRENGTHS** - Why this team can execute. Relevant experience, credentials.

6. **BRAMBLE FIT** - Why this aligns with our thesis and values.

7. **TRACTION SIGNALS** - Evidence that this is working.

Write in British English. Be assertive and confident. Bold **key points**.
Your goal: Make the IC want to pursue this deal."""

    print("    [1/3] Bull analyst building investment case...")
    bull_response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{"role": "user", "content": bull_prompt}]
    )
    bull_case = bull_response.content[0].text

    # ========== BEAR ANALYST ==========
    bear_prompt = f"""You are a BEAR ANALYST at Bramble Partners. Your job is to make the STRONGEST POSSIBLE CASE for PASSING on this company.

You are a skeptic and devil's advocate. Find every reason to say no. Poke holes. Be adversarial but fair.

Your reputation depends on protecting the fund from bad deals. Most deals should be passed on.

{shared_context}

Write a rigorous critique covering:

1. **RED FLAGS** - What's concerning about this company? What claims are unverified or suspicious?

2. **MARKET RISKS** - Why the market may be smaller, slower, or more competitive than claimed.

3. **COMPETITIVE THREATS** - Who could crush them? Why might they lose?

4. **THE BEAR CASE** - 4-5 specific reasons to pass. Be specific about what could go wrong.

5. **TEAM CONCERNS** - Gaps in experience, missing roles, any yellow flags in backgrounds.

6. **EXECUTION RISKS** - What has to go right for this to work? What's fragile?

7. **VALUATION/TERMS CONCERNS** - Are they asking too much? Is the round structure problematic?

Write in British English. Be assertive and direct. Bold **key concerns**.
Your goal: Make the IC think twice before pursuing this deal."""

    print("    [2/3] Bear analyst stress-testing the opportunity...")
    bear_response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{"role": "user", "content": bear_prompt}]
    )
    bear_case = bear_response.content[0].text

    # ========== IC CHAIR (SYNTHESIS) ==========
    synthesis_prompt = f"""You are the IC CHAIR at Bramble Partners, writing the final investment screening memo.

You have received arguments from two analysts:
- The BULL ANALYST argued for investing
- The BEAR ANALYST argued for passing

Your job: Weigh both sides fairly, identify the key debates, and make a clear recommendation.

===== BULL ANALYST'S CASE =====
{bull_case}

===== BEAR ANALYST'S CASE =====
{bear_case}

===== ORIGINAL SOURCES =====
{shared_context}

===== YOUR TASK =====

FIRST, write a DELIBERATION section where you think through the decision:
- Which bull arguments are most compelling and why?
- Which bear arguments are most concerning and why?
- Where is the bull analyst overreaching or being too optimistic?
- Where is the bear analyst being too harsh or missing the point?
- What's the crux of this decision?
- How do you weigh the risk/reward?

THEN, write the final formatted memo.

Your output MUST follow this structure:

===== DELIBERATION =====
[Your thinking process here - be candid about how you're weighing the arguments]

===== MEMO =====
[The formatted memo follows]

LANGUAGE:
- British English (organisation, analyse, colour, labour, etc.)
- Use £ for currency

WRITING STYLE:
- Sophisticated, confident, direct
- Short punchy paragraphs (2-3 sentences max)
- Bold **key terms** and **critical findings**
- No hedge words - be assertive
- Use "we" when referring to Bramble

After ===== MEMO =====, write the memo in this EXACT format:

---

# [COMPANY NAME]
## Investment Screening Memo

---

### THE OPPORTUNITY

One compelling paragraph: What does this company do and why does it matter for the food system? Bold the **key insight**.

---

### SNAPSHOT

**Company:** [Name]
**Stage:** [Series A/B/C]
**Raising:** [Amount if known]
**Business Model:** [One line]
**Traction:** [Key metric]

---

### THE MARKET

Two short paragraphs maximum. Bold **market size** and **key growth drivers**. Note if market size claims are unverified.

---

### COMPETITIVE POSITION

Who else is in this space? One paragraph on the landscape, then:

**Why [Company] wins:** [Their differentiation in one sentence]

**Why competitors might win:** [Counter-argument in one sentence]

---

### THE TEAM

List each key person on their own line with a blank line between them. Bold their **relevant credentials**. Explicitly flag gaps or concerns.

Format:
**[Name]** ([Role]) - [Background and credentials]

**[Name]** ([Role]) - [Background and credentials]

**Gaps:** [Any missing roles or concerns]

---

### EXISTING INVESTORS

List ALL known investors. Include:
- Lead investors for each round
- All participating VCs and funds
- Angel investors by name
- Government grants (Innovate UK, UKRI, etc.)
- Total funding raised

Cite each fact with the source URL. If investor information is sparse, state what's missing.

---

### BRAMBLE FIT

| Criterion | Rating | Assessment |
|-----------|--------|------------|
| Food System Impact | Strong/Moderate/Weak | [One line why] |
| Stage Fit | Strong/Moderate/Weak | [One line why] |
| Value Chain Position | Strong/Moderate/Weak | [One line why] |
| Values Alignment | Strong/Moderate/Weak | [One line why] |

**Overall Fit:** [STRONG / MODERATE / WEAK]

---

### THE BULL CASE

Summarise the bull analyst's strongest 3-4 arguments:
- **[Driver 1]** - Why this matters and what it could mean
- **[Driver 2]** - Why this matters and what it could mean
- **[Driver 3]** - Why this matters and what it could mean

---

### THE BEAR CASE

Summarise the bear analyst's strongest 3-4 arguments:
- **[Concern 1]** - Why this is worrying and what could go wrong
- **[Concern 2]** - Why this is worrying and what could go wrong
- **[Concern 3]** - Why this is worrying and what could go wrong

---

### KEY DEBATES

Where do bull and bear fundamentally disagree? Frame as questions DD must answer.

1. **[Question]:** Bull view vs Bear view
2. **[Question]:** Bull view vs Bear view
3. **[Question]:** Bull view vs Bear view

---

### RECOMMENDATION

# [PURSUE] / [PASS] / [MONITOR]

**Confidence:** [HIGH / MEDIUM / LOW]

Two sentences explaining the call. Which side of the key debates are you landing on and why?

---

### PROPOSED TERMS
*(Only if PURSUE - otherwise delete this section entirely)*

**Ticket Size:** £[X-Y]
**Ticket Rationale:** [One sentence - portfolio fit, ownership target, round dynamics]
**Valuation View:** [One sentence]
**Key Terms:** [What we'd negotiate for]
**Syndicate:** [Ideal co-investors]

---

### RISKS & GAPS

**Critical Risks:**
1. **[Risk]:** [Why it matters]
2. **[Risk]:** [Why it matters]
3. **[Risk]:** [Why it matters]

**Information Gaps:** What we don't know yet that could change the verdict.

---

### DUE DILIGENCE PRIORITIES

If we proceed, answer these first (directly address the key debates):
1. [Question]
2. [Question]
3. [Question]

---

### BOTTOM LINE

One final confident paragraph. Acknowledge the tension between bull and bear, then make the call. End with a clear action.

---
"""

    print("    [3/3] IC Chair synthesising and making recommendation...")
    synthesis_response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=7000,
        messages=[{"role": "user", "content": synthesis_prompt}]
    )

    full_response = synthesis_response.content[0].text

    # Parse out deliberation and memo sections
    deliberation = ""
    memo = full_response

    if "===== DELIBERATION =====" in full_response and "===== MEMO =====" in full_response:
        parts = full_response.split("===== MEMO =====")
        deliberation_part = parts[0]
        memo = parts[1].strip() if len(parts) > 1 else full_response

        # Extract just the deliberation content
        if "===== DELIBERATION =====" in deliberation_part:
            deliberation = deliberation_part.split("===== DELIBERATION =====")[1].strip()

    return {
        'memo': memo,
        'bull_case': bull_case,
        'bear_case': bear_case,
        'deliberation': deliberation
    }


def main():
    parser = argparse.ArgumentParser(description="Bramble Company Screener")
    parser.add_argument("pdf", help="Path to the company pitch deck (PDF)")
    parser.add_argument("--notes", "-n", default="", help="Additional notes from meeting")
    parser.add_argument("--output", "-o", help="Save output to file")
    parser.add_argument("--no-research", action="store_true", help="Skip web research")

    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"\n  ERROR: File not found: {args.pdf}\n")
        sys.exit(1)

    if pdf_path.suffix.lower() != ".pdf":
        print(f"\n  ERROR: File must be a PDF: {args.pdf}\n")
        sys.exit(1)

    # Extract text
    try:
        deck_content = extract_pdf_text(str(pdf_path))
    except Exception as e:
        print(f"\n  ERROR reading PDF: {e}\n")
        sys.exit(1)

    if not deck_content.strip():
        print("\n  ERROR: Could not extract text from this PDF.")
        print("  The PDF might be image-based (scanned).")
        print("  Try a PDF with selectable text.\n")
        sys.exit(1)

    # Initialize client
    try:
        client = anthropic.Anthropic()
    except anthropic.AuthenticationError:
        print("\n  ERROR: Invalid API key.")
        print("  Delete the .api_key file and run again to enter a new key.\n")
        sys.exit(1)

    # Research phase
    research_text = ""
    if not args.no_research:
        print("\n  Extracting company info from deck...")
        company_info = extract_company_info(client, deck_content)
        company_name = company_info.get('company_name', 'Unknown')
        print(f"  Found: {company_name}")

        print("\n  Checking Companies House (UK registry)...")
        ch_research = research_companies_house(company_name)
        print("  Companies House lookup complete.")

        print("\n  Researching investors & funding...")
        investor_research = research_investors(company_name, company_info.get('industry', 'technology'))
        print("  Investor research complete.")

        print("\n  Conducting general research via Perplexity...")
        perplexity_research = research_with_perplexity(company_info)
        print("  General research complete.\n")

        # Combine research
        research_text = f"""=== COMPANIES HOUSE (UK OFFICIAL REGISTRY) ===
{ch_research}

=== INVESTOR & FUNDING RESEARCH ===
{investor_research}

=== GENERAL COMPANY RESEARCH ===
{perplexity_research}"""
    else:
        print("\n  Skipping research (--no-research flag).\n")

    # Analyze
    print("  Running investment committee debate...")
    try:
        analysis = analyze_company(deck_content, research_text, args.notes)
    except anthropic.AuthenticationError:
        print("\n  ERROR: Invalid API key.")
        print("  Delete the .api_key file and run again to enter a new key.\n")
        sys.exit(1)
    except anthropic.APIError as e:
        print(f"\n  ERROR from Claude API: {e}\n")
        sys.exit(1)

    # Output to console (minimal)
    print("\n  Analysis complete.")

    # Generate HTML
    from datetime import datetime
    from html_generator import create_memo
    import webbrowser

    # Extract components from analysis dict
    memo_text = analysis['memo']
    bull_case = analysis['bull_case']
    bear_case = analysis['bear_case']
    deliberation = analysis.get('deliberation', '')

    company_name = "Company"
    # Try to extract company name from the analysis (look for # COMPANY NAME line)
    for line in memo_text.split("\n"):
        if line.startswith("# ") and not line.startswith("## "):
            potential_name = line[2:].strip()
            if potential_name not in ['PURSUE', 'PASS', 'MONITOR']:
                company_name = potential_name
                break

    # Create output filename
    date_str = datetime.now().strftime("%Y-%m-%d")
    date_display = datetime.now().strftime("%d %B %Y")
    safe_company_name = company_name.replace(" ", "_").replace("/", "-")

    if args.output:
        output_path = Path(args.output)
        if not output_path.suffix:
            output_path = output_path.with_suffix('.html')
    else:
        output_path = pdf_path.parent / f"MEMO_{safe_company_name}_{date_str}.html"

    print("  Generating memo...")

    try:
        create_memo(
            analysis=memo_text,
            output_path=str(output_path),
            source=pdf_path.name,
            date_str=date_display,
            bull_case=bull_case,
            bear_case=bear_case,
            deliberation=deliberation
        )
        print(f"\n")
        print(f"  ============================================")
        print(f"  MEMO SAVED: {output_path.name}")
        print(f"  ============================================")

        # Open in browser
        webbrowser.open(f'file://{output_path.absolute()}')
        print(f"\n  Opened in browser. Print to PDF if needed.")

    except Exception as e:
        print(f"\n  Warning: Could not generate HTML: {e}")
        import traceback
        traceback.print_exc()
        print("  Saving as markdown instead...")
        # Fallback to markdown
        md_path = output_path.with_suffix('.md')
        with open(md_path, "w") as f:
            f.write(f"# Bramble Partners - Screening Memo\n\n")
            f.write(f"**Date:** {date_display}\n")
            f.write(f"**Source:** {pdf_path.name}\n\n---\n\n")
            f.write(memo_text)
        print(f"  Saved to: {md_path.name}")


if __name__ == "__main__":
    main()
