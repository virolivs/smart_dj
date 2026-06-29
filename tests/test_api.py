import unittest

from fastapi import HTTPException

from app.main import analyze, config, create_session, health, playlists, simulate
from app.schemas import AnalyzeRequest, SimulateRequest


class ApiTest(unittest.TestCase):
    def test_health(self):
        self.assertEqual(health(), {"status": "ok"})

    def test_config_exposes_safe_public_settings(self):
        response = config()

        self.assertGreaterEqual(response.vision_interval_seconds, 1)
        self.assertGreaterEqual(response.min_track_seconds, 1)
        self.assertFalse(hasattr(response, "groq_api_key"))

    def test_session_and_simulation_flow(self):
        session = create_session()

        response = simulate(
            SimulateRequest(session_id=session.session_id, level="alta"),
        )

        self.assertEqual(response.energy_level, "alta")
        self.assertEqual(response.current_track.level, "alta")
        self.assertTrue(response.current_track.audio_url.startswith("https://"))

    def test_playlists_include_audio_and_license(self):
        response = playlists()

        self.assertEqual(len(response), 6)
        self.assertTrue(response[0].audio_url.startswith("https://"))
        self.assertIn("Creative Commons", response[0].license)

    def test_rejects_frame_with_wrong_dimensions(self):
        session = create_session()

        with self.assertRaises(HTTPException) as exc:
            analyze(
                AnalyzeRequest(
                    session_id=session.session_id,
                    width=2,
                    height=2,
                    pixels=[0, 1],
                )
            )
        self.assertEqual(exc.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
