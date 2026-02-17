#!/usr/bin/env python3
"""Convert lethal_intent_mismatch.html to Substack-ready format.

Transformations:
1. Comment out <style> block and MathJax <script> tags
2. Convert LaTeX tables from $$...$$ to <pre> blocks, splitting large tables
3. Convert .finding/.warning/.critical divs to <blockquote>
4. Remove .table-container wrappers (keep contents)
5. Unescape \_ to _, remove \; thin spaces, strip \text{...} to bare content
6. Unescape \% to % in header lines only (Substack needs bare % in \textbf{})
   Content rows keep \% escaped (bare % is a LaTeX comment character)
"""

import re
import sys
from pathlib import Path


def comment_out_style(html: str) -> str:
    """Comment out <style>...</style> block."""
    return re.sub(
        r'(<style>)(.*?)(</style>)',
        r'<!-- \1\2\3 -->',
        html,
        flags=re.DOTALL
    )


def comment_out_scripts(html: str) -> str:
    """Comment out MathJax <script> tags."""
    # The inline config script
    html = re.sub(
        r'(<script>\s*window\.MathJax\s*=.*?</script>)',
        r'<!-- \1 -->',
        html,
        flags=re.DOTALL
    )
    # The external MathJax script
    html = re.sub(
        r'(<script src="https://cdn\.jsdelivr\.net/npm/mathjax@3.*?</script>)',
        r'<!-- \1 -->',
        html,
        flags=re.DOTALL
    )
    return html


def split_table_rows(rows: list[str], header_line: str, hline: str, col_spec: str) -> list[list[str]]:
    """Split data rows into chunks of up to 4, keeping total rows with preceding chunk.

    Returns list of chunks, where each chunk is a list of row strings.
    A chunk may include a \hline before a total/overall row.
    """
    if len(rows) <= 4:
        return [rows]

    chunks = []
    current_chunk = []
    i = 0
    while i < len(rows):
        row = rows[i]
        # Check if this is a \hline before a total/overall row
        stripped = row.strip()
        if stripped == '\\hline':
            # This is a separator before a total row - attach it + next row to current chunk
            current_chunk.append(row)
            if i + 1 < len(rows):
                current_chunk.append(rows[i + 1])
                i += 2
            else:
                i += 1
            chunks.append(current_chunk)
            current_chunk = []
            continue

        current_chunk.append(row)
        if len(current_chunk) >= 4:
            # Check if next row is a \hline (total separator) - if so, keep going
            if i + 1 < len(rows) and rows[i + 1].strip() == '\\hline':
                pass  # Will be handled in next iteration
            else:
                chunks.append(current_chunk)
                current_chunk = []
        i += 1

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def convert_latex_table(match: re.Match) -> str:
    """Convert a single LaTeX table match to <pre> block(s)."""
    content = match.group(1)

    # Unescape LaTeX (but NOT bare \% — in LaTeX, bare % is a comment character)
    content = content.replace('\\_', '_')
    content = content.replace('\\;', ' ')
    content = content.replace('\\text{-}', '-')
    # Unescape \% inside \text{} — \text{} already treats content as literal,
    # so \% inside it renders wrong in Substack. Bare \% outside \text{} must stay.
    content = re.sub(r'\\text\{([^}]*)\}', lambda m: '\\text{' + m.group(1).replace('\\%', '%') + '}', content)

    # Parse the table structure
    lines = content.strip().split('\n')

    # Find the \begin{array} line to get column spec
    begin_line = None
    header_line = None
    hline_line = None
    data_rows = []
    end_line = None
    col_spec = ''

    state = 'before'  # before, header, after_hline, data, done

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('\\begin{array}'):
            begin_line = line
            # Extract column spec
            m = re.search(r'\\begin\{array\}\{([^}]+)\}', stripped)
            if m:
                col_spec = m.group(1)
            state = 'header'
        elif state == 'header':
            if stripped == '\\hline':
                hline_line = line
                state = 'data'
            else:
                header_line = line
        elif state == 'data':
            if stripped == '\\end{array}':
                end_line = line
                state = 'done'
            else:
                data_rows.append(line)
        elif state == 'done':
            pass

    if not begin_line or not header_line:
        # Fallback: just wrap as-is
        return f'<pre>\n{content}\n</pre>'

    # Unescape \% ONLY in header line — Substack's LaTeX parser needs bare %
    # in \textbf{} headers, but content rows need \% (bare % is a comment char)
    header_line = header_line.replace('\\%', '%')

    # Count actual data rows (excluding \hline separators)
    actual_data_rows = [r for r in data_rows if r.strip() != '\\hline']

    if len(actual_data_rows) <= 4:
        # No splitting needed
        table_content = begin_line + '\n'
        table_content += header_line + '\n'
        if hline_line:
            table_content += hline_line + '\n'
        for row in data_rows:
            table_content += row + '\n'
        table_content += '\\end{array}'
        return f'<pre>\n{table_content}\n</pre>'

    # Need to split
    chunks = split_table_rows(data_rows, header_line, hline_line, col_spec)

    pre_blocks = []
    for chunk in chunks:
        table_content = begin_line + '\n'
        table_content += header_line + '\n'
        if hline_line:
            table_content += hline_line + '\n'
        for row in chunk:
            table_content += row + '\n'
        table_content += '\\end{array}'
        pre_blocks.append(f'<pre>\n{table_content}\n</pre>')

    return '\n\n'.join(pre_blocks)


def convert_latex_tables(html: str) -> str:
    """Convert all LaTeX tables from div.latex-table with $$ to <pre> blocks."""
    # Match <div class="latex-table"...> ... $$...$$ ... </div>
    # Some have style attributes too
    pattern = re.compile(
        r'<div class="latex-table"[^>]*>\s*\$\$\s*(.*?)\s*\$\$\s*</div>',
        re.DOTALL
    )
    return pattern.sub(convert_latex_table, html)


def convert_non_table_latex_divs(html: str) -> str:
    """Convert remaining .latex-table divs that don't contain $$ (e.g., the classification gate)."""
    # These are just styled divs with regular HTML content
    # Remove the div wrapper but keep content
    pattern = re.compile(
        r'<div class="latex-table"[^>]*>(.*?)</div>',
        re.DOTALL
    )
    return pattern.sub(r'\1', html)


def convert_finding_divs(html: str) -> str:
    """Convert .finding divs to <blockquote>."""
    return re.sub(
        r'<div class="finding">\s*',
        '<blockquote>\n',
        html
    ).replace('</div>', '</div>')  # Will handle closing tags separately
    # Actually need a more targeted approach
    pass


def convert_styled_divs(html: str) -> str:
    """Convert .finding, .warning, .critical divs to <blockquote>."""
    for cls in ['finding', 'warning', 'critical']:
        # We need to match opening and closing divs for these specific classes
        # Using a non-greedy approach that finds the next </div>
        pattern = re.compile(
            rf'<div class="{cls}">\s*(.*?)\s*</div>',
            re.DOTALL
        )
        html = pattern.sub(r'<blockquote>\n\1\n</blockquote>', html)
    return html


def remove_table_container_wrappers(html: str) -> str:
    """Remove .table-container div wrappers, keeping contents."""
    html = re.sub(r'<div class="table-container">\s*', '', html)
    # The corresponding </div> is tricky - we need to be careful
    # Since table-container only wraps latex-table divs which are already converted,
    # this should be straightforward
    return html


def unescape_latex_globally(html: str) -> str:
    """Unescape \_ and remove \; in any remaining LaTeX content.

    NOTE: \% must NOT be unescaped — in LaTeX, bare % is a comment character
    and will swallow everything after it on the line, breaking table rows.
    """
    # These should already be handled in tables, but catch any stragglers
    # Only apply within <pre> blocks to be safe
    def unescape_pre(match):
        content = match.group(1)
        content = content.replace('\\_', '_')
        content = content.replace('\\;', ' ')
        content = content.replace('\\text{-}', '-')
        # Unescape \% inside \text{} only (bare \% must stay)
        content = re.sub(r'\\text\{([^}]*)\}', lambda m: '\\text{' + m.group(1).replace('\\%', '%') + '}', content)
        return f'<pre>{content}</pre>'

    return re.sub(r'<pre>(.*?)</pre>', unescape_pre, html, flags=re.DOTALL)


def remove_class_subtitle_byline(html: str) -> str:
    """Remove class attributes from subtitle and byline paragraphs.
    Substack doesn't understand these classes."""
    html = re.sub(r'<p class="subtitle">', '<p><em>', html)
    html = re.sub(r'</p>(\s*<p class="byline">)', r'</em></p>\1', html)
    # Actually, let's keep them simple - Substack ignores unknown classes
    # but they don't hurt. Let's leave them.
    # Revert - just leave classes as-is, they won't affect rendering
    return html


def main():
    src = Path('/home/p/Coding/aeonisk-yags/.claude/articles/lethal_intent_mismatch.html')
    dst = Path('/home/p/Coding/aeonisk-yags/.claude/articles/lethal_intent_mismatch_substack.html')

    html = src.read_text()

    # 1. Comment out style and scripts
    html = comment_out_style(html)
    html = comment_out_scripts(html)

    # 2. Convert styled divs BEFORE table conversion (since some divs are nested)
    #    But first handle latex tables since .finding etc contain no latex tables

    # 3. Convert LaTeX tables (div.latex-table with $$) to <pre> blocks
    html = convert_latex_tables(html)

    # 4. Convert remaining .latex-table divs (non-$$ content like classification gate)
    html = convert_non_table_latex_divs(html)

    # 5. Convert .finding, .warning, .critical divs to <blockquote>
    html = convert_styled_divs(html)

    # 6. Remove .table-container wrappers
    html = remove_table_container_wrappers(html)

    # 7. Unescape any remaining LaTeX in <pre> blocks
    html = unescape_latex_globally(html)

    dst.write_text(html)

    src_lines = src.read_text().count('\n') + 1
    dst_lines = html.count('\n') + 1
    print(f"Source: {src_lines} lines")
    print(f"Output: {dst_lines} lines")
    print(f"Written to: {dst}")


if __name__ == '__main__':
    main()
