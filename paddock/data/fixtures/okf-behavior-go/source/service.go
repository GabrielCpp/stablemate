package dispatch

import "errors"

func Dispatch(items []string, sent *[]string, limit int) (string, int, error) {
	if limit < 0 {
		return "", 0, errors.New("limit must be nonnegative")
	}
	if len(items) == 0 {
		return "empty", 0, nil
	}
	if limit > len(items) {
		limit = len(items)
	}
	selected := items[:limit]
	*sent = append(*sent, selected...)
	return "sent", len(selected), nil
}
