package youtube

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const defaultBaseURL = "https://www.googleapis.com/youtube/v3"

type Client struct {
	apiKey  string
	baseURL string
	http    *http.Client
}

func NewClient(apiKey, baseURL string, timeout time.Duration) (*Client, error) {
	if strings.TrimSpace(apiKey) == "" {
		return nil, fmt.Errorf("YSA_YOUTUBE_API_KEY is required")
	}
	if baseURL == "" {
		baseURL = defaultBaseURL
	}
	if timeout <= 0 {
		timeout = 10 * time.Second
	}
	return &Client{apiKey: apiKey, baseURL: strings.TrimRight(baseURL, "/"), http: &http.Client{Timeout: timeout}}, nil
}

func (c *Client) Fetch(ctx context.Context, videoID string) (Metadata, error) {
	endpoint, err := url.Parse(c.baseURL + "/videos")
	if err != nil {
		return Metadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err}
	}
	query := endpoint.Query()
	query.Set("part", "snippet,contentDetails,liveStreamingDetails,status")
	query.Set("id", videoID)
	query.Set("key", c.apiKey)
	endpoint.RawQuery = query.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return Metadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err}
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return Metadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err}
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return Metadata{}, classifyHTTPError(resp)
	}
	var payload videosResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return Metadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err}
	}
	if len(payload.Items) == 0 {
		return Metadata{}, &GatewayError{Code: CodeVideoNotFound}
	}
	return normalize(payload.Items[0])
}

func classifyHTTPError(resp *http.Response) error {
	var payload apiErrorResponse
	_ = json.NewDecoder(resp.Body).Decode(&payload)
	reason := ""
	if len(payload.Error.Errors) > 0 {
		reason = payload.Error.Errors[0].Reason
	}
	switch {
	case resp.StatusCode == http.StatusForbidden && (reason == "quotaExceeded" || reason == "dailyLimitExceeded"):
		return &GatewayError{Code: CodeQuotaExceeded}
	case resp.StatusCode == http.StatusForbidden || resp.StatusCode == http.StatusUnauthorized:
		return &GatewayError{Code: CodeAccessDenied}
	case resp.StatusCode == http.StatusNotFound:
		return &GatewayError{Code: CodeVideoNotFound}
	case resp.StatusCode == http.StatusTooManyRequests || resp.StatusCode >= 500:
		return &GatewayError{Code: CodeTemporarilyUnavailable}
	default:
		return &GatewayError{Code: CodeTemporarilyUnavailable}
	}
}

func normalize(item videoItem) (Metadata, error) {
	if item.LiveStreamingDetails == nil || item.LiveStreamingDetails.ActualEndTime == "" || item.LiveStreamingDetails.ActualStartTime == "" {
		return Metadata{}, &GatewayError{Code: CodeNotEndedLiveStream}
	}
	start, err := time.Parse(time.RFC3339, item.LiveStreamingDetails.ActualStartTime)
	if err != nil {
		return Metadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err}
	}
	end, err := time.Parse(time.RFC3339, item.LiveStreamingDetails.ActualEndTime)
	if err != nil {
		return Metadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err}
	}
	duration, err := ParseDuration(item.ContentDetails.Duration)
	if err != nil {
		return Metadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err}
	}
	metadata := Metadata{YouTubeVideoID: item.ID, Title: item.Snippet.Title, ChannelID: item.Snippet.ChannelID, ChannelTitle: item.Snippet.ChannelTitle, ThumbnailURL: thumbnail(item.Snippet.Thumbnails), ActualStartAt: start, ActualEndAt: end, DurationSeconds: duration}
	if value := item.LiveStreamingDetails.ScheduledStartTime; value != "" {
		parsed, err := time.Parse(time.RFC3339, value)
		if err != nil { return Metadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err} }
		metadata.ScheduledStartAt = &parsed
	}
	if item.Snippet.PublishedAt != "" {
		parsed, err := time.Parse(time.RFC3339, item.Snippet.PublishedAt)
		if err != nil { return Metadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err} }
		metadata.PublishedAt = &parsed
	}
	return metadata, nil
}

func thumbnail(items map[string]thumbnailValue) string {
	for _, key := range []string{"maxres", "standard", "high", "medium", "default"} {
		if value := items[key].URL; value != "" { return value }
	}
	return ""
}

type videosResponse struct { Items []videoItem `json:"items"` }
type videoItem struct {
	ID string `json:"id"`
	Snippet struct {
		Title string `json:"title"`
		ChannelID string `json:"channelId"`
		ChannelTitle string `json:"channelTitle"`
		PublishedAt string `json:"publishedAt"`
		Thumbnails map[string]thumbnailValue `json:"thumbnails"`
	} `json:"snippet"`
	ContentDetails struct { Duration string `json:"duration"` } `json:"contentDetails"`
	LiveStreamingDetails *struct {
		ScheduledStartTime string `json:"scheduledStartTime"`
		ActualStartTime string `json:"actualStartTime"`
		ActualEndTime string `json:"actualEndTime"`
	} `json:"liveStreamingDetails"`
}
type thumbnailValue struct { URL string `json:"url"` }
type apiErrorResponse struct { Error struct { Errors []struct { Reason string `json:"reason"` } `json:"errors"` } `json:"error"` }
