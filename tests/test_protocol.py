"""Protocol tests. The status frames below were captured from a real desk
(Ergonice, TiMotion TC15S control box, TWD1 module), except the one marked as
computed; every command frame is either documented by the phone app or was
verified on that desk."""

from __future__ import annotations

import unittest

from _loader import protocol as p


def status(hex_frame: str):
    return p.parse_status(bytes.fromhex(hex_frame))


class ChecksumTests(unittest.TestCase):
    def test_mask_is_seven_bits(self):
        # Only the reset-mode frames have a byte sum with bit 7 set; they prove
        # that the mask is 0x7F and not 0xFF.
        self.assertEqual(p.checksum(bytes.fromhex("990301ff")), 0x1C)
        self.assertEqual(p.checksum(bytes.fromhex("994101ff")), 0x5A)

    def test_known_command_frames(self):
        self.assertEqual(p.build_command(p.CMD_UP, 0x63).hex(), "d9ff01633c")
        self.assertEqual(p.build_command(p.CMD_DOWN, 0x60).hex(), "d9ff02603a")
        self.assertEqual(p.build_command(p.CMD_TARGET, 0x50).hex(), "d9ff04502c")

    def test_fixed_frames(self):
        self.assertEqual(p.STOP_FRAME.hex(), "d9ff000058")
        self.assertEqual(p.UP_FRAME.hex(), "d9ff010059")
        self.assertEqual(p.DOWN_FRAME.hex(), "d9ff02005a")
        self.assertEqual(p.RESET_FRAME.hex(), "d9ff03005b")


class MoveToTests(unittest.TestCase):
    def test_verified_on_the_desk(self):
        # 74 cm: this exact frame drove the desk from 130 cm down to 74 cm.
        self.assertEqual(p.move_to_frame(74).hex(), "d9ff044a26")

    def test_range(self):
        for height in (p.HEIGHT_MIN_CM, 111, p.HEIGHT_MAX_CM):
            self.assertEqual(len(p.move_to_frame(height)), 5)
        for height in (0, 64, 131, 255, -1):
            with self.assertRaises(ValueError):
                p.move_to_frame(height)


class StatusTests(unittest.TestCase):
    def test_idle(self):
        s = status("9940016f49")
        self.assertEqual((s.height_cm, s.direction), (111, p.Direction.IDLE))
        self.assertFalse(s.moving or s.collision or s.reset_mode)

    def test_moving_down_and_up(self):
        down = status("9941016e49")
        self.assertEqual((down.height_cm, down.direction), (110, p.Direction.DOWN))
        up = status("9942014b27")
        self.assertEqual((up.height_cm, up.direction), (75, p.Direction.UP))
        self.assertTrue(up.moving)

    def test_collision_reverse(self):
        # Captured while the anti-collision sensor tripped at 75 cm.
        down = status("9951014b36")
        self.assertEqual((down.height_cm, down.direction), (75, p.Direction.DOWN))
        self.assertTrue(down.collision)
        up = status("9952014b37")
        self.assertEqual(up.direction, p.Direction.UP)
        self.assertTrue(up.collision)

    def test_reset_mode(self):
        for frame in ("990301ff1c", "994101ff5a", "994201ff5b"):
            s = status(frame)
            self.assertTrue(s.reset_mode, frame)
            self.assertIsNone(s.height_cm, frame)
        self.assertEqual(status("994101ff5a").direction, p.Direction.DOWN)

    def test_limits_and_calibration_points(self):
        self.assertEqual(status("994001411b").height_cm, 65)  # lowest
        self.assertEqual(status("9940014620").height_cm, 70)
        self.assertEqual(status("9940014a24").height_cm, 74)
        # 130 cm (factory top) is computed with the checksum rule, not captured:
        # the logged run recorded heights, not raw frames.
        self.assertEqual(status("994001825c").height_cm, 130)

    def test_rejects_garbage(self):
        self.assertIsNone(p.parse_status(b""))
        self.assertIsNone(p.parse_status(bytes(5)))
        self.assertIsNone(status("9940016f48"))  # bad checksum
        self.assertIsNone(status("9840016f49"))  # wrong head
        self.assertIsNone(status("9940016f4900"))  # wrong length

    def test_protocol2_frames_are_recognised_but_not_decoded(self):
        for length, kind in ((11, 0), (14, 1), (19, 2)):
            frame = bytes([0x9D, kind]) + bytes(length - 2)
            self.assertTrue(p.is_protocol2_frame(frame), length)
            self.assertIsNone(p.parse_status(frame))
        self.assertFalse(p.is_protocol2_frame(bytes.fromhex("9940016f49")))
        self.assertFalse(p.is_protocol2_frame(b""))
        self.assertFalse(p.is_protocol2_frame(bytes([0x9D, 3]) + bytes(9)))

    def test_equality_ignores_raw_bytes(self):
        a = p.DeskStatus(74, p.Direction.IDLE, False, False, b"a")
        b = p.DeskStatus(74, p.Direction.IDLE, False, False, b"b")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
