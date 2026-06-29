import json
import unittest

from app.groq_music import GroqMusicResearcher


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class GroqMusicResearcherTest(unittest.TestCase):
    def test_researches_and_validates_profiles(self):
        def opener(request, timeout):
            self.assertEqual(timeout, 90)
            body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(body["model"], "groq/compound-mini")
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": """```json
                                {"tracks":[{
                                  "id":"track-1",
                                  "energy":0.84,
                                  "danceability":0.91,
                                  "bpm":128,
                                  "genre":"house",
                                  "confidence":0.8,
                                  "reason":"BPM alto e produção intensa."
                                }]}
                                ```"""
                            }
                        }
                    ]
                }
            )

        researcher = GroqMusicResearcher(api_key="test-key", opener=opener)
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
                    "choices": [
                        {
                            "message": {
                                "content": '{"tracks":[{"id":"other","energy":0.5}]}'
                            }
                        }
                    ]
                }
            )

        researcher = GroqMusicResearcher(api_key="test-key", opener=opener)

        with self.assertRaises(RuntimeError):
            researcher.research(
                [{"id": "track-1", "title": "Example", "artist": "Artist"}]
            )


if __name__ == "__main__":
    unittest.main()
