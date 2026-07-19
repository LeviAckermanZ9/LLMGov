import pytest
from app.core.toxicity import classify_toxicity

def test_toxicity_clearly_toxic():
    # Severe term asshole (0.8) -> should score >= 0.5 and be toxic
    score, is_toxic = classify_toxicity("You are an asshole.")
    assert score == 0.8
    assert is_toxic is True

    # Mild term crap (0.2) + stupid (0.5) -> 0.7 -> toxic
    score, is_toxic = classify_toxicity("This crap is stupid.")
    assert score == 0.7
    assert is_toxic is True

def test_toxicity_clearly_clean():
    score, is_toxic = classify_toxicity("Hello! How can I help you today?")
    assert score == 0.0
    assert is_toxic is False

def test_toxicity_ambiguous_borderline():
    # Mild term garbage (0.2) -> should score 0.2 and not be toxic
    score, is_toxic = classify_toxicity("This garbage code contains too many bugs.")
    assert score == 0.2
    assert is_toxic is False

def test_toxicity_meta_discussion_false_positive():
    # Severe term asshole (0.8) inside reporting context "called me" -> 0.8 * 0.2 = 0.16 -> not toxic
    score, is_toxic = classify_toxicity("The customer called me an asshole in the ticket.")
    assert score == 0.16
    assert is_toxic is False

    # Toxic term "fuck" enclosed in quotes -> treated as meta/quoted -> 0.8 * 0.2 = 0.16 -> not toxic
    score, is_toxic = classify_toxicity("The log contains the word 'fuck'.")
    assert score == 0.16
    assert is_toxic is False

def test_toxicity_evasion_resistance_weakness():
    # Leetspeak trick "1d1ot" or spacing "a s s h o l e" should evade detection for now.
    # We assert they do NOT trigger toxicity, demonstrating the current weakness.
    score_leet, is_toxic_leet = classify_toxicity("You are an 1d1ot.")
    assert score_leet == 0.0
    assert is_toxic_leet is False

    score_spaced, is_toxic_spaced = classify_toxicity("You are a s s h o l e.")
    assert score_spaced == 0.0
    assert is_toxic_spaced is False
