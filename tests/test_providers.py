import base64

import httpx
import pytest

from server.discovery import google_search, public_search, semantic_compare, serpapi_search


def test_google_adapter_passes_image_and_preserves_full_vs_partial_evidence(monkeypatch):
    monkeypatch.setenv("GOOGLE_VISION_API_KEY", "test-key")

    def post(url, **kwargs):
        assert url == "https://vision.googleapis.com/v1/images:annotate"
        request = kwargs["json"]["requests"][0]
        assert request["image"]["content"] == base64.b64encode(b"reference").decode()
        assert request["features"][0]["type"] == "WEB_DETECTION"
        return httpx.Response(
            200,
            json={
                "responses": [
                    {
                        "webDetection": {
                            "pagesWithMatchingImages": [
                                {
                                    "url": "https://shop.example/one",
                                    "pageTitle": "<b>Character</b> print",
                                    "fullMatchingImages": [{"url": "https://shop.example/one.png"}],
                                },
                                {
                                    "url": "https://shop.example/two",
                                    "partialMatchingImages": [
                                        {"url": "https://shop.example/two.png"}
                                    ],
                                },
                            ]
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr("server.discovery.httpx.post", post)
    candidates, coverage = google_search(b"reference", 12)
    assert candidates[0]["title"] == "Character print"
    assert candidates[0]["provider_match"] == "full"
    assert candidates[1]["provider_match"] == "partial"
    assert coverage[0]["status"] == "searched"


def test_google_missing_key_and_provider_error_are_explicit(monkeypatch):
    monkeypatch.delenv("GOOGLE_VISION_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GOOGLE_VISION_API_KEY"):
        google_search(b"image", 12)
    monkeypatch.setenv("GOOGLE_VISION_API_KEY", "do-not-leak")
    monkeypatch.setattr("server.discovery.httpx.post", lambda *args, **kwargs: httpx.Response(403))
    with pytest.raises(ValueError) as error:
        google_search(b"image", 12)
    assert "403" in str(error.value)
    assert "do-not-leak" not in str(error.value)


def test_lens_adapter_requires_public_reference_and_returns_visual_matches(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    with pytest.raises(ValueError, match="public reference"):
        serpapi_search("", "Orbit", 12)

    def api_json(url, **kwargs):
        assert kwargs["params"]["engine"] == "google_lens"
        assert kwargs["params"]["q"] == "Orbit"
        assert kwargs["params"]["url"] == "https://art.example/reference.png"
        return {
            "visual_matches": [
                {
                    "link": "https://shop.example/product",
                    "thumbnail": "https://shop.example/image.png",
                    "title": "Orbit shirt",
                }
            ]
        }

    monkeypatch.setattr("server.discovery.api_json", api_json)
    candidates, coverage = serpapi_search("https://art.example/reference.png", "Orbit", 12)
    assert candidates[0]["image_url"] == "https://shop.example/image.png"
    assert "Visual matches" in coverage[0]["detail"]


def test_public_sources_are_interleaved_and_source_failures_remain_visible(monkeypatch):
    def api_json(url, **kwargs):
        if "wikimedia" in url:
            return {
                "query": {
                    "pages": {
                        str(i): {
                            "title": f"File:Artwork {i}",
                            "index": i,
                            "imageinfo": [
                                {
                                    "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{i}",
                                    "thumburl": f"https://images.example/{i}.png",
                                }
                            ],
                        }
                        for i in range(3)
                    }
                }
            }
        return {
            "results": [
                {
                    "foreign_landing_url": "https://gallery.example/art",
                    "url": "https://gallery.example/art.png",
                    "title": "Character art",
                }
            ]
        }

    monkeypatch.setattr("server.discovery.api_json", api_json)
    candidates, coverage = public_search("Character", 3)
    assert [c["provider"] for c in candidates[:3]] == [
        "Wikimedia Commons",
        "Openverse",
        "Wikimedia Commons",
    ]
    assert all(c["status"] == "searched" for c in coverage)
    monkeypatch.setattr(
        "server.discovery.api_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    )
    candidates, coverage = public_search("Character", 3)
    assert not candidates
    assert all(c["status"] == "failed" for c in coverage)


def test_gemini_adapter_uses_two_images_and_keeps_identity_assessment_separate(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def post(url, **kwargs):
        parts = kwargs["json"]["contents"][0]["parts"]
        assert len(parts) == 3
        assert "untrusted" in parts[0]["text"]
        assert parts[1]["inlineData"]["data"] == base64.b64encode(b"reference").decode()
        assert parts[2]["inlineData"]["data"] == base64.b64encode(b"candidate").decode()
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": '{"kind":"same_character","reason":"Matching ears and uniform."}'
                                }
                            ]
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("server.discovery.httpx.post", post)
    assessment = semantic_compare(b"reference", b"candidate", "Space cat")
    assert assessment["kind"] == "same_character"
    assert "permission" not in assessment
    assert "infringement" not in assessment
