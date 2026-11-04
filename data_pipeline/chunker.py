"""Chunk clean public/internal documents, retaining provenance and access labels.

Run ``python -m data_pipeline.chunker --help`` from the repository root.
No extraction, inferred topic tagging, or knowledge-unit embedding happens here.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import logging
import os
from pathlib import Path
import re

from chunking.semantic import chunk_semantic, load_embeddings, make_chunker, MODEL_NAME

logger = logging.getLogger(__name__)
TAG_PATTERN = re.compile(r'\[(INFERRED|UNKNOWN|IN TITLE)\]', re.IGNORECASE)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def read_documents(inputs):
    """Read clean-doc files/directories or the legacy exported section array.

    Return (document, path) pairs. Explicit paths avoid silently mixing public and
    internal corpora. Input errors fail the run before any output is replaced.
    """
    documents = []
    seen = {}
    paths = []
    for name in inputs:
        path = Path(name)
        if not path.exists():
            raise ValueError(f'Input does not exist: {path}')
        paths.extend(sorted(path.glob('*.json')) if path.is_dir() else [path])
    if not paths:
        raise ValueError('No input JSON documents found')
    for path in dict.fromkeys(paths):
        value = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(value, list):
            # Old public export: do not use this format for internal documents.
            grouped = {}
            for section in value:
                if not isinstance(section, dict) or not section.get('source_url'):
                    raise ValueError('Legacy sections require a public source_url')
                if section.get('visibility', 'public') != 'public' or section.get('sensitivity'):
                    raise ValueError('Use clean-doc JSON for internal/sensitive documents')
                url = section['source_url']
                key = section.get('doc_id') or digest(url)[:16]
                doc = grouped.setdefault(key, {
                    'doc_id': key, 'url': url, 'title': section.get('page_title'),
                    'domain': section.get('domain'), 'category': section.get('category'),
                    'category_name': section.get('category_name'),
                    'scraped_at': section.get('scraped_at'), 'visibility': 'public',
                    'sections': [],
                })
                doc['sections'].append({'heading': section.get('heading'), 'level': None,
                                        'text': section['text']})
            values = list(grouped.values())
        else:
            values = [value]
        for doc in values:
            if not isinstance(doc, dict) or not isinstance(doc.get('doc_id'), str) or not doc['doc_id']:
                raise ValueError('Clean docs require a nonempty doc_id')
            if doc.get('visibility') not in ('public', 'internal'):
                raise ValueError(f"Document {doc['doc_id']} requires explicit visibility")
            if doc['visibility'] == 'internal' and doc.get('sensitivity') not in ('internal', 'confidential'):
                raise ValueError(f"Internal document {doc['doc_id']} requires sensitivity")
            if doc['visibility'] == 'public' and doc.get('sensitivity') not in (None, '', 'public'):
                raise ValueError('Public visibility conflicts with document sensitivity')
            if not isinstance(doc.get('sections'), list):
                raise ValueError('Clean docs require a sections array')
            for section in doc['sections']:
                if not isinstance(section, dict) or not isinstance(section.get('text'), str):
                    raise ValueError('Each section requires string text')
            if doc['doc_id'] in seen:
                if seen[doc['doc_id']] != doc:
                    raise ValueError(f"Conflicting documents share doc_id {doc['doc_id']}")
                continue
            seen[doc['doc_id']] = doc
            documents.append((doc, str(path)))
    if not documents:
        raise ValueError('No documents found; refusing to replace previous output')
    return documents


def bound_spans(text, spans, max_chars):
    """Split oversized semantic spans at a paragraph, sentence, word, then char.

    Only whitespace between chunks may be omitted. Safety splits are flagged in
    the output because they may divide a sentence/list/table. This is a character
    ceiling, not a guarantee about any downstream model's token window.
    """
    result = []
    for start, end in spans:
        limited = end - start > max_chars
        while start < end:
            while start < end and text[start].isspace():
                start += 1
            if start == end:
                break
            stop = min(start + max_chars, end)
            if stop < end:
                fragment = text[start:stop]
                preferred = [m.end() for m in re.finditer(r'\n\s*\n|(?<=[.!?])\s+', fragment)]
                words = [m.start() for m in re.finditer(r'\s+', fragment)]
                cuts = [i for i in preferred if i >= max_chars // 2]
                if cuts:
                    stop = start + cuts[-1]
                elif words:
                    stop = start + words[-1]
            trimmed = stop
            while trimmed > start and text[trimmed - 1].isspace():
                trimmed -= 1
            if trimmed > start:
                result.append((start, trimmed, limited))
            start = stop
    return result


def chunk_documents(documents, chunker, settings):
    """Return records with offsets into the exact original section text."""
    records = []
    for doc, source_path in documents:
        before = len(records)
        source_metadata = {k: deepcopy(v) for k, v in doc.items() if k not in ('sections', 'text')}
        heading_stack = []
        for section_index, section in enumerate(doc['sections']):
            level, heading = section.get('level'), section.get('heading')
            if heading:
                if isinstance(level, int) and level > 0:
                    heading_stack = [(n, h) for n, h in heading_stack if n < level]
                    heading_stack.append((level, heading))
                else:
                    heading_stack = [(0, heading)]
            text = section['text']
            spans = chunk_semantic(text, chunker, settings['min_chunk_chars'])
            bounded = bound_spans(text, spans, settings['max_chunk_chars'])
            # Prevent a splitter alignment bug from silently dropping meaningful text.
            cursor = 0
            for start, end, _ in bounded:
                if start < cursor or text[cursor:start].strip():
                    raise ValueError(f"Invalid chunk coverage in {doc['doc_id']} section {section_index}")
                cursor = end
            if text[cursor:].strip():
                raise ValueError(f"Incomplete chunk coverage in {doc['doc_id']} section {section_index}")
            section_hash = digest(text)
            section_id = f"{doc['doc_id']}:section:{section_index}"
            for chunk_index, (start, end, safety_split) in enumerate(bounded):
                content = text[start:end]
                identity = json.dumps([doc['doc_id'], section_index, section_hash, start, end, content], ensure_ascii=False)
                tags = sorted({m.group(1).upper().replace(' ', '_') for m in TAG_PATTERN.finditer(content)})
                records.append({
                    'schema_version': '1.0', 'chunk_id': 'sem-' + digest(identity),
                    'doc_id': doc['doc_id'], 'section_id': section_id,
                    'section_index': section_index, 'chunk_index': chunk_index,
                    'strategy': 'semantic', 'source_url': doc.get('url'),
                    'source_file': doc.get('source_file'), 'domain': doc.get('domain'),
                    'page_title': doc.get('title'), 'heading': section.get('heading'),
                    'heading_level': section.get('level'),
                    'heading_path': [h for _, h in heading_stack],
                    'category': doc.get('category'), 'category_name': doc.get('category_name'),
                    'also_categories': deepcopy(doc.get('also_categories', [])),
                    'visibility': doc['visibility'], 'sensitivity': doc.get('sensitivity'),
                    'provenance': doc.get('provenance'), 'tags': tags,
                    'source_metadata': source_metadata, 'source_path': source_path,
                    'section_sha256': section_hash, 'content_sha256': digest(content),
                    'start': start, 'end': end, 'offset_reference': 'section.text',
                    'text': content, 'char_count': len(content),
                    'word_count': len(content.split()), 'size_limited': safety_split,
                    'chunking': dict(settings),
                })
        logger.info('CHUNK: doc_id=%s visibility=%s sections=%s chunks=%s',
                    doc['doc_id'], doc['visibility'], len(doc['sections']), len(records) - before)
    return records


def check_output(path):
    """Keep all generated text under gitignored data/output by default.

    Outside the repository, callers must select an appropriately protected SCC
    directory. Never allow repository output in tracked sample/source directories.
    """
    root = Path(__file__).resolve().parents[1]
    resolved = path.resolve()
    if resolved.is_relative_to(root) and not resolved.is_relative_to(root / 'data/output'):
        raise ValueError('Generated chunks inside the repository must be under data/output/')
    if path.exists() and path.is_dir():
        raise ValueError('Output must be a JSON file')


def package_versions():
    result = {}
    for package in ('langchain-experimental', 'langchain-huggingface', 'sentence-transformers'):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = None
    return result


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('legacy_threshold', nargs='?', type=float, help=argparse.SUPPRESS)
    parser.add_argument('legacy_min_chars', nargs='?', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--input', action='append', dest='inputs', help='Clean JSON file/directory; repeat for multiple inputs')
    parser.add_argument('--output', type=Path, default=Path('data/output/chunking/chunks_semantic.json'))
    parser.add_argument('--threshold', type=float, default=None)
    parser.add_argument('--min-chunk-chars', type=int, default=None)
    parser.add_argument('--max-chunk-chars', type=int, default=2000)
    parser.add_argument('--model', default=os.environ.get('CHUNK_EMBED_MODEL', MODEL_NAME))
    parser.add_argument('--device', default='cpu', help='Sentence Transformers device (default cpu)')
    parser.add_argument('--batch-size', type=int, default=32)
    args = parser.parse_args(argv)
    threshold = args.threshold if args.threshold is not None else (args.legacy_threshold if args.legacy_threshold is not None else 90)
    minimum = args.min_chunk_chars if args.min_chunk_chars is not None else (args.legacy_min_chars if args.legacy_min_chars is not None else 200)
    if not 0 <= threshold <= 100 or minimum < 1 or args.max_chunk_chars < minimum or args.batch_size < 1:
        parser.error('Require threshold 0..100, 1 <= min-chunk-chars <= max-chunk-chars, and batch-size >= 1')
    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    inputs = args.inputs or ([str(Path(os.environ.get('SCRAPER_OUT', 'data/output/scrape')) / 'clean')]
                            if args.legacy_threshold is None else ['data/output/sections.json'])
    try:
        check_output(args.output)
        if args.output.suffix.lower() != '.json':
            raise ValueError('Output must have a .json extension')
        summary_path = args.output.with_suffix('.summary.json')
        documents = read_documents(inputs)
        if any(Path(path).resolve() in (args.output.resolve(), summary_path.resolve()) for _, path in documents):
            raise ValueError('Output must not overwrite an input document')
        settings = {'model': args.model, 'threshold_type': 'percentile', 'threshold': threshold,
                    'min_chunk_chars': minimum, 'max_chunk_chars': args.max_chunk_chars,
                    'buffer_size': 1, 'normalize_embeddings': True, 'device': args.device,
                    'batch_size': args.batch_size, 'packages': package_versions()}
        logger.info('INPUT: %s documents; MODEL: %s; threshold=%s', len(documents), args.model, threshold)
        embeddings = load_embeddings(args.model, device=args.device, batch_size=args.batch_size)
        splitter = make_chunker(embeddings, threshold, minimum)
        records = chunk_documents(documents, splitter, settings)
        if not records:
            raise ValueError('No nonempty chunks; previous output was not replaced')
        summary = {'created_at': datetime.now(timezone.utc).isoformat(), 'documents': len(documents),
                   'chunks': len(records), 'size_limited_chunks': sum(r['size_limited'] for r in records),
                   'visibility_counts': {v: sum(r['visibility'] == v for r in records) for v in ('public', 'internal')},
                   'min_chars': min(r['char_count'] for r in records),
                   'max_chars': max(r['char_count'] for r in records), 'settings': settings}
        write_json(args.output, records)
        write_json(args.output.with_suffix('.summary.json'), summary)
        logger.info('SAVE: %s chunks to %s; summary written alongside output', len(records), args.output)
    except (ValueError, OSError, ImportError) as error:
        # Never print source passages or third-party exception bodies (may contain text).
        logger.error('Chunking failed (%s); check inputs, configuration and installed dependencies. Output is written only after successful chunking.', type(error).__name__)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
