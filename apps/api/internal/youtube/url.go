package youtube

import (
	"errors"
	"net/url"
	"strings"
)

var ErrInvalidURL = errors.New("INVALID_YOUTUBE_URL")

func VideoID(raw string) (string, error) {
	u, err := url.ParseRequestURI(strings.TrimSpace(raw))
	if err != nil || u.Scheme != "https" {
		return "", ErrInvalidURL
	}
	host := strings.ToLower(u.Hostname())
	var id string
	switch host {
	case "youtu.be":
		id = strings.Trim(strings.Split(strings.TrimPrefix(u.Path, "/"), "/")[0], " ")
	case "youtube.com", "www.youtube.com", "m.youtube.com":
		parts := strings.Split(strings.Trim(u.Path, "/"), "/")
		if len(parts) == 1 && parts[0] == "watch" {
			id = u.Query().Get("v")
		} else if len(parts) == 2 && parts[0] == "live" {
			id = parts[1]
		}
	default:
		return "", ErrInvalidURL
	}
	if len(id) != 11 || strings.ContainsAny(id, " /?&#") {
		return "", ErrInvalidURL
	}
	return id, nil
}
