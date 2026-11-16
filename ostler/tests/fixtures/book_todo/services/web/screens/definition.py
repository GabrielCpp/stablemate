from ostler.book import no_repeat, request
from ostler.book.screen import Lists

ROLE = {"text": "textbox", "longtext": "textbox", "number": "spinbutton", "choice": "combobox", "flag": "checkbox"}


def definition_fields(answer):
    """each field of the details form, with its label and kind, in the definition's order"""
    return [(field["label"], ROLE[field["type"]]) for field in answer["fields"]]


DETAILS = Lists(given=request("GET", "/definition"), derived=definition_fields, entries=(no_repeat(),))
