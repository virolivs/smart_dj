import unittest

from app.domain import DJEngine, JourneyGenerator, MotionAnalyzer


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class MotionAnalyzerTest(unittest.TestCase):
    def test_first_frame_has_zero_motion(self):
        analyzer = MotionAnalyzer()

        self.assertEqual(analyzer.score(None, [10, 20, 30]), 0.0)

    def test_scores_mean_absolute_difference(self):
        analyzer = MotionAnalyzer()

        self.assertEqual(analyzer.score([10, 20, 30], [20, 25, 50]), 35 / 3)

    def test_classifies_energy_levels(self):
        analyzer = MotionAnalyzer(calm_threshold=6, high_threshold=18)

        self.assertEqual(analyzer.classify(3), "calma")
        self.assertEqual(analyzer.classify(12), "media")
        self.assertEqual(analyzer.classify(22), "alta")

    def test_calibrates_camera_noise(self):
        clock = FakeClock()
        engine = DJEngine(clock=clock)
        session = engine.create_session()

        engine.analyze(session.session_id, [10, 10, 10, 10])
        for value in [14, 10, 13, 11, 14, 10]:
            clock.advance(9)
            result = engine.analyze(session.session_id, [value, value, value, value])

        self.assertEqual(result.energy_level, "calma")
        self.assertLess(result.motion_score, 6)


class DJEngineTest(unittest.TestCase):
    def test_keeps_track_during_cooldown(self):
        clock = FakeClock()
        engine = DJEngine(min_seconds_between_changes=8, clock=clock)
        session = engine.create_session()

        engine.analyze(session.session_id, [0, 0, 0, 0])
        result = engine.analyze(session.session_id, [255, 255, 255, 255])

        self.assertEqual(result.energy_level, "calma")
        self.assertFalse(result.changed_track)

    def test_changes_track_after_cooldown(self):
        clock = FakeClock()
        engine = DJEngine(min_seconds_between_changes=8, clock=clock)
        session = engine.create_session()

        engine.analyze(session.session_id, [0, 0, 0, 0])
        clock.advance(9)
        result = engine.analyze(session.session_id, [255, 255, 255, 255])

        self.assertEqual(result.energy_level, "alta")
        self.assertTrue(result.changed_track)
        self.assertEqual(result.current_track.level, "alta")

    def test_rejects_invalid_pixels(self):
        engine = DJEngine()
        session = engine.create_session()

        with self.assertRaises(ValueError):
            engine.analyze(session.session_id, [0, 300])


class JourneyGeneratorTest(unittest.TestCase):
    def test_generates_four_phase_progression(self):
        generator = JourneyGenerator()
        tracks = [
            {
                "id": f"track-{index}",
                "name": f"Track {index}",
                "artists": "Artist",
                "uri": f"spotify:track:{index}",
                "energy": min(1.0, 0.15 + index * 0.04),
                "danceability": 0.65,
                "bpm": 90 + index,
                "genre": "pop",
                "confidence": 0.8,
                "reason": "Teste.",
            }
            for index in range(20)
        ]

        result = generator.generate(
            situation="resenha que começa leve e termina animada",
            venue="resenha",
            start_energy="calmo",
            end_energy="mais_intenso",
            discovery="equilibrado",
            total_tracks=12,
            tracks=tracks,
        )

        self.assertEqual(len(result.phases), 4)
        self.assertEqual(sum(len(phase.tracks) for phase in result.phases), 12)
        self.assertIn("Resenha", result.title)
        self.assertLess(result.phases[0].energy_target, result.phases[2].energy_target)


if __name__ == "__main__":
    unittest.main()
