"""Tests for French/Italian sentence segmentation (`tradurre/services/segment.py`)."""

import re

import pytest

from tradurre.services.segment import split_sentences

CASES = [
    # Terminators followed by a capital.
    ("Il pleut. Marie part.", ["Il pleut.", "Marie part."]),
    ("Tu viens ? Non. Pourquoi ! Parce que.", ["Tu viens ?", "Non.", "Pourquoi !", "Parce que."]),
    ("Piove. Maria esce? Sì!", ["Piove.", "Maria esce?", "Sì!"]),
    ("Quoi ?! Rien.", ["Quoi ?!", "Rien."]),
    # Ellipses.
    ("Il attendit… Personne ne vint.", ["Il attendit…", "Personne ne vint."]),
    ("Il attendit... Personne ne vint.", ["Il attendit...", "Personne ne vint."]),
    ("Il attendit… et personne ne vint.", ["Il attendit… et personne ne vint."]),
    ("Aspettò... e nessuno venne.", ["Aspettò... e nessuno venne."]),
    # Closers: the sentence ends after them.
    ("Il cria : « Viens ! » Puis il partit.", ["Il cria : « Viens ! »", "Puis il partit."]),
    ("« Viens ! » dit-il.", ["« Viens ! » dit-il."]),
    ("« Tu viens ? » demanda-t-elle.", ["« Tu viens ? » demanda-t-elle."]),
    ('Disse: "Vieni." Poi uscì.', ['Disse: "Vieni."', "Poi uscì."]),
    ("Disse: “Vieni.” Poi uscì.", ["Disse: “Vieni.”", "Poi uscì."]),
    ("(Il pleuvait.) Marie partit.", ["(Il pleuvait.)", "Marie partit."]),
    # French spacing: no-break spaces before ? and ».
    ("Tu viens ? Non.", ["Tu viens ?", "Non."]),
    ("« Viens ! » Puis rien.", ["« Viens ! »", "Puis rien."]),
    # Dialogue and openers.
    ("— Tu viens ? — Non.", ["— Tu viens ?", "— Non."]),
    ("– Vieni? – No.", ["– Vieni?", "– No."]),
    ("Il se tut. - Alors ?", ["Il se tut.", "- Alors ?"]),
    ("Il se tut. « Viens », dit-elle.", ["Il se tut.", "« Viens », dit-elle."]),
    ("Il se tut. (Elle aussi.)", ["Il se tut.", "(Elle aussi.)"]),
    ('Il dit. "Viens" et partit.', ["Il dit.", '"Viens" et partit.']),
    # Lowercase after a terminator: no boundary.
    ("Que faire ? se demanda-t-il.", ["Que faire ? se demanda-t-il."]),
    # Accented capitals.
    ("Fin. À cette époque, rien. État calme.", ["Fin.", "À cette époque, rien.", "État calme."]),
    ("Finì. È tardi.", ["Finì.", "È tardi."]),
    # Abbreviations and initials.
    ("M. Dupont et Mme Durand virent Mlle Rose. Dr. Martin aussi.",
     ["M. Dupont et Mme Durand virent Mlle Rose.", "Dr. Martin aussi."]),
    ("Il vit Me. Durand et MM. Leroy.", ["Il vit Me. Durand et MM. Leroy."]),
    ("Il Sig. Rossi e il Dott. Bianchi. La Prof. Verdi e l'Avv. Neri.",
     ["Il Sig. Rossi e il Dott. Bianchi.", "La Prof. Verdi e l'Avv. Neri."]),
    ("Voir p. 12 et pp. 13-14, cf. Note.", ["Voir p. 12 et pp. 13-14, cf. Note."]),
    ("Voir (cf. Durand). Fin.", ["Voir (cf. Durand).", "Fin."]),
    ("J. Dupont arriva. E. Rossi no.", ["J. Dupont arriva.", "E. Rossi no."]),
    # Not abbreviations here.
    ("Des pommes, des poires, etc. Puis rien.", ["Des pommes, des poires, etc.", "Puis rien."]),
    ("Mele, pere, ecc. Poi niente.", ["Mele, pere, ecc.", "Poi niente."]),
    ("Lo disse a me. Poi uscì.", ["Lo disse a me.", "Poi uscì."]),
    # Digits never start a sentence.
    ("En 1914. 1915 fut dure.", ["En 1914. 1915 fut dure."]),
    # No whitespace, no boundary; blanks dropped.
    ("Vers 3.5 km.Puis.", ["Vers 3.5 km.Puis."]),
    ("  ", []),
    ("Une phrase sans point", ["Une phrase sans point"]),
]


@pytest.mark.parametrize("text, expected", CASES)
def test_split(text, expected):
    assert split_sentences(text) == expected


@pytest.mark.parametrize("text", [text for text, _ in CASES])
def test_no_text_is_lost(text):
    assert "".join(re.sub(r"\s", "", s) for s in split_sentences(text)) == re.sub(r"\s", "", text)
