"""Offline pipeline contract tests; no real internal data or network access."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chunking.semantic import chunk_semantic, make_chunker
from data_pipeline.chunker import chunk_documents, main, read_documents

SETTINGS = {'min_chunk_chars': 20, 'max_chunk_chars': 120, 'model': 'test-only', 'threshold': 90}


def document(doc_id='public-example', visibility='public'):
    return {'doc_id': doc_id, 'url': 'https://example.com/guide' if visibility == 'public' else None,
            'title': 'Synthetic sales guide', 'category': 2, 'category_name': 'segmentation_territory',
            'visibility': visibility, 'sensitivity': 'confidential' if visibility == 'internal' else None,
            'source_file': 'invented.txt' if visibility == 'internal' else None,
            'provenance': 'Synthetic test fixture', 'confidence_tags': {'inferred': 1},
            'sections': [{'heading': 'Qualification', 'level': 2,
                          'text': '[INFERRED] Ask who approves the purchase.\n- Confirm the buying process.\n- Record any unknown information.'}]}


class WholeSection:
    def split_text(self, text):
        return [text]


class ChunkPipelineTests(unittest.TestCase):
    def test_preserves_metadata_and_exact_offsets(self):
        doc = document('internal-example', 'internal')
        chunks = chunk_documents([(doc, '/synthetic/input.json')], WholeSection(), SETTINGS)
        self.assertTrue(chunks)
        for chunk in chunks:
            self.assertEqual(chunk['text'], doc['sections'][0]['text'][chunk['start']:chunk['end']])
            self.assertEqual(chunk['visibility'], 'internal')
            self.assertEqual(chunk['sensitivity'], 'confidential')
            self.assertIsNone(chunk['source_url'])
            self.assertEqual(chunk['source_metadata']['confidence_tags'], {'inferred': 1})
            self.assertEqual(chunk['provenance'], 'Synthetic test fixture')
        self.assertEqual(chunks[0]['tags'], ['INFERRED'])

    def test_stable_ids_when_documents_reordered(self):
        one, two = document('one'), document('two')
        before = chunk_documents([(one, 'one.json'), (two, 'two.json')], WholeSection(), SETTINGS)
        after = chunk_documents([(two, 'two.json'), (one, 'one.json')], WholeSection(), SETTINGS)
        self.assertEqual({c['chunk_id'] for c in before}, {c['chunk_id'] for c in after})
        edited = deepcopy(one)
        edited['sections'][0]['text'] += ' Changed.'
        new = chunk_documents([(edited, 'one.json')], WholeSection(), SETTINGS)
        self.assertNotEqual(before[0]['chunk_id'], new[0]['chunk_id'])

    def test_never_combines_sections_and_bounds_long_text(self):
        doc = document()
        doc['sections'] = [{'heading': 'A', 'text': 'Long table row without punctuation ' * 60},
                           {'heading': 'B', 'text': 'Other section.'}, {'heading': 'Empty', 'text': '  '}]
        chunks = chunk_documents([(doc, 'doc.json')], WholeSection(), SETTINGS)
        self.assertEqual({c['heading'] for c in chunks}, {'A', 'B'})
        for i, section in enumerate(doc['sections'][:2]):
            pieces = [c for c in chunks if c['section_index'] == i]
            self.assertEqual(''.join(''.join(c['text'].split()) for c in pieces), ''.join(section['text'].split()))
            self.assertTrue(all(c['char_count'] <= 120 for c in pieces))
        self.assertTrue(any(c['size_limited'] for c in chunks))

    def test_splitter_omission_is_rejected(self):
        class DropsBeginning:
            def split_text(self, text):
                return ['Second sentence. Third sentence. Fourth sentence.']
        with self.assertRaises(ValueError):
            chunk_semantic('First sentence. Second sentence. Third sentence. Fourth sentence.', DropsBeginning(), 1)

    def test_input_contract_and_legacy_format(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'doc.json'
            doc = document()
            path.write_text(json.dumps(doc))
            self.assertEqual(len(read_documents([str(path)])), 1)
            doc['visibility'] = 'internal'
            doc['sensitivity'] = None
            path.write_text(json.dumps(doc))
            with self.assertRaises(ValueError):
                read_documents([str(path)])
            path.write_text(json.dumps([{'source_url': 'https://example.com', 'text': 'Guide', 'heading': 'Title'}]))
            self.assertEqual(read_documents([str(path)])[0][0]['visibility'], 'public')
            path.write_text('[]')
            with self.assertRaises(ValueError):
                read_documents([str(path)])

    def test_cli_writes_json_summary_and_preserves_output_on_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary) / 'input.json', Path(temporary) / 'chunks.json'
            source.write_text(json.dumps(document()))
            with patch('data_pipeline.chunker.load_embeddings', return_value=object()), patch('data_pipeline.chunker.make_chunker', return_value=WholeSection()):
                status = main(['--input', str(source), '--output', str(output), '--max-chunk-chars', '250'])
            self.assertEqual(status, 0)
            before = output.read_text()
            self.assertTrue(json.loads(before))
            self.assertEqual(json.loads(output.with_suffix('.summary.json').read_text())['documents'], 1)
            source.write_text('{}')
            self.assertEqual(main(['--input', str(source), '--output', str(output)]), 1)
            self.assertEqual(output.read_text(), before)

    def test_heading_context_and_confidence_tags_are_not_invented(self):
        doc = document()
        doc['sections'] = [
            {'heading': 'Method', 'level': 1, 'text': ''},
            {'heading': 'Qualification', 'level': 2, 'text': 'Confirm the buyer.'},
            {'heading': 'Territory', 'level': 2, 'text': '[UNKNOWN] The owner is unspecified.'},
        ]
        chunks = chunk_documents([(doc, 'synthetic.json')], WholeSection(), SETTINGS)
        self.assertEqual(chunks[0]['heading_path'], ['Method', 'Qualification'])
        self.assertEqual(chunks[1]['heading_path'], ['Method', 'Territory'])
        self.assertEqual(chunks[0]['tags'], [])
        self.assertEqual(chunks[1]['tags'], ['UNKNOWN'])
        self.assertNotIn('role', chunks[0])

    def test_generated_output_cannot_be_written_to_samples(self):
        with patch('data_pipeline.chunker.load_embeddings') as model:
            self.assertEqual(main(['--input', 'data/samples/sections.json',
                                   '--output', 'data/samples/unsafe_chunks.json']), 1)
            model.assert_not_called()

    def test_conflicting_document_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            one = document()
            two = deepcopy(one)
            two['sections'][0]['text'] = 'Different source content.'
            for name, doc in [('one', one), ('two', two)]:
                (Path(temporary) / (name + '.json')).write_text(json.dumps(doc))
            with self.assertRaises(ValueError):
                read_documents([temporary])

    def test_real_langchain_splitter_with_deterministic_embeddings(self):
        # Tests the installed SemanticChunker API without downloading a model.
        class LocalEmbeddings:
            def embed_documents(self, texts):
                return [[1.0, float('territory' in t.lower()), float('qualify' in t.lower())] for t in texts]
        splitter = make_chunker(LocalEmbeddings(), threshold=50, min_chunk_chars=1)
        text = 'Qualify the buyer. Qualify the opportunity. Design the territory. Review territory coverage.'
        spans = chunk_semantic(text, splitter, min_chunk_chars=1)
        self.assertTrue(spans)
        self.assertEqual(''.join(''.join(text[a:b].split()) for a, b in spans), ''.join(text.split()))


if __name__ == '__main__':
    unittest.main()
