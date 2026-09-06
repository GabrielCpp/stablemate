package dispatch

import (
	"reflect"
	"testing"
)

func TestDispatchContract(t *testing.T) {
	for _, tc := range []struct {
		name string
		items []string
		limit int
		status string
		count int
		want []string
		err string
	}{
		{"success", []string{"a", "b", "c"}, 2, "sent", 2, []string{"existing", "a", "b"}, ""},
		{"empty", nil, 2, "empty", 0, []string{"existing"}, ""},
		{"error", []string{"a"}, -1, "", 0, []string{"existing"}, "limit must be nonnegative"},
		{"empty-error", nil, -1, "", 0, []string{"existing"}, "limit must be nonnegative"},
		{"zero", []string{"a"}, 0, "sent", 0, []string{"existing"}, ""},
		{"bounded", []string{"a"}, 9, "sent", 1, []string{"existing", "a"}, ""},
	} {
		t.Run(tc.name, func(t *testing.T) {
			sent := []string{"existing"}
			status, count, err := Dispatch(tc.items, &sent, tc.limit)
			if status != tc.status || count != tc.count || !reflect.DeepEqual(sent, tc.want) {
				t.Fatalf("got status=%q count=%d sent=%v; want %q %d %v", status, count, sent, tc.status, tc.count, tc.want)
			}
			if tc.err == "" && err != nil || tc.err != "" && (err == nil || err.Error() != tc.err) {
				t.Fatalf("got error %v; want %q", err, tc.err)
			}
		})
	}
}
