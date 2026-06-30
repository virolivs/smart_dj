import json
import unittest

from app.groq_music import GeminiMusicResearcher


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class GeminiMusicResearcherTest(unittest.TestCase):
    def test_researches_and_validates_profiles(self):
        def opener(request, timeout):
            self.assertEqual(timeout, 90)
            body = json.loads(request.data.decode("utf-8"))
            self.assertIn("gemini-3.1-flash-lite", request.full_url)
            self.assertIn("contents", body)
            return FakeResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": """```json
                                {"tracks":[{
                                  "id":"track-1",
                                  "energy":0.84,
                                  "danceability":0.91,
                                  "bpm":128,
                                  "genre":"house",
                                  "confidence":0.8,
                                  "reason":"BPM alto e produção intensa."
                                }]}
                                ```"""}]
                            }
                        }
                    ]
                }
            )

        researcher = GeminiMusicResearcher(api_key="test-key", opener=opener)
        result = researcher.research(
            [{"id": "track-1", "title": "Example", "artist": "Artist"}]
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "track-1")
        self.assertEqual(result[0].bpm, 128)
        self.assertEqual(result[0].genre, "house")

    def test_ignores_unknown_ids(self):
        def opener(request, timeout):
            return FakeResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": '{"tracks":[{"id":"other","energy":0.5}]}'}]
                            }
                        }
                    ]
                }
            )

        researcher = GeminiMusicResearcher(api_key="test-key", opener=opener)

        with self.assertRaises(RuntimeError):
            researcher.research(
                [{"id": "track-1", "title": "Example", "artist": "Artist"}]
            )

    def test_plans_journey_tracks_from_prompt(self):
        def opener(request, timeout):
            body = json.loads(request.data.decode("utf-8"))
            prompt = body["contents"][0]["parts"][0]["text"]
            self.assertIn("jornada musical do zero", prompt)
            self.assertIn("pesquisador de tendências", prompt)
            self.assertIn("Spotify Charts/Top 50/Viral BR", prompt)
            self.assertIn("viral recente", prompt)
            return FakeResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": json.dumps(
                                    {
                                        "title": "Resenha que cresce",
                                        "summary": "Começa leve e sobe.",
                                        "explanation": "Quatro fases com progressão.",
                                        "phases": [
                                            {
                                                "name": "Chegada",
                                                "intent": "Receber bem.",
                                                "energy_target": 0.3,
                                                "tracks": [
                                                    {
                                                        "title": "Example Song",
                                                        "artist": "Example Artist",
                                                        "energy": 0.35,
                                                        "danceability": 0.7,
                                                        "bpm": 100,
                                                        "genre": "pop",
                                                        "reason": "Boa abertura.",
                                                        "search_query": "Example Song Example Artist",
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                )}]
                            }
                        }
                    ]
                }
            )

        researcher = GeminiMusicResearcher(api_key="test-key", opener=opener)
        result = researcher.plan_journey(
            situation="resenha em casa",
            venue="resenha",
            start_energy="calmo",
            end_energy="mais_intenso",
            discovery="equilibrado",
            total_tracks=8,
        )

        self.assertEqual(result.title, "Resenha que cresce")
        self.assertEqual(result.phases[0].tracks[0].search_query, "Example Song Example Artist")


if __name__ == "__main__":
    unittest.main()
