package youtube

import (
	"errors"
	"fmt"
	"regexp"
	"strconv"
	"time"
)

type ErrorCode string

const (
	CodeVideoNotFound       ErrorCode = "YOUTUBE_VIDEO_NOT_FOUND"
	CodeNotEndedLiveStream  ErrorCode = "NOT_ENDED_LIVE_STREAM"
	CodeAccessDenied        ErrorCode = "YOUTUBE_ACCESS_DENIED"
	CodeQuotaExceeded       ErrorCode = "YOUTUBE_QUOTA_EXCEEDED"
	CodeTemporarilyUnavailable ErrorCode = "YOUTUBE_TEMPORARILY_UNAVAILABLE"
)

type GatewayError struct {
	Code ErrorCode
	Err  error
}

func (e *GatewayError) Error() string { return string(e.Code) }
func (e *GatewayError) Unwrap() error { return e.Err }

type Metadata struct {
	YouTubeVideoID string
	Title          string
	ChannelID      string
	ChannelTitle   string
	ThumbnailURL   string
	ScheduledStartAt *time.Time
	ActualStartAt  time.Time
	ActualEndAt    time.Time
	DurationSeconds int64
	PublishedAt    *time.Time
}

var durationPattern = regexp.MustCompile(`^P(?:([0-9]+)D)?(?:T(?:([0-9]+)H)?(?:([0-9]+)M)?(?:([0-9]+)S)?)?$`)

func ParseDuration(value string) (int64, error) {
	matches := durationPattern.FindStringSubmatch(value)
	if matches == nil {
		return 0, fmt.Errorf("invalid ISO 8601 duration")
	}
	var values [4]int64
	for i := 1; i < len(matches); i++ {
		if matches[i] == "" {
			continue
		}
		parsed, err := strconv.ParseInt(matches[i], 10, 64)
		if err != nil {
			return 0, err
		}
		values[i-1] = parsed
	}
	seconds := values[0]*86400 + values[1]*3600 + values[2]*60 + values[3]
	if seconds < 0 {
		return 0, errors.New("duration must not be negative")
	}
	return seconds, nil
}
