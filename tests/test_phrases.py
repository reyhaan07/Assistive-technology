from phrases import PhraseBook


def test_defaults_and_fallback(tmp_path):
    book = PhraseBook(str(tmp_path / "p.json"))
    assert book.get("thumbs_up", "cafe") == "{usual|One coffee please}"
    assert book.get("thumbs_up", "hospital") == "I am okay"
    assert book.get("unknown_gesture", "cafe") == "Unknown gesture"


def test_set_keep_existing_and_persist(tmp_path):
    path = str(tmp_path / "p.json")
    book = PhraseBook(path)
    book.set("water", {"cafe": "Water please", "hospital": "I need water"})
    book.set("water", {"cafe": "", "bank": "  Hello  "}, keep_existing=True)
    msgs = PhraseBook(path).messages_for("water")
    assert msgs == {"cafe": "Water please", "hospital": "I need water", "college": "", "bank": "Hello"}
    assert PhraseBook(path).get("water", "college") == "Water"


def test_delete_restores_builtin_defaults(tmp_path):
    book = PhraseBook(str(tmp_path / "p.json"))
    book.set("stop", {"cafe": "Custom"})
    book.delete("stop")
    assert book.get("stop", "cafe") == "Stop order"
    book.set("custom", {"cafe": "x"})
    book.delete("custom")
    assert not book.has("custom")
