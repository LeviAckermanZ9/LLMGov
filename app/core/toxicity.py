import re
from typing import Tuple

# Lexicon of toxic terms with weights.
# Structure: Dict mapping lowercased term to its severity weight.
# Mild: 0.2, Medium: 0.5, Severe: 0.8
TOXIC_LEXICON = {
    # Hate Category (~5 terms)
    "hate speech": 0.8,
    "bigot": 0.8,
    "racist": 0.8,
    "sexist": 0.8,
    "slur": 0.5,
    
    # Insults Category (~6 terms)
    "asshole": 0.8,
    "bastard": 0.5,
    "idiot": 0.5,
    "moron": 0.5,
    "stupid": 0.5,
    "garbage": 0.2,
    
    # Obscenity Category (~4 terms)
    "fuck": 0.8,
    "shit": 0.8,
    "bitch": 0.8,
    "crap": 0.2,
    
    # Threat/Violence Category (~4 terms)
    "kill yourself": 0.8,
    "murder": 0.8,
    "harm you": 0.8,
    "attack you": 0.8
}

# Heuristic indicator patterns for meta-discussion/quoted reporting
META_INDICATORS = [
    r'called me',
    r'said to me',
    r'referred to as',
    r'the word',
    r'someone said',
    r'quote',
    r'reporting',
    r'reported'
]

# Quote detection pattern to find text inside double or single quotes
QUOTE_PATTERN = re.compile(r'["\'](.*?)["\']')

# Default toxicity threshold (un-tuned first-pass default per specification)
DEFAULT_TOXICITY_THRESHOLD = 0.5

def classify_toxicity(text: str) -> Tuple[float, bool]:
    """
    Classify a text string for toxicity.
    Splits the text into sentences, scores each sentence individually,
    and returns (max_sentence_score, is_toxic).
    
    Toxicity score is computed based on weighted lexicons, with discounts
    applied to sentences matching meta-discussion reporting indicators or
    quoted toxic terms.
    """
    if not text:
        return 0.0, False

    # Split text into sentences using simple punctuation lookbehind
    sentences = re.split(r'(?<=[.!?])\s+', text)
    max_score = 0.0

    for sentence in sentences:
        sentence_lower = sentence.lower()
        score = 0.0
        
        # 1. Identify all toxic terms matching in this sentence
        matched_terms = []
        for term, weight in TOXIC_LEXICON.items():
            # Use word boundary checks for terms
            pattern = rf'\b{re.escape(term)}\b'
            if re.search(pattern, sentence_lower):
                matched_terms.append((term, weight))
        
        if not matched_terms:
            continue
            
        # 2. Heuristic check: is this a meta-discussion or quoted reference?
        is_meta = False
        for meta_pat in META_INDICATORS:
            if re.search(meta_pat, sentence_lower):
                is_meta = True
                break
                
        # Also check if matches are exclusively within quotes
        quotes = QUOTE_PATTERN.findall(sentence_lower)
        if quotes:
            # If all found toxic terms are nested inside quotes, treat as meta-discussion
            all_in_quotes = True
            for term, _ in matched_terms:
                term_in_any_quote = any(term in q for q in quotes)
                if not term_in_any_quote:
                    all_in_quotes = False
                    break
            if all_in_quotes:
                is_meta = True

        # 3. Sum weights with dynamic discount factor if reporting/meta
        sum_weights = 0.0
        for term, weight in matched_terms:
            if is_meta:
                # Apply 80% discount for reported/quoted toxicity to mitigate false positives
                sum_weights += weight * 0.2
            else:
                sum_weights += weight

        sentence_score = min(1.0, sum_weights)
        if sentence_score > max_score:
            max_score = sentence_score

    # Determine if overall score crosses the untuned default threshold
    is_toxic = max_score >= DEFAULT_TOXICITY_THRESHOLD
    
    return round(max_score, 2), is_toxic
