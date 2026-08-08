package youtube

import "testing"

func TestVideoID(t *testing.T) {
	t.Parallel()
	const want = "abcdefghijk"
	valid := []string{
		"https://www.youtube.com/watch?v=abcdefghijk",
		"https://youtube.com/watch?v=abcdefghijk&t=10",
		"https://m.youtube.com/watch?v=abcdefghijk",
		"https://youtu.be/abcdefghijk?t=10",
		"https://www.youtube.com/live/abcdefghijk?feature=share",
	}
	for _, raw := range valid {
		raw := raw
		t.Run(raw, func(t *testing.T) {
			t.Parallel()
			got, err := VideoID(raw)
			if err != nil || got != want {
				t.Fatalf("VideoID() = %q, %v; want %q", got, err, want)
			}
		})
	}

	invalid := []string{"abcdefghijk", "http://youtube.com/watch?v=abcdefghijk", "https://example.com/watch?v=abcdefghijk", "https://youtube.com/watch", "https://youtube.com/shorts/abcdefghijk"}
	for _, raw := range invalid {
		if _, err := VideoID(raw); err != ErrInvalidURL {
			t.Fatalf("VideoID(%q) error = %v; want ErrInvalidURL", raw, err)
		}
	}
}
