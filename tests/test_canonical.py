from __future__ import annotations

import textwrap
import unittest

from cartero.canonical import (
    DuplicateTopLevelBlockError,
    EmbeddedDelimiterError,
    EmptyRecordError,
    EmptyRequiredBlockError,
    InvalidBlockOrderError,
    InvalidDelimiterSpacingError,
    InvalidEmptyMarkerError,
    MalformedFAQItemError,
    MalformedKBItemError,
    MissingRecordEndDelimiterError,
    MissingRecordStartDelimiterError,
    MissingTopLevelBlockError,
    parse_canonical_record,
    validate_canonical_record,
)


def _build_record(
    *,
    summary: str,
    changelog: str,
    faq: str,
    knowledge_base: str,
) -> str:
    return "\n".join(
        [
            "<<<CARTERO_RECORD_V1>>>",
            "<<<SUMMARY>>>",
            summary,
            "<<<END_SUMMARY>>>",
            "<<<CHANGELOG>>>",
            changelog,
            "<<<END_CHANGELOG>>>",
            "<<<FAQ>>>",
            faq,
            "<<<END_FAQ>>>",
            "<<<KNOWLEDGE_BASE>>>",
            knowledge_base,
            "<<<END_KNOWLEDGE_BASE>>>",
            "<<<END_CARTERO_RECORD_V1>>>",
        ]
    )


VALID_MINIMAL_RECORD = _build_record(
    summary="Cartero now shows a real changelog preview before execution.",
    changelog=(
        "Cartero now shows the real changelog preview before execution.\n\n"
        "- Users can review the external-facing text before moving forward"
    ),
    faq="NONE",
    knowledge_base="NONE",
)

VALID_FULL_RECORD = _build_record(
    summary="Cartero now preserves a reusable communication record for documentation outputs.",
    changelog=(
        "Cartero now stores a reusable communication record for downstream outputs.\n\n"
        "- FAQ and knowledge base content can be prepared from the same source record\n"
        "- Release communication stays aligned across output surfaces"
    ),
    faq=textwrap.dedent(
        """\
        <<<FAQ_ITEM>>>
        Q:
        What changed in the documentation flow?
        A:
        Cartero now keeps a structured communication record that downstream outputs can reuse.
        <<<END_FAQ_ITEM>>>
        <<<FAQ_ITEM>>>
        Q:
        Does this change execution behavior?
        A:
        No. This layer only validates and parses the canonical communication record.
        <<<END_FAQ_ITEM>>>"""
    ),
    knowledge_base=textwrap.dedent(
        """\
        <<<KB_ITEM>>>
        TITLE:
        Canonical record purpose
        BODY:
        The canonical record is the internal source of truth for communication outputs.
        It is parsed in memory and stays independent from the current JSON and YAML pipeline.
        <<<END_KB_ITEM>>>
        <<<KB_ITEM>>>
        TITLE:
        FAQ and knowledge base scope
        BODY:
        FAQ and knowledge base blocks are part of the contract even when a surface does not use them yet.
        <<<END_KB_ITEM>>>"""
    ),
)


class CanonicalRecordValidTests(unittest.TestCase):
    def test_parses_valid_record_with_empty_faq_and_knowledge_base(self) -> None:
        record = parse_canonical_record(VALID_MINIMAL_RECORD)

        self.assertEqual(
            record.summary,
            "Cartero now shows a real changelog preview before execution.",
        )
        self.assertEqual(record.faq_items, ())
        self.assertEqual(record.knowledge_base_items, ())

    def test_parses_valid_record_with_faq_and_knowledge_base_items(self) -> None:
        record = parse_canonical_record(VALID_FULL_RECORD)

        self.assertEqual(len(record.faq_items), 2)
        self.assertEqual(
            record.faq_items[0].question,
            "What changed in the documentation flow?",
        )
        self.assertEqual(len(record.knowledge_base_items), 2)
        self.assertEqual(
            record.knowledge_base_items[0].title,
            "Canonical record purpose",
        )

    def test_normalizes_windows_newlines(self) -> None:
        record = parse_canonical_record(VALID_MINIMAL_RECORD.replace("\n", "\r\n"))

        self.assertTrue(record.changelog.startswith("Cartero now shows"))

    def test_structure_layer_does_not_validate_language_semantics(self) -> None:
        non_english_record = _build_record(
            summary="Cartero ahora muestra un changelog antes de la ejecución.",
            changelog="Cartero ahora muestra una vista previa real antes de continuar.",
            faq="NONE",
            knowledge_base="NONE",
        )

        record = parse_canonical_record(non_english_record)

        self.assertIn("ahora", record.summary)

    def test_validate_canonical_record_accepts_valid_input(self) -> None:
        validate_canonical_record(VALID_MINIMAL_RECORD)


class CanonicalRecordInvalidTests(unittest.TestCase):
    def test_rejects_empty_document(self) -> None:
        with self.assertRaises(EmptyRecordError):
            parse_canonical_record("  \n\t")

    def test_rejects_missing_record_start_delimiter(self) -> None:
        invalid = "\n".join(VALID_MINIMAL_RECORD.splitlines()[1:])

        with self.assertRaises(MissingRecordStartDelimiterError):
            parse_canonical_record(invalid)

    def test_rejects_missing_record_end_delimiter(self) -> None:
        invalid = "\n".join(VALID_MINIMAL_RECORD.splitlines()[:-1])

        with self.assertRaises(MissingRecordEndDelimiterError):
            parse_canonical_record(invalid)

    def test_rejects_top_level_block_out_of_order(self) -> None:
        invalid = "\n".join(
            [
                "<<<CARTERO_RECORD_V1>>>",
                "<<<SUMMARY>>>",
                "Cartero now shows a real changelog preview before execution.",
                "<<<END_SUMMARY>>>",
                "<<<FAQ>>>",
                "NONE",
                "<<<END_FAQ>>>",
                "<<<CHANGELOG>>>",
                "Cartero now shows the real changelog preview before execution.",
                "<<<END_CHANGELOG>>>",
                "<<<KNOWLEDGE_BASE>>>",
                "NONE",
                "<<<END_KNOWLEDGE_BASE>>>",
                "<<<END_CARTERO_RECORD_V1>>>",
            ]
        )

        with self.assertRaises(InvalidBlockOrderError):
            parse_canonical_record(invalid)

    def test_rejects_duplicate_top_level_block(self) -> None:
        invalid = "\n".join(
            [
                "<<<CARTERO_RECORD_V1>>>",
                "<<<SUMMARY>>>",
                "Cartero now shows a real changelog preview before execution.",
                "<<<END_SUMMARY>>>",
                "<<<CHANGELOG>>>",
                "Cartero now shows the real changelog preview before execution.",
                "<<<END_CHANGELOG>>>",
                "<<<CHANGELOG>>>",
                "Cartero repeats the changelog block.",
                "<<<END_CHANGELOG>>>",
                "<<<FAQ>>>",
                "NONE",
                "<<<END_FAQ>>>",
                "<<<KNOWLEDGE_BASE>>>",
                "NONE",
                "<<<END_KNOWLEDGE_BASE>>>",
                "<<<END_CARTERO_RECORD_V1>>>",
            ]
        )

        with self.assertRaises(DuplicateTopLevelBlockError):
            parse_canonical_record(invalid)

    def test_rejects_missing_top_level_block(self) -> None:
        invalid = "\n".join(
            [
                "<<<CARTERO_RECORD_V1>>>",
                "<<<SUMMARY>>>",
                "Cartero now shows a real changelog preview before execution.",
                "<<<END_SUMMARY>>>",
                "<<<CHANGELOG>>>",
                "Cartero now shows the real changelog preview before execution.",
                "<<<END_CHANGELOG>>>",
                "<<<FAQ>>>",
                "NONE",
                "<<<END_FAQ>>>",
                "<<<END_CARTERO_RECORD_V1>>>",
            ]
        )

        with self.assertRaises(MissingTopLevelBlockError):
            parse_canonical_record(invalid)

    def test_rejects_none_mixed_with_content(self) -> None:
        invalid = _build_record(
            summary="Cartero now shows a real changelog preview before execution.",
            changelog="Cartero now shows the real changelog preview before execution.",
            faq="NONE\n<<<FAQ_ITEM>>>\nQ:\nWhat changed?\nA:\nThe preview is visible.\n<<<END_FAQ_ITEM>>>",
            knowledge_base="NONE",
        )

        with self.assertRaises(InvalidEmptyMarkerError):
            parse_canonical_record(invalid)

    def test_rejects_malformed_faq_item(self) -> None:
        invalid = _build_record(
            summary="Cartero now shows a real changelog preview before execution.",
            changelog="Cartero now shows the real changelog preview before execution.",
            faq="<<<FAQ_ITEM>>>\nQ:\nWhat changed?\n<<<END_FAQ_ITEM>>>",
            knowledge_base="NONE",
        )

        with self.assertRaises(MalformedFAQItemError):
            parse_canonical_record(invalid)

    def test_rejects_malformed_kb_item(self) -> None:
        invalid = _build_record(
            summary="Cartero now shows a real changelog preview before execution.",
            changelog="Cartero now shows the real changelog preview before execution.",
            faq="NONE",
            knowledge_base="<<<KB_ITEM>>>\nTITLE:\nCanonical purpose\n<<<END_KB_ITEM>>>",
        )

        with self.assertRaises(MalformedKBItemError):
            parse_canonical_record(invalid)

    def test_rejects_embedded_delimiter_inside_content(self) -> None:
        invalid = _build_record(
            summary="Cartero now shows a real changelog preview before execution.\n<<<FAQ>>>",
            changelog="Cartero now shows the real changelog preview before execution.",
            faq="NONE",
            knowledge_base="NONE",
        )

        with self.assertRaises(EmbeddedDelimiterError):
            parse_canonical_record(invalid)

    def test_rejects_delimiter_with_extra_spacing(self) -> None:
        invalid = VALID_MINIMAL_RECORD.replace("<<<SUMMARY>>>", " <<<SUMMARY>>>", 1)

        with self.assertRaises(InvalidDelimiterSpacingError):
            parse_canonical_record(invalid)

    def test_rejects_empty_summary(self) -> None:
        invalid = _build_record(
            summary="",
            changelog="Cartero now shows the real changelog preview before execution.",
            faq="NONE",
            knowledge_base="NONE",
        )

        with self.assertRaises(EmptyRequiredBlockError):
            parse_canonical_record(invalid)

    def test_rejects_empty_changelog(self) -> None:
        invalid = _build_record(
            summary="Cartero now shows a real changelog preview before execution.",
            changelog="",
            faq="NONE",
            knowledge_base="NONE",
        )

        with self.assertRaises(EmptyRequiredBlockError):
            parse_canonical_record(invalid)
