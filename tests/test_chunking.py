"""Offline checks for source preservation across the pipeline reorganization."""
import json
from pathlib import Path
import unittest

from chunking.character import chunk_sections
from chunking.semantic import chunk_semantic


class PipelineStructureTests(unittest.TestCase):
    def test_character_chunks_preserve_source_spans(self):
        sections = json.loads(Path('data/samples/sections.json').read_text())
        chunks = chunk_sections(sections)
        self.assertTrue(chunks)
        for chunk in chunks:
            source = sections[chunk['section_id']]
            self.assertEqual(chunk['text'], source['text'][chunk['start']:chunk['end']])
            self.assertEqual(chunk['source_url'], source['source_url'])
            self.assertEqual(chunk['heading'], source['heading'])

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
