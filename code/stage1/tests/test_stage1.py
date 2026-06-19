"""Stage 1 regression tests — repeatable, offline, no API key.

Locks in what we proved by hand:
- coerce_record fails closed on bad input (the 12-bad-value set + the
  dict-in-text-field bug that escaped the floor),
- enum validation rejects out-of-vocabulary values (object-conditioned parts,
  resolver-owned flags, etc.),
- the directed-detail trigger fires only when blind confidence != "high".

The adapter is mocked, so nothing here touches the network.

Run from code/:  python -m unittest stage1.tests.test_stage1
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stage1 import schema as s
from stage1.vision import see_image_passes


def valid_raw(confidence: str = "high", **overrides):
    """A fully-valid model output dict; override fields per test."""
    raw = {
        "object_seen": "car",
        "object_part_seen": "door",
        "additional_parts_seen": [],
        "issue_type_seen": "dent",
        "severity_seen": "low",
        "valid_image": True,
        "quality_flags": [],
        "looks_manipulated": False,
        "looks_non_original": False,
        "text_seen": False,
        "text_content": "",
        "observation": "A car door with a small dent.",
        "confidence": confidence,
    }
    raw.update(overrides)
    return raw


class MockAdapter:
    """Returns queued raw records; records the prompts it was called with."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []  # (system_prompt, user_prompt) per call

    def see(self, *, image_b64, media_type, system_prompt, user_prompt, schema):
        self.calls.append((system_prompt, user_prompt))
        raw = self.responses[len(self.calls) - 1]
        return raw, {"model": "mock", "input_tokens": 0, "output_tokens": 0}


class TestCoerceFailsClosed(unittest.TestCase):
    def test_twelve_bad_value_set(self):
        repairs = []
        rec = s.coerce_record({
            "object_seen": "truck",                          # invalid -> unknown
            "object_part_seen": "windshield",                # invalid once object unknown
            "additional_parts_seen": ["door", "keyboard"],   # invalid for unknown -> dropped
            "issue_type_seen": "exploded",                   # invalid -> unknown
            "severity_seen": "catastrophic",                 # invalid -> unknown
            "valid_image": "yes",                            # non-bool -> False
            "quality_flags": ["blurry_image", "claim_mismatch"],  # resolver-owned dropped
            "looks_manipulated": True, "looks_non_original": False,
            "text_seen": True, "text_content": "x" * 500,    # capped to 200
            "observation": "a " * 200,                       # capped
            "confidence": "pretty sure",                     # invalid -> low (fail closed)
        }, image_id="img_1", image_ref="r", on_repair=repairs.append)

        self.assertEqual(rec.object_seen, "unknown")
        self.assertEqual(rec.object_part_seen, "unknown")
        self.assertEqual(rec.additional_parts_seen, [])
        self.assertEqual(rec.issue_type_seen, "unknown")
        self.assertEqual(rec.severity_seen, "unknown")
        self.assertIs(rec.valid_image, False)
        self.assertEqual(rec.quality_flags, ["blurry_image"])
        self.assertEqual(rec.confidence, "low")
        self.assertEqual(len(rec.text_content), s.TEXT_CONTENT_CAP)
        self.assertEqual(len(repairs), 12)  # every bad value was repaired & logged

    def test_dict_in_text_fields_fails_closed(self):
        # The bug that escaped the floor: a dict where a string was expected
        # must become "" — not a str()'d "{'type': 'string'}".
        repairs = []
        rec = s.coerce_record(
            valid_raw(observation={"type": "string"}, text_content={"type": "string"}),
            image_id="img_1", image_ref="r", on_repair=repairs.append,
        )
        self.assertEqual(rec.observation, "")
        self.assertEqual(rec.text_content, "")
        self.assertEqual(len(repairs), 2)

    def test_valid_record_needs_no_repair(self):
        repairs = []
        rec = s.coerce_record(valid_raw(), image_id="img_1", image_ref="r",
                              on_repair=repairs.append)
        self.assertEqual(repairs, [])
        self.assertEqual(rec.object_seen, "car")
        self.assertEqual(rec.confidence, "high")


class TestEnumValidation(unittest.TestCase):
    def test_out_of_vocab_rejected(self):
        rec = s.coerce_record(valid_raw(
            object_seen="laptop",
            object_part_seen="windshield",   # car part on a laptop -> unknown
            issue_type_seen="banana",        # not an issue -> unknown
            confidence="meh",                # -> low
            quality_flags=["wrong_object"],  # resolver-owned -> dropped
        ), image_id="i", image_ref="r")
        self.assertEqual(rec.object_part_seen, "unknown")
        self.assertEqual(rec.issue_type_seen, "unknown")
        self.assertEqual(rec.confidence, "low")
        self.assertEqual(rec.quality_flags, [])

    def test_object_conditioned_part_accepted(self):
        rec = s.coerce_record(valid_raw(object_seen="package", object_part_seen="seal"),
                              image_id="i", image_ref="r")
        self.assertEqual(rec.object_seen, "package")
        self.assertEqual(rec.object_part_seen, "seal")

    def test_schema_is_well_formed(self):
        sch = s.vision_output_schema()
        self.assertIs(sch["additionalProperties"], False)
        self.assertEqual(set(sch["required"]), set(sch["properties"]))


class TestDirectedTrigger(unittest.TestCase):
    def setUp(self):
        # A real path is needed (image bytes are read); contents are irrelevant
        # because the adapter is mocked.
        self.tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        self.tmp.write(b"\xff\xd8\xff\xe0not-a-real-jpeg")
        self.tmp.close()
        self.path = Path(self.tmp.name)

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_high_confidence_does_not_trigger(self):
        mock = MockAdapter([valid_raw(confidence="high")])
        passes = see_image_passes(self.path, adapter=mock, use_cache=False)
        self.assertEqual(len(passes), 1)
        self.assertEqual(len(mock.calls), 1)            # exactly one vision call
        self.assertEqual(passes[-1].pass_type, "blind_global")

    def test_low_confidence_triggers_directed(self):
        mock = MockAdapter([
            valid_raw(confidence="low", object_seen="laptop", object_part_seen="hinge"),
            valid_raw(confidence="high", object_seen="laptop", object_part_seen="hinge"),
        ])
        passes = see_image_passes(self.path, adapter=mock, use_cache=False)
        self.assertEqual(len(passes), 2)
        self.assertEqual(len(mock.calls), 2)
        self.assertEqual(passes[0].pass_type, "blind_global")
        self.assertEqual(passes[-1].pass_type, "directed_detail")   # detail supersedes

        blind_sys, _ = mock.calls[0]
        directed_sys, _ = mock.calls[1]
        self.assertNotEqual(blind_sys, directed_sys)     # different prompt -> caches apart
        self.assertIn("SECOND LOOK", directed_sys)       # directed is the look-closer prompt
        self.assertIn("laptop", directed_sys)            # steered by the blind record...
        self.assertIn("hinge", directed_sys)             # ...its object and part

    def test_medium_confidence_triggers(self):
        mock = MockAdapter([valid_raw(confidence="medium"), valid_raw(confidence="high")])
        passes = see_image_passes(self.path, adapter=mock, use_cache=False)
        self.assertEqual(len(passes), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
