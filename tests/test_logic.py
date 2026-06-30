"""Unit tests for the pure detection logic (no Discord, no network)."""

from pathlib import Path

import yaml

from flowlybot.detection import analyze, is_newer, version_tuple


# --- auto-mod detection ---------------------------------------------------

def kinds(violations):
    return {v.kind for v in violations}


def test_clean_message_passes():
    assert analyze("hey, has anyone tried the new memory feature?") == []


def test_plain_question_about_nitro_is_not_scam():
    # scam phrase but NO link -> must stay clean (no false positive)
    assert analyze("is discord nitro free for students?") == []


def test_scam_keyword_with_link_flags():
    v = analyze("free nitro here -> http://example.com/claim")
    assert "scam_keyword" in kinds(v)


def test_phishing_lookalike_domain():
    v = analyze("claim at https://dlscord-nitro.ru/gift")
    assert "phishing" in kinds(v)


def test_invite_blocked_by_default():
    v = analyze("join https://discord.gg/abcd1234")
    assert "invite" in kinds(v)


def test_whitelisted_invite_allowed():
    v = analyze("join https://discord.gg/ourvanity", allowed_invites=("ourvanity",))
    assert "invite" not in kinds(v)


def test_mass_mention():
    v = analyze("hi", mention_count=9, max_mentions=5)
    assert "mass_mention" in kinds(v)


def test_everyone_ping_flags():
    v = analyze("look @everyone", mention_everyone=True)
    assert "mass_mention" in kinds(v)


# --- release version comparison -------------------------------------------

def test_version_tuple():
    assert version_tuple("3.0.1") == (3, 0, 1)
    assert version_tuple("v2.10.0") == (2, 10, 0)


def test_is_newer():
    assert is_newer("3.0.0", "3.0.1") is True
    assert is_newer("3.0.1", "3.0.1") is False
    assert is_newer("3.0.2", "3.0.1") is False
    assert is_newer(None, "1.0.0") is True
    assert is_newer("1.0.0", None) is False


# --- FAQ tags file --------------------------------------------------------

def test_tags_yaml_is_valid_and_complete():
    path = Path(__file__).resolve().parent.parent / "flowlybot" / "data" / "tags.yaml"
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict)
    for required in ("install", "byok", "selfhost"):
        assert required in data, f"missing tag: {required}"
        assert data[required].get("body"), f"tag {required} has no body"
