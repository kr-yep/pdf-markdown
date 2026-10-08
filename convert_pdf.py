"""Local Docling entry point with source hashes, safe reuse and failure receipts."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote, unquote, urlsplit


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--pages', help='Inclusive source page range, e.g. 1-6')
    parser.add_argument('--full-page-ocr', action='store_true')
    parser.add_argument('--enrich-formula', action='store_true')
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--timeout-seconds', type=int, default=1800)
    args = parser.parse_args()
    source = args.pdf.resolve(strict=True)
    if source.suffix.lower() != '.pdf' or not source.is_file():
        parser.error('Provide one local PDF file. Download and register remote sources first.')
    if args.pages and not re.fullmatch(r'[1-9]\d*(?:-[1-9]\d*)?', args.pages):
        parser.error('--pages must be an inclusive positive range, e.g. 1-6')
    if args.pages and '-' in args.pages:
        low, high = map(int, args.pages.split('-'))
        if low > high:
            parser.error('Page range must be ascending')
    if not 1 <= args.threads <= 32 or args.timeout_seconds < 30:
        parser.error('Invalid thread count or timeout')

    tool_root = Path(__file__).resolve().parent
    version = importlib.metadata.version('docling')
    settings = dict(version=version, wrapper_sha256=digest(Path(__file__)), pages=args.pages, full_page_ocr=args.full_page_ocr,
                    formula=args.enrich_formula, device='cpu', threads=args.threads,
                    pipeline='standard', ocr_engine='rapidocr', tables=True)
    source_hash = digest(source)
    key = hashlib.sha256((source_hash + json.dumps(settings, sort_keys=True)).encode()).hexdigest()[:16]
    output = (args.output or tool_root / 'outputs' / key).resolve()
    receipt_path = output / 'conversion.json'
    if output.exists() and any(output.iterdir()):
        if receipt_path.is_file():
            old = json.loads(receipt_path.read_text(encoding='utf-8'))
            files = old.get('outputs', [])
            if (old.get('status') == 'converted_unverified' and old.get('source_sha256') == source_hash
                    and old.get('settings') == settings and files
                    and all((output / x['path']).is_file() and digest(output / x['path']) == x['sha256'] for x in files)):
                print(json.dumps(dict(reused=True, output=str(output), receipt=str(receipt_path)), ensure_ascii=False))
                return 0
        raise FileExistsError(f'Output is nonempty or has incomplete/changed evidence: {output}. Use a fresh output directory; preserve failed evidence.')
    output.mkdir(parents=True, exist_ok=True)
    cli = Path(sys.executable).parent / ('docling.exe' if os.name == 'nt' else 'docling')
    command = [str(cli), 'convert', str(source), '--to', 'md', '--to', 'json',
               '--output', str(output), '--image-export-mode', 'referenced',
               '--pipeline', 'standard', '--device', 'cpu', '--num-threads', str(args.threads),
               '--ocr-engine', 'rapidocr', '--ocr', '--tables', '--abort-on-error']
    if args.pages:
        command += ['--page-range', args.pages]
    if args.full_page_ocr:
        command += ['--ocr-mode', 'full_page']
    if args.enrich_formula:
        command += ['--enrich-formula']
    record = dict(status='running', source=str(source), source_sha256=source_hash,
                  started_utc=datetime.now(timezone.utc).isoformat(), settings=settings,
                  command=command, content_verified=False)
    def save() -> None:
        receipt_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    save()
    started = time.monotonic()
    try:
        env = os.environ.copy()
        env['PYTHONUTF8'] = '1'
        with (output / 'docling.log').open('w', encoding='utf-8') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env,
                                    timeout=args.timeout_seconds, check=False)
        record['exit_code'] = result.returncode
        if result.returncode:
            raise RuntimeError(f'Docling exit {result.returncode}; see {output / "docling.log"}')
        md_files = list(output.glob('*.md'))
        json_files = [p for p in output.glob('*.json') if p != receipt_path]
        if len(md_files) != 1 or len(json_files) != 1 or not md_files[0].read_text(encoding='utf-8').strip():
            raise RuntimeError('Expected one nonempty Markdown and one structured JSON document')
        doc = json.loads(json_files[0].read_text(encoding='utf-8'))
        if not doc.get('pages'):
            raise RuntimeError('No page provenance in the structured document')
        # Normalize actual image links, including Windows file URIs and escaped spaces.
        markdown = md_files[0].read_text(encoding='utf-8')
        def normalize_image(match: re.Match) -> str:
            target = match.group(2).strip('<>')
            parsed = urlsplit(target)
            if parsed.scheme == 'file':
                if parsed.netloc:
                    raise RuntimeError('Network image paths are not expected in local conversion')
                raw_path = unquote(parsed.path)
                if re.match(r'^/[A-Za-z]:/', raw_path):
                    raw_path = raw_path[1:]
                asset = Path(raw_path)
            elif parsed.scheme in ('http', 'https', 'data'):
                raise RuntimeError(f'Unexpected nonlocal image reference: {target[:80]}')
            else:
                asset = Path(unquote(target))
            asset = (output / asset).resolve()
            if not asset.is_file() or not asset.is_relative_to(output):
                raise RuntimeError(f'Missing or nonlocal image asset: {target}')
            relative = quote(asset.relative_to(output).as_posix(), safe='/._-')
            return f'![{match.group(1)}]({relative})'
        markdown = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', normalize_image, markdown)
        md_files[0].write_text(markdown, encoding='utf-8')
        if digest(source) != source_hash:
            raise RuntimeError('Source PDF changed during conversion')
        record.update(status='converted_unverified', converted_pages=sorted(map(int, doc['pages'])),
                      tables=len(doc.get('tables', [])), pictures=len(doc.get('pictures', [])),
                      formulas=sum(t.get('label') == 'formula' for t in doc.get('texts', [])))
        record['outputs'] = [dict(path=p.relative_to(output).as_posix(), bytes=p.stat().st_size, sha256=digest(p))
                             for p in sorted(output.rglob('*')) if p.is_file() and p != receipt_path]
    except Exception as exc:
        record.update(status='failed', error=f'{type(exc).__name__}: {exc}')
    record['elapsed_seconds'] = round(time.monotonic() - started, 3)
    save()
    print(json.dumps(dict(status=record['status'], output=str(output), receipt=str(receipt_path),
                          error=record.get('error')), ensure_ascii=False))
    return 0 if record['status'] == 'converted_unverified' else 1


if __name__ == '__main__':
    raise SystemExit(main())
