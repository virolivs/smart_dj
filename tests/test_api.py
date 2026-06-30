import unittest

from fastapi import HTTPException

from app.main import analyze, config, create_session, generate_journey, health, plan_journey, playlists, simulate
from app.schemas import AnalyzeRequest, JourneyCatalogTrack, JourneyGenerateRequest, JourneyPlanRequest, SimulateRequest


class ApiTest(unittest.TestCase):
    def test_health(self):
        self.assertEqual(health(), {"status": "ok"})

    def test_config_exposes_safe_public_settings(self):
        response = config()

        self.assertGreaterEqual(response.vision_interval_seconds, 1)
        self.assertGreaterEqual(response.min_track_seconds, 1)
        self.assertEqual(response.ai_provider, "gemini")
        self.assertTrue(response.ai_model)
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

    def test_generates_journey(self):
        tracks = [
            JourneyCatalogTrack(
                id=f"track-{index}",
                name=f"Track {index}",
                artists="Artist",
                uri=f"spotify:track:{index}",
                energy=min(1, 0.2 + index * 0.05),
                danceability=0.7,
                bpm=90 + index,
                genre="pop",
                confidence=0.8,
                reason="Teste.",
            )
            for index in range(12)
        ]

        response = generate_journey(
            JourneyGenerateRequest(
                situation="resenha em casa que cresce aos poucos",
                venue="resenha",
                start_energy="calmo",
                end_energy="mais_intenso",
                discovery="equilibrado",
                total_tracks=10,
                tracks=tracks,
            )
        )

        self.assertEqual(len(response.phases), 4)
        self.assertEqual(sum(len(phase.tracks) for phase in response.phases), 10)
        self.assertIn("quatro blocos", response.explanation)

    def test_plans_journey_with_fallback_when_groq_is_unavailable(self):
        response = plan_journey(
            JourneyPlanRequest(
                situation="resenha em casa",
                venue="resenha",
                total_tracks=8,
            )
        )

        self.assertEqual(len(response.phases), 4)
        self.assertEqual(sum(len(phase.tracks) for phase in response.phases), 8)
        self.assertTrue(response.phases[0].tracks[0].search_query)


if __name__ == "__main__":
    unittest.main()
