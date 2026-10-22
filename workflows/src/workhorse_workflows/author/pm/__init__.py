"""The product manager: reviews each stage's output and answers the writers' questions."""
from workhorse_workflows.author.pm.answer import MAX_ANSWERS, GapAnswer
from workhorse_workflows.author.pm.flow import PMReview

__all__ = ["GapAnswer", "MAX_ANSWERS", "PMReview"]
