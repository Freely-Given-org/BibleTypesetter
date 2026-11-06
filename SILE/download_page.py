"""Render a static download index from the same catalogue used by other sites."""
from html import escape


def download_page(catalogue, settings):
    esc = lambda value: escape(str(value), quote=True)
    def table(entries, caption, edition):
        rows = []
        for entry in entries:
            title = f'{entry["title"]} ({entry["id"]})' if entry['kind'] == 'book' else entry['title']
            cells = []
            for medium, label in [('print', 'Print'), ('screen', 'Online')]:
                links = []
                for file in entry['files']:
                    if file['medium'] != medium:
                        continue
                    links.append(f'<div class="pdf-choice"><a href="{esc(file["url"])}" aria-label="{esc(title)} — {esc(edition)} — {label} {esc(file["paper_size"])} PDF">'
                                 f'{esc(file["paper_size"])} PDF</a><small>{file["bytes"] / 1048576:.1f} MB · {file["pages"]:,} pages</small></div>')
                cells.append('<td>' + ''.join(links) + '</td>')
            rows.append(f'<tr><th scope="row">{esc(title)}</th>{"".join(cells)}</tr>')
        return f'<div class="table-wrap"><table><caption>{esc(caption)}</caption><thead><tr><th scope="col">Title</th><th scope="col">Print</th><th scope="col">Online</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    sections = []
    for edition in catalogue['editions']:
        entries = edition['entries']
        label = edition['label']
        sections.append(f'<section id="{esc(edition["id"])}"><h2>{esc(label)} ({esc(edition["id"])})</h2>')
        sections.append(table([e for e in entries if e['kind'] == 'collection'], 'Collections', label))
        sections.append('<h3>Individual books</h3>')
        for group in catalogue['groups']:
            books = [e for e in entries if e['kind'] == 'book' and e['group'] == group['id']]
            sections.append(f'<details><summary>{esc(group["title"])} ({len(books)} books)</summary>'
                            + table(books, group['title'], label) + '</details>')
        sections.append('</section>')
    shortcuts = ' · '.join(f'<a href="#{esc(e["id"])}">{esc(e["label"])}</a>' for e in catalogue['editions'])
    navigation = '  '.join(f'<a href="{esc(link["url"])}">{esc(link["label"])}</a>'
                           for link in settings.get('navigation', []))
    styles = '\n'.join(f'<link rel="stylesheet" href="{esc(url)}">' for url in settings.get('stylesheets', []))
    script = f'<script src="{esc(settings["script"])}"></script>' if settings.get('script') else ''
    logo = (f'<a href="{esc(settings["logo_href"])}"><img class="download-logo" src="{esc(settings["logo_url"])}" '
            f'alt="{esc(catalogue["title"])}"></a>') if settings.get('logo_url') else ''
    intro = ''.join(f'<p>{esc(p)}</p>' for p in settings.get('introduction', []))
    title = settings.get('title', catalogue['title'] + ' — Downloads')
    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>{styles}{script}
<style>
main.downloads {{ max-width: 66rem; margin: 2rem auto; padding: 0 1rem 3rem; }}
.downloads p {{ line-height: 1.55; }}
.download-logo {{ display:block; width: min(28rem,85%); margin: 1.5rem auto; }}
.table-wrap {{ overflow-x:auto; }}
.downloads table {{ border-collapse:collapse; width:100%; margin:1rem 0; }}
.downloads caption {{ text-align:left; font-size:1.3rem; font-weight:bold; padding:1rem 0; }}
.downloads th,.downloads td {{ text-align:left; vertical-align:top; padding:.7rem .5rem; border-bottom:1px solid #87949c; }}
.downloads th:first-child {{ width:42%; }}
.downloads tbody th {{ font-weight:normal; }}
.downloads td small {{ display:block; margin-top:.2rem; }}
.pdf-choice {{ margin-bottom:.8rem; }}
.downloads section {{ margin-top:2.5rem; }}
.downloads details {{ margin:1rem 0; }}
.downloads summary {{ cursor:pointer; font-weight:bold; padding:.5rem 0; }}
</style></head><body class="container" data-page-type="downloads">
<div class="topLine"><p class="site">{navigation}  <span aria-current="page" data-site-downloads>Downloads</span></p>
<div class="themeControls"><button type="button" id="settingsButton" class="themeSettings" aria-haspopup="dialog" aria-expanded="false" aria-controls="obdSettingsPanel">Settings</button></div></div>
<main class="downloads" id="Top">{logo}<h1>{esc(title)}</h1>{intro}
<p>Translation draft {esc(catalogue.get('draft_version') or 'in progress')}.</p><nav aria-label="PDF editions">{shortcuts}</nav>
{''.join(sections)}</main></body></html>
'''
