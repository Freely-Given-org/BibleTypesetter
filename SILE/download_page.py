"""Render a static download index from the same catalogue used by other sites."""
from html import escape


def download_page(catalogue, settings):
    esc = lambda value: escape(str(value), quote=True)
    def table(entries, caption):
        rows = []
        for entry in entries:
            title = f'{entry["title"]} ({entry["id"]})' if entry['kind'] == 'book' else entry['title']
            cells = []
            for medium, label in [('print', 'Print'), ('screen', 'Online')]:
                file = entry[medium]
                cells.append(f'<td><a href="{esc(file["url"])}" aria-label="{esc(title)} — {label} PDF">'
                             f'{label} PDF</a><small>{file["bytes"] / 1048576:.1f} MB · {file["pages"]:,} pages</small></td>')
            rows.append(f'<tr><th scope="row">{esc(title)}</th>{"".join(cells)}</tr>')
        return f'<div class="table-wrap"><table><caption>{esc(caption)}</caption><thead><tr><th scope="col">Title</th><th scope="col">Print</th><th scope="col">Online</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    entries = catalogue['entries']
    sections = [table([e for e in entries if e['kind'] == 'collection'], 'Collections')]
    sections.append('<h2>Individual books</h2>')
    for group in catalogue['groups']:
        books = [e for e in entries if e['kind'] == 'book' and e['group'] == group['id']]
        sections.append(f'<details><summary>{esc(group["title"])} ({len(books)} books)</summary>'
                        + table(books, group['title']) + '</details>')
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
.downloads th:first-child {{ width:46%; }}
.downloads tbody th {{ font-weight:normal; }}
.downloads td small {{ display:block; margin-top:.2rem; white-space:nowrap; }}
.downloads details {{ margin:1rem 0; }}
.downloads summary {{ cursor:pointer; font-weight:bold; padding:.5rem 0; }}
</style></head><body class="container" data-page-type="downloads">
<div class="topLine"><p class="site">{navigation}  <span aria-current="page" data-site-downloads>Downloads</span></p>
<div class="themeControls"><button type="button" id="settingsButton" class="themeSettings" aria-haspopup="dialog" aria-expanded="false" aria-controls="obdSettingsPanel">Settings</button></div></div>
<main class="downloads" id="Top">{logo}<h1>{esc(title)}</h1>{intro}
<p>Translation draft {esc(catalogue.get('draft_version') or 'in progress')} · {esc(catalogue['paper_size'])} pages.</p>
{''.join(sections)}</main></body></html>
'''
