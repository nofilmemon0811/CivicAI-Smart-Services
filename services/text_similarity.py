import math
import re
from collections import Counter


STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "this", "that", "it", "as",
    "at", "by", "from", "about", "what", "which", "who", "where", "when",
    "how", "does", "do", "can", "could", "should", "please", "me", "my",
}


def tokens(text):
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [w for w in words if len(w) > 2 and w not in STOPWORDS]


def _tfidf_vectors(texts):
    token_lists = [tokens(t) for t in texts]
    document_frequency = Counter()
    for words in token_lists:
        document_frequency.update(set(words))

    n = max(len(texts), 1)
    vectors = []
    for words in token_lists:
        counts = Counter(words)
        total = max(len(words), 1)
        vector = {}
        for word, count in counts.items():
            idf = math.log((1 + n) / (1 + document_frequency[word])) + 1
            vector[word] = (count / total) * idf
        vectors.append(vector)
    return vectors


def cosine_similarity(text_a, text_b):
    vectors = _tfidf_vectors([text_a, text_b])
    a, b = vectors
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def rank_by_similarity(query, documents):
    return sorted(
        ((doc, cosine_similarity(query, doc)) for doc in documents),
        key=lambda item: item[1],
        reverse=True,
    )
