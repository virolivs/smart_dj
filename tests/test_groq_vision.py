import base64
import json
import unittest

from app.groq_vision import GroqVisionAnalyzer, energy_level


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class GroqVisionAnalyzerTest(unittest.TestCase):
    def test_energy_levels(self):
        self.assertEqual(energy_level(0.1), "calma")
        self.assertEqual(energy_level(0.5), "media")
        self.assertEqual(energy_level(0.9), "alta")

    def test_analyzes_frames_and_clamps_values(self):
        captured = {}

        def opener(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "energy": 1.4,
                                        "confidence": 0.82,
                                        "people_count": 12,
                                        "active_ratio": 0.7,
                                        "summary": "Movimento coletivo sustentado.",
                                    }
                                )
                            }
                        }
                    ]
                }
            )

        analyzer = GroqVisionAnalyzer(api_key="test-key", opener=opener)
        frame = "data:image/jpeg;base64," + base64.b64encode(b"fake-jpeg").decode()

        result = analyzer.analyze([frame], [2.0, 8.0])

        self.assertEqual(result.energy, 1.0)
        self.assertEqual(result.level, "alta")
        self.assertEqual(result.people_count, 12)
        self.assertEqual(captured["timeout"], 45)
        self.assertEqual(len(captured["body"]["messages"][0]["content"]), 2)

    def test_rejects_non_image_data_url(self):
        analyzer = GroqVisionAnalyzer(api_key="test-key")

        with self.assertRaises(ValueError):
            analyzer.analyze(["https://example.com/frame.jpg"], [])

    def test_requires_api_key(self):
        analyzer = GroqVisionAnalyzer(api_key="")

        with self.assertRaises(RuntimeError):
            analyzer.analyze([], [])


if __name__ == "__main__":
    unittest.main()
