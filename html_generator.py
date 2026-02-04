#!/usr/bin/env python3
"""
Bramble Partners - HTML Memo Generator
Parses markdown analysis and generates beautiful HTML memo
"""

import re
from pathlib import Path
from datetime import datetime


def parse_analysis(analysis: str) -> dict:
    """Parse the markdown analysis into sections."""

    sections = {
        'company_name': '',
        'opportunity': '',
        'snapshot': [],
        'market': '',
        'competition': '',
        'team': '',
        'investors': '',
        'fit_table': [],
        'overall_fit': '',
        'bull_case': [],
        'bear_case': [],
        'key_debates': [],
        'verdict': '',
        'verdict_rationale': '',
        'confidence': '',
        'terms': [],
        'risks': [],
        'info_gaps': '',
        'dd_priorities': [],
        'bottom_line': ''
    }

    lines = analysis.split('\n')
    current_section = None
    current_content = []

    for line in lines:
        line_stripped = line.strip()

        # Company name (# COMPANY NAME)
        if line_stripped.startswith('# ') and not line_stripped.startswith('## '):
            name = line_stripped[2:].strip()
            # Remove any bold markdown formatting
            name_clean = name.replace('**', '').replace('*', '').strip()
            if name_clean.upper() in ['PURSUE', 'PASS', 'MONITOR']:
                sections['verdict'] = name_clean.upper()
            else:
                sections['company_name'] = name
            continue

        # Section headers (### SECTION)
        if line_stripped.startswith('### '):
            # Save previous section
            if current_section and current_content:
                save_section(sections, current_section, current_content)

            current_section = line_stripped[4:].strip().upper()
            current_content = []
            continue

        # Skip other headers and dividers
        if line_stripped.startswith('## ') or line_stripped == '---':
            continue

        # Collect content
        if current_section:
            current_content.append(line)

    # Save last section
    if current_section and current_content:
        save_section(sections, current_section, current_content)

    return sections


def save_section(sections: dict, section_name: str, content: list):
    """Process and save a section's content."""

    text = '\n'.join(content).strip()

    if 'OPPORTUNITY' in section_name:
        sections['opportunity'] = markdown_to_html(text)

    elif 'SNAPSHOT' in section_name:
        sections['snapshot'] = parse_snapshot(text)

    elif 'MARKET' in section_name:
        sections['market'] = markdown_to_html(text)

    elif 'COMPETITIVE' in section_name or 'COMPETITION' in section_name:
        sections['competition'] = markdown_to_html(text)

    elif 'TEAM' in section_name:
        sections['team'] = markdown_to_html(text, preserve_breaks=True)

    elif 'INVESTOR' in section_name or 'EXISTING INVESTOR' in section_name:
        sections['investors'] = markdown_to_html(text)

    elif 'FIT' in section_name:
        sections['fit_table'], sections['overall_fit'] = parse_fit_table(text)

    elif 'BULL' in section_name:
        sections['bull_case'] = parse_bullet_points(text)

    elif 'BEAR' in section_name:
        sections['bear_case'] = parse_bullet_points(text)

    elif 'KEY DEBATE' in section_name or 'DEBATES' in section_name:
        sections['key_debates'] = parse_debates(text)

    elif 'RECOMMENDATION' in section_name:
        verdict, confidence, rationale = parse_verdict(text)
        if verdict:
            sections['verdict'] = verdict
        if confidence:
            sections['confidence'] = confidence
        sections['verdict_rationale'] = rationale

    elif 'TERMS' in section_name:
        sections['terms'] = parse_terms(text)

    elif 'RISK' in section_name:
        sections['risks'], sections['info_gaps'] = parse_risks(text)

    elif 'DUE DILIGENCE' in section_name or 'DD' in section_name:
        sections['dd_priorities'] = parse_dd(text)

    elif 'BOTTOM' in section_name:
        sections['bottom_line'] = markdown_to_html(text)


def markdown_to_html(text: str, preserve_breaks: bool = False) -> str:
    """Convert markdown to HTML."""
    # Remove empty citation links [](url) or [text]()
    text = re.sub(r'\[\]\([^)]*\)', '', text)
    text = re.sub(r'\[[^\]]+\]\(\)', '', text)
    # Links [text](url) -> <a href="url" target="_blank">text</a>
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" class="citation">\1</a>', text)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Paragraphs
    paragraphs = text.split('\n\n')
    html_parts = []
    for p in paragraphs:
        p = p.strip()
        if p:
            # Check if it's a list
            if p.startswith('- ') or p.startswith('* '):
                items = re.split(r'\n[-*]\s', p)
                items[0] = items[0][2:]  # Remove first bullet
                html_parts.append('<ul>' + ''.join(f'<li>{item.strip()}</li>' for item in items if item.strip()) + '</ul>')
            elif preserve_breaks:
                # Keep line breaks (for team section)
                lines = p.split('\n')
                html_parts.append('<p>' + '<br>\n'.join(line.strip() for line in lines if line.strip()) + '</p>')
            else:
                html_parts.append(f'<p>{p.replace(chr(10), " ")}</p>')
    return '\n'.join(html_parts)


def parse_snapshot(text: str) -> list:
    """Parse snapshot section into label/value pairs."""
    items = []
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('**') and ':**' in line:
            match = re.match(r'\*\*(.+?):\*\*\s*(.+)', line)
            if match:
                value = match.group(2)
                # Convert markdown links to HTML
                value = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" class="citation">\1</a>', value)
                items.append({
                    'label': match.group(1),
                    'value': value
                })
    return items


def parse_fit_table(text: str) -> tuple:
    """Parse fit table and overall fit."""
    rows = []
    overall = ''

    lines = text.split('\n')
    in_table = False

    for line in lines:
        line = line.strip()

        if line.startswith('|') and '---' not in line:
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if len(cells) >= 3 and cells[0].lower() not in ['criterion', '']:
                rows.append({
                    'criterion': cells[0],
                    'rating': cells[1],
                    'assessment': cells[2] if len(cells) > 2 else ''
                })

        if 'Overall Fit' in line or 'OVERALL FIT' in line:
            match = re.search(r'(STRONG|MODERATE|WEAK)', line, re.IGNORECASE)
            if match:
                overall = match.group(1).upper()

    return rows, overall


def parse_verdict(text: str) -> tuple:
    """Parse verdict, confidence, and rationale."""
    verdict = ''
    confidence = ''
    rationale = ''

    lines = text.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if line in ['# PURSUE', '# PASS', '# MONITOR']:
            verdict = line[2:]
        elif line in ['PURSUE', 'PASS', 'MONITOR']:
            verdict = line
        elif '**Confidence:**' in line or 'Confidence:' in line:
            match = re.search(r'(HIGH|MEDIUM|LOW)', line, re.IGNORECASE)
            if match:
                confidence = match.group(1).upper()
        elif line and not line.startswith('#') and not line.startswith('*') and 'Confidence' not in line:
            # This is the rationale
            rationale = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            break

    # Get remaining text as rationale if not found
    if not rationale:
        remaining = '\n'.join(lines).strip()
        remaining = re.sub(r'#\s*(PURSUE|PASS|MONITOR)', '', remaining)
        remaining = re.sub(r'\*\*Confidence:\*\*\s*(HIGH|MEDIUM|LOW)', '', remaining, flags=re.IGNORECASE)
        remaining = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', remaining)
        rationale = remaining.strip()

    return verdict, confidence, rationale


def parse_bullet_points(text: str) -> list:
    """Parse bullet points with bold headers (for bull/bear cases)."""
    points = []

    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('- ') or line.startswith('* '):
            line = line[2:]
            # Extract bold header and description - handle "**Title** - desc" or "**Title:** desc" or "**Title::** desc"
            match = re.match(r'\*\*(.+?)\*\*\s*[-:]+\s*(.+)', line)
            if match:
                title = match.group(1).rstrip(':')  # Remove any trailing colons from title
                points.append({
                    'title': title,
                    'description': match.group(2)
                })
            elif line:
                points.append({
                    'title': '',
                    'description': line
                })

    return points


def parse_debates(text: str) -> list:
    """Parse key debates section."""
    debates = []

    for line in text.split('\n'):
        line = line.strip()
        if re.match(r'^\d+\.', line):
            # Remove the number prefix
            line = re.sub(r'^\d+\.\s*', '', line)
            # Extract bold question and views
            match = re.match(r'\*\*(.+?)\*\*:?\s*(.+)', line)
            if match:
                debates.append({
                    'question': match.group(1),
                    'views': match.group(2)
                })
            elif line:
                debates.append({
                    'question': line,
                    'views': ''
                })

    return debates


def parse_terms(text: str) -> list:
    """Parse proposed terms."""
    terms = []
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('**') and ':**' in line:
            match = re.match(r'\*\*(.+?):\*\*\s*(.+)', line)
            if match:
                terms.append({
                    'label': match.group(1),
                    'value': match.group(2)
                })
    return terms


def parse_risks(text: str) -> tuple:
    """Parse risks and info gaps."""
    risks = []
    info_gaps = ''

    lines = text.split('\n')
    in_risks = False

    for line in lines:
        line = line.strip()

        if 'Critical Risks' in line or 'Key Risks' in line:
            in_risks = True
            continue

        if 'Information Gaps' in line:
            in_risks = False
            match = re.search(r'Information Gaps:?\s*(.+)', line, re.IGNORECASE)
            if match:
                info_gaps = match.group(1)
            continue

        if in_risks and re.match(r'^\d+\.', line):
            # Numbered risk
            match = re.match(r'^\d+\.\s*\*\*(.+?):\*\*\s*(.+)', line)
            if match:
                risks.append({
                    'title': match.group(1),
                    'description': match.group(2)
                })
            else:
                # No bold formatting
                match = re.match(r'^\d+\.\s*(.+?):\s*(.+)', line)
                if match:
                    risks.append({
                        'title': match.group(1),
                        'description': match.group(2)
                    })

        if not in_risks and line and 'Information' not in line:
            # Might be info gaps continuation
            if info_gaps:
                info_gaps += ' ' + line

    return risks, info_gaps


def parse_dd(text: str) -> list:
    """Parse due diligence priorities."""
    priorities = []

    for line in text.split('\n'):
        line = line.strip()
        if re.match(r'^\d+\.', line):
            item = re.sub(r'^\d+\.\s*', '', line)
            if item:
                priorities.append(item)

    return priorities


def markdown_to_simple_html(text: str) -> str:
    """Convert markdown to simple HTML for analyst sections."""
    import html as html_lib

    lines = text.strip().split('\n')
    result = []
    current_list = []
    in_list = False

    for line in lines:
        line_stripped = line.strip()

        # Skip empty lines but close any open list
        if not line_stripped:
            if in_list and current_list:
                result.append('<ul>' + ''.join(current_list) + '</ul>')
                current_list = []
                in_list = False
            continue

        # Escape HTML
        line_escaped = html_lib.escape(line_stripped)

        # Bold
        line_escaped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line_escaped)

        # Headers
        if line_stripped.startswith('### '):
            if in_list and current_list:
                result.append('<ul>' + ''.join(current_list) + '</ul>')
                current_list = []
                in_list = False
            result.append(f'<h4>{line_escaped[4:]}</h4>')
        elif line_stripped.startswith('## '):
            if in_list and current_list:
                result.append('<ul>' + ''.join(current_list) + '</ul>')
                current_list = []
                in_list = False
            result.append(f'<h3>{line_escaped[3:]}</h3>')
        elif line_stripped.startswith('# '):
            if in_list and current_list:
                result.append('<ul>' + ''.join(current_list) + '</ul>')
                current_list = []
                in_list = False
            result.append(f'<h3>{line_escaped[2:]}</h3>')
        # Bullet points
        elif line_stripped.startswith('- ') or line_stripped.startswith('* '):
            in_list = True
            current_list.append(f'<li>{line_escaped[2:]}</li>')
        # Numbered lists
        elif re.match(r'^\d+\.\s', line_stripped):
            in_list = True
            content = re.sub(r'^\d+\.\s*', '', line_escaped)
            current_list.append(f'<li>{content}</li>')
        # Regular paragraph
        else:
            if in_list and current_list:
                result.append('<ul>' + ''.join(current_list) + '</ul>')
                current_list = []
                in_list = False
            result.append(f'<p>{line_escaped}</p>')

    # Close any remaining list
    if in_list and current_list:
        result.append('<ul>' + ''.join(current_list) + '</ul>')

    return '\n'.join(result)


def generate_html(sections: dict, source: str = '', date_str: str = '',
                  bull_case: str = '', bear_case: str = '', deliberation: str = '') -> str:
    """Generate HTML from sections using template."""

    template_path = Path(__file__).parent / 'memo_template.html'
    with open(template_path, 'r') as f:
        html = f.read()

    # Basic replacements
    html = html.replace('{{COMPANY_NAME}}', sections['company_name'])
    html = html.replace('{{DATE}}', date_str or datetime.now().strftime('%d %B %Y'))
    html = html.replace('{{SOURCE}}', source)
    html = html.replace('{{OPPORTUNITY}}', sections['opportunity'])
    html = html.replace('{{MARKET}}', sections['market'])
    html = html.replace('{{COMPETITION}}', sections['competition'])
    html = html.replace('{{TEAM}}', sections['team'])

    # Investors
    investors_content = sections.get('investors', '')
    html = html.replace('{{INVESTORS}}', investors_content if investors_content else '<p>No prior investor information found.</p>')

    # Snapshot
    snapshot_html = ''
    for item in sections['snapshot']:
        snapshot_html += f'''
        <div class="snapshot-row">
            <span class="snapshot-label">{item['label']}</span>
            <span class="snapshot-value">{item['value']}</span>
        </div>'''
    html = html.replace('{{SNAPSHOT}}', snapshot_html)

    # Fit table
    fit_html = '<table class="fit-table"><thead><tr><th>Criterion</th><th>Rating</th><th>Assessment</th></tr></thead><tbody>'
    for row in sections['fit_table']:
        rating_class = row['rating'].lower().split()[0] if row['rating'] else ''
        fit_html += f'''
        <tr>
            <td class="criterion">{row['criterion']}</td>
            <td class="rating"><span class="rating-badge {rating_class}">{row['rating']}</span></td>
            <td>{row['assessment']}</td>
        </tr>'''
    fit_html += '</tbody></table>'
    if sections['overall_fit']:
        fit_html += f'<div class="overall-fit"><strong>Overall Fit: {sections["overall_fit"]}</strong></div>'
    html = html.replace('{{FIT_TABLE}}', fit_html)

    # Bull/Bear cases
    bull_html = '<ul class="case-list bull">'
    for point in sections['bull_case']:
        if point['title']:
            bull_html += f'<li><span class="case-title">{point["title"]}:</span> {point["description"]}</li>'
        else:
            bull_html += f'<li>{point["description"]}</li>'
    bull_html += '</ul>'
    html = html.replace('{{BULL_CASE}}', bull_html if sections['bull_case'] else '<p>Not provided</p>')

    bear_html = '<ul class="case-list bear">'
    for point in sections['bear_case']:
        if point['title']:
            bear_html += f'<li><span class="case-title">{point["title"]}:</span> {point["description"]}</li>'
        else:
            bear_html += f'<li>{point["description"]}</li>'
    bear_html += '</ul>'
    html = html.replace('{{BEAR_CASE}}', bear_html if sections['bear_case'] else '<p>Not provided</p>')

    # Key debates
    debates_html = '<ul class="debates-list">'
    for debate in sections['key_debates']:
        debates_html += f'<li><span class="debate-question">{debate["question"]}</span>'
        if debate['views']:
            debates_html += f'<span class="debate-views">{debate["views"]}</span>'
        debates_html += '</li>'
    debates_html += '</ul>'
    html = html.replace('{{KEY_DEBATES}}', debates_html if sections['key_debates'] else '<p>Not provided</p>')

    # Verdict
    verdict = sections['verdict']
    confidence = sections.get('confidence', '')
    html = html.replace('{{VERDICT}}', verdict)
    html = html.replace('{{VERDICT_CLASS}}', verdict.lower())
    html = html.replace('{{CONFIDENCE}}', confidence)
    html = html.replace('{{CONFIDENCE_CLASS}}', confidence.lower() if confidence else '')
    html = html.replace('{{VERDICT_RATIONALE}}', sections['verdict_rationale'])

    # Terms (only if PURSUE)
    if verdict == 'PURSUE' and sections['terms']:
        terms_html = '''
        <div class="section">
            <h2 class="section-title">Proposed Terms</h2>
            <div class="terms-grid">'''

        # Find ticket rationale to pair with ticket size
        ticket_rationale = ''
        for term in sections['terms']:
            if 'rationale' in term['label'].lower():
                ticket_rationale = term['value']
                break

        for term in sections['terms']:
            # Skip rationale - it gets merged with ticket size
            if 'rationale' in term['label'].lower():
                continue

            # Add rationale under ticket size
            if 'ticket size' in term['label'].lower() and ticket_rationale:
                terms_html += f'''
                <div class="term-item">
                    <div class="term-label">{term['label']}</div>
                    <div class="term-value">{term['value']}</div>
                    <div class="term-rationale">{ticket_rationale}</div>
                </div>'''
            else:
                terms_html += f'''
                <div class="term-item">
                    <div class="term-label">{term['label']}</div>
                    <div class="term-value">{term['value']}</div>
                </div>'''
        terms_html += '</div></div>'
        html = html.replace('{{TERMS_SECTION}}', terms_html)
    else:
        html = html.replace('{{TERMS_SECTION}}', '')

    # Risks
    risks_html = '<ul class="risk-list">'
    for risk in sections['risks']:
        risks_html += f'''
        <li>
            <span class="risk-title">{risk['title']}:</span> {risk['description']}
        </li>'''
    risks_html += '</ul>'
    if sections['info_gaps']:
        risks_html += f'''
        <div class="info-gaps">
            <div class="info-gaps-title">Information Gaps</div>
            {sections['info_gaps']}
        </div>'''
    html = html.replace('{{RISKS}}', risks_html)

    # DD Priorities
    dd_html = '<ul class="dd-list">'
    for priority in sections['dd_priorities']:
        dd_html += f'<li>{priority}</li>'
    dd_html += '</ul>'
    html = html.replace('{{DD_PRIORITIES}}', dd_html)

    # Bottom line
    html = html.replace('{{BOTTOM_LINE}}', sections['bottom_line'].replace('<p>', '').replace('</p>', ''))

    # Analyst arguments (collapsible sections)
    if bull_case and bear_case:
        bull_html = markdown_to_simple_html(bull_case)
        bear_html = markdown_to_simple_html(bear_case)
        deliberation_html = markdown_to_simple_html(deliberation) if deliberation else ''
        html = html.replace('{{BULL_ANALYST}}', bull_html)
        html = html.replace('{{BEAR_ANALYST}}', bear_html)
        html = html.replace('{{DELIBERATION}}', deliberation_html)
        html = html.replace('{{ANALYST_SECTIONS}}', '')  # Show the section
    else:
        # Hide the entire analyst appendix if no data
        html = re.sub(r'<!-- ANALYST_APPENDIX_START -->.*?<!-- ANALYST_APPENDIX_END -->', '', html, flags=re.DOTALL)

    return html


def create_memo(analysis: str, output_path: str, source: str = '', date_str: str = '',
                bull_case: str = '', bear_case: str = '', deliberation: str = ''):
    """Parse analysis and create HTML memo."""

    sections = parse_analysis(analysis)
    html = generate_html(sections, source, date_str, bull_case, bear_case, deliberation)

    with open(output_path, 'w') as f:
        f.write(html)

    return output_path


if __name__ == '__main__':
    # Test with sample
    test_analysis = """
# ACME FOODS
## Investment Screening Memo

---

### THE OPPORTUNITY

ACME Foods is building **the future of sustainable protein** through precision fermentation. They've cracked the code on cost-effective mycoprotein production.

---

### SNAPSHOT

**Company:** ACME Foods
**Stage:** Series A
**Raising:** £5M
**Business Model:** B2B ingredient supplier
**Traction:** 3 pilots, £500K ARR

---

### THE MARKET

The **£50B global protein market** is shifting. Plant-based hit a wall; fermentation is next.

---

### COMPETITIVE POSITION

Competitors include Quorn and Perfect Day.

**Why ACME wins:** Lowest cost production at scale.

---

### THE TEAM

Strong team with **biotech and food experience**.

---

### BRAMBLE FIT

| Criterion | Rating | Assessment |
|-----------|--------|------------|
| Food System Impact | Strong | Direct sustainability impact |
| Stage Fit | Strong | Series A sweet spot |
| Value Chain Position | Strong | Processing - core focus |
| Values Alignment | Strong | Long-term thinking |

**Overall Fit:** STRONG

---

### RECOMMENDATION

# PURSUE

This fits our thesis perfectly.

---

### PROPOSED TERMS

**Ticket Size:** £500K-1M
**Valuation View:** Fair at £15M pre
**Key Terms:** Board seat, pro-rata
**Syndicate:** Biotech specialists

---

### RISKS & GAPS

**Critical Risks:**
1. **Regulatory:** Novel food approval pending
2. **Scale-up:** Lab to factory risk
3. **Customer:** Concentrated pipeline

**Information Gaps:** Unit economics detail needed.

---

### DUE DILIGENCE PRIORITIES

1. Validate cost claims
2. Check regulatory timeline
3. Customer references

---

### BOTTOM LINE

Strong fit. Move quickly.
"""

    create_memo(test_analysis, '/tmp/test_memo.html', 'acme_deck.pdf', '03 February 2026')
    print('Test HTML generated: /tmp/test_memo.html')
