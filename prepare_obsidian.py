"""Stage Docling figures for an Obsidian note without overwriting the vault."""
from pathlib import Path
from urllib.parse import unquote, urlsplit, quote
import argparse
import hashlib
import json
import re
import shutil


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', type=Path, required=True, help='Existing Obsidian vault root')
    parser.add_argument('--conversion', type=Path, required=True)
    parser.add_argument('--note', type=Path, required=True)
    parser.add_argument('--stage', type=Path, required=True)
    args = parser.parse_args()
    vault = args.vault.resolve(strict=True)
    if not vault.is_dir():
        parser.error('--vault must be an existing directory')
    note = args.note.resolve()
    if not note.is_relative_to(vault) or note.suffix.lower() != '.md':
        parser.error('--note must name the intended Markdown note inside --vault')
    stage = args.stage.resolve()
    if stage.is_relative_to(vault):
        parser.error('--stage must stay outside the reading vault')
    if stage.exists() and any(stage.iterdir()):
        parser.error('Use an empty staging directory; do not overwrite reviewed assets')
    conversion = args.conversion.resolve()
    receipt = json.loads((conversion / 'conversion.json').read_text(encoding='utf-8'))
    if receipt['status'] != 'converted_unverified':
        parser.error('Conversion must have passed the structural checks first')
    for entry in receipt['outputs']:
        file = (conversion / entry['path']).resolve()
        if not file.is_relative_to(conversion) or sha(file) != entry['sha256']:
            parser.error('Conversion output hash mismatch or path escape')
    document_path = next(p for p in conversion.glob('*.json') if p.name != 'conversion.json')
    document = json.loads(document_path.read_text(encoding='utf-8'))
    asset_root = note.parent.relative_to(vault) / 'assets' / note.stem
    rows, snippets, used_names = [], [], set()
    stage.mkdir(parents=True, exist_ok=True)
    for index, picture in enumerate(document.get('pictures', []), 1):
        page = picture['prov'][0]['page_no']
        captions = []
        for ref in picture.get('captions', []):
            value = document
            for key in ref['$ref'].removeprefix('#/').split('/'):
                value = value[int(key)] if isinstance(value, list) else value[key]
            captions.append(value.get('text', ''))
        caption = ' '.join(captions)
        number = re.search(r'\b(?:Figure|Fig\.)\s+([A-Za-z]?\.?\d+)', caption)
        figure_id = number.group(1) if number else f'page-{page:02d}-picture-{index:02d}'
        filename = f'figure-{figure_id}.png'
        if filename in used_names:
            filename = f'figure-{figure_id}-page-{page:02d}-picture-{index:02d}.png'
        used_names.add(filename)
        uri = picture.get('image', {}).get('uri')
        if not uri:
            raise ValueError(f'Missing exported image for {picture["self_ref"]}')
        if uri.startswith('file:'):
            parsed = urlsplit(uri)
            if parsed.netloc:
                raise ValueError('Network image URI is not allowed')
            uri = unquote(parsed.path)
            if re.match(r'^/[A-Za-z]:/', uri):
                uri = uri[1:]
        source = (conversion / Path(uri)).resolve()
        if not source.is_file() or not source.is_relative_to(conversion):
            raise ValueError('Picture is absent or outside the conversion directory')
        destination = stage / asset_root / filename
        existing = vault / asset_root / filename
        if existing.exists() and sha(existing) != sha(source):
            raise FileExistsError(f'Existing vault asset differs; review explicitly: {existing}')
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        relative_link = (Path('assets') / note.stem / filename).as_posix()
        link = quote(relative_link, safe='/._-')
        snippets.append(f'![Figure {figure_id}，原文第 {page} 頁]({link})\n\n來源：原始 PDF 第 {page} 頁，Figure {figure_id}。\n\n原圖說（未校訂）：{caption}\n')
        rows.append(dict(figure_id=figure_id, source_page=page, docling_ref=picture['self_ref'],
                         bbox=picture['prov'][0]['bbox'], caption_unverified=caption,
                         vault_relative_path=(asset_root / filename).as_posix(),
                         markdown_relative_path=relative_link, sha256=sha(destination)))
    (stage / 'figure-map.md').write_text('\n\n'.join(snippets), encoding='utf-8')
    manifest = dict(status='staged_unverified', source=receipt['source'], source_sha256=receipt['source_sha256'],
                    conversion_receipt=str(conversion/'conversion.json'), target_note=str(note), figures=rows,
                    scope='Only converted pages; verify crops/captions before placing into the vault. No note overwritten.')
    (stage / 'asset-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(stage=str(stage), figures=len(rows), target_note=str(note)), ensure_ascii=False))


if __name__ == '__main__':
    main()
