"""Supervisor tests with scripted statuses (no hardware)."""

from __future__ import annotations

import unittest

from _loader import motion as m
from _loader import protocol as p

D = p.Direction


def st(height, direction=D.IDLE, collision=False, reset=False):
    return p.DeskStatus(None if reset else height, direction, collision, reset)


def run(sup, script, *, step=0.1, age=0.0):
    """Feed (status) items one step apart; return the first non-CONTINUE decision."""
    now = 0.0
    for status in script:
        now += step
        decision = sup.update(status, age, now)
        if decision.outcome is not m.Outcome.CONTINUE:
            return decision, now
    return m.Decision(m.Outcome.CONTINUE), now


def target_sup(start, target):
    return m.MoveSupervisor(m.MoveKind.TARGET, target_cm=target, start=st(start), now=0.0)


class TargetMoveTests(unittest.TestCase):
    def test_down_move_completes_after_idle(self):
        script = [st(130 - i, D.DOWN) for i in range(0, 56)] + [st(74)] * 20
        decision, _ = run(target_sup(130, 74), script)
        self.assertEqual(decision.outcome, m.Outcome.DONE)

    def test_wrong_direction_aborts(self):
        decision, _ = run(target_sup(130, 74), [st(130), st(131, D.UP)])
        self.assertEqual(decision.outcome, m.Outcome.ABORT)
        self.assertIn("wrong way", decision.reason)

    def test_collision_aborts(self):
        decision, _ = run(target_sup(130, 74), [st(120, D.DOWN), st(119, D.DOWN, collision=True)])
        self.assertEqual(decision.outcome, m.Outcome.ABORT)
        self.assertIn("collision", decision.reason)

    def test_desk_that_never_starts_aborts(self):
        decision, now = run(target_sup(130, 74), [st(130)] * 100)
        self.assertEqual(decision.outcome, m.Outcome.ABORT)
        self.assertIn("did not start", decision.reason)
        self.assertGreater(now, m.START_GRACE_SECONDS)

    def test_already_there_finishes_without_moving(self):
        decision, _ = run(target_sup(74, 74), [st(74)] * 30)
        self.assertEqual(decision.outcome, m.Outcome.DONE)

    def test_stale_status_aborts(self):
        sup = target_sup(130, 74)
        decision = sup.update(st(130, D.DOWN), m.NO_STATUS_SECONDS + 0.1, 1.0)
        self.assertEqual(decision.outcome, m.Outcome.ABORT)
        self.assertEqual(sup.update(None, 0.0, 1.0).outcome, m.Outcome.ABORT)

    def test_overall_timeout(self):
        sup = target_sup(130, 74)
        decision = sup.update(st(100, D.DOWN), 0.0, m.MAX_SECONDS_TARGET + 1)
        self.assertEqual(decision.outcome, m.Outcome.ABORT)
        self.assertIn("timed out", decision.reason)

    def test_reset_mode_aborts_a_target_move(self):
        decision, _ = run(target_sup(130, 74), [st(None, D.IDLE, reset=True)])
        self.assertEqual(decision.outcome, m.Outcome.ABORT)

    def test_needs_a_known_start_height(self):
        with self.assertRaises(ValueError):
            m.MoveSupervisor(m.MoveKind.TARGET, target_cm=74, start=st(None, reset=True), now=0.0)
        with self.assertRaises(ValueError):
            m.MoveSupervisor(m.MoveKind.TARGET, target_cm=None, start=st(74), now=0.0)


class ResetTests(unittest.TestCase):
    def sup(self):
        return m.MoveSupervisor(m.MoveKind.RESET, target_cm=None, start=st(100), now=0.0)

    def test_reset_runs_through_collisions_and_finishes_when_idle(self):
        script = (
            [st(None, D.IDLE, reset=True)] * 3
            + [st(None, D.DOWN, reset=True)] * 10
            + [st(70, D.DOWN, collision=True)] * 5  # bottoming out is expected
            + [st(65)] * 30
        )
        decision, _ = run(self.sup(), script)
        self.assertEqual(decision.outcome, m.Outcome.DONE)

    def test_reset_that_never_starts_aborts(self):
        decision, _ = run(self.sup(), [st(100)] * 100)
        self.assertEqual(decision.outcome, m.Outcome.ABORT)

    def test_reset_has_a_hard_time_limit(self):
        decision = self.sup().update(st(None, D.DOWN, reset=True), 0.0, m.MAX_SECONDS_RESET + 1)
        self.assertEqual(decision.outcome, m.Outcome.ABORT)


if __name__ == "__main__":
    unittest.main()
