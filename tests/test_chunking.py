"""Offline checks for source preservation across the pipeline reorganization."""
import json
from pathlib import Path
import unittest

from chunking.character import chunk_sections
from chunking.semantic import chunk_semantic
from data_pipeline.cleaner import split_into_sections
from data_pipeline.scraper import load_urls
from scraper.scrape import split_into_sections as legacy_split


class PipelineStructureTests(unittest.TestCase):
    def test_character_chunks_preserve_source_spans(self):
        sections = json.loads(Path('data/samples/sections.json').read_text(encoding='utf-8'))
        chunks = chunk_sections(sections)
        self.assertTrue(chunks)
        for chunk in chunks:
            source = sections[chunk['section_id']]
            self.assertEqual(chunk['text'], source['text'][chunk['start']:chunk['end']])
            self.assertEqual(chunk['source_url'], source['source_url'])
            self.assertEqual(chunk['heading'], source['heading'])

    def test_cleaner_and_legacy_import_preserve_behavior(self):
        body = 'A supported sales recommendation with enough context. ' * 3
        html = '<title>Guide</title><main><nav>Menu</nav><h2>Qualification</h2><p>' + body + '</p><p>Subscribe to our newsletter</p></main>'
        result = split_into_sections(html, 'https://example.com/guide')
        self.assertEqual(result, legacy_split(html, 'https://example.com/guide'))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['heading'], 'Qualification')
        self.assertEqual(result[0]['text'], body.strip())
        self.assertEqual(result[0]['source_url'], 'https://example.com/guide')

    def test_seed_url_list_still_loads(self):
        self.assertEqual(len(load_urls(['data/urls/demo_seed.txt'])), 1)

    def test_semantic_offsets_without_model_download(self):
        class FixedChunker:
            def split_text(self, text):
                return ['First sentence. Second sentence.', 'Third sentence. Fourth sentence.']
        text = 'First sentence.  Second sentence.\nThird sentence. Fourth sentence.'
        spans = chunk_semantic(text, FixedChunker(), min_chunk_chars=1)
        self.assertEqual([text[a:b] for a, b in spans],
                         ['First sentence.  Second sentence.', 'Third sentence. Fourth sentence.'])


if __name__ == '__main__':
    unittest.main()
